;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns frontend-tests.plugins.file-test
  (:require
   [app.main.repo :as rp]
   [app.plugins.file :as file]
   [beicon.v2.core :as rx]
   [cljs.test :as t :include-macros true]
   [frontend-tests.helpers.mock :as mock]))

(t/deftest file-version-created-at-returns-stored-date
  (let [created-at (js/Date.)
        version    (file/file-version-proxy
                    "00000000-0000-0000-0000-000000000000"
                    (random-uuid)
                    {}
                    {:id (random-uuid)
                     :label "Version"
                     :created-at created-at})]
    (t/is (identical? created-at (.-createdAt version)))))

(t/deftest pin-resolves-the-pinned-version
  ;; Regression: `pin` named the RPC answer like the version's data and
  ;; dereferenced the answer, so the promise never settled.
  (t/async done
    (let [snapshot-id (random-uuid)
          calls       (atom [])
          version     (file/file-version-proxy
                       "00000000-0000-0000-0000-000000000000"
                       (random-uuid)
                       {}
                       {:id snapshot-id
                        :label "internal/snapshot/3"
                        :created-by "system"
                        :created-at (js/Date. 0)})]
      (t/is (true? (.-isAutosave version)))
      (with-redefs [rp/cmd! (mock/stub
                             (fn [cmd params]
                               (swap! calls conj [cmd params])
                               (case cmd
                                 :get-team-users (rx/of [])
                                 :update-file-snapshot (rx/of true))))]
        (-> (.pin ^js version)
            (.then (fn [^js pinned]
                     (t/is (false? (.-isAutosave pinned)))
                     (t/is (not= "internal/snapshot/3" (.-label pinned)))
                     (t/is (= snapshot-id (get-in @calls [1 1 :id])))
                     (done)))
            (.catch (fn [cause]
                      (t/is false (str "pin rejected: " cause))
                      (done))))))))
