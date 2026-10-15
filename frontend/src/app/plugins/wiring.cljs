;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns app.plugins.wiring
  "Connects the plugin proxies that would otherwise require each other.
  Loading this namespace is enough; anything that builds a plugin context
  (the browser plugins runtime, the server-side MCP executor) requires it."
  (:require
   [app.plugins.flex :as flex]
   [app.plugins.format :as format]
   [app.plugins.grid :as grid]
   [app.plugins.library :as library]
   [app.plugins.ruler-guides :as rg]
   [app.plugins.shape :as shape]))

(set! flex/shape-proxy? shape/shape-proxy?)
(set! grid/shape-proxy? shape/shape-proxy?)
(set! format/shape-proxy shape/shape-proxy)
(set! rg/shape-proxy shape/shape-proxy)
(set! rg/shape-proxy? shape/shape-proxy?)

(set! shape/lib-typography-proxy? library/lib-typography-proxy?)
(set! shape/lib-component-proxy library/lib-component-proxy)
