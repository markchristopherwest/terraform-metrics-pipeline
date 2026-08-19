# prisma-cloud-telemetry

Terraform snapshots of a **Prisma Cloud** tenant (PaloAltoNetworks/prismacloud provider) written as JSON
into `./reports` every 5 minutes → Prometheus metrics + Loki log lines → Grafana dashboards that show
**consumption** (what the customer uses) and **churn risk** (whether they are about to stop using it).

```
 ┌──────────────────────────┐   every 300 s   ┌──────────────────────────────┐
 │ terraform-runner         │ ──────────────► │ ./reports/                   │
 │  terraform/ (prismacloud │  local_file     │   prisma_summary.json   (1 line, tenant totals)
 │  provider + REST calls)  │  re-creates     │   prisma_cloud_accounts.jsonl (1 line / account)
 │  or terraform-mock/      │  the files      │   prisma_users.jsonl, prisma_policies.jsonl,
 └──────────────────────────┘                 │   prisma_alert_rules.jsonl, prisma_integrations.jsonl
                                              │   derived/prisma_changes.jsonl (change feed)
                                              └───────┬──────────────────┬───────────────────┘
                     parse + diff (5 s) ┌─────────────┘                  └─────────────┐ tail (poll, new inode)
                          ┌─────────────▼──────────┐                 ┌─────────────────▼──────────┐
                          │ metrics_scraper.py     │                 │ Promtail 3.6.11 (or Alloy)  │
                          │ :9464/metrics          │                 │ json → labels/metadata      │
                          │ + writes change feed   │                 │ timestamp = "@timestamp"    │
                          └─────────────┬──────────┘                 └─────────────────┬──────────┘
                                        ▼                                              ▼
                                  Prometheus 3.x  ◄───── recording/alert rules         Loki 3.7
                                        └───────────────────┬──────────────────────────┘
                                                            ▼
                                   Grafana 13: Consumption & Adoption · Churn Risk & Health · Snapshot Explorer
```

## Quick start

```bash
cp .env.example .env            # PRISMACLOUD_URL / USERNAME (access key) / PASSWORD (secret) / TENANT_LABEL
docker compose up -d --build    # or: make up
open http://localhost:3000      # anonymous Viewer; admin/admin to edit
```

No tenant at hand? `make demo` (`TF_MODULE=terraform-mock`) runs the **same pipeline on synthetic data**
that drifts run-to-run (users log in, an account gets disabled, an integration breaks, usage wanders),
so every panel and the change feed light up within ~10 minutes.

Ports: Grafana 3000 · Prometheus 9090 · Loki 3100 · scraper 9464 · Promtail 9080 (Alloy 12345).

## What Terraform collects (read-only)

| Source | Data | Drives |
|---|---|---|
| `prismacloud_cloud_accounts`, `_account_groups` | onboarded accounts / groups | footprint |
| `prismacloud_user_profiles`, `_user_roles`, `_permission_groups` | users, `last_login_ts`, roles, admins | engagement |
| `prismacloud_policies` (full catalogue) | enabled/disabled, custom, by type/severity/cloud | adoption depth |
| `prismacloud_alert_rules`, `_integrations`, `_notification_templates` | wiring into the customer's workflow | adoption / hygiene |
| `prismacloud_alerts` ×5 windows (`limit = 1`, reads `total`) | opened 24h/7d, resolved/dismissed/snoozed 7d | alert hygiene |
| `prismacloud_compliance_standards`, `_reports`, `_rql_historic_searches`, `_resource_lists`, `_trusted_*_ips`, `_enterprise_settings` (+ optional collections, anomaly settings) | customisation footprint, settings | adoption |
| **REST via `hashicorp/http`** (optional, `api_enrichment = true`): `GET /cloud`, `GET /v3/inventory` (by cloud type + by account), `POST /license/api/v2/usage` + `/time_series`, `POST /license/api/v1/credit-allocation-rule-summary`, `POST /alert/v1/aggregate` (severity, policy type), `POST /alert/v1/policy` (top policies), `GET /audit/redlock` | account health, asset counts, **licence workloads / credits used vs purchased**, open alerts by severity, console activity | consumption, churn |

Nothing is ever created or modified in the tenant; `terraform destroy` only deletes the local files.
The provider has no licence/usage data source, which is why the REST calls exist — turn them off with
`API_ENRICHMENT=false` for a provider-only run (the summary sections become `null`).

