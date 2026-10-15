;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns app.executor.main
  "Entry point of the server-side MCP executor process.

  CLI mode (experiments and tests):
    PENPOT_EXECUTOR_TOKEN=<token> node executor.js run <code-file> <file-id> [page-id]
  opens the file, runs the code as the body of an async function with the
  plugin API globals, saves, and prints one JSON line with the result."
  (:require
   ["node:fs" :as fs]
   ;; Registers the transit handler of the file data objects map, as
   ;; `app.main` does in the browser.
   [app.common.types.objects-map]
   [app.common.uuid :as uuid]
   [app.executor.auth :as auth]
   [app.executor.session :as session]
   [app.executor.wasm :as ewasm]
   [app.main.data.workspace]
   [app.plugins.api :as api]
   [app.plugins.register :as preg]
   [app.render-wasm.api :as wasm.api]
   [promesa.core :as p]))

(defn- env
  [name default]
  (or (unchecked-get js/process.env name) default))

(defn- run-code
  "Runs `code` as the body of an async function receiving the plugin API
  globals, as the MCP plugin's `executeCode` handler does."
  [code]
  (let [context (api/create-context preg/mcp-plugin-id)
        flags   (.-flags ^js context)]
    (set! (.-naturalChildOrdering ^js flags) true)
    (set! (.-throwValidationErrors ^js flags) true)
    (let [f (js/Function. "penpot" "penpotMgmt" "storage" "console"
                          (str "return (async () => { " code " })();"))]
      (f context (.-management ^js context) #js {} js/console))))

(defn- run-cli
  [[code-path file-id page-id]]
  (let [code (str (fs/readFileSync code-path))]
    (auth/install! (env "PENPOT_EXECUTOR_TOKEN" nil))
    (session/install-error-handler!)
    (when (seq (env "PENPOT_EXECUTOR_TRACE" nil))
      (session/trace-events!))
    (when (seq (env "PENPOT_EXECUTOR_TRACE_REFLOW" nil))
      (session/trace-reflow!))
    (p/let [_      (ewasm/init! (env "PENPOT_EXECUTOR_WASM_DIR" "resources/public/js"))
            opened (session/open! {:file-id (uuid/uuid file-id)
                                   :page-id (some-> page-id uuid/uuid)})
            start  (js/Date.now)
            result (run-code code)
            ;; let debounced derived-value commits (text position data)
            ;; land before saving
            _      (p/delay (js/parseInt (env "PENPOT_EXECUTOR_SETTLE_MS" "1500")))
            _      (session/flush!)]
      (js/console.log
       (js/JSON.stringify
        #js {:ok true
             :fileId (str (:file-id opened))
             :pageId (str (:page-id opened))
             :wasm (wasm.api/initialized?)
             :ms (- (js/Date.now) start)
             :result result}))
      (js/process.exit 0))))

(defn init
  []
  (let [[_ _ command & args] (js->clj js/process.argv)]
    (case command
      "run" (-> (run-cli args)
                (p/catch (fn [cause]
                           (js/console.error "executor failed:" cause (ex-data cause))
                           (js/console.error "pending reflow:" (pr-str (session/pending-reflow)))
                           (js/process.exit 1))))
      (js/console.error "usage: executor.js run <code-file> <file-id> [page-id]"))))
