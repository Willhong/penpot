;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns frontend-tests.data.workspace-wasm-text-test
  (:require
   [app.main.data.workspace.wasm-text :as dwwt]
   [cljs.test :as t :include-macros true]))

(defn- content
  [text]
  {:type "root"
   :children [{:type "paragraph-set"
               :children [{:type "paragraph"
                           :children [{:text text
                                       :font-id "sourcesanspro"
                                       :font-variant-id "regular"
                                       :font-weight "400"
                                       :font-style "normal"}]}]}]})

(t/deftest text-fonts-include-the-fallback-fonts-of-its-glyphs
  ;; Regression: a text was measured once its named fonts were ready, before
  ;; the fallback fonts for its Korean or emoji glyphs arrived, and saved the
  ;; size of the text without them.
  (let [latin  (dwwt/text-fonts (content "Hello"))
        mixed  (dwwt/text-fonts (content "Hello 안녕 😀"))
        extra  (remove (set latin) mixed)]
    (t/is (= #{"sourcesanspro"} (into #{} (map :font-id) latin)))
    (t/is (seq extra) "the Korean and emoji glyphs add fonts")
    (t/is (every? :is-fallback extra))))
