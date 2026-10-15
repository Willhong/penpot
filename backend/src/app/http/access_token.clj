;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns app.http.access-token
  (:require
   [app.common.logging :as l]
   [app.config :as cf]
   [app.db :as db]
   [app.http :as-alias http]
   [app.http.middleware :as mw]
   [app.main :as-alias main]
   [app.setup :as-alias setup]
   [app.tokens :as tokens]
   [cuerdas.core :as str]
   [yetti.request :as yreq]))

(defn decode-token
  [cfg token]
  (try
    (tokens/verify cfg {:token token :iss "access-token"})
    (catch Throwable cause
      (l/trc :hint "exception on decoding token"
             :token token
             :cause cause))))

(def mcp-token-issuer
  "Issuer claim of the tokens created with `type = \"mcp\"`."
  "urn:penpot:mcp-token")

(defn decode-mcp-token
  [cfg token]
  (try
    (tokens/verify cfg {:token token :iss mcp-token-issuer})
    (catch Throwable cause
      (l/trc :hint "exception on decoding mcp token"
             :cause cause))))

(defn mcp-service-request?
  "True when the request carries the `mcp` shared key, which identifies the
  server-side MCP executor. The key grants nothing on its own: it only lets
  that service present the user's MCP token, so an MCP token presented by
  anyone else is still not an access token."
  [request shared-keys]
  (let [expected (get shared-keys :mcp)]
    (boolean
     (when-let [[key-id key] (some-> (yreq/get-header request "x-shared-key")
                                     (str/split #"\s+" 2))]
       (and (string? expected)
            (string? key)
            (= "mcp" (str/lower key-id))
            (mw/constant-time-eq? key expected))))))

(defn- resolve-mcp-claims
  "Decodes an MCP token presented by the server-side MCP executor. Returns the
  auth data unchanged for any other request."
  [cfg request {:keys [type token claims] :as auth-data}]
  (if (and (= :token type)
           (nil? claims)
           (mcp-service-request? request (::setup/shared-keys cfg)))
    (assoc auth-data :claims (decode-mcp-token cfg token))
    auth-data))

(def sql:get-token-data
  "SELECT perms, profile_id, expires_at, type
     FROM access_token
    WHERE id = ?
      AND (expires_at IS NULL
           OR (expires_at > now()));")

(defn- get-token-data
  [pool claims]
  (when-not (db/read-only? pool)
    (when-let [token-id (get claims :tid)]
      (some-> (db/exec-one! pool [sql:get-token-data token-id])
              (update :perms db/decode-pgarray #{})))))

(defn- wrap-authz
  [handler {:keys [::db/pool] :as cfg}]
  (fn [request]
    (let [{:keys [type claims]} (resolve-mcp-claims cfg request (get request ::http/auth-data))]
      (if (= :token type)
        (let [{:keys [perms profile-id expires-at type]} (some->> claims (get-token-data pool))
              token-id (get claims :tid)]
          (handler (cond-> request
                     (some? perms)
                     (assoc ::perms perms)
                     (some? profile-id)
                     (assoc ::profile-id profile-id)
                     (some? expires-at)
                     (assoc ::expires-at expires-at)
                     (some? token-id)
                     (assoc ::id token-id)
                     (some? type)
                     (assoc ::type type))))

        (handler request)))))

(def authz
  {:name ::authz
   :compile (fn [& _]
              (when (contains? cf/flags :access-tokens)
                wrap-authz))})
