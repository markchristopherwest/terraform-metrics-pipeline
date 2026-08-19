# Churn & consumption playbook — reading the dashboards inside a customer's tenant

This is the interpretation layer for a post-sales / customer-success engineer who runs the stack against a
customer's Prisma Cloud tenant (read-only key). Two questions, two dashboards:

* **Are they consuming what they bought, and is it growing?** → *Consumption & Adoption*
* **Are they about to leave?** → *Churn Risk & Health*

Everything below maps to a metric (`docs/metrics.md`) and, where useful, to a line in the change feed.

## 1. Consumption — what to look at and what it means

| Panel / metric | Healthy | Watch | Why it matters |
|---|---|---|---|
| **Licence utilisation** `prisma_license_utilization_pct` (or `prisma_license_credits_utilization_pct`) | 60–95 % | < 50 %: under-consumption, > 100 %: true-up / expansion | Renewal is decided on perceived value per dollar. Sustained < 25 % is the single best churn predictor and triggers `license_utilization_low`. |
| **Usage by cloud type vs purchased** `prisma_license_usage_by_cloud_type` | stacked area approaching the dashed entitlement | a cloud type disappearing from the stack | A provider dropping to zero = workloads migrated away or account offboarded. |
| **Usage by resource type** `prisma_license_usage_by_resource_type` | mix matches the modules sold (VMs, containers, serverless, PaaS …) | a class flat at 0 | Modules they pay for but never onboarded (e.g. containers) are expansion or shelf-ware. |
| **Resources monitored** `prisma_inventory_total_resources`, by cloud type | growing with their estate | `prisma:inventory_total_resources:pct7d` < –10 % | Footprint shrinking under Prisma's eyes = coverage being pulled or accounts removed. |
| **Cloud accounts** `prisma_cloud_accounts_total / enabled / disabled`, by cloud type | growing, all enabled, status `ok` | `disabled` > 0, `by_status` with `warning/error`, `delta30d` < 0 | Disabled/removed accounts are deliberate acts — ask why. Status errors = onboarding credentials broke and nobody fixed them (nobody is looking). |
| **Policies enabled by module** `prisma_policies_enabled_by_type` | config + network + audit_event + anomaly + iam/data where licensed | a licensed module at 0 enabled policies | Module adoption. Cheap wins for the CSM: enable default policies, schedule a workshop. |
| **Customisation footprint** (custom policies, custom compliance standards, saved searches, scheduled reports, custom roles) | > 0 and creeping up | all zero months after go-live | A customer who never customises has not made the product part of a process; they churn quietly. |
| **Integrations** `prisma_integrations_by_type`, `_valid/_invalid`, **alert rules** `prisma_alert_rules_enabled` | ≥ 1 valid integration, ≥ 1 enabled rule | `invalid` > 0, rules disabled | This is how findings reach humans. Broken = the product went silent from the customer's point of view. |
| **Engagement** `prisma_users_human_active_7d/30d/90d`, `prisma_users_by_login_bucket`, `prisma_activity_*` | several humans active weekly; audit events > 0 daily | only service accounts active; `never` bucket dominating | Logins are the heartbeat. Service accounts only = automation keeps running after people stopped caring (last stage before cancellation). |

Per-account view (`Cloud accounts` table, `prisma_cloud_account_*`): resources and licence workloads per account tell
you **where** consumption sits — useful for expansion (large un-onboarded org children: `child_accounts`) and for
right-sizing.

## 2. Churn risk — the composite scores

**Snapshot risk** (`prisma_scores_risk_score`, Terraform, weights in `terraform/variables.tf → risk_weights`):

| flag (`scores.risk_flags`) | default points | trigger |
|---|---|---|
| `no_human_login_30d` | 30 | no USER_ACCOUNT logged in for 30 d |
| `single_active_user_30d` | 15 | exactly one human active in 30 d (bus factor) |
| `accounts_disabled` | 10 | ≥ 1 onboarded account disabled |
| `integrations_broken` | 10 | any integration invalid, or none valid |
| `no_alert_rules` | 15 | zero enabled alert rules |
| `alerts_open_no_activity` | 10 | open alerts, none resolved or dismissed in 7 d |
| `license_utilization_low` | 10 | utilisation < 25 % |

**Trend risk** (`prisma:churn_risk_trend_score`, Prometheus rules — needs history): accounts shrinking over 30 d (25),
resources –10 % in 7 d (20), licence usage –10 % in 7 d (15), no human login 14 d (25), active-user ratio < 25 % (15),
alert backlog growing with 0 resolved (10). `prisma:churn_risk_combined` = max of both.

Reading: **0–24 healthy · 25–49 watch · 50–74 act this week · 75+ escalate**. The *Risk flags over time* timeline shows
which signal fired when; the change feed gives the concrete event behind it.

## 3. The change feed — from "line moved" to "what happened"

`{job="prisma_reports", report="changes"}` (Loki) / `prisma_changes_total{entity,change}` (Prometheus):

| event | read as |
|---|---|
| `cloud_account removed` / `disabled` | offboarding — confirm intent (migration? consolidation? leaving?) |
| `cloud_account changed status ok → error` | onboarding credentials broke; if it stays for days nobody is watching |
| `integration broken` | alerts stopped flowing to Slack/Splunk/ServiceNow… silent product |
| `alert_rule disabled` | someone turned off notifications — alert fatigue |
| `user logged_in` after a long gap, `user added` | re-engagement / new stakeholder — good moment for a check-in |
| `user admin_granted` | new admin — new owner? |
| `custom_policy added`, `summary metric_changed saved_searches.saved` | adoption deepening |
| `risk_flag raised` / `cleared` | composite moved; the timeline panel shows it |

## 4. A weekly CSM routine with this stack

1. Open *Churn Risk & Health* for the tenant, 30-day range: risk scores, days since last human login, utilisation.
2. Scan the *Risk flags over time* timeline and the change feed for `removed / disabled / broken` events → ticket them.
3. Open *Consumption & Adoption*: usage vs purchased (renewal conversation), modules at zero (enablement),
   customisation trend (stickiness), active users (who to talk to — the *Humans not seen for 30+ days* table).
4. Note the top alert-generating policies — a tuning session that removes 60 % of the noise is the cheapest retention
   action there is.

## 5. Caveats

* Login data comes from `last_login_ts` on user profiles and the audit log; SSO-only tenants still record logins.
* Licence numbers are averages over `license_usage_days`; the console's *Settings → Licensing* is the source of truth.
* Multi-tenant keys: set `PRISMACLOUD_CUSTOMER_NAME`; one stack (one `tenant` label) per customer keeps the scoring honest.
* Heuristics are starting points — edit the weights to match the success plan agreed with the customer.
