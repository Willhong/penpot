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
   [app.common.time :as ct]
   [app.common.transit :as t]
   [app.common.uuid :as uuid]
   [app.config :as cf]
   [app.executor.auth :as auth]
   [app.executor.history :as history]
   [app.executor.session :as session]
   [app.executor.wasm :as ewasm]
   [app.main.data.changes :as dch]
   [app.main.data.helpers :as dsh]
   [app.main.data.persistence :as dps]
   [app.main.data.websocket :as dws]
   [app.main.data.workspace.pages :as dwpg]
   [app.main.data.workspace.wasm-text :as dwwt]
   [app.main.router :as rt]
   [app.main.store :as st]
   [app.plugins.api :as plugins.api]
   [app.plugins.public-utils :as public-utils]
   [app.plugins.register :as preg]
   ;; as `app.plugins` does in the browser
   [app.plugins.wiring]
   [app.render-wasm.api.fonts :as wasm.fonts]
   [beicon.v2.core :as rx]
   [cuerdas.core :as str]
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
                   (#{:settle-timeout :too-many-changes} code) "resource-limit"
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
  `render-wasm.js`), `backendUri` (address the backend is reached at from
  here, when it differs from the public URI users open Penpot at). Resolves
  to `{profileId, sessionId}`."
  [^js opts]
  ;; As `app.main/init` does: populate the Date prototype with the transit
  ;; handlers before the host hardens the intrinsics for the plugin sandbox.
  (-> (ct/now) (t/encode-str) (t/decode-str))
  (auth/install! (.-token opts) (.-sharedKey opts) (.-backendUri opts))
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

(defn ^:export viewerQuery
  "Query of the viewer URL of the current page, as `penpot.openViewer()`
  navigates to it (`?screen=viewer&...`), or null with no file open."
  []
  (let [state   @st/state
        file-id (:current-file-id state)
        page-id (:current-page-id state)]
    (when (and file-id page-id)
      (rt/resolve (:router state) :viewer {:file-id file-id
                                           :page-id page-id
                                           :section "interactions"}))))

(defn ^:export centerShapes
  "What `penpot.utils.geometry.center` returns; the plugins runtime reaches it
  through `window.app`, which the executor does not have."
  [shapes]
  (public-utils/centerShapes shapes))

(defn- following-tabs
  "Sessions of the same user on the open file whose tab has \"AI follow\"
  on, as their presence messages report it (PEN-24)."
  []
  (let [state @st/state
        own   (:session-id state)]
    (->> (:workspace-presence state)
         (filter (fn [[session-id presence]]
                   (and (not= own session-id)
                        (= (:profile-id state) (:profile-id presence))
                        (true? (:ai-follow presence)))))
         (count))))

(defn- send-follow!
  "Sends a followed call to the user's tabs on the open file (the backend
  hands `:broadcast` to the sessions of the same profile only) and records
  it in the execution. Returns how many tabs follow."
  [action fields]
  (let [tabs (following-tabs)]
    (when (pos? tabs)
      (st/emit! (dws/send (merge {:type :broadcast
                                  :kind :ai-follow
                                  :action action
                                  :file-id (current-file-id)
                                  :page-id (:current-page-id @st/state)}
                                 fields))))
    (swap! execution
           (fn [state]
             (when state
               (-> state
                   (update :follow (fnil conj []) (name action))
                   (assoc :follow-tabs tabs)))))
    tabs))

(defn ^:export follow
  "Shows a call on the screen of the user's tabs that follow the session
  (PEN-24): `{action, ...}` with `action` one of `page`, `select` (`ids`),
  `center` (`x`, `y`), `zoom` (`zoom`), `zoom-reset`, `zoom-fit-all`,
  `zoom-into-view` (`ids`). Returns how many tabs follow; with none, the
  caller answers `ui-only` for the calls that only move a screen."
  [^js action]
  (let [kind (keyword (.-action action))]
    (send-follow! kind
                  (cond-> {}
                    (some? (.-ids action)) (assoc :ids (mapv uuid/uuid (.-ids action)))
                    (some? (.-x action)) (assoc :x (.-x action))
                    (some? (.-y action)) (assoc :y (.-y action))
                    (some? (.-zoom action)) (assoc :zoom (.-zoom action))))))

