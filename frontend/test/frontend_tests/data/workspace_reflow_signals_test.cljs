;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns frontend-tests.data.workspace-reflow-signals-test
  (:require
   [app.common.uuid :as uuid]
   [app.main.data.workspace.reflow.signals :as wrfs]
   [cljs.test :as t :include-macros true]))

(def ^:private page-id (uuid/next))
(def ^:private text-id (uuid/next))

(defn- text-ids
  "Texts a wasm-renderer update of a text from `before` to `after` signals
  for re-measurement."
  [before after]
  (let [shape (merge {:id text-id :type :text :width 100 :height 20} before)
        state {:features #{"render-wasm/v1"} :current-page-id page-id}]
    (:text-ids (wrfs/reflow-ids state page-id {text-id shape}
                                {text-id (merge shape after)} [text-id] nil))))

(t/deftest wasm-text-reflow-follows-the-updated-grow-type
  (t/testing "an auto-sized text whose content changes is re-measured"
    (t/is (= [text-id] (text-ids {:grow-type :auto-height :content :a} {:content :b}))))
  (t/testing "a text that becomes auto-sized is re-measured"
    (t/is (= [text-id] (text-ids {:grow-type :fixed} {:grow-type :auto-width}))))
  (t/testing "a text that becomes fixed gets no wasm work, so nothing waits for it"
    (t/is (nil? (text-ids {:grow-type :auto-height} {:grow-type :fixed :height 900}))))
  (t/testing "a fixed text stays unsignalled"
    (t/is (nil? (text-ids {:grow-type :fixed :content :a} {:content :b})))))

(defn- content
  "A one-run text content."
  [text fill-color font-size]
  {:type "root"
   :children [{:type "paragraph-set"
               :children [{:type "paragraph"
                           :children [{:text text
                                       :font-size font-size
                                       :fills [{:fill-color fill-color :fill-opacity 1}]}]}]}]})

(t/deftest wasm-text-reflow-ignores-paint-only-content-changes
  (t/testing "a new fill does not change the size, so nothing waits for a measure"
    (t/is (nil? (text-ids {:grow-type :auto-width :content (content "Buy" "#000000" "14")}
                          {:content (content "Buy" "#ffffff" "14")}))))
  (t/testing "new characters are re-measured"
    (t/is (= [text-id] (text-ids {:grow-type :auto-width :content (content "Buy" "#000000" "14")}
                                 {:content (content "Buy now" "#000000" "14")}))))
  (t/testing "a new font size is re-measured, also with a new fill"
    (t/is (= [text-id] (text-ids {:grow-type :auto-width :content (content "Buy" "#000000" "14")}
                                 {:content (content "Buy" "#ffffff" "16")})))))
