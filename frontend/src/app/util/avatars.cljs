;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns app.util.avatars
  (:require
   [app.util.object :as obj]
   [cuerdas.core :as str]))

(defn- initials
  [name]
  (let [parts (str/words (str/upper name))]
    (if (= 1 (count parts))
      (ffirst parts)
      (str (ffirst parts) (first (second parts))))))

(defn svg-avatar
  "The avatar `generate*` draws, as an SVG data URL: it needs no DOM, so the
  server-side MCP executor, which has none, can give users an avatar too."
  [{:keys [name color size]
    :or {size 128}}]
  (let [letters    (-> (str (initials name))
                       (str/replace "&" "&amp;")
                       (str/replace "<" "&lt;")
                       (str/replace ">" "&gt;"))
        text-color (if color "#2e3434" "#fff")
        color      (or color "#000000")
        svg        (str "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"" size "\" height=\"" size "\">"
                        "<rect width=\"" size "\" height=\"" size "\" fill=\"" color "\"/>"
                        "<text x=\"" (/ size 2) "\" y=\"" (/ size 1.5) "\" font-family=\"Arial\" font-size=\"" (/ size 2)
                        "\" text-anchor=\"middle\" fill=\"" text-color "\">" letters "</text></svg>")]
    (str "data:image/svg+xml;charset=utf-8," (js/encodeURIComponent svg))))

(defn generate*
  [{:keys [name color size]
    :or {size 128}
    :as params}]

  (if-not (exists? js/document)
    (svg-avatar params)
    (let [letters (initials name)
          canvas  (.createElement js/document "canvas")
          context (.getContext canvas "2d")
          text-color (if color
                       "#2e3434"
                       "#fff")
          color (or color "#000000")]

      (obj/set! canvas "width" size)
      (obj/set! canvas "height" size)

      (obj/set! context "fillStyle" color)
      (.fillRect context 0 0 size size)

      (obj/set! context "font" (str (/ size 2) "px Arial"))
      (obj/set! context "textAlign" "center")
      (obj/set! context "fillStyle" text-color)
      (.fillText context letters (/ size 2) (/ size 1.5))

      (.toDataURL canvas))))

(def generate (memoize generate*))

