;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns frontend-tests.util-avatars-test
  (:require
   [app.util.avatars :as avatars]
   [cljs.test :as t :include-macros true]))

(defn- svg-of
  [url]
  (js/decodeURIComponent (subs url (count "data:image/svg+xml;charset=utf-8,"))))

(t/deftest svg-avatar-needs-no-dom
  (t/testing "draws the initials on the color, as the canvas avatar does"
    (let [url (avatars/svg-avatar {:name "MCPV Editor" :color "#ff0000"})
          svg (svg-of url)]
      (t/is (.startsWith url "data:image/svg+xml;charset=utf-8,"))
      (t/is (.includes svg "fill=\"#ff0000\""))
      (t/is (.includes svg ">ME</text>"))))
  (t/testing "keeps initials outside ASCII and drops markup characters"
    (t/is (.includes (svg-of (avatars/svg-avatar {:name "홍 길동"})) ">홍길</text>"))
    (t/is (.includes (svg-of (avatars/svg-avatar {:name "<a> b"})) ">AB</text>")))
  (t/testing "uses the default colors without a color"
    (t/is (.includes (svg-of (avatars/svg-avatar {:name "Solo"})) "fill=\"#000000\""))))
