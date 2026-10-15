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
  `Authorization: Token <user token>`. Requests elsewhere (font CDNs) pass
  through untouched, so the token never leaves the backend origin."
  (:require
   [app.common.uri :as u]
   [app.config :as cf]
   [cuerdas.core :as str]))

(defonce ^:private token nil)

(defn- origin
  [uri]
  (let [uri (u/uri uri)]
    (str (:scheme uri) "://" (:host uri) (when-let [port (:port uri)] (str ":" port)))))

(defn- backend-url?
  [url]
  (str/starts-with? (str url) (origin cf/public-uri)))

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
                   (if (backend-url? (request-url input))
                     (let [init    (js/Object.assign #js {} init)
                           headers (js/Headers. (unchecked-get init "headers"))]
                       (.set headers "authorization" (str "Token " token))
                       (unchecked-set init "headers" headers)
                       ;; There is no cookie jar; `include` would only make
                       ;; undici reject some redirect combinations.
                       (js-delete init "credentials")
                       (native input init))
                     (native input init)))))

(defn- install-websocket!
  [native]
  (let [klass (fn [url protocols]
                (if (backend-url? (str/replace (str url) #"^ws" "http"))
                  (new native url #js {:protocols (or protocols #js [])
                                       :headers #js {"authorization" (str "Token " token)}})
                  (new native url protocols)))]
    (unchecked-set klass "CONNECTING" (.-CONNECTING native))
    (unchecked-set klass "OPEN" (.-OPEN native))
    (unchecked-set klass "CLOSING" (.-CLOSING native))
    (unchecked-set klass "CLOSED" (.-CLOSED native))
    (unchecked-set js/globalThis "WebSocket" klass)))

(defonce ^:private installed? (atom false))

(defn install!
  "Routes all backend traffic of this process through `user-token`."
  [user-token]
  (set! token user-token)
  (when (compare-and-set! installed? false true)
    (install-fetch! (.bind js/fetch js/globalThis))
    (install-websocket! js/WebSocket)))
