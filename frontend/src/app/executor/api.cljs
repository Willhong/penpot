;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns app.executor.api
  "Interface of the headless workspace for the executor host process
  (`mcp/packages/server/src/executor/`), exported from the `:executor`
  build. Everything crosses as plain JS values.

  One executor process serves one user and one MCP session (D12). The host
  boots it once, then for each execution: `beginExecution`, runs the user code
  against `context()`, then `finishExecution` (settle derived values, save in
  one request) or `abortExecution` (save nothing, reload the file)."
  (:require
   [app.common.data :as d]
   [app.common.time :as ct]
   [app.common.transit :as t]
   [app.common.uuid :as uuid]
   [app.config :as cf]
   [app.executor.auth :as auth]
   [app.executor.session :as session]
   [app.executor.wasm :as ewasm]
   [app.main.data.changes :as dch]
   [app.main.data.helpers :as dsh]
   [app.main.data.persistence :as dps]
   [app.main.data.workspace.pages :as dwpg]
   [app.main.store :as st]
   [app.plugins.api :as plugins.api]
   [app.plugins.register :as preg]
   [beicon.v2.core :as rx]
   [potok.v2.core :as ptk]
   [promesa.core :as p]))

(defonce ^:private plugin-context (atom nil))

;; State of the execution in progress: revn and file at its start, ids of
;; the shapes its local commits touched, saves acknowledged since.
(defonce ^:private execution (atom nil))

(defn- current-file-id [] (:workspace-ready @st/state))

;; Revn of each file after the executor's last save. `update-file` answers
;; with the revn the file had before the change and the store keeps that
;; value, so the store lags one behind the executor's own saves.
(defonce ^:private saved-revn (atom {}))

(defn- file-revn
  [file-id]
  (max (or (:revn (dsh/lookup-file @st/state file-id)) 0)
       (get @saved-revn file-id 0)))

(defn- contract-error
  "Turns a failure of the workspace code into a JS error carrying the error
  code of 03-runtime-contract §7 as `code`."
  [cause]
  (let [{:keys [type code]} (ex-data cause)
        contract (cond
                   (or (= code :forbidden) (= type :authentication)) "forbidden"
                   ;; the backend answers 404 to a write without edit rights; the
                   ;; workspace refuses it before sending (03-runtime-contract §7)
                   (or (#{:object-not-found :not-found :save-permission-denied} code)
                       (= type :not-found)) "not-found"
                   (= code :precondition-failed) "precondition-failed"
                   (= code :revn-conflict) "revn-conflict"
                   (= code :vern-conflict) "vern-conflict"
                   (= type :validation) "validation"
                   :else "engine-error")
        error    (js/Error. (or (ex-message cause) (str cause)))]
    (unchecked-set error "code" contract)
    error))

(defn- with-contract-errors
  [promise]
  (p/catch promise (fn [cause] (p/rejected (contract-error cause)))))

(defn- change-ids
  [{:keys [type id shapes]}]
  (case type
    (:add-obj :mod-obj :del-obj) [id]
    :mov-objects shapes
    []))

(defn ^:export boot
  "Boots the engine and the store for the user of `token`. Options (JS
  object): `token`, `sharedKey` (MCP shared key), `wasmDir` (directory of
  `render-wasm.js`). Resolves to `{profileId, sessionId}`."
  [^js opts]
  ;; As `app.main/init` does: populate the Date prototype with the transit
  ;; handlers before the host hardens the intrinsics for the plugin sandbox.
  (-> (ct/now) (t/encode-str) (t/decode-str))
  (auth/install! (.-token opts) (.-sharedKey opts))
  (session/install-error-handler!)
  (session/install-router!)
  (with-contract-errors
    (p/let [_       (ewasm/init! (.-wasmDir opts))
            profile (session/bootstrap!)]
      #js {:profileId (str (:id profile))
           :sessionId (str cf/session-id)})))

(defn ^:export context
  "The plugin API context (`penpot` before the plugins runtime wraps it),
  with the MCP plugin's identity and permissions."
  []
  (or @plugin-context
      (reset! plugin-context (plugins.api/create-context preg/mcp-plugin-id))))

(defn ^:export status
  "Current file, page and revision."
  []
  (let [file-id (current-file-id)]
    #js {:fileId (some-> file-id str)
         :pageId (some-> (:current-page-id @st/state) str)
         :canEdit (boolean (get-in @st/state [:permissions :can-edit]))
         :revn (some-> file-id file-revn)
         :frontendVersion (:full cf/version)}))

