;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns app.executor.main
  "Entry point of the `:executor` build.

  Imported by the executor host, the module only exports `app.executor.api`.
  Run directly, it is a command line tool for experiments:

    PENPOT_EXECUTOR_TOKEN=<token> PENPOT_MCP_SHARED_KEY=<key> \\
      node executor.js run <code-file> <file-id> [page-id]

  opens the file, runs the code as the body of an async function with the
  plain plugin context as `penpot` (no plugins runtime, no sandbox), saves,
  and prints one JSON line with the result and the commit report."
  (:require
   ["node:fs" :as fs]
   ;; Registers the transit handler of the file data objects map, as
   ;; `app.main` does in the browser.
   [app.common.types.objects-map]
   [app.executor.api :as api]
   [app.executor.session :as session]
   [app.main.data.workspace]
   [promesa.core :as p]))

(defn- env
  [name]
  (not-empty (unchecked-get js/process.env name)))

(defn- run-code
  "Runs `code` as the body of an async function receiving the plugin context,
  with the flags the MCP plugin's `executeCode` handler sets."
  [code]
  (let [context (api/context)
        flags   (.-flags ^js context)]
    (set! (.-naturalChildOrdering ^js flags) true)
    (set! (.-throwValidationErrors ^js flags) true)
    (let [f (js/Function. "penpot" "penpotMgmt" "storage" "console"
                          (str "return (async () => { " code " })();"))]
      (f context (.-management ^js context) #js {} js/console))))

(defn- run-cli
  [[code-path file-id page-id]]
  (let [code (str (fs/readFileSync code-path))]
    (when (env "PENPOT_EXECUTOR_TRACE")
      (session/trace-events!))
    (when (env "PENPOT_EXECUTOR_TRACE_REFLOW")
      (session/trace-reflow!))
    (p/let [_      (api/boot #js {:token (env "PENPOT_EXECUTOR_TOKEN")
                                  :sharedKey (env "PENPOT_MCP_SHARED_KEY")
                                  :wasmDir (or (env "PENPOT_EXECUTOR_WASM_DIR")
                                               "resources/public/js")})
            opened (api/openFile file-id page-id)
            start  (js/Date.now)
            _      (api/beginExecution)
            result (-> (run-code code)
                       (p/catch (fn [cause]
                                  (p/do (api/abortExecution)
                                        (p/rejected cause)))))
            commit (api/finishExecution #js {})]
      (js/console.log
       (js/JSON.stringify
        #js {:ok true
             :fileId (.-fileId ^js opened)
             :pageId (.-pageId ^js opened)
             :ms (- (js/Date.now) start)
             :result result
             :commit commit
             :status (api/status)
             :memory (js/process.memoryUsage)}))
      (js/process.exit 0))))

(defn init
  []
  (let [[_ script command & args] (js->clj js/process.argv)]
    ;; Imported as a module the host drives it through the exports instead.
    (when (and (= "run" command)
               (re-find #"executor\.js$" (str script)))
      (-> (run-cli args)
          (p/catch (fn [cause]
                     (js/console.error "executor failed:" cause (ex-data cause))
                     (js/console.error "pending reflow:" (pr-str (session/pending-reflow)))
                     (js/process.exit 1)))))))
