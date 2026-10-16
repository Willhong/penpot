#!/usr/bin/env bash
#
# Rehearses the rollback of design.hktlabs.com in a throwaway namespace; it
# never touches the `penpot` namespace.
#
#   BACKUP_DIR=<pre-upgrade backup> TAG=hkt-<sha> docker/hkt-deploy/rollback-rehearsal.sh
#
# BACKUP_DIR holds penpot.pgdump, assets.tgz and helm-values.yaml taken
# before the upgrade (see README.md). Delete the namespace afterwards:
#   helm -n penpot-rollback-test uninstall penpot-rbt
#   kubectl delete ns penpot-rollback-test
#
#   rev 1: chart with the 2.18.3 values, DB + assets restored from the
#          pre-upgrade backup
#   rev 2: upgrade to the hkt images (runs the 0153-0156 migrations)
#   rollback: the README procedure (restore the 2.18.3 dump, helm rollback 1)
set -euo pipefail

NS=penpot-rollback-test
REL=penpot-rbt
B="${BACKUP_DIR:?set BACKUP_DIR}"
HKT_VALUES="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/values.yaml"
TAG="${TAG:?set TAG, e.g. hkt-41b20fcbe}"

step() { echo; echo "=== [$(date '+%T')] $*"; }
kc() { kubectl -n "$NS" "$@"; }

step "namespace + secret"
kubectl create ns "$NS" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl -n penpot get secret penpot-secrets -o json \
  | jq 'del(.metadata.namespace,.metadata.uid,.metadata.resourceVersion,.metadata.creationTimestamp,.metadata.ownerReferences,.metadata.managedFields)' \
  | kc apply -f - >/dev/null

step "postgres + valkey"
kubectl -n penpot get sts postgres -o json \
  | jq 'del(.metadata.namespace,.metadata.uid,.metadata.resourceVersion,.metadata.creationTimestamp,.metadata.generation,.metadata.managedFields,.metadata.annotations,.status)' \
  | kc apply -f - >/dev/null
kubectl -n penpot get svc postgres valkey -o json \
  | jq '.items |= map(del(.metadata.namespace,.metadata.uid,.metadata.resourceVersion,.metadata.creationTimestamp,.metadata.managedFields,.metadata.annotations,.spec.clusterIP,.spec.clusterIPs,.status))' \
  | kc apply -f - >/dev/null
kubectl -n penpot get deploy valkey -o json \
  | jq 'del(.metadata.namespace,.metadata.uid,.metadata.resourceVersion,.metadata.creationTimestamp,.metadata.generation,.metadata.managedFields,.metadata.annotations,.status)' \
  | kc apply -f - >/dev/null
kc rollout status sts/postgres --timeout=180s
kc rollout status deploy/valkey --timeout=120s
sleep 5

restore_db() {
  kc exec postgres-0 -- sh -c 'dropdb -U "$POSTGRES_USER" --force --if-exists penpot && createdb -U "$POSTGRES_USER" penpot'
  kc exec -i postgres-0 -- sh -c 'pg_restore -U "$POSTGRES_USER" -d penpot --no-owner' < "$B/penpot.pgdump"
}

base_values() {
  sed -e "s#penpot.svc.cluster.local#$NS.svc.cluster.local#g" \
      -e 's#https://design.hktlabs.com#https://design-rbt.invalid#' "$B/helm-values.yaml" \
    > /tmp/rbt-base.yaml
  printf 'ingress:\n  enabled: false\n' > /tmp/rbt-noingress.yaml
}

step "rev 1: restore 2.18.3 dump, install 2.18.3"
restore_db
base_values
helm -n "$NS" upgrade --install "$REL" penpot/penpot --version 1.11.3 -f /tmp/rbt-base.yaml -f /tmp/rbt-noingress.yaml --wait --timeout 8m >/dev/null
kc exec -i deploy/$REL-backend -- tar -C /opt/data/assets --strip-components=1 --no-same-permissions -m -xzf - < "$B/assets.tgz"
kc logs deploy/$REL-backend | grep -a 'welcome to penpot' | grep -o 'version="[^"]*"'

step "rev 2: upgrade to $TAG (runs the new migrations)"
helm -n "$NS" upgrade "$REL" penpot/penpot --version 1.11.3 -f /tmp/rbt-base.yaml -f "$HKT_VALUES" -f /tmp/rbt-noingress.yaml \
  --set-string frontend.image.tag=$TAG,backend.image.tag=$TAG,exporter.image.tag=$TAG,mcp.image.tag=$TAG \
  --set-string 'mcp.extraEnvs[1].value=http://penpot-rbt:8080' --wait --timeout 8m >/dev/null
kc logs deploy/$REL-backend | grep -a -E 'apply migration|welcome to penpot' | sed -E 's/.*(name="[^"]*"|version="[^"]*").*/\1/'
kc exec postgres-0 -- sh -c 'psql -U "$POSTGRES_USER" -d penpot -Atc "select count(*) from migrations; select to_regclass('"'"'http_session'"'"');"'

step "rollback (README procedure)"
kc scale deploy $REL-backend $REL-exporter $REL-mcp $REL-frontend --replicas=0
sleep 20
restore_db
helm -n "$NS" rollback "$REL" 1 --wait --timeout 8m
kc rollout status deploy/$REL-backend --timeout=300s

step "after rollback"
kc get deploy -o custom-columns=NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image,READY:.status.readyReplicas
kc logs deploy/$REL-backend | grep -a -E 'apply migration|welcome to penpot|E app' | sed -E 's/.*(name="[^"]*"|version="[^"]*").*/\1/' | head
kc exec postgres-0 -- sh -c 'psql -U "$POSTGRES_USER" -d penpot -Atc "select count(*) from migrations; select to_regclass('"'"'http_session'"'"'); select count(*) from file where deleted_at is null; select count(*) from profile where deleted_at is null;"'
kc exec deploy/$REL-backend -- sh -c 'find /opt/data/assets -type f | wc -l'
