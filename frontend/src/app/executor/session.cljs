;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns app.executor.session
  "Headless workspace: keeps one file open in the frontend store the same way
  the workspace page does, minus the UI.

  The browser opens a file by fetching the profile, initializing the team,
  persistence and the workspace, then the page; the wasm viewport finally loads
  the page's shapes into render-wasm. Navigation drives all of it: the
  workspace page mounts on a `:workspace` route. The executor has no page to
  mount, so a headless router (`install-router!`) answers the same navigation
  events the plugin API emits (`penpotMgmt.openFile`, `penpot.openPage`) by
  emitting the events the page would. Every later edit then runs the
  workspace's own event code and render-wasm computations."
  (:require
   [app.common.files.helpers :as cfh]
   [app.common.render-wasm.helpers :as h]
   [app.common.render-wasm.wasm :as wasm]
   [app.common.uuid :as uuid]
   [app.config :as cf]
   [app.main.data.helpers :as dsh]
   [app.main.data.persistence :as dps]
   [app.main.data.team :as dtm]
   [app.main.data.websocket :as dws]
   [app.main.data.workspace :as dw]
   [app.main.data.workspace.pages :as dwpg]
   [app.main.data.workspace.reflow :as wrf]
   [app.main.repo :as rp]
   [app.main.router :as rt]
   [app.main.store :as st]
   [app.render-wasm.api :as wasm.api]
   [beicon.v2.core :as rx]
   [potok.v2.core :as ptk]
   [promesa.core :as p]))

(def ^:private default-timeout 60000)

