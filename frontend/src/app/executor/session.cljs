;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns app.executor.session
  "Headless workspace: opens a file in the frontend store the same way the
  workspace page does, minus the UI.

  The browser opens a file by fetching the profile, initializing the team,
  persistence and the workspace, then the page; the wasm viewport finally loads
  the page's shapes into render-wasm. The executor emits the same events in
  the same order, so every later edit runs the workspace's own event code and
  render-wasm computations."
  (:require
   [app.common.files.helpers :as cfh]
   [app.common.logging :as l]
   [app.common.render-wasm.helpers :as h]
   [app.common.render-wasm.wasm :as wasm]
   [app.common.uuid :as uuid]
   [app.config :as cf]
   [app.main.data.helpers :as dsh]
   [app.main.data.persistence :as dps]
   [app.main.data.team :as dtm]
   [app.main.data.workspace :as dw]
   [app.main.data.workspace.reflow :as wrf]
   [app.main.repo :as rp]
   [app.main.store :as st]
   [app.render-wasm.api :as wasm.api]
   [beicon.v2.core :as rx]
   [potok.v2.core :as ptk]
   [promesa.core :as p]))

(def ^:private default-timeout 60000)

(defn wait-event
  "Resolves with the first event on the store stream whose type is `type`.
  Rejects after `timeout` ms. Subscribe before emitting the event that
  causes it."
  ([type] (wait-event type default-timeout))
  ([type timeout]
   (p/create
    (fn [resolve reject]
      (->> st/stream
           (rx/filter (ptk/type? type))
           (rx/take 1)
           (rx/timeout timeout (rx/throw (ex-info "timeout waiting for event"
                                                  {:type :executor :code :timeout
                                                   :event type})))
           (rx/subs! resolve reject))))))

(defn emit-and-wait!
  "Emits `events` and resolves with the first following event of type
  `type`."
  [type & events]
  (let [result (wait-event type)]
    (apply st/emit! events)
    result))

(defn- cmd!
  [name params]
  (p/create
   (fn [resolve reject]
     (rx/subs! resolve reject (rp/cmd! name params)))))

(defn- load-page-shapes!
  "Loads the current page's objects into render-wasm, as the wasm viewport does
  on mount, minus the view setup (there is no render surface). Resolves once
  the shapes, their fonts and images are in the engine."
  []
  (p/create
   (fn [resolve _]
     (let [objects (dsh/lookup-page-objects @st/state)
           shapes  (into [] (keep #(get objects %))
                         (cfh/get-children-ids-with-self objects uuid/zero))]
       (h/call wasm/internal-module "_init_shapes_pool" (count shapes))
       (wasm.api/set-objects-callback
        shapes
        (fn []
          (st/emit! (dw/update-page-position-data))
          (resolve nil)))))))

(defn install-error-handler!
  "Logs store errors. The workspace shows them in the UI; the executor has
  only its log."
  []
  (reset! st/on-error
          (fn [cause]
            (js/console.error "[executor] unexpected error in store:" cause))))

(defn pending-reflow
  "Current `{id {kind #{task-id}}}` map of layout work in flight; a debugging
  aid for `waitForLayoutUpdate` timeouts."
  []
  (.getValue ^js @#'wrf/pending-shapes))

(defn trace-reflow!
  "Prints every change of the pending layout work map; a debugging aid."
  []
  (rx/subs! (fn [pending]
              (let [objects (dsh/lookup-page-objects @st/state)]
                (js/console.log "[reflow]"
                                (pr-str (into {} (map (fn [[id kinds]]
                                                        [(or (get-in objects [id :name]) id) kinds]))
                                              pending)))))
            @#'wrf/pending-shapes))

(defn trace-events!
  "Prints the type of every store event; a debugging aid."
  []
  (rx/subs! (fn [event] (js/console.log "[event]" (str (ptk/type event))))
            st/stream))

(defn open!
  "Opens `file-id` (and `page-id`, or the file's first page) in the store.
  Resolves to {:file-id :page-id :team-id} once the page's shapes are loaded
  into the engine."
  [{:keys [file-id page-id]}]
  (p/let [profile   (cmd! :get-profile {})
          ;; `dp/set-profile` would also load UI translations and the plugin
          ;; registry, which the executor has no use for.
          ;; The backend does not notify a connection of its own session's
          ;; changes, so the executor never shares a browser tab's id.
          _         (st/emit! #(assoc % :session-id cf/session-id)
                              #(assoc % :profile-id (:id profile) :profile profile)
                              ;; The server always computes with render-wasm
                              ;; (D10), whatever renderer the profile prefers.
                              #(assoc-in % [:profile :props :renderer] :wasm))
          ;; the workspace fetches the file again with the team features
          file      (cmd! :get-file {:id file-id})
          team-id   (:team-id file)
          _         (emit-and-wait! :app.main.data.team/team-initialized
                                    (dtm/initialize-team team-id))
          _         (emit-and-wait! :app.main.data.workspace/workspace-initialized
                                    (dps/initialize-persistence)
                                    (dw/initialize-workspace team-id file-id))
          page-id   (or page-id
                        (-> (dsh/lookup-file-data @st/state file-id) :pages first))
          _         (emit-and-wait! :app.main.data.workspace.pages/initialized
                                    (dw/initialize-page file-id page-id))
          _         (load-page-shapes!)]
    (l/info :hint "file opened" :file-id (str file-id) :page-id (str page-id))
    {:file-id file-id :page-id page-id :team-id team-id}))

(defn flush!
  "Forces pending local changes to be persisted. Resolves once the queue is
  saved; rejects when the save failed or did not settle in `timeout` ms."
  ([] (flush! default-timeout))
  ([timeout]
   (p/create
    (fn [resolve reject]
      (st/emit! ::dps/force-persist)
      (rx/subs! (fn [_] (resolve nil))
                reject
                (dps/wait-persisted-or-error timeout))))))
