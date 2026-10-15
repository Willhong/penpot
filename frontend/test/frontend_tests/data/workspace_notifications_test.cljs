;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns frontend-tests.data.workspace-notifications-test
  (:require
   [app.common.test-helpers.files :as cthf]
   [app.common.uuid :as uuid]
   [app.main.data.workspace.notifications :as dwn]
   [app.main.repo :as rp]
   [beicon.v2.core :as rx]
   [cljs.test :as t :include-macros true]
   [frontend-tests.helpers.mock :as mock]
   [frontend-tests.helpers.state :as ths]
   [potok.v2.core :as ptk]))

(def ^:private own-session (uuid/next))
(def ^:private other-session (uuid/next))

(defn- catch-up
  "Events `fetch-missed-changes` emits for a file at revn 3, given the
  backend's answer."
  [answer]
  (let [file   (-> (cthf/sample-file :file1 :page-label :page1)
                   (assoc :revn 3 :vern 0))
        store  (ths/setup-store file)
        state  (assoc @store :session-id own-session)
        events (atom [])
        calls  (atom [])]
    (with-redefs [rp/cmd! (mock/stub (fn [cmd params]
                                       (swap! calls conj [cmd params])
                                       (rx/of answer)))]
      (->> (ptk/watch (#'dwn/fetch-missed-changes (:id file)) state (rx/empty))
           (rx/subs! #(swap! events conj %))))
    {:events @events :calls @calls :file-id (:id file)}))

(t/deftest catch-up-applies-what-other-sessions-saved
  (let [{:keys [events calls file-id]}
        (catch-up {:revn 6 :vern 0 :complete true
                   :changes [{:revn 4 :session-id other-session :changes [{:type :del-page :id (uuid/next)}]}
                             {:revn 5 :session-id own-session :changes [{:type :del-page :id (uuid/next)}]}
                             {:revn 6 :session-id other-session :changes [{:type :del-page :id (uuid/next)}]}]})]
    (t/is (= [[:get-file-changes {:file-id file-id :since-revn 3}]] calls))
    (t/testing "the other sessions' saves, in order, as remote commits; not this session's own"
      (t/is (= [4 6] (mapv #(:file-revn (deref %)) events)))
      (t/is (every? #(= :remote (:source (deref %))) events)))))

(t/deftest catch-up-reloads-when-saves-are-missing
  (let [{:keys [events]} (catch-up {:revn 6 :vern 0 :complete false :changes []})]
    (t/is (= [:app.main.data.workspace/reload-current-file] (mapv ptk/type events)))))

(t/deftest catch-up-reloads-a-restored-file
  (let [{:keys [events]} (catch-up {:revn 6 :vern 9 :complete true :changes []})]
    (t/is (= [:app.main.data.workspace/reload-current-file] (mapv ptk/type events)))))

(defn- viewport-sends
  "Events `handle-viewport-send` emits for a state, and what it records as
  last sent."
  [state last-sent force?]
  (let [last-sent (atom last-sent)
        events    (atom [])]
    (->> (ptk/watch (#'dwn/handle-viewport-send (uuid/next) nil last-sent force?) state (rx/empty))
         (rx/subs! #(swap! events conj %)))
    {:types (mapv ptk/type @events) :last-sent @last-sent}))

(t/deftest viewport-is-sent-when-it-changes
  (let [vbox  {:x 0 :y 0 :width 100 :height 50}
        state {:current-page-id own-session
               :profile {:theme "light"}
               :workspace-local {:zoom 2 :vbox vbox}}
        sent  {:page-id own-session :zoom 2 :vbox vbox :theme "light"}]
    (t/testing "a new viewport is sent and recorded"
      (t/is (= {:types [:app.main.data.websocket/send-message] :last-sent sent}
               (viewport-sends state nil false))))
    (t/testing "the same viewport is not sent again, unless forced (a session joined)"
      (t/is (= [] (:types (viewport-sends state sent false))))
      (t/is (= [:app.main.data.websocket/send-message] (:types (viewport-sends state sent true)))))
    (t/testing "a session without a screen sends nothing"
      (t/is (= [] (:types (viewport-sends (update state :workspace-local dissoc :vbox) nil true)))))))