;; Routes the plugin API navigates to. Only `:workspace` opens anything; the
;; others exist so `rt/nav` resolves them like the browser router does.
(def ^:private routes
  #{:workspace :viewer :dashboard-recent :dashboard-files :settings-profile})

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

(defn load-page-shapes!
  "Loads the current page's objects into render-wasm, as the wasm viewport does
  on mount, minus the view setup (there is no render surface). The shapes are
  serialized synchronously; the returned promise resolves once their fonts and
  images are in the engine too."
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

;; --- PROFILE

(defn bootstrap!
  "Loads the profile and starts the store the way `app.main` does, minus the
  UI, then initializes the profile's default team as the dashboard would.
  Resolves to the profile."
  []
  (p/let [profile (cmd! :get-profile {})]
    (when (= uuid/zero (:id profile))
      (throw (ex-info "the token does not identify a user"
                      {:type :executor :code :forbidden})))
    ;; `dp/set-profile` would also load UI translations and the plugin
    ;; registry, which the executor has no use for. The backend does not
    ;; notify a connection of its own session's changes, so the executor
    ;; never shares a browser tab's id.
    (st/emit! #(assoc % :session-id cf/session-id)
              #(assoc % :profile-id (:id profile) :profile profile)
              ;; The server always computes with render-wasm (D10), whatever
              ;; renderer the profile prefers.
              #(assoc-in % [:profile :props :renderer] :wasm)
              (rt/initialize-router routes)
              (dps/initialize-persistence)
              ;; as `app.main` does once the profile is known: other
              ;; sessions' changes reach the open file through it
              (dws/initialize))
    ;; The browser lands on the default team's dashboard: `penpotMgmt` calls
    ;; made before opening a file need that team and its features.
    (p/do (emit-and-wait! ::dtm/team-initialized
                          (dtm/initialize-team (:default-team-id profile)))
          profile)))

;; --- WORKSPACE

(defonce ^:private opening (atom nil))

(defn- current-team-id [] (:current-team-id @st/state))
(defn- current-file-id [] (:workspace-ready @st/state))

(defn- open-workspace!
  "Opens `file-id` of `team-id` in the store, closing the file open before.
  Resolves once the page `page-id` (or the file's first page) is initialized
  and its shapes are in the engine."
  [team-id file-id page-id]
  (p/let [;; fails fast, as the workspace page does, when the user may not
          ;; read the file (the backend answers 404 to both)
          _         (cmd! :get-file-summary {:id file-id})
          prev-file (current-file-id)
          _         (when (some? prev-file)
                      (st/emit! ::dps/force-persist
                                (dw/finalize-workspace (current-team-id) prev-file)))
          _         (when (not= team-id (current-team-id))
                      (emit-and-wait! ::dtm/team-initialized
                                      (dtm/initialize-team team-id)))
          _         (emit-and-wait! ::dw/workspace-initialized
                                    (dw/initialize-workspace team-id file-id))
          page-id   (or page-id
                        (-> (dsh/lookup-file-data @st/state file-id) :pages first))]
    ;; The page's shapes are loaded when `::dwpg/initialized` arrives (see
    ;; `install-router!`), before a waiting plugin promise resumes.
    (emit-and-wait! ::dwpg/initialized (dw/initialize-page file-id page-id))))

(defn- open-page!
  [file-id page-id]
  (let [prev-page (:current-page-id @st/state)]
    (when (some? prev-page)
      (st/emit! (dwpg/finalize-page file-id prev-page)))
    (emit-and-wait! ::dwpg/initialized (dw/initialize-page file-id page-id))))

(defn- navigated!
  "Handles a `:workspace` navigation: records the route, as the browser's
  history listener does, then opens what it names."
  [{:keys [id params]}]
  (let [router (:router @st/state)
        match  (rt/match router (rt/resolve router id params))]
    (st/emit! (rt/navigated match false))
    (when (= :workspace id)
      (let [team-id (some-> (:team-id params) str uuid/uuid)
            file-id (some-> (:file-id params) str uuid/uuid)
            page-id (some-> (:page-id params) str uuid/uuid)
            task    (cond
                      (and file-id (not= file-id (current-file-id)))
                      (open-workspace! (or team-id (current-team-id)) file-id page-id)

                      (and page-id (not= page-id (:current-page-id @st/state)))
                      (open-page! file-id page-id))]
        (when task
          (reset! opening task)
          (p/catch task (fn [cause]
                          (js/console.error "[executor] navigation failed:" cause)
                          (st/emit! (rt/assign-exception cause)))))))))

(defn install-router!
  "Answers the navigation events of the plugin API with the events the
  workspace page would emit, and loads each initialized page's shapes into
  the engine."
  []
  (rx/subs! (fn [event] (navigated! @event))
            (->> st/stream
                 (rx/filter (ptk/type? ::rt/navigate))
                 (rx/filter #(not (::rt/new-window (:options @%))))))
  (rx/subs! (fn [_] (load-page-shapes!))
            (->> st/stream
                 (rx/filter (ptk/type? ::dwpg/initialized))))
  ;; A reload of the open file (another session restored a version) fetches
  ;; it again without initializing the page; the wasm viewport reloads its
  ;; shapes on the new version, so does the executor.
  (rx/subs! (fn [_]
              (when (:current-page-id @st/state)
                (load-page-shapes!)))
            (->> st/stream
                 (rx/filter (ptk/type? ::dw/bundle-fetched)))))

(defn open!
  "Opens `file-id` (and `page-id`, or the file's first page) as
  `penpotMgmt.openFile` would. Resolves to {:file-id :page-id :team-id}."
  [{:keys [file-id page-id]}]
  (p/let [file    (cmd! :get-file {:id file-id})
          team-id (:team-id file)
          _       (do (reset! opening nil)
                      (st/emit! (rt/nav :workspace (cond-> {:team-id team-id :file-id file-id}
                                                     (some? page-id) (assoc :page-id page-id))))
                      @opening)]
    {:file-id file-id
     :page-id (:current-page-id @st/state)
     :team-id team-id}))

;; --- EXECUTION LIFECYCLE

(defn pending-reflow
  "Current `{id {kind #{task-id}}}` map of layout work in flight."
  []
  (.getValue ^js @#'wrf/pending-shapes))

(defn settle!
  "Waits until no layout, text or component work is in flight. Resolves to
  nil, or to the still pending map when `timeout` ms pass first."
  [timeout]
  (p/create
   (fn [resolve _]
     (->> (rx/race (->> (wrf/settled nil) (rx/map (constantly nil)))
                   (->> (rx/of :timeout) (rx/delay timeout)
                        (rx/map (fn [_] (pending-reflow)))))
          (rx/take 1)
          (rx/subs! resolve)))))

(defn flush!
  "Saves the buffered local changes, text position data included, in one
  request. Resolves once the backend acknowledged them; rejects when the save
  failed or did not settle in `timeout` ms."
  ([] (flush! default-timeout))
  ([timeout]
   (p/create
    (fn [resolve reject]
      (st/emit! (dw/flush-position-data))
      ;; the position data commit lands on the next tick
      (js/setTimeout
       (fn []
         (st/emit! ::dps/force-persist)
         (rx/subs! (fn [_] (resolve nil))
                   reject
                   (dps/wait-persisted-or-error timeout)))
       0)))))

(defn discard!
  "Drops the changes buffered since the last save and reloads the file, so
  the store matches the backend again."
  []
  (let [file-id (current-file-id)
        team-id (current-team-id)
        page-id (:current-page-id @st/state)]
    (st/emit! ::dps/discard-buffered)
    (if (some? file-id)
      (p/do
        (st/emit! (dw/finalize-workspace team-id file-id))
        (open-workspace! team-id file-id page-id))
      (p/resolved nil))))

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
