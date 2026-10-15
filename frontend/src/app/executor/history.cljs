;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS SUBSIDIARY SL

(ns app.executor.history
  "Undo and redo of the executor's saved executions (PEN-20, D6).

  Each saved execution is one step, as a browser's undo step is one user
  action: the undo changes of its commits, newest first. Steps are kept per
  file for the life of the executor session. Undoing a step saves its undo
  changes as a new execution; redoing saves its changes again.

  A step is refused, and nothing is saved, when another session has changed
  what it would revert since it was saved: undoing it would overwrite that
  change. The backend's record of saved changes (`get-file-changes`) tells
  what other sessions changed, so the check holds across missed
  notifications and file reloads; when that record is gone, or the file was
  restored to a version, the step is refused as well."
  (:require
   [app.main.data.helpers :as dsh]
   [app.main.repo :as rp]
   [app.main.store :as st]
   [beicon.v2.core :as rx]
   [promesa.core :as p]))

;; as the workspace undo stack (`app.main.data.workspace.undo`)
(def ^:private max-steps 50)

;; file-id -> {:undo [step ...] :redo [step ...]}, newest last. A step:
;; {:redo changes, :undo changes, :entities #{...}, :revn saved revn,
;;  :vern file vern}
(defonce ^:private stacks (atom {}))

(defn- page-key [kind page-id id] [kind page-id id])

(defn change-entities
  "What a change touches, as keys compared between sessions: shapes,
  pages, library assets, tokens, guides, flows, plugin data."
  [{:keys [type id page-id component-id] :as change}]
  (case type
    (:add-obj :mod-obj :del-obj :fix-obj) [[:shape id]]
    :mov-objects (conj (mapv #(vector :shape %) (:shapes change))
                       [:shape (:parent-id change)])
    :reorder-children [[:shape (:parent-id change)]]
    ;; derived: geometry of groups recomputed from their children
    :reg-objects []
    (:add-page :mod-page :del-page :mov-page) [[:page id]]
    :set-guide [(page-key :guide page-id id)]
    :set-flow [(page-key :flow page-id id)]
    :set-default-grid [[:grid page-id]]
    :set-plugin-data [[:plugin-data (:object-type change) (or (:object-id change) page-id)
                       (:namespace change) (:key change)]]
    (:add-color :mod-color) [[:color (get-in change [:color :id])]]
    :del-color [[:color id]]
    (:add-media :mod-media) [[:media (get-in change [:object :id])]]
    :del-media [[:media id]]
    (:add-component :mod-component :del-component :restore-component :purge-component)
    [[:component (or id component-id)]]
    (:add-typography :mod-typography) [[:typography (get-in change [:typography :id])]]
    :del-typography [[:typography id]]
    :set-token [[:token (:set-id change) (:token-id change)]]
    :set-token-set [[:token-set id]]
    :set-token-theme [[:token-theme id]]
    :set-tokens-status [[:tokens-status]]
    ;; whole-library and structure changes of the tokens
    (:set-tokens-lib :rename-token-set-group :move-token-set :move-token-set-group
                     :set-base-font-size :set-tokens-source)
    [[:tokens-structure]]
    ;; comment positions are saved at once, outside of executions
    :set-comment-thread-position []
    [[:unknown type]]))

(defn record!
  "Records a saved execution of `file-id` as an undo step. `commits` are its
  local commits that a browser would keep for undo, oldest first. A new step
  drops the steps that were undone."
  [file-id commits revn vern]
  (let [redo (into [] (mapcat :redo-changes) commits)
        undo (into [] (mapcat :undo-changes) (reverse commits))]
    (when (seq redo)
      (let [step {:redo redo
                  :undo undo
                  :entities (into #{} (mapcat change-entities) (concat redo undo))
                  :revn revn
                  :vern vern}]
        (swap! stacks update file-id
               (fn [stack]
                 {:undo (->> (conj (vec (:undo stack)) step)
                             (take-last max-steps)
                             (vec))
                  :redo []}))))))

(defn counts
  "Number of steps that can be undone and redone in `file-id`."
  [file-id]
  (let [{:keys [undo redo]} (get @stacks file-id)]
    {:undo (count undo) :redo (count redo)}))

(defn- others-changes
  "Entities that sessions other than `session-id` changed in `file-id`
  after `revn`, or a reason why that cannot be told."
  [file-id revn vern session-id]
  (->> (rp/cmd! :get-file-changes {:file-id file-id :since-revn revn})
       (rx/map (fn [{:keys [complete changes] :as answer}]
                 (cond
                   (not= vern (:vern answer))
                   {:unknown "the file was restored to another version since"}

                   (not complete)
                   {:unknown "the record of later changes is no longer kept"}

                   :else
                   {:latest (:revn answer)
                    :entities (into #{}
                                    (comp (remove #(= session-id (:session-id %)))
                                          (mapcat :changes)
                                          (mapcat change-entities))
                                    changes)})))))

(defn- describe
  [file-id entities]
  (let [pages (vals (:pages-index (dsh/lookup-file-data @st/state file-id)))
        label (fn [[kind & ids]]
                (let [id    (last ids)
                      named (when (= kind :shape)
                              (some #(get-in % [:objects id :name]) pages))]
                  (if named
                    (str "shape '" named "' (" id ")")
                    (str (name kind) " " id))))
        named (->> entities
                   (map label)
                   (sort)
                   (take 5))]
    (str (apply str (interpose ", " named))
         (when (> (count entities) 5) (str " and " (- (count entities) 5) " more")))))

(defn prepare
  "Picks the step to undo (`:undo`) or redo (`:redo`) in `file-id` and checks
  that no other session changed what it touches since it was saved.
  Resolves to `{:step step :changes changes-to-commit :latest revn}`;
  rejects with a `:precondition-failed` error when it is in the way of
  another session's change, `:not-found` when there is nothing to do."
  [direction file-id session-id]
  (let [stack (get-in @stacks [file-id direction])
        step  (peek stack)]
    (if (nil? step)
      (p/rejected (ex-info (str "there is no saved execution of this session to "
                                (name direction) " in this file")
                           {:type :not-found :code :object-not-found}))
      (p/let [{:keys [unknown latest entities]}
              (p/create (fn [resolve reject]
                          (rx/subs! resolve reject
                                    (rx/first (others-changes file-id (:revn step) (:vern step) session-id)))))]
        (cond
          (some? unknown)
          (throw (ex-info (str "cannot " (name direction) " the execution: " unknown
                               ", so changes by others cannot be ruled out")
                          {:type :validation :code :precondition-failed}))

          (seq (filter (:entities step) entities))
          (throw (ex-info (str "cannot " (name direction) " the execution: since it was saved, someone else changed "
                               (describe file-id (filter (:entities step) entities))
                               ", which it would change back; their work is kept")
                          {:type :validation :code :precondition-failed}))

          :else
          {:step step
           :latest latest
           :changes (if (= direction :undo) (:undo step) (:redo step))})))))

(defn moved!
  "Moves the top step of `direction` in `file-id` to the other stack once its
  undo or redo is saved at `revn`."
  [direction file-id revn]
  (let [other (if (= direction :undo) :redo :undo)]
    (swap! stacks update file-id
           (fn [stack]
             (let [step (peek (get stack direction))]
               (-> stack
                   (update direction pop)
                   (update other (fnil conj []) (assoc step :revn revn))))))))