Every run also computes two transparent heuristics (`terraform/variables.tf` → `adoption_weights`, `risk_weights`):
`scores.adoption_score` (0–100, what is wired in) and `scores.risk_score` + `risk_flags` (0–100, what is wrong right now).
Trend-based signals that need history live in `prometheus/rules/prisma_rules.yml` (`prisma:churn_risk_trend_score`).

Report schema: [`docs/report-schema.md`](docs/report-schema.md) · metric names: [`docs/metrics.md`](docs/metrics.md) ·
how to read the dashboards: [`docs/churn-consumption-playbook.md`](docs/churn-consumption-playbook.md).

## How the pieces fit

**Scheduler** (`scheduler/`): `hashicorp/terraform` image + `entrypoint.sh` loop: `terraform init` once, then
`terraform apply -auto-approve -parallelism=3` every `INTERVAL_SECONDS`, writes `reports/.runner/last_run.json`
(success/duration) for the scraper, maps `PRISMACLOUD_*` env to `TF_VAR_*`. Bare-metal alternatives:
`scheduler/systemd/` (timer) and `scheduler/crontab.example` — same script with `RUN_ONCE=true`.

**Why the same file can be "updated" and still tailed**: `local_file` replaces the file on every content change
(delete + create → new inode; the `"@timestamp"` changes each run, so every run rewrites every file). Promtail's
poll-based tailer notices the inode change, drains the old handle and reads the new file from byte 0; every line
ends in `\n` so only whole lines ship; `"@timestamp"` sorts first in `jsonencode()` output, which also satisfies
Alloy's 1 KiB "same file?" signature. The `timestamp` stage uses `"@timestamp"`, so all lines of one run share one
timestamp; positions are deliberately not persisted (a restart re-reads the current files once — same timestamp, same
content, so at worst a few exact-duplicate lines rather than the stale-offset bugs persisted positions cause with
re-created files).

**metrics_scraper.py** (`scraper/`, stdlib + `prometheus_client`): re-parses a file only when its SHA-256 changes,
rebuilds all metrics from the latest snapshot on every scrape (a custom Collector → vanished accounts/users simply
disappear, no stale series), diffs entity files + a curated set of summary fields against the previous snapshot and
appends one JSON line per change to `reports/derived/prisma_changes.jsonl` (`added/removed/enabled/disabled/broken/
recovered/logged_in/admin_granted/metric_changed/risk_flag raised|cleared`, plus a `baseline` line on first sight).
State is persisted (`derived/.scraper_state.json`) so a restart does not fake a flood of "added" events.
Endpoints `/metrics`, `/healthz`, `/state`. Tests: `make test`.

**Promtail / Alloy**: stream labels are only `job, source, report, tenant` (low cardinality); `entity, change,
cloud_type, severity, account_type, integration_type, policy_type` are **structured metadata** — filter with
`{report="changes"} | change="removed"` with no cardinality cost. Promtail is EOL (2026-03-02, last image 3.6.11);
`alloy/config.alloy` is the equivalent (`docker compose --profile alloy up -d`, then stop promtail).

**Prometheus**: scrapes the scraper every 30 s; `rules/prisma_rules.yml` adds deltas (`prisma:license_usage_total:pct7d`
…), ratios, the trend churn score and alert rules (`PrismaNoHumanLogin14d`, `PrismaAccountsShrinking`,
`PrismaLicenseUnderused`, `PrismaAlertBacklogStalling`, `PrismaSnapshotStale`, …).

**Grafana** (provisioned, folder *Prisma Cloud*, generated from `grafana/build_dashboards.py`):

* **Consumption & Adoption** — accounts/resources/licence workloads by cloud type, usage vs purchased, credits,
  policies by module, customisation footprint, integrations, engagement (active users, login buckets, audit activity),
  per-account table, top alert-generating policies.
* **Churn Risk & Health** — snapshot + trend risk scores, days since last human login, active-user ratio, utilisation,
  disabled accounts, invalid integrations, risk-flag timeline, alert hygiene, footprint health, 7-day % changes,
  Loki change feed, "humans not seen for 30+ days" table, playbook.
