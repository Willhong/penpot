;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns app.main.ui.workspace.presence
  (:require-macros [app.main.style :as stl])
  (:require
   [app.common.data :as d]
   [app.common.data.macros :as dm]
   [app.config :as cfg]
   [app.main.refs :as refs]
   [app.util.dom :as dom]
   [app.util.i18n :refer [tr]]
   [app.util.timers :as tm]
   [rumext.v2 :as mf]))

(mf/defc session-widget*
  {::mf/props :obj
   ::mf/memo true}
  [{:keys [color profile index ai]}]
  (let [profile       (assoc profile :color color)
        ;; the user's AI working through the server-side MCP (D3)
        full-name     (if ai
                        (tr "workspace.presence.ai-session" (:fullname profile))
                        (:fullname profile))]
    [:li {:class (stl/css :session-icon)
          :style {:z-index (dm/str (+ 2 (* -1 index)))
                  :background-color color}
          :title full-name
          :data-ai (when ai "true")}
     [:img {:alt full-name
            :style {:background-color color}
            :src (cfg/resolve-profile-photo-url profile)}]
     (when ai
       [:span {:class (stl/css :ai-badge)} "AI"])]))

(mf/defc active-sessions*
  {::mf/memo true}
  []
  (let [profiles     (mf/deref refs/profiles)
        presence     (mf/deref refs/workspace-presence)

        sessions     (vals presence)
        num-sessions (count sessions)
        max-avatar-count 3
        avatar-count (if (= num-sessions max-avatar-count) max-avatar-count (- max-avatar-count 1))

        open*        (mf/use-state false)
        open?        (and ^boolean (deref open*) (> num-sessions max-avatar-count))
        on-open
        (mf/use-fn
         (fn []
           (reset! open* true)
           (tm/schedule-on-idle
            #(dom/focus! (dom/get-element "users-close")))))

        on-close
        (mf/use-fn #(reset! open* false))]

    [:*
     (when ^boolean open?
       [:button {:id "users-close"
                 :class (stl/css :active-users-opened)
                 :on-click on-close
                 :on-blur on-close}
        [:ul {:class (stl/css :active-users-list) :data-testid "active-users-list"}
         (for [session sessions]
           [:> session-widget*
            {:color (:color session)
             :index 0
             :ai (:ai session)
             :profile (get profiles (:profile-id session))
             :key (dm/str (:id session))}])]])

     [:button {:class (stl/css-case :active-users true)
               :on-click on-open}
      [:ul {:class (stl/css :active-users-list) :data-testid "active-users-list"}
       (when (> num-sessions max-avatar-count)
         [:li {:class (stl/css :users-num)} (dm/str "+" (+ 1 (- num-sessions max-avatar-count)))])

       (for [[index session] (d/enumerate (take avatar-count sessions))]
         [:> session-widget*
          {:color (:color session)
           :index index
           :ai (:ai session)
           :profile (get profiles (:profile-id session))
           :key (dm/str (:id session))}])]]]))
