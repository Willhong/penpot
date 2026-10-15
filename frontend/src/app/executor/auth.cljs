;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns app.executor.auth
  "Authenticates the executor's backend traffic with the user's token.

  The workspace code talks to the backend with `fetch` and a `WebSocket`, and
  relies on the browser's session cookie. The executor has no cookie: it wraps
  both globals so every request to the backend origin carries
  `Authorization: Token <user's MCP token>` and the `mcp` shared key, which
  is how the backend tells the MCP service apart from other holders of an
  MCP token (D11). Requests elsewhere (font CDNs) pass through untouched, so
  neither value leaves the backend origin.

  The executor's public URI (`cf/public-uri`) is the address users open
  Penpot at, so every link it builds or hands out (font and image URLs in an
  SVG export, the viewer URL) works for them. That address may not be
  reachable from where the executor runs: requests to it go to the backend
  address the executor is given, with the same authentication."
  (:require
   [app.common.uri :as u]
   [app.config :as cf]
   [cuerdas.core :as str]))

(defonce ^:private token nil)
(defonce ^:private shared-key nil)
;; backend origin requests go to, when it differs from the public one
(defonce ^:private backend-origin nil)

(defn- auth-headers
  []
  (cond-> {"authorization" (str "Token " token)}
    (some? shared-key)
    (assoc "x-shared-key" (str "mcp " shared-key))))

(defn- origin
  [uri]
  (let [uri (u/uri uri)]
    (str (:scheme uri) "://" (:host uri) (when-let [port (:port uri)] (str ":" port)))))

(defn- on-origin?
  [url origin]
  (or (= url origin)
      (str/starts-with? url (str origin "/"))))

(defn- backend-url?
  [url]
  (on-origin? (str url) (or backend-origin (origin cf/public-uri))))

(defn- to-backend
  "`url` moved from the public origin to the backend origin, or nil when it
  is not on the public origin or both are the same."
  [url]
  (let [url    (str url)
        public (origin cf/public-uri)]
    (when (and (some? backend-origin) (on-origin? url public))
      (str backend-origin (subs url (count public))))))

(defn- request-url
  [input]
  (cond
    (string? input) input
    (instance? js/URL input) (.-href ^js input)
    :else (.-url ^js input)))

(defn- install-fetch!
  [native]
  (unchecked-set js/globalThis "fetch"
                 (fn [input init]
                   (let [input (if-let [moved (to-backend (request-url input))]
                                 (if (or (string? input) (instance? js/URL input))
                                   moved
                                   (js/Request. moved input))
                                 input)]
                     (if (backend-url? (request-url input))
                       (let [init    (js/Object.assign #js {} init)
                             headers (js/Headers. (unchecked-get init "headers"))]
                         (doseq [[k v] (auth-headers)]
                           (.set headers k v))
                         (unchecked-set init "headers" headers)
                         ;; There is no cookie jar; `include` would only make
                         ;; undici reject some redirect combinations.
                         (js-delete init "credentials")
                         (native input init))
                       (native input init))))))

(defn- install-websocket!
  [native]
  (let [klass (fn [url protocols]
                (let [http (str/replace (str url) #"^ws" "http")
                      http (or (to-backend http) http)]
                  (if (backend-url? http)
                    (new native (str/replace http #"^http" "ws")
                         #js {:protocols (or protocols #js [])
                              :headers (clj->js (auth-headers))})
                    (new native url protocols))))]
    (unchecked-set klass "CONNECTING" (.-CONNECTING native))
    (unchecked-set klass "OPEN" (.-OPEN native))
    (unchecked-set klass "CLOSING" (.-CLOSING native))
    (unchecked-set klass "CLOSED" (.-CLOSED native))
    (unchecked-set js/globalThis "WebSocket" klass)))

(defonce ^:private installed? (atom false))

(defn install!
  "Routes all backend traffic of this process through `user-token`, sent
  along with the MCP service's `mcp-shared-key` when given. `backend-uri` is
  the address the backend is reached at from here, when it differs from the
  public URI."
  [user-token mcp-shared-key backend-uri]
  (set! token user-token)
  (set! shared-key mcp-shared-key)
  (let [backend (some-> backend-uri origin)]
    (set! backend-origin (when (and (some? backend) (not= backend (origin cf/public-uri))) backend)))
  (when (compare-and-set! installed? false true)
    (install-fetch! (.bind js/fetch js/globalThis))
    (install-websocket! js/WebSocket)))
