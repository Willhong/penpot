;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns frontend-tests.ai-follow-test
  (:require
   [app.common.uuid :as uuid]
   [app.main.data.workspace.ai-follow :as ai-follow]
   [beicon.v2.core :as rx]
   [cljs.test :as t :include-macros true]
   [potok.v2.core :as ptk]))

(def ^:private file-id (uuid/next))
(def ^:private page-a (uuid/next))
(def ^:private page-b (uuid/next))
(def ^:private shape (uuid/next))

(defn- state
  [following?]
  (cond-> {:current-file-id file-id
           :current-page-id page-a
           :workspace-local {:zoom 1 :vbox {:x 0 :y 0 :width 100 :height 100}}}
    following? (assoc :workspace-ai-follow true)))

(defn- emitted
  "Types of the events a followed call emits at once in `state`."
  [msg state]
  (let [out (atom [])]
    (rx/sub! (ptk/watch (ai-follow/handle-message msg) state (rx/empty))
             #(swap! out conj (ptk/type %)))
    @out))

(t/deftest a-tab-that-does-not-follow-ignores-the-calls
  (t/is (= [] (emitted {:action :select :file-id file-id :page-id page-a :ids [shape]} (state false)))))

(t/deftest calls-on-another-file-are-ignored
  (t/is (= [] (emitted {:action :select :file-id (uuid/next) :page-id page-a :ids [shape]} (state true)))))

(t/deftest a-call-on-the-tabs-page-applies-there
  (t/is (= [::ai-follow/apply-actions]
           (emitted {:action :select :file-id file-id :page-id page-a :ids [shape]} (state true)))))

(t/deftest a-call-on-another-page-goes-there-first
  (t/is (= [:app.main.data.common/go-to-workspace]
           (emitted {:action :zoom :zoom 2 :file-id file-id :page-id page-b} (state true)))))

(t/deftest changes-on-the-tabs-page-leave-the-screen-alone
  (t/is (= [] (emitted {:action :show-changes :file-id file-id :pages {page-a [shape] page-b [shape]}}
                       (state true))))
  (t/is (= [:app.main.data.common/go-to-workspace]
           (emitted {:action :show-changes :file-id file-id :pages {page-b [shape]}} (state true)))))

(t/deftest the-tab-reports-whether-it-follows
  (t/is (true? (ai-follow/following? (state true))))
  (t/is (false? (ai-follow/following? (state false)))))