(defn- changes-by-page
  "The shapes among `ids` that exist in the open file, by page."
  [ids]
  (let [pages (:pages-index (dsh/lookup-file-data @st/state))]
    (into {}
          (keep (fn [[page-id {:keys [objects]}]]
                  (let [here (filterv #(contains? objects %) ids)]
                    (when (seq here) [page-id here]))))
          pages)))

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
                     (rx/subs! (fn [{:keys [redo-changes save-undo?] :as commit}]
                                 (swap! execution
                                        (fn [state]
                                          (cond-> (-> state
                                                      (update :changed into (mapcat change-ids) redo-changes)
                                                      (update :change-count + (count redo-changes)))
                                            ;; what a browser would keep for undo (PEN-20)
                                            save-undo?
                                            (update :commits conj (select-keys commit [:redo-changes :undo-changes]))))))))
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
                       :change-count 0
                       :commits []
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

(defn- font-fallback-warnings
  "`font-fallback` warnings (03-runtime-contract §3) for the texts among
  `ids` laid out without one of their fonts: its file could not be had (a
  deleted custom font, a failed download), so another font stands in."
  [ids]
  (let [objects (dsh/lookup-page-objects @st/state)]
    (into []
          (comp
           (map #(get objects %))
           (filter #(= :text (:type %)))
           (mapcat (fn [{:keys [id content]}]
                     (->> (dwwt/text-fonts content)
                          (map wasm.fonts/make-font-data)
                          (filter #(and (wasm.fonts/font-ready? %)
                                        (not (wasm.fonts/font-stored? % (:emoji? %)))))
                          (map (fn [font] {:code "font-fallback"
                                           :shapeId (str id)
                                           :fontId (:font-id font)}))
                          (distinct)))))
          ids)))

(defn ^:export finishExecution
  "Completes the derived values of the execution (layout, text size and
  position data, booleans, component sync) and saves them with its edits.
  Options: `settleTimeout` (ms) bounds the wait for derived values;
  `maxChanges` the number of changes one save may hold (D9). Resolves to the
  commit report of 03-runtime-contract §3."
  [^js opts]
  (let [settle-timeout (or (some-> opts .-settleTimeout) 10000)
        max-changes    (or (some-> opts .-maxChanges) 5000)]
    (-> (p/let [_         (when-let [reloading (:reloading @execution)]
                            (p/race [reloading (p/delay settle-timeout)]))
                _         (when (pos? (:refused @execution))
                            (throw (ex-info "this user has read-only access to the file; its edits were not applied"
                                            {:type :not-found :code :object-not-found})))
                pending   (session/settle! settle-timeout)
                ;; 03-runtime-contract §3: an execution always completes its
                ;; derived values; saving them half done would leave the rest
                ;; to whichever browser opens the file next
                _         (when (some? pending)
                            (throw (ex-info (str "layout, text or component work did not finish within "
                                                 settle-timeout " ms ("
                                                 (->> pending
                                                      (map (fn [[id kinds]] (str id " " (str/join "," (map name (keys kinds))))))
                                                      (take 5)
                                                      (str/join "; "))
                                                 "); nothing was saved")
                                            {:type :resource-limit :code :settle-timeout})))
                ;; D9: one save holds at most `max-changes` changes, derived
                ;; ones included
                _         (let [n (:change-count @execution)]
                            (when (> n max-changes)
                              (throw (ex-info (str "the execution made " n " changes; one save holds at most "
                                                   max-changes "; nothing was saved")
                                              {:type :resource-limit :code :too-many-changes}))))
                ;; D4, checked again right before the save: another session's
                ;; change may have arrived while the code ran
                _         (let [{:keys [precondition file-id]} @execution
                                revn (some-> file-id file-revn)]
                            (when (and (some? precondition) (some? revn) (> revn precondition))
                              (throw (ex-info (str "the file changed since revn " precondition
                                                   " (now " revn "); nothing was saved")
                                              {:type :validation :code :precondition-failed}))))
                _         (session/flush!)
                warnings  (font-fallback-warnings (:changed @execution))
                state     (end-execution!)
                file-id   (or (current-file-id) (:file-id state))
                ;; the revn the last `update-file` answered: the file's revn
                ;; before that change, so the saved revn is one more
                answered  (some-> file-id file-revn)
                before    (:revn-before state)
                saves     (:saves state)
                revn      (if (pos? saves) (inc answered) answered)
                _         (when (and file-id (pos? saves))
                            (swap! saved-revn assoc file-id revn)
                            (if-let [direction (:history state)]
                              (history/moved! direction file-id revn)
                              (history/record! file-id (:commits state) revn
                                               (:vern (dsh/lookup-file @st/state file-id)))))
                changed   (disj (:changed state) uuid/zero)
                follow    (when (and (pos? saves) (seq changed) (pos? (following-tabs)))
                            ;; tabs that follow on another page go to the page of the
                            ;; changed shapes and show them selected (PEN-24)
                            (let [tabs (following-tabs)]
                              (st/emit! (dws/send {:type :broadcast
                                                   :kind :ai-follow
                                                   :action :show-changes
                                                   :file-id file-id
                                                   :pages (changes-by-page changed)}))
                              {:tabs tabs :actions (conj (vec (:follow state)) "show-changes")}))
                follow    (or follow
                              (when (seq (:follow state))
                                {:tabs (:follow-tabs state) :actions (:follow state)}))]
          #js {:saved (pos? saves)
               :fileId (some-> file-id str)
               :revnBefore before
               :revn revn
               :changedShapeIds (clj->js (mapv str changed))
               ;; changes the save held, derived ones included (D9)
               :changes (if (pos? saves) (:change-count state) 0)
               ;; changes of other sessions applied in between
               :lagged (if (and (pos? saves) before)
                         (max 0 (- answered before (dec saves)))
                         0)
               ;; derived values always complete before a save (see above)
               :computed #js {:layout true :text true :bool true :componentSync true}
               :pending nil
               :warnings (clj->js warnings)
               ;; calls shown on the user's following tabs (PEN-24)
               :follow (clj->js follow)})
        (p/catch (fn [cause]
                   (end-execution!)
                   (p/rejected (contract-error cause)))))))

