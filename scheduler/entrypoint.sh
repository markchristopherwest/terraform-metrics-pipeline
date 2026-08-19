#!/usr/bin/env bash
# Apply the Terraform module at TF_DIR every INTERVAL_SECONDS, forever.
#
# Env (all optional unless noted):
#   PRISMACLOUD_URL / PRISMACLOUD_USERNAME / PRISMACLOUD_PASSWORD   (required for ../terraform)
#   PRISMACLOUD_CUSTOMER_NAME   multi-tenant keys only
#   TENANT_LABEL                label stamped on every report line
#   API_ENRICHMENT              true|false  (direct REST calls on top of the provider)
#   INTERVAL_SECONDS            default 300
#   TF_PARALLELISM              default 3 (keeps Prisma's 429s away)
#   RUN_ONCE                    true -> single apply, then exit (cron / systemd timer mode)
#   TF_DIR / REPORTS_DIR / STATE_DIR / TF_PLUGIN_CACHE_DIR
#   TF_EXTRA_ARGS               appended to `terraform apply`
set -uo pipefail

TF_DIR="${TF_DIR:-/terraform}"
REPORTS_DIR="${REPORTS_DIR:-/reports}"
STATE_DIR="${STATE_DIR:-/var/lib/prisma-reports}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-300}"
TF_PARALLELISM="${TF_PARALLELISM:-3}"
RUN_ONCE="${RUN_ONCE:-false}"
TF_EXTRA_ARGS="${TF_EXTRA_ARGS:-}"
RUNNER_STATUS_DIR="${REPORTS_DIR}/.runner"

export TF_IN_AUTOMATION=1 TF_INPUT=0
export TF_PLUGIN_CACHE_DIR="${TF_PLUGIN_CACHE_DIR:-/var/cache/terraform-plugins}"
# keep .terraform/ (provider symlinks, backend config) out of the bind-mounted module dir;
# only .terraform.lock.hcl is written next to the code
export TF_DATA_DIR="${TF_DATA_DIR:-${STATE_DIR}/.terraform}"

# --- map PRISMACLOUD_* / TENANT_LABEL onto Terraform variables -----------------
# (The provider reads PRISMACLOUD_* itself, but the hashicorp/http enrichment and
#  the report labels need them as variables too, so feed both paths.)
[[ -n "${PRISMACLOUD_URL:-}" ]]           && export TF_VAR_prismacloud_url="${PRISMACLOUD_URL#https://}"
[[ -n "${PRISMACLOUD_USERNAME:-}" ]]      && export TF_VAR_prismacloud_username="$PRISMACLOUD_USERNAME"
[[ -n "${PRISMACLOUD_PASSWORD:-}" ]]      && export TF_VAR_prismacloud_password="$PRISMACLOUD_PASSWORD"
[[ -n "${PRISMACLOUD_CUSTOMER_NAME:-}" ]] && export TF_VAR_prismacloud_customer_name="$PRISMACLOUD_CUSTOMER_NAME"
[[ -n "${TENANT_LABEL:-}" ]]              && export TF_VAR_tenant_label="$TENANT_LABEL"
[[ -n "${API_ENRICHMENT:-}" ]]            && export TF_VAR_api_enrichment="$API_ENRICHMENT"
[[ -n "${PSEUDONYMIZE_USERS:-}" ]]        && export TF_VAR_pseudonymize_users="$PSEUDONYMIZE_USERS"
export TF_VAR_reports_dir="$REPORTS_DIR"
export TF_VAR_interval_hint_seconds="$INTERVAL_SECONDS"

mkdir -p "$REPORTS_DIR" "$RUNNER_STATUS_DIR" "$STATE_DIR" "$TF_PLUGIN_CACHE_DIR" "$TF_DATA_DIR"
cd "$TF_DIR" || { echo "TF_DIR $TF_DIR not found"; exit 1; }

log() { printf '%s [runner] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# --- graceful stop ------------------------------------------------------------
STOP=0
trap 'STOP=1; log "signal received, finishing current run"' TERM INT

# --- init (retry: registry hiccups at container start are common) -------------
init_ok=0
for attempt in 1 2 3 4 5; do
  if terraform init -input=false -no-color -upgrade=false \
       -backend-config="path=${STATE_DIR}/terraform.tfstate" >/tmp/init.log 2>&1; then
    init_ok=1; break
  fi
  log "terraform init failed (attempt $attempt)"; tail -n 20 /tmp/init.log
  sleep $((attempt * 10))
done
[[ $init_ok -eq 1 ]] || { log "giving up on terraform init"; exit 1; }
log "terraform init ok (module: $(basename "$(pwd)"), interval: ${INTERVAL_SECONDS}s, parallelism: ${TF_PARALLELISM})"

# --- status file for the metrics scraper --------------------------------------
write_status() {  # $1 = success(1/0) $2 = duration $3 = exit code
  local ts; ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  local tmp="${RUNNER_STATUS_DIR}/last_run.json.tmp"
  printf '{"@timestamp":"%s","report":"runner","success":%s,"duration_seconds":%s,"exit_code":%s,"interval_seconds":%s,"module":"%s","runs_total":%s,"failures_total":%s}\n' \
    "$ts" "$1" "$2" "$3" "$INTERVAL_SECONDS" "$(basename "$(pwd)")" "$RUNS" "$FAILS" > "$tmp"
  mv -f "$tmp" "${RUNNER_STATUS_DIR}/last_run.json"
}

RUNS=0; FAILS=0
while :; do
  start=$(date +%s)
  RUNS=$((RUNS + 1))
  log "apply #${RUNS} starting"
  # shellcheck disable=SC2086
  terraform apply -auto-approve -input=false -no-color -compact-warnings \
      -parallelism="$TF_PARALLELISM" $TF_EXTRA_ARGS 2>&1 | grep -Ev '^[[:space:]]*$' | sed 's/^/[terraform] /'
  rc=${PIPESTATUS[0]}
  end=$(date +%s); dur=$((end - start))
  if [[ "$rc" -eq 0 ]]; then
    log "apply #${RUNS} ok in ${dur}s"
    write_status 1 "$dur" 0
  else
    FAILS=$((FAILS + 1))
    log "apply #${RUNS} FAILED (rc=$rc) after ${dur}s"
    write_status 0 "$dur" "$rc"
  fi

  [[ "$RUN_ONCE" == "true" ]] && exit "$rc"
  [[ $STOP -eq 1 ]] && exit 0

  sleep_for=$((INTERVAL_SECONDS - dur))
  [[ $sleep_for -lt 5 ]] && sleep_for=5
  log "next run in ${sleep_for}s"
  # sleep in small steps so SIGTERM is honoured quickly
  while [[ $sleep_for -gt 0 && $STOP -eq 0 ]]; do
    s=$(( sleep_for < 5 ? sleep_for : 5 )); sleep "$s"; sleep_for=$((sleep_for - s))
  done
  [[ $STOP -eq 1 ]] && exit 0
done
