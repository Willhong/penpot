;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at http://mozilla.org/MPL/2.0/.
;;
;; Copyright (c) KALEIDOS INC Sucursal en España SL

(ns backend-tests.http-websocket-test
  (:require
   [app.common.uuid :as uuid]
   [app.db :as db]
   [app.http.access-token :as actoken]
   [app.http.websocket :as ws]
   [app.msgbus :as mbus]
   [app.nitrate :as nitrate]
   [app.rpc :as-alias rpc]
   [app.rpc.commands.files :as files]
   [app.rpc.commands.teams :as teams]
   [app.util.websocket :as util-ws]
   [backend-tests.helpers :as th]
   [clojure.test :as t]
   [promesa.exec.csp :as sp]))

(t/use-fixtures :once th/state-init)
(t/use-fixtures :each th/database-reset)

(defn make-wsp
  [profile-id state output-ch]
  {::util-ws/id (uuid/next)
   ::util-ws/state state
   ::util-ws/output-ch output-ch
   ::ws/profile-id profile-id
   ::ws/session-id (uuid/next)})

(t/deftest subscribe-file-permission-check
  (let [profile1 (th/create-profile* 1 {:is-active true})
        profile2 (th/create-profile* 2 {:is-active true})
        file     (th/create-file* 1 {:profile-id (:id profile1)
                                     :project-id (:default-project-id profile1)})
        cfg      th/*system*
        state    (atom {})
        output-ch (sp/chan :buf (sp/dropping-buffer 64))]

    (t/testing "rejects unauthorized user"
      (let [wsp (make-wsp (:id profile2) state output-ch)]
        (t/is (thrown-with-msg?
               clojure.lang.ExceptionInfo
               #"not found"
               ((get-method ws/handle-message :subscribe-file)
                cfg wsp {:file-id (:id file)})))))

    (t/testing "permission check passes for authorized user"
      (t/is (nil? (files/check-read-permissions! cfg (:id profile1) (:id file)))))))

(t/deftest subscribe-team-permission-check
  (let [profile1 (th/create-profile* 1 {:is-active true})
        profile2 (th/create-profile* 2 {:is-active true})
        team     (th/create-team* 1 {:profile-id (:id profile1)})
        cfg      th/*system*
        state    (atom {})
        output-ch (sp/chan :buf (sp/dropping-buffer 64))]

    (t/testing "rejects unauthorized user"
      (let [wsp (make-wsp (:id profile2) state output-ch)]
        (t/is (thrown-with-msg?
               clojure.lang.ExceptionInfo
               #"not found"
               ((get-method ws/handle-message :subscribe-team)
                cfg wsp {:team-id (:id team)})))))

    (t/testing "permission check passes for authorized user"
      (t/is (nil? (teams/check-read-permissions! cfg (:id profile1) (:id team)))))))

(defn- subscribed-topics
  "Runs :subscribe-team for `profile-id` on `team-id` with `nitrate-call`
  standing in for nitrate; returns the topics and the stored subscription."
  [profile-id team-id nitrate-call]
  (let [state     (atom {})
        output-ch (sp/chan :buf (sp/dropping-buffer 64))
        wsp       (make-wsp profile-id state output-ch)
        calls     (atom [])]
    (with-redefs [nitrate/call nitrate-call
                  mbus/sub!    (fn [_ & {:keys [topics]}]
                                 (swap! calls conj topics))]
      ((get-method ws/handle-message :subscribe-team)
       th/*system* wsp {:team-id team-id}))
    (some-> @state ::ws/team-subscription :channel sp/close!)
    {:topics @calls
     :subscription (::ws/team-subscription @state)}))

(t/deftest subscribe-team-subscribes-to-team-organization
  (let [profile (th/create-profile* 1 {:is-active true})
        team-id (:id (th/create-team* 1 {:profile-id (:id profile)}))
        org-id  (uuid/next)]

    (t/testing "adds the organization topic when the team has one"
      (let [{:keys [topics subscription]}
            (subscribed-topics (:id profile) team-id
                               (fn [_ method params]
                                 (when (= :get-team-organization method)
                                   {:id (:team-id params)
                                    :organization {:id org-id}})))]
        (t/is (= [[team-id org-id]] topics))
        (t/is (= org-id (:organization-id subscription)))))

    (t/testing "subscribes only to the team when it has no organization"
      (let [{:keys [topics subscription]}
            (subscribed-topics (:id profile) team-id (constantly nil))]
        (t/is (= [[team-id]] topics))
        (t/is (nil? (:organization-id subscription)))))

    (t/testing "subscribes to the team when nitrate fails"
      (let [{:keys [topics]}
            (subscribed-topics (:id profile) team-id
                               (fn [& _] (throw (ex-info "nitrate down" {}))))]
        (t/is (= [[team-id]] topics))))))

(t/deftest pointer-update-validates-file-id
  (let [profile  (th/create-profile* 1 {:is-active true})
        file     (th/create-file* 1 {:profile-id (:id profile)
                                     :project-id (:default-project-id profile)})
        cfg      th/*system*
        file-id  (:id file)
        sub-ch   (sp/chan :buf (sp/dropping-buffer 64))
        state    (atom {::ws/file-subscription {:file-id file-id
                                                :channel sub-ch
                                                :topic file-id}})
        output-ch (sp/chan :buf (sp/dropping-buffer 64))
        wsp      (make-wsp (:id profile) state output-ch)]

    (t/testing "skips publish when file-id does not match subscription"
      (let [wrong-msg {:type :pointer-update
                       :file-id (uuid/next)
                       :position {:x 10 :y 20}
                       :zoom 1.0}]
        (t/is (nil?
               ((get-method ws/handle-message :pointer-update)
                cfg wsp wrong-msg)))))

    (t/testing "does nothing when no file subscription exists"
      (let [empty-state (atom {})
            empty-wsp   (make-wsp (:id profile) empty-state output-ch)
            msg         {:type :pointer-update
                         :file-id file-id
                         :position {:x 10 :y 20}
                         :zoom 1.0}]
        (t/is (nil?
               ((get-method ws/handle-message :pointer-update)
                cfg empty-wsp msg)))))))

(defn- handler-error
  "Calls the notifications handler with a non-upgrade request and returns the
  data of the error it raises: `:authentication` when it found no profile,
  `:websocket-request-expected` once authentication passed."
  [cfg request]
  (try
    (#'ws/http-handler cfg request)
    nil
    (catch Exception cause
      (select-keys (ex-data cause) [:type :code]))))

(t/deftest notifications-accept-token-only-from-mcp-service
  (let [profile-id (uuid/next)
        cfg        {:app.setup/shared-keys {:mcp "mcp-secret"}}
        request    (fn [headers]
                     (-> (th/make-dummy-request {:headers headers})
                         (assoc :params {:session-id (str (uuid/next))})
                         (assoc ::actoken/profile-id profile-id)))]

    (t/testing "a token holder other than the MCP service is not authenticated"
      (t/is (= :authentication (:type (handler-error cfg (request {})))))
      (t/is (= :authentication (:type (handler-error cfg (request {"x-shared-key" "mcp wrong"}))))))

    (t/testing "the MCP service is authenticated by the user's token"
      (t/is (= :websocket-request-expected
               (:code (handler-error cfg (request {"x-shared-key" "mcp mcp-secret"}))))))))

(defn- join-message
  "The :join-file message a connection publishes when it subscribes to `file`,
  as the AI of its user (the MCP executor) when `ai?`."
  [profile-id file-id ai?]
  (let [published (atom [])
        wsp       (cond-> (make-wsp profile-id (atom {}) (sp/chan :buf (sp/dropping-buffer 64)))
                    ai? (assoc ::ws/ai? true))]
    (with-redefs [mbus/pub! (fn [_ & {:keys [message]}] (swap! published conj message))
                  mbus/sub! (fn [& _] nil)]
      ((get-method ws/handle-message :subscribe-file)
       th/*system* wsp {:file-id file-id}))
    (some-> @(::util-ws/state wsp) ::ws/file-subscription :channel sp/close!)
    (first (filter #(= :join-file (:type %)) @published))))

(t/deftest executor-joins-a-file-as-the-ai-of-its-user
  (let [profile (th/create-profile* 1 {:is-active true})
        file    (th/create-file* 1 {:profile-id (:id profile)
                                    :project-id (:default-project-id profile)})]

    (t/testing "the MCP executor's connection joins as AI (D3)"
      (let [message (join-message (:id profile) (:id file) true)]
        (t/is (= (:id profile) (:profile-id message)))
        (t/is (true? (:ai message)))))

    (t/testing "a browser's connection does not"
      (t/is (not (contains? (join-message (:id profile) (:id file) false) :ai))))))
