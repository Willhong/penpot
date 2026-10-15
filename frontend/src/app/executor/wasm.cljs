;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns app.executor.wasm
  "Headless boot of the frontend's render-wasm module under Node.

  The workspace normally loads `js/render-wasm.js` with a dynamic import and
  binds it to a WebGL canvas. The executor has neither, so it instantiates the
  same artifact from local bytes and boots it with `_init_headless` (design
  state + GPU-free resources only). Once booted, every `app.render-wasm.api`
  computation the workspace events call (modifier propagation, text layout,
  position data, boolean paths) runs on the real engine. Interactive frame
  rendering is disabled: there is no surface to draw on."
  (:require
   ["node:fs" :as fs]
   ["node:path" :as path]
   [app.common.logging :as l]
   [app.common.render-wasm.helpers :as h]
   [app.common.render-wasm.wasm :as wasm]
   [promesa.core :as p]
   [shadow.esm :refer [dynamic-import]]))

(def ^:private viewport-width 1920)
(def ^:private viewport-height 1080)

(defn init!
  "Loads `render-wasm.js`/`render-wasm.wasm` from `dir` and boots the module
  headless. Resolves to the module once `app.render-wasm.api/initialized?`
  holds."
  [dir]
  (let [js-path    (path/resolve dir "render-wasm.js")
        wasm-path  (path/resolve dir "render-wasm.wasm")
        wasm-bytes (fs/readFileSync wasm-path)]
    (l/info :hint "loading render-wasm (headless)" :js js-path)
    (->> (dynamic-import (str "file://" js-path))
         (p/mcat
          (fn [mod]
            (let [factory (unchecked-get mod "default")]
              (factory
               #js {:instantiateWasm
                    (fn [imports success]
                      (-> (js/WebAssembly.instantiate wasm-bytes imports)
                          (.then (fn [result] (success (.-instance result)))))
                      #js {})
                    :locateFile (fn [p] (path/resolve dir p))
                    :printErr   (fn [s] (l/warn :wasm s))}))))
         (p/fmap
          (fn [module]
            (set! wasm/internal-module module)
            (h/call module "_init_headless" viewport-width viewport-height)
            ;; No canvas to present to: frame requests become no-ops while
            ;; every computation entry point stays live.
            (reset! wasm/disable-request-render? true)
            (set! wasm/headless? true)
            (set! wasm/context-initialized? true)
            module)))))
