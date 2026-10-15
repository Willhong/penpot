;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns app.plugins
  "RPC for plugins runtime."
  (:require
   ["@penpot/plugins-runtime" :as runtime]
   [app.main.errors :as errors]
   [app.main.features :as features]
   [app.main.store :as st]
   [app.plugins.api :as api]
   [app.plugins.public-utils]
   [app.plugins.register :as preg]
   ;; connects the proxies that would otherwise require each other
   [app.plugins.wiring]
   [beicon.v2.core :as rx]
   [potok.v2.core :as ptk]))

(defn init-plugins-runtime
  []
  (runtime/initPluginsRuntime (fn [plugin-id] (api/create-context plugin-id)))
  ;; Signal that runtime is ready
  (preg/signal-runtime-ready))

(defn initialize
  []
  (ptk/reify ::initialize
    ptk/WatchEvent
    (watch [_ _ stream]
      (set! errors/is-plugin-error? runtime/isPluginError)

      (->> stream
           (rx/filter (ptk/type? ::features/initialize))
           (rx/observe-on :async)
           (rx/filter #(features/active-feature? @st/state "plugins/runtime"))
           (rx/take 1)
           (rx/tap init-plugins-runtime)
           (rx/ignore)))))