(defn ^:export applyHistory
  "Within an execution, undoes (`\"undo\"`) or redoes (`\"redo\"`) the
  last saved execution of this executor session in the open file
  (`app.executor.history`). `finishExecution` saves it. Rejects with
  `precondition-failed` when another session changed what it would revert,
  `not-found` when there is nothing to undo or redo. Resolves to the number
  of changes applied."
  [direction]
  (let [direction (keyword direction)
        file-id   (current-file-id)]
    (with-contract-errors
      (p/let [{:keys [changes latest]} (history/prepare direction file-id (:session-id @st/state))]
        ;; saved only if nobody saved past the revn checked above meanwhile
        (swap! execution update :precondition #(if (some? %) (min % latest) latest))
        (swap! execution assoc :history direction)
        (st/emit! (dch/commit-changes {:redo-changes changes
                                       :undo-changes []
                                       :save-undo? false
                                       :origin (ptk/data-event ::apply-history {:direction direction})
                                       :file-id file-id}))
        (count changes)))))

(defn ^:export historyStatus
  "Number of saved executions of this executor session that can be undone
  and redone in the open file."
  []
  (let [{:keys [undo redo]} (history/counts (current-file-id))]
    #js {:undo undo :redo redo}))

(defn ^:export abortExecution
  "Saves nothing of the execution in progress and reloads the file."
  []
  (end-execution!)
  (session/discard!))
