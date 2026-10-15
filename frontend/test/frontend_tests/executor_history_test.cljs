;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns frontend-tests.executor-history-test
  (:require
   [app.common.uuid :as uuid]
   [app.executor.history :as history]
   [cljs.test :as t :include-macros true]
   [promesa.core :as p]))

(t/deftest change-entities-name-what-a-change-touches
  (let [a (uuid/next) b (uuid/next) page (uuid/next)]
    (t/is (= [[:shape a]] (history/change-entities {:type :mod-obj :id a :page-id page})))
    (t/is (= #{[:shape a] [:shape b]}
             (set (history/change-entities {:type :mov-objects :shapes [a] :parent-id b}))))
    (t/is (= [[:color a]] (history/change-entities {:type :mod-color :color {:id a}})))
    (t/is (= [[:token a b]] (history/change-entities {:type :set-token :set-id a :token-id b})))
    (t/is (= [[:guide page a]] (history/change-entities {:type :set-guide :page-id page :id a})))
    ;; recomputed group geometry is not a change of its own
    (t/is (= [] (history/change-entities {:type :reg-objects :shapes [a]})))
    ;; an unknown change type still counts, so it is never ignored by mistake
    (t/is (= [[:unknown :new-type]] (history/change-entities {:type :new-type})))))

(defn- commit
  [id]
  {:redo-changes [{:type :mod-obj :id id :operations []}]
   :undo-changes [{:type :mod-obj :id id :operations []}]})

(t/deftest steps-move-between-undo-and-redo
  (let [file (uuid/next) a (uuid/next) b (uuid/next)]
    (history/record! file [(commit a)] 2 0)
    (history/record! file [(commit b)] 3 0)
    (t/is (= {:undo 2 :redo 0} (history/counts file)))
    (history/moved! :undo file 4)
    (t/is (= {:undo 1 :redo 1} (history/counts file)))
    (history/moved! :redo file 5)
    (t/is (= {:undo 2 :redo 0} (history/counts file)))
    (history/moved! :undo file 6)
    ;; a new execution drops what was undone
    (history/record! file [(commit a)] 7 0)
    (t/is (= {:undo 2 :redo 0} (history/counts file)))))

(t/deftest an-execution-without-undoable-changes-is-no-step
  (let [file (uuid/next)]
    (history/record! file [] 2 0)
    (t/is (= {:undo 0 :redo 0} (history/counts file)))))

(t/deftest steps-are-bounded
  (let [file (uuid/next)]
    (dotimes [i 60]
      (history/record! file [(commit (uuid/next))] i 0))
    (t/is (= 50 (:undo (history/counts file))))))

(t/deftest nothing-to-undo-is-not-found
  (t/async done
    (-> (history/prepare :undo (uuid/next) (uuid/next))
        (p/then (fn [_] (t/is false "expected a refusal")))
        (p/catch (fn [cause] (t/is (= :object-not-found (:code (ex-data cause))))))
        (p/finally (fn [] (done))))))