* **Snapshot Explorer (Loki)** — the same numbers charted straight from the JSON lines
  (`| json | unwrap cloud_accounts_total`), raw lines per report, compact views.

## Reading the dashboards post-sales (short version)

* **Consumption** = licence workloads / credits used vs purchased, resources by cloud, accounts onboarded, modules with
  enabled policies, integrations. Rising = expansion conversation; flat far below entitlement = renewal risk.
* **Churn precursors** (each is a flag in `scores.risk_flags` or a Prometheus rule): no human login for 14–30 d,
  ≤1 active user, accounts disabled/removed or shrinking over 30 d, licence utilisation < 25 %, open alerts with zero
  resolved/dismissed in 7 d, integrations invalid, no enabled alert rules, custom content stuck at zero.
* The **change feed** turns "the dashboard moved" into "account X was disabled on Tuesday" / "integration Y broke" /
  "user Z logged in for the first time in 60 days" — the lines you paste into the customer-success ticket.

Full playbook with thresholds and suggested actions: `docs/churn-consumption-playbook.md`.

## Configuration knobs

`.env` → compose; `terraform/variables.tf` for everything else (all have defaults):
`collect` (toggle data sources your key cannot read — *Account Group Read Only* keys cannot list users, integrations,
account details, enterprise settings), `api_enrichment`, `license_usage_days` (7) / `license_trend_days` (30),
`activity_window_hours` (24), `top_n`, `pseudonymize_users` (sha256 prefix instead of e-mails), `provider_max_retries`
/ `provider_retry_max_delay` (429 handling), `adoption_weights`, `risk_weights`.

Sizing: a 5-minute apply makes ~25 API calls per run (one per data source + the REST calls); `prismacloud_policies`
is the heaviest (whole catalogue). Keep `TF_PARALLELISM` at 3 or below — Prisma rate-limits per token.

## Security notes

* The API key is a **read-only inventory key**; a System Admin role is needed for the full picture
  (see `collect` above for read-only keys).
* Terraform state (`tf-state` volume, or `terraform.tfstate` on bare metal) contains the `data.http` request
  headers/bodies — i.e. the JWT and the secret key. Keep the volume private; it is never bind-mounted.
* Reports contain user e-mails (`prisma_users.jsonl`, audit top users) unless `PSEUDONYMIZE_USERS=true`.
* Grafana ships with anonymous Viewer access for convenience — set `GRAFANA_ANONYMOUS=false` and change the admin
  password before exposing it.

## Validate / test

```bash
make validate   # terraform validate (both modules), promtool, compose config, scraper unit tests,
                # dashboards in sync, promtail -check-syntax, loki -verify-config, alloy fmt
make test       # scraper unit tests only
make fixtures RUN=1 && make scrape   # exercise the scraper on fixture data without Terraform
```

## Layout

```
terraform/            real module: versions, providers, variables, data_provider.tf (provider data sources),
                      data_api.tf (hashicorp/http REST calls), locals_*.tf (shaping + scores), reports.tf (files)
terraform-mock/       same output schema from synthetic data (demo / CI)
scheduler/            Dockerfile, entrypoint.sh (5-min loop), systemd timer, crontab example
scraper/              metrics_scraper.py, Dockerfile, tests/ (unittest + fixture generator)
promtail/ alloy/      log shipping configs (Promtail = as requested; Alloy = its successor)
loki/ prometheus/     Loki 3.7 single-binary config; Prometheus config + recording/alert rules
grafana/              provisioning (datasources, dashboard provider), dashboards/*.json, build_dashboards.py
docs/                 report schema, metric catalogue, churn & consumption playbook
reports/              output directory (git-ignored)
```

## Troubleshooting

* `Prisma Cloud login failed (HTTP 401)` → wrong key/secret or wrong `PRISMACLOUD_URL` (console `app.X` → API `api.X`).
* Apply fails with 429 → raise `provider_max_retries`, lower `TF_PARALLELISM`, or disable heavy data sources.
* A section is `null` in `prisma_summary.json` → that REST call failed/was disabled; `run.api_status` has the HTTP codes.
* Dashboards empty → `curl localhost:9464/metrics | grep prisma_cloud_accounts_total`; `docker compose logs metrics-scraper`.
* Loki shows nothing → `docker compose logs promtail` (look for `/reports/...` targets); the `@timestamp` must be RFC 3339.