(defn ^:export observedScreen
  "Screen of a browser tab of the same user on the open file, as its
  pointer updates report it (D8 (b)): `{pageId, zoom, vbox, theme,
  updatedAt}` of the tab on the current page that reported last, else of
  any tab of the user on the file; null when there is none."
  []
  (let [state      @st/state
        profile-id (:profile-id state)
        own        (:session-id state)
        page-id    (:current-page-id state)
        tabs       (->> (:workspace-presence state)
                        (keep (fn [[session-id presence]]
                                (when (and (not= own session-id)
                                           (= profile-id (:profile-id presence))
                                           (some? (:vbox presence)))
                                  presence)))
                        (sort-by #(some-> % :updated-at inst-ms)))
        tab        (or (->> tabs (filter #(= page-id (:page-id %))) last)
                       (last tabs))]
    (when-let [{:keys [vbox zoom theme updated-at] :as tab} tab]
      #js {:pageId (some-> (:page-id tab) str)
           :zoom zoom
           :vbox #js {:x (:x vbox) :y (:y vbox) :width (:width vbox) :height (:height vbox)}
           :theme theme
           :updatedAt (some-> updated-at inst-ms)})))

(defn ^:export openFile
  "Opens a file as `penpotMgmt.openFile` would. Resolves to the status."
  [file-id page-id]
  (with-contract-errors
    (p/let [_ (session/open! {:file-id (uuid/uuid file-id)
                              :page-id (some-> page-id uuid/uuid)})]
      (status))))

(defn ^:export beginExecution
  "Starts an execution: holds the autosave so the execution is saved in one
  request, and starts recording what it changes. Option
  `ifUnchangedSinceRevn` (D4) makes the save refuse when the file moved past
  that revn in the meantime."
  [^js opts]
  (let [file-id (current-file-id)
        sub     (->> st/stream
                     (rx/filter dch/commit?)
                     (rx/map deref)
                     (rx/filter #(= :local (:source %)))
                     (rx/subs! (fn [{:keys [redo-changes]}]
                                 (swap! execution update :changed
                                        into (mapcat change-ids) redo-changes))))
        saves   (->> st/stream
                     (rx/filter (ptk/type? ::dps/commit-persisted))
                     (rx/subs! (fn [_] (swap! execution update :saves inc))))
        ;; The workspace drops edits on a read-only file without a word
        ;; (`dch/commit-changes`); the executor reports them instead.
        refused (->> st/stream
                     (rx/filter (ptk/type? ::dch/commit-changes))
                     (rx/filter (fn [_] (not (get-in @st/state [:permissions :can-edit]))))
                     (rx/subs! (fn [_] (swap! execution update :refused inc))))
        ;; A version restore reloads the file; the execution ends after it.
        reload  (->> st/stream
                     (rx/filter (ptk/type? :app.main.data.workspace.versions/restore-version-from-plugins))
                     (rx/subs! (fn [_]
                                 (swap! execution assoc :reloading
                                        (session/wait-event ::dwpg/initialized)))))]
    (reset! dps/autosave-held? true)
    (reset! execution {:file-id file-id
                       :precondition (some-> opts .-ifUnchangedSinceRevn)
                       :revn-before (some-> file-id file-revn)
                       :changed #{}
                       :saves 0
                       :refused 0
                       :subs [sub saves refused reload]})
    nil))

(defn- end-execution!
  []
  (let [{:keys [subs] :as state} @execution]
    (run! rx/dispose! subs)
    (reset! execution nil)
    (reset! dps/autosave-held? false)
    state))

(defn ^:export finishExecution
  "Completes the derived values of the execution (layout, text size and
  position data, booleans, component sync) and saves them with its edits.
  Option `settleTimeout` (ms) bounds the wait for derived values. Resolves to
  the commit report of 03-runtime-contract §3."
  [^js opts]
  (let [settle-timeout (or (some-> opts .-settleTimeout) 10000)]
    (-> (p/let [_         (when-let [reloading (:reloading @execution)]
                            (p/race [reloading (p/delay settle-timeout)]))
                _         (when (pos? (:refused @execution))
                            (throw (ex-info "this user has read-only access to the file; its edits were not applied"
                                            {:type :not-found :code :object-not-found})))
                pending   (session/settle! settle-timeout)
                ;; D4, checked again right before the save: another session's
                ;; change may have arrived while the code ran
                _         (let [{:keys [precondition file-id]} @execution
                                revn (some-> file-id file-revn)]
                            (when (and (some? precondition) (some? revn) (> revn precondition))
                              (throw (ex-info (str "the file changed since revn " precondition
                                                   " (now " revn "); nothing was saved")
                                              {:type :validation :code :precondition-failed}))))
                _         (session/flush!)
                state     (end-execution!)
                file-id   (or (current-file-id) (:file-id state))
                ;; the revn the last `update-file` answered: the file's revn
                ;; before that change, so the saved revn is one more
                answered  (some-> file-id file-revn)
                before    (:revn-before state)
                saves     (:saves state)
                revn      (if (pos? saves) (inc answered) answered)
                _         (when (and file-id (pos? saves))
                            (swap! saved-revn assoc file-id revn))
                changed   (disj (:changed state) uuid/zero)]
          #js {:saved (pos? saves)
               :fileId (some-> file-id str)
               :revnBefore before
               :revn revn
               :changedShapeIds (clj->js (mapv str changed))
               ;; changes of other sessions applied in between
               :lagged (if (and (pos? saves) before)
                         (max 0 (- answered before (dec saves)))
                         0)
               :computed #js {:layout (nil? pending)
                              :text (nil? pending)
                              :bool true
                              :componentSync (nil? pending)}
               :pending (when (some? pending)
                          (clj->js (d/update-vals pending (comp vec keys))))})
        (p/catch (fn [cause]
                   (end-execution!)
                   (p/rejected (contract-error cause)))))))

(defn ^:export abortExecution
  "Saves nothing of the execution in progress and reloads the file."
  []
  (end-execution!)
  (session/discard!))
