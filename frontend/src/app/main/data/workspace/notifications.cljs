;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns app.main.data.workspace.notifications
  (:require
   [app.common.data :as d]
   [app.common.data.macros :as dm]
   [app.common.files.changes :as cpc]
   [app.common.schema :as sm]
   [app.common.time :as ct]
   [app.common.uuid :as uuid]
   [app.main.data.changes :as dch]
   [app.main.data.comments :as dcmt]
   [app.main.data.common :as dc]
   [app.main.data.helpers :as dsh]
   [app.main.data.modal :as modal]
   [app.main.data.plugins :as dpl]
   [app.main.data.websocket :as dws]
   [app.main.data.workspace :as-alias dw]
   [app.main.data.workspace.ai-follow :as ai-follow]
   [app.main.data.workspace.common :as dwc]
   [app.main.data.workspace.edition :as dwe]
   [app.main.data.workspace.layout :as dwly]
   [app.main.data.workspace.libraries :as dwl]
   [app.main.data.workspace.texts :as dwt]
   [app.main.repo :as rp]
   [app.main.router :as rt]
   [app.util.globals :refer [global]]
   [app.util.mouse :as mse]
   [app.util.object :as obj]
   [app.util.rxops :as rxs]
   [app.util.theme :as theme]
   [beicon.v2.core :as rx]
   [clojure.set :as set]
   [potok.v2.core :as ptk]))

;; FIXME: this ns should be renamed to something different

(declare process-message)
(declare handle-presence)
(declare handle-pointer-update)
(declare handle-file-change)
(declare handle-file-deleted)
(declare handle-file-restored)
(declare handle-library-change)
(declare handle-pointer-send)
(declare handle-viewport-send)
(declare handle-export-update)
(declare fetch-missed-changes)

