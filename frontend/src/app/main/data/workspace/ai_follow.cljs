;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns app.main.data.workspace.ai-follow
  "\"AI follow\" of a browser tab (PEN-24, D8 (f) of
  mcp/docs/server-mcp/01-feature-contract.md).

  Off by default. A tab that turns it on shows what the user's server-side
  MCP sessions do in the file it has open: the page they open, the
  selection they set, the viewport moves they ask for, and the page of the
  shapes an execution changed when the tab is on another page. The
  executor sends these as `:broadcast` messages, which the backend hands to
  the sessions of the same profile only. The tab reports that it follows in
  its presence messages, so the executor can tell whether any tab applied
  a call.

  When the user moves the screen (page, zoom, scroll, selection) while it is
  on, following turns off with a notice, so the AI does not pull the screen
  away from them."
  (:require
   [app.common.data :as d]
   [app.common.uuid :as uuid]
   [app.main.data.common :as dcm]
   [app.main.data.notifications :as ntf]
   [app.main.data.workspace.pages :as dwpg]
   [app.main.data.workspace.selection :as dws]
   [app.main.data.workspace.viewport :as dwv]
   [app.main.data.workspace.zoom :as dwz]
   [app.util.i18n :refer [tr]]
   [beicon.v2.core :as rx]
   [potok.v2.core :as ptk]))

;; Until when screen events come from a followed call, not from the user.
(defonce ^:private applying-until (atom 0))

;; How long after a followed call its screen events may still arrive.
(def ^:private apply-window-ms 700)

(defn- applying! [] (reset! applying-until (+ (js/Date.now) apply-window-ms)))

(defn following?
  [state]
  (true? (:workspace-ai-follow state)))

;; Screen events a user causes by moving around: a page change, zoom,
;; scrolling and panning, selection.
(def ^:private navigation-events
  #{::dcm/go-to-workspace
    ::dwz/increase-zoom ::dwz/decrease-zoom ::dwz/set-zoom ::dwz/reset-zoom
    ::dwz/zoom-to-fit-all ::dwz/zoom-to-selected-shape ::dwz/fit-to-shapes ::dwz/center-on-shape
    ::dwv/update-viewport-position ::dwv/update-viewport-position-center ::dwv/start-panning
    ::dws/select-shape ::dws/select-prev-shape ::dws/select-next-shape ::dws/deselect-shape
    ::dws/shift-select-shapes ::dws/select-shapes ::dws/select-all ::dws/deselect-all
    ::dws/select-inside-group ::dws/select-shapes-by-current-selrect})

(declare stop)

(defn start
  "Turns following on in this tab."
  []
  (ptk/reify ::start
    ptk/UpdateEvent
    (update [_ state]
      (assoc state :workspace-ai-follow true))

    ptk/WatchEvent
    (watch [_ _ stream]
      (let [stopper (rx/filter (ptk/type? ::stop) stream)]
        (rx/concat
         (rx/of (ntf/info (tr "workspace.ai-follow.on")))
         (->> stream
              (rx/filter #(contains? navigation-events (ptk/type %)))
              (rx/filter (fn [_] (> (js/Date.now) @applying-until)))
              (rx/take 1)
              (rx/map (fn [_] (stop true)))
              (rx/take-until stopper)))))))

(defn stop
  "Turns following off in this tab; `by-user-move?` when the user moved the
  screen, which says so."
  ([] (stop false))
  ([by-user-move?]
   (ptk/reify ::stop
     ptk/UpdateEvent
     (update [_ state]
       (dissoc state :workspace-ai-follow))

     ptk/WatchEvent
     (watch [_ _ _]
       (rx/of (ntf/info (if by-user-move?
                          (tr "workspace.ai-follow.off-moved")
                          (tr "workspace.ai-follow.off"))))))))

(defn toggle
  []
  (ptk/reify ::toggle
    ptk/WatchEvent
    (watch [_ state _]
      (rx/of (if (following? state) (stop) (start))))))

(defn- ->uuid [v] (if (uuid? v) v (uuid/parse* (str v))))

(defn- uuids [ids] (into (d/ordered-set) (keep ->uuid) ids))

(defn- page-of-changes
  "Page to show for the shapes an execution changed: none when some of them
  are on the tab's page, else the page with most of them."
  [state pages]
  (when-not (contains? pages (:current-page-id state))
    (key (apply max-key (comp count val) pages))))

(defn- actions
  "Events applying a followed call `msg` in a tab on `state`."
  [state {:keys [action page-id ids x y zoom pages]}]
  (let [vbox (get-in state [:workspace-local :vbox])
        current-zoom (get-in state [:workspace-local :zoom])]
    (case action
      :page   []
      :select [(dws/select-shapes (uuids ids))]
      :center (let [dx (- x (+ (:x vbox) (/ (:width vbox) 2)))
                    dy (- y (+ (:y vbox) (/ (:height vbox) 2)))]
                [(dwv/update-viewport-position {:x #(+ % dx) :y #(+ % dy)})])
      :zoom   [(dwz/set-zoom (/ zoom current-zoom))]
      :zoom-reset [dwz/reset-zoom]
      :zoom-fit-all [dwz/zoom-to-fit-all]
      :zoom-into-view [(dwz/fit-to-shapes (uuids ids))]
      :show-changes (let [ids (get pages page-id)]
                      [(dws/select-shapes (uuids ids))])
      [])))

(defn- apply-actions
  "Applies `msg` on the tab's page as it is now."
  [msg]
  (ptk/reify ::apply-actions
    ptk/WatchEvent
    (watch [_ state _]
      (applying!)
      (rx/from (actions state msg)))))

(defn handle-message
  "Applies a followed call of the user's server-side MCP session: `:page`
  (opened a page), `:select`, `:center`, `:zoom`, `:zoom-reset`,
  `:zoom-fit-all`, `:zoom-into-view`, or `:show-changes` (the shapes an
  execution changed, by page). Only for the file the tab has open."
  [{:keys [action file-id page-id pages] :as msg}]
  (ptk/reify ::handle-message
    ptk/WatchEvent
    (watch [_ state stream]
      (let [pages   (some-> pages (update-keys ->uuid))
            page-id (if (= action :show-changes)
                      (page-of-changes state pages)
                      (some-> page-id ->uuid))
            msg     (assoc msg :page-id page-id :pages pages)]
        (cond
          (not (and (following? state)
                    (= (->uuid file-id) (:current-file-id state))
                    (or (not= action :show-changes) (some? page-id))))
          (rx/empty)

          (or (nil? page-id) (= page-id (:current-page-id state)))
          (do (applying!)
              (rx/of (apply-actions msg)))

          :else
          (do (applying!)
              (rx/merge
               (rx/of (dcm/go-to-workspace :page-id page-id))
               (->> stream
                    (rx/filter (ptk/type? ::dwpg/initialized))
                    (rx/take 1)
                    (rx/take-until (rx/timer 10000))
                    ;; on the page's own viewport once it is in place
                    (rx/map (fn [_] (apply-actions msg)))))))))))