(defn initialize
  [team-id file-id]
  (ptk/reify ::initialize
    ptk/WatchEvent
    (watch [_ state stream]
      (let [stopper     (rx/filter (ptk/type? ::finalize) stream)
            profile-id (:profile-id state)
            organization-id (dm/get-in state [:teams team-id :organization :id])
            ;; last pointer position and last viewport sent to the others
            last-point (atom nil)
            last-sent  (atom nil)

            initmsg    [{:type :subscribe-file
                         :file-id file-id
                         :version (obj/get global "penpotVersion")}
                        {:type :subscribe-team
                         :team-id team-id}]

            endmsg     {:type :unsubscribe-file
                        :file-id file-id}

            stream     (->> (rx/merge
                             ;; Send the subscription message
                             (->> (rx/from initmsg)
                                  (rx/map dws/send))

                             ;; Subscribe to notifications of the subscription
                             (->> stream
                                  (rx/filter (ptk/type? ::dws/message))
                                  (rx/map deref)
                                  (rx/filter (fn [{:keys [topic] :as msg}]
                                               (or (= topic uuid/zero)
                                                   (= topic profile-id)
                                                   (= topic team-id)
                                                   (= topic file-id)
                                                   (when (some? organization-id)
                                                     (= topic organization-id)))))
                                  (rx/map process-message))

                             ;; On reconnect, send again the subscription messages
                             (->> stream
                                  (rx/filter (ptk/type? ::dws/opened))
                                  (rx/mapcat #(->> (rx/from initmsg)
                                                   (rx/map dws/send))))

                             ;; and catch up with what was published meanwhile,
                             ;; comments included (they are not file changes)
                             (->> stream
                                  (rx/filter (ptk/type? ::dws/opened))
                                  (rx/mapcat #(rx/of (fetch-missed-changes file-id)
                                                     (dcmt/refresh-comment-threads file-id nil))))

                             ;; Emit presence event for current user;
                             ;; this is because websocket server don't
                             ;; emits this for the same user.
                             (rx/of (handle-presence {:type :connect
                                                      :session-id (:session-id state)
                                                      :profile-id (:profile-id state)}))

                             ;; Emit to all other connected users the current pointer
                             ;; position changes.
                             (->> stream
                                  (rx/filter mse/pointer-event?)
                                  (rx/filter #(= :viewport (mse/get-pointer-source %)))
                                  (rx/tap #(reset! last-point (:pt %)))
                                  (rx/pipe (rxs/throttle 50))
                                  (rx/map #(handle-pointer-send file-id (:pt %) last-sent)))

                             ;; Send the viewport too when it changes without a pointer
                             ;; move (zoom shortcuts, scrolling), and to a session that
                             ;; joins the file: the MCP executor of the same user reads it
                             ;; (D8 (b) of mcp/docs/server-mcp/01-feature-contract.md).
                             (->> stream
                                  (rx/filter (complement mse/pointer-event?))
                                  (rx/filter (complement (ptk/type? ::handle-viewport-send)))
                                  (rx/pipe (rxs/throttle 250))
                                  (rx/map #(handle-viewport-send file-id @last-point last-sent false)))

                             (->> stream
                                  (rx/filter (ptk/type? ::dws/message))
                                  (rx/map deref)
                                  (rx/filter #(and (= :join-file (:type %))
                                                   (= file-id (:file-id %))))
                                  (rx/map #(handle-viewport-send file-id @last-point last-sent true))))

                            (rx/take-until stopper))]

        (rx/concat stream (rx/of (dws/send endmsg)))))))

(defn- handle-change-team-role
  [{:keys [role] :as msg}]
  (ptk/reify ::handle-change-team-role
    ptk/WatchEvent
    (watch [_ _ _]
      (rx/concat
       (rx/of :interrupt
              (dwe/clear-edition-mode)
              (dwc/set-workspace-read-only false))
       (->> (rx/of (dc/change-team-role msg)
                   ::dwt/update-editor-state)
            ;; Delay so anything that launched :interrupt can finish
            (rx/delay 100))
       (if (= :viewer role)
         (rx/of (modal/hide)
                (dwly/set-options-mode :inspect)
                (dpl/close-current-plugin {:close-only-edition-plugins? true}))
         (rx/of (dwly/set-options-mode :design)))))))

(defn- process-message
  [{:keys [type] :as msg}]
  (case type
    :join-file               (handle-presence msg)
    :leave-file              (handle-presence msg)
    :presence                (handle-presence msg)
    :disconnect              (handle-presence msg)
    :pointer-update          (handle-pointer-update msg)
    ;; a followed call of this user's server-side MCP session (PEN-24)
    :broadcast               (when (= :ai-follow (:kind msg)) (ai-follow/handle-message msg))
    :file-change             (handle-file-change msg)
    :comment-change          (dcmt/refresh-comment-threads (:file-id msg) (:thread-id msg))
    :file-deleted            (handle-file-deleted msg)
    :file-restored           (handle-file-restored msg)
    :library-change          (handle-library-change msg)
    :notification            (dc/handle-notification msg)
    :team-role-change        (handle-change-team-role msg)
    :team-membership-change  (dc/team-membership-change msg)
    :team-organization-change         (dc/handle-change-team-organization msg)
    :organization-change-sso (dc/handle-organization-change-sso msg)
    nil))

(defn- pointer-message
  [state file-id point]
  (let [local (:workspace-local state)]
    {:type :pointer-update
     :file-id file-id
     :page-id (:current-page-id state)
     :zoom (:zoom local)
     :zoom-inverse (:zoom-inverse local)
     :vbox (:vbox local)
     :vport (:vport local)
     :theme (theme/resolve-theme (dm/get-in state [:profile :theme])
                                 (theme/get-system-theme))
     ;; whether this tab follows the user's server-side MCP sessions (PEN-24)
     :ai-follow (ai-follow/following? state)
     :position point}))

(defn- viewport-of
  [message]
  (select-keys message [:page-id :zoom :vbox :theme :ai-follow]))

(defn- handle-pointer-send
  [file-id point last-sent]
  (ptk/reify ::handle-pointer-send
    ptk/WatchEvent
    (watch [_ state _]
      (let [message (pointer-message state file-id point)]
        (reset! last-sent (viewport-of message))
        (rx/of (dws/send message))))))

(defn- handle-viewport-send
  "Sends the pointer update message when the viewport changed since the
  last one sent, or always when `force?`. Nothing while there is no
  viewport (a session without a screen)."
  [file-id point last-sent force?]
  (ptk/reify ::handle-viewport-send
    ptk/WatchEvent
    (watch [_ state _]
      (let [message  (pointer-message state file-id point)
            viewport (viewport-of message)]
        (if (and (some? (:vbox message))
                 (or force? (not= viewport @last-sent)))
          (do (reset! last-sent viewport)
              (rx/of (dws/send message)))
          (rx/empty))))))

;; --- Finalize Websocket

(defn finalize
  [_]
  (ptk/reify ::finalize))

;; --- Handle: Presence

(def ^:private presence-palette
  #{"#f49ef7" ; pink
    "#75cafc" ; blue
    "#fdcf79" ; gold
    "#a9bdfa" ; indigo
    "#faa6b7" ; red
    "#cbaaff" ; purple
    "#f9b489" ; orange
    "#dee563" ; yellow -> default presence color
    "#b1e96f" ; lemon
    })

(defn handle-presence
  [{:keys [type session-id profile-id version] :as message}]
  (letfn [(get-next-color [presence]
            (let [xfm   (comp (map second)
                              (map :color)
                              (remove nil?))
                  used  (into #{} xfm presence)
                  avail (set/difference presence-palette used)]
              ;; If all colores are used we select the default one
              (or (first avail) "#dee563")))

          (update-color [color presence]
            (if (some? color)
              color
              (get-next-color presence)))

          (update-session [session presence]
            (-> session
                (assoc :id session-id)
                (assoc :profile-id profile-id)
                (assoc :updated-at (ct/now))
                (assoc :version version)
                (update :color update-color presence)
                (assoc :text-color "#000000")))

          (update-presence [presence]
            (-> presence
                (update session-id update-session presence)
                (d/without-nils)))]

    (ptk/reify ::handle-presence
      ptk/UpdateEvent
      (update [_ state]
        (if (or (= :disconnect type) (= :leave-file type))
          (update state :workspace-presence dissoc session-id)
          (update state :workspace-presence update-presence))))))


(defn handle-pointer-update
  [{:keys [page-id session-id position zoom zoom-inverse vbox vport theme ai-follow] :as msg}]
  (ptk/reify ::handle-pointer-update
    ptk/UpdateEvent
    (update [_ state]
      (update-in state [:workspace-presence session-id]
                 (fn [session]
                   (assoc session
                          :zoom zoom
                          :zoom-inverse zoom-inverse
                          :vbox vbox
                          :vport vport
                          :theme theme
                          :ai-follow (true? ai-follow)
                          :point position
                          :updated-at (ct/now)
                          :page-id page-id))))))

(def ^:private
  schema:handle-file-change
  [:map {:title "handle-file-change"}
   [:type :keyword]
   [:profile-id ::sm/uuid]
   [:file-id ::sm/uuid]
   [:session-id ::sm/uuid]
   [:revn :int]
   [:vern :int]
   [:changes cpc/schema:changes]])

(def ^:private check-file-change-params!
  (sm/check-fn schema:handle-file-change))

(defn handle-file-change
  [{:keys [file-id changes revn vern] :as msg}]

  (dm/assert!
   "expected valid parameters"
   (check-file-change-params! msg))

  (ptk/reify ::handle-file-change
    IDeref
    (-deref [_] {:changes changes})

    ptk/WatchEvent
    (watch [_ _ _]
      ;; The commit event is responsible to apply the data localy
      ;; and update the persistence internal state with the updated
      ;; file-revn

      (rx/of (dch/commit {:file-id file-id
                          :file-revn revn
                          :file-vern vern
                          :save-undo? false
                          :source :remote
                          :redo-changes (vec changes)
                          :undo-changes []})))))

(defn- fetch-missed-changes
  "Applies the changes other sessions saved while the notification
  connection was down: they were published while nobody listened for them.
  Reloads the file when the backend no longer has them all, or when the
  file was restored meanwhile."
  [file-id]
  (ptk/reify ::fetch-missed-changes
    ptk/WatchEvent
    (watch [_ state _]
      (let [file       (dsh/lookup-file state file-id)
            since      (:revn file)
            session-id (:session-id state)]
        (if (or (nil? file) (nil? since))
          (rx/empty)
          (->> (rp/cmd! :get-file-changes {:file-id file-id :since-revn since})
               (rx/mapcat
                (fn [{:keys [complete changes vern]}]
                  (if (or (not complete) (not= vern (:vern file)))
                    (rx/of (ptk/event ::dw/reload-current-file))
                    (->> changes
                         ;; this session's own saves are applied already
                         (remove #(= session-id (:session-id %)))
                         (map (fn [{:keys [revn changes]}]
                                (dch/commit {:file-id file-id
                                             :file-revn revn
                                             :file-vern vern
                                             :save-undo? false
                                             :source :remote
                                             :redo-changes (vec changes)
                                             :undo-changes []})))
                         (rx/from)))))
               (rx/catch (fn [cause]
                           (js/console.error "unable to catch up with missed changes" cause)
                           (rx/empty)))))))))

(defn handle-file-deleted
  [{:keys [file-id] :as msg}]
  (ptk/reify ::handle-file-deleted
    ptk/WatchEvent
    (watch [_ state _]
      (let [curr-file-id (:current-file-id state)
            team-id      (:current-team-id state)]
        ;; If the deleted file is the currently open one
        (when (= file-id curr-file-id)
          (rx/of
           (rt/nav :dashboard-recent {:team-id team-id})))))))

(def ^:private
  schema:handle-file-restored
  [:map {:title "handle-file-restored"}
   [:type :keyword]
   [:file-id ::sm/uuid]
   [:vern :int]])

(def ^:private check-file-restored-params
  (sm/check-fn schema:handle-file-restored))

(defn handle-file-restored
  [{:keys [file-id vern] :as msg}]

  (assert (check-file-restored-params msg)
          "expected valid parameters")

  (ptk/reify ::handle-file-restored
    ptk/WatchEvent
    (watch [_ state _]
      (let [curr-file-id    (:current-file-id state)
            file            (dsh/lookup-file state curr-file-id)
            curr-vern       (:vern file)]

        (when (and (= file-id curr-file-id)
                   (not= vern curr-vern))
          (rx/of (ptk/event ::dw/reload-current-file)))))))

(def ^:private schema:handle-library-change
  [:map {:title "handle-library-change"}
   [:type :keyword]
   [:profile-id ::sm/uuid]
   [:file-id ::sm/uuid]
   [:session-id ::sm/uuid]
   [:revn :int]
   [:modified-at ::ct/inst]
   [:changes cpc/schema:changes]])

(def ^:private check-library-change-params
  (sm/check-fn schema:handle-library-change))

(defn handle-library-change
  [{:keys [file-id modified-at changes revn] :as msg}]
  (assert (check-library-change-params msg)
          "expected valid arguments")

  (ptk/reify ::handle-library-change
    ptk/WatchEvent
    (watch [_ state _]
      (when (contains? (:files state) file-id)
        (rx/of (dwl/ext-library-changed file-id modified-at revn changes)
               (dwl/notify-sync-file))))))
