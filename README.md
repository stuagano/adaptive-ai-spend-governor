# Adaptive AI Spend Governor for Databricks

## What this is

This repository is a Databricks-native control plane for governing AI and agent spend.
It combines:

- A mandatory OpenAI-compatible proxy that enforces immediate session USD/token limits.
- A burn-rate governor that forecasts month-end spend and adjusts Unity AI Gateway
  QPM/TPM limits.
- Policy-as-code for account budgets, endpoint rate limits, session budgets, and
  managed Omnigent cost policies.
- Lakebase for transactional session, reservation, governor, idempotency, and audit state.
- A Databricks App for the proxy and control-plane APIs.
- A scheduled Lakeflow Job for authoritative billing reconciliation.

It does not replace Unity AI Gateway. It adds immediate runtime enforcement and adaptive
controls around the Gateway while keeping Databricks system tables as the authoritative
source for reconciled spend.

## Why this exists

AI spend controls operate at different speeds:

- Account budgets and billing tables provide authoritative visibility, but billing data
  arrives too late to stop a single runaway agent session.
- Static QPM/TPM limits constrain capacity, but do not react to whether the organization
  is ahead of or behind its monthly budget.
- Omnigent can interrupt managed agent sessions, but it does not govern every application
  or replace account-wide platform controls.
- Provider fallback improves availability after `429`/`5xx` responses, but is not
  proactive cost routing.

This project closes those gaps with two coordinated loops:

1. **Immediate loop:** reserve estimated cost in Lakebase before a model request, reject
   requests that exceed the session cap, and reconcile the reservation with actual usage.
2. **Adaptive loop:** query Databricks billing and AI Gateway telemetry, forecast
   month-end spend, and progressively tighten or restore QPM/TPM using deterministic
   thresholds, hysteresis, and cooldowns.

The result is one centrally operated path for Omnigent and non-Omnigent teams without
requiring every team to adopt the same agent framework.

## What a request looks like

```text
Application or Omnigent agent
        |
        | Databricks OAuth + signed gateway-session header
        v
Databricks App: mandatory session-budget proxy
        |
        | App service-principal OAuth + request tags
        v
Unity AI Gateway model service
        |
        v
Model destination

Lakeflow Job -> system billing/AI Gateway tables -> forecast -> adaptive QPM/TPM
                          |
                          v
                       Lakebase audit
```

All production clients use the App URL. Omnigent teams additionally receive its built-in
ASK/DENY policies. Non-Omnigent clients still receive session enforcement, centralized
budgets, attribution, and adaptive rate limits.

## Who operates what

**Central platform team**

- Deploys the App, Lakeflow Job, Lakebase resources, and optional forecast endpoint.
- Owns account budgets, session policies, QPM/TPM baselines, and governor thresholds.
- Grants teams access to the App and removes their direct access to the governed model
  service.
- Reviews governor decisions and audit records.

**Application teams**

- Create a budgeted session through the App.
- Send OpenAI-compatible requests using the returned signed session token.
- Include approved metadata such as `project`, `team`, and `environment`.
- Do not need account-admin credentials or direct model-service access.

## Repository map

| Path | What it explains or implements |
|---|---|
| `deployment/gateway-policy.yaml` | Runtime policy: session cap, models, governor stages, QPM/TPM |
| `deployment/account-policy.yaml` | Centrally managed account/workspace AI Gateway budgets |
| `src/gateway_policy/control_plane.py` | Assembles the App, governor, Lakebase, and mandatory proxy |
| `src/gateway_policy/proxy/` | Session lifecycle, signed tokens, request enforcement, and routing |
| `src/gateway_policy/governor/` | Forecasting, telemetry, adaptive decisions, and persistence |
| `src/gateway_policy/jobs.py` | Scheduled reconciliation entry point |
| `src/gateway_policy/models.py` | Complete policy schema and validation |
| `databricks.yml`, `resources/`, `app.yaml` | Deployable Databricks bundle resources |
| `tests/` | Governor, proxy, policy, CLI, and end-to-end behavior |

## Use it locally

### 1. Install

```bash
git clone https://github.com/stuagano/adaptive-ai-spend-governor.git
cd adaptive-ai-spend-governor
python -m pip install -e ".[dev]"
```

### 2. Authenticate

```bash
databricks auth login --account-id <account-id>
databricks auth login --host https://<workspace-host>
```

OAuth is recommended. Never place Databricks tokens or session-signing secrets in policy
files.

### 3. Validate and inspect the example

```bash
gateway-policy validate gateway-policy.example.yaml
gateway-policy show gateway-policy.example.yaml --json
gateway-policy plan gateway-policy.example.yaml --offline
```

### 4. Test the governor without changing Databricks

```bash
gateway-policy governor status gateway-policy.example.yaml \
  --name ml-platform-monthly-burn --offline --json

gateway-policy governor evaluate gateway-policy.example.yaml \
  --name ml-platform-monthly-burn --offline --json
```

### 5. Preview or apply platform policy

```bash
gateway-policy plan gateway-policy.example.yaml --json
gateway-policy apply gateway-policy.example.yaml --yes
```

`plan` is read-only. `apply` requires live credentials and explicit confirmation.
For a production deployment, continue with [Databricks-native deployment](#databricks-native-deployment).

Background and product comparison are documented in
[`AI-GATEWAY-COST-PRIOR-ART.md`](AI-GATEWAY-COST-PRIOR-ART.md).

## Policy model

Policies are YAML bundles (`apiVersion: gateway-policy.databricks.com/v1`).

| Section | Purpose |
|---|---|
| `spec.account` | Account ID + Databricks CLI profile |
| `spec.workspaces` | Named workspaces for rate-limit targets |
| `spec.budgets` | Unity AI Gateway / Genie budget definitions |
| `spec.rateLimits` | Endpoint AI Gateway rate limits |

Ownership is stamped on managed resources via tags:

- `managed_by: gateway-policy`
- `gateway_policy_bundle: <bundle metadata.name>`
- `policy_name: <budget policy name>`

**Validation guardrails** (fail fast):

- `blockUsage` and `perUserOverrides` only for `resourceType: genie`
- Genie budgets require `tags: { databricks-product: genie }` only
- Max 4 shared thresholds and 20 per-user overrides per budget

## Commands

| Command | Description |
|---|---|
| `validate` | Schema + semantic validation only |
| `show` | Normalized policy JSON |
| `plan` | Create/update/delete/no-op diff vs live APIs |
| `apply` | Reconcile remote state (`--yes` required) |

Common flags:

- `--json` — machine-readable output for CI/Terraform `external` data sources
- `--offline` — skip Databricks API calls
- `--prune` — include deletes for managed resources removed from policy
- `--profile` — override account profile from policy file

## Safety model

- `plan` is read-only.
- `apply` refuses to mutate without `--yes`.
- Deletes require `--prune` and only touch resources owned by the bundle (`managed_by` + `gateway_policy_bundle` tags).
- Rate-limit updates preserve unrelated AI Gateway settings (guardrails, inference tables, usage tracking) via read-merge-write.

## API mapping

| Policy field | Databricks API |
|---|---|
| Budgets | `POST/PATCH/DELETE /api/2.1/accounts/{account_id}/budgets` |
| Rate limits | `PUT /api/2.0/serving-endpoints/{name}/ai-gateway` |

Budget list-price USD thresholds map to `alert_configurations` with `EMAIL_NOTIFICATION` actions. Per-user thresholds set `scope: PER_USER`. Genie `blockUsage` maps to `block_usage` when supported by the account API.

## CI example

```bash
gateway-policy validate policies/prod.yaml
gateway-policy plan policies/prod.yaml --json > plan.json
test "$(jq '.summary.create + .summary.update + .summary.delete' plan.json)" -eq 0
```

## Adaptive burn-rate governor and session budgets

The toolkit adds two coordinated controls on top of budgets and rate limits:

1. **Burn-rate governor** — polls Databricks SQL telemetry (`system.billing.usage`, `system.ai_gateway.usage`, `system.ai_gateway.external_model_spend`), forecasts month-end spend, and progressively tightens declared QPM/TPM baselines through staged actions.
2. **Session-budget proxy** — OpenAI-compatible FastAPI proxy that enforces immediate per-session USD/token caps before delayed billing telemetry arrives.

```bash
# Governor status (offline fake telemetry for local dev)
gateway-policy governor status gateway-policy.example.yaml \
  --name ml-platform-monthly-burn --offline --json

# One-shot evaluation (read-only)
gateway-policy governor evaluate gateway-policy.example.yaml \
  --name ml-platform-monthly-burn --offline --json

# Apply selected stage to serving endpoint rate limits
gateway-policy governor evaluate gateway-policy.example.yaml \
  --name ml-platform-monthly-burn --apply

# Polling daemon
gateway-policy governor run gateway-policy.example.yaml --apply

# Session lifecycle
gateway-policy session create gateway-policy.example.yaml \
  --policy-name agent-sandbox-session --identity agent-runtime@example.com --json

gateway-policy proxy run gateway-policy.example.yaml \
  --policy-name agent-sandbox-session --port 8080
```

### Policy sections

| Section | Purpose |
|---|---|
| `spec.governors` | Monthly target, SQL warehouse, staged QPM/TPM multipliers, proxy block stage |
| `spec.sessionBudgets` | Per-session USD/token caps, upstream route, model price catalog |
| `spec.omnigent` | Managed Omnigent built-in session and user-daily cost policies |

Render a configuration that is accepted by managed Omnigent:

```bash
gateway-policy omnigent render gateway-policy.example.yaml \
  --output omnigent-policies.yaml
```

The renderer deliberately emits only:

- `omnigent.policies.builtins.cost.cost_budget`
- `omnigent.policies.builtins.cost.user_daily_cost_budget`

It does not accept arbitrary Python policy handlers.

### Operating modes

- **Estimated real-time session cost** — proxy reservations use configured model prices and upstream usage payloads.
- **Authoritative delayed billing cost** — governor telemetry uses billing tables plus lag-aware token estimates.

Stale governor telemetry defaults to **no autonomous tightening** and emits unhealthy status. The session proxy can be configured `fail_closed` (default) or `fail_open`.

### Container runtime

```bash
docker compose -f docker-compose.example.yaml up proxy governor
```

Persistent SQLite state is mounted at `/data/state.db`. Set `GATEWAY_POLICY_SESSION_SECRET` in production.

## Databricks-native deployment

The production path separates enforcement by latency:

1. Managed Omnigent interrupts a session at deterministic ASK and DENY thresholds.
2. Unity AI Gateway budgets provide account and workspace visibility.
3. A scheduled Lakeflow Job reconciles system-table USD telemetry and applies adaptive QPM/TPM.
4. Lakebase stores governor state, session budgets, reservations, idempotency records, and the decision audit transactionally.
5. A Databricks App exposes the control plane and the mandatory OpenAI-compatible proxy.
6. An optional Model Serving endpoint supplies an advisory forecast. The deterministic EWMA forecast remains the fallback and the final stage evaluator remains deterministic.

The deployment policy is `deployment/gateway-policy.yaml`. It uses runtime environment substitution for Databricks resource names injected by the App or passed by the Job.

Apply account-level AI Gateway budgets separately using account-admin credentials:

```bash
export DATABRICKS_ACCOUNT_ID=<account-id>
export DATABRICKS_WORKSPACE_ID=<numeric-workspace-id>
export DATABRICKS_HOST=https://<workspace-host>

gateway-policy plan deployment/account-policy.yaml --profile account
gateway-policy apply deployment/account-policy.yaml --profile account --yes
```

Keeping account budgets separate prevents the App service principal from requiring
account-admin credentials.

### Bundle validation

```bash
python -m build
databricks bundle validate --strict -t dev \
  --var warehouse_id=<warehouse-id> \
  --var governed_endpoint_name=<ai-gateway-endpoint> \
  --var forecast_endpoint_name=<forecast-endpoint> \
  --var lakebase_branch=projects/<project>/branches/<branch> \
  --var lakebase_database=projects/<project>/branches/<branch>/databases/<database> \
  --var lakebase_endpoint=projects/<project>/branches/<branch>/endpoints/<endpoint> \
  --var run_as_service_principal_name=<application-id> \
  --var session_secret_scope=<secret-scope> \
  --var session_secret_key=<secret-key>
```

Deploying is intentionally separate from validation and requires operator confirmation:

```bash
databricks apps deploy -t dev --profile DEFAULT
```

The reconciliation schedule is deployed paused. Before unpausing it, grant the run-as service principal:

- `CAN_USE` on the SQL warehouse
- `CAN_MANAGE` on the governed serving endpoint
- `CAN_QUERY` on the forecast endpoint
- Lakebase connection and schema-creation privileges

### Team request path

All production model traffic goes through the App's `/api` routes rather than directly
to the governed endpoint. Databricks App authentication continues to use the standard
`Authorization: Bearer <Databricks OAuth token>` header. The separate signed budget
token is sent as `X-Gateway-Session-Token`.

1. Create a session with `POST /api/sessions`. The App derives the identity from
   Databricks' trusted `X-Forwarded-Email` or `X-Forwarded-User` header; a caller cannot
   select another identity in the JSON body.
2. Keep the returned `gpst_...` token for the lifetime of that session.
3. Call `/api/v1/chat/completions`, `/api/v1/responses`, or `/api/v1/embeddings` with
   both the Databricks OAuth header and `X-Gateway-Session-Token`.

Example using the OpenAI Python client:

```python
import os

import requests
from databricks.sdk import WorkspaceClient
from openai import OpenAI

app_url = os.environ["GATEWAY_APP_URL"].rstrip("/")
app_auth = WorkspaceClient().config.authenticate()

session = requests.post(
    f"{app_url}/api/sessions",
    headers=app_auth,
    json={"policy_name": "central-session", "project": "my-project"},
    timeout=30,
).json()

client = OpenAI(
    api_key=app_auth["Authorization"].removeprefix("Bearer "),
    base_url=f"{app_url}/api/v1",
    default_headers={"X-Gateway-Session-Token": session["session_token"]},
)

response = client.chat.completions.create(
    model="governed-model",  # The proxy replaces this with the approved policy endpoint.
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```

Unsigned `X-Session-Id` values, missing gateway-session tokens, and invalid or expired
tokens are rejected.
The App authenticates to the governed endpoint with its own refreshed OAuth
service-principal credentials. Omnigent teams use the same proxy path and additionally
receive Omnigent's built-in ASK/DENY policy behavior.

To make this path mandatory, remove direct `CAN_QUERY`/`EXECUTE` grants on the governed
model service from application-team principals. Grant teams `CAN_USE` on the App and
grant only the App service principal query access to the governed model service.

### Forecast endpoint contract

The optional endpoint receives one dataframe record:

```json
{
  "month_to_date_usd": 19000,
  "recent_window_usd": 1000,
  "daily_burn_rates": [900, 950, 1000],
  "monthly_target_usd": 25000,
  "horizon_days": 30
}
```

It returns a prediction object containing `projected_month_end_usd`, `daily_velocity_usd`, and optional `confidence`. Endpoint failure never causes autonomous tightening; the governor falls back to its deterministic forecast.

### Fallback routing is not cost routing

`fallbackEnabled` controls Unity AI Gateway availability fallback. It retries another configured destination only after a destination returns a supported error such as `429` or `5xx`. It does not proactively switch to a cheaper model when a spend threshold is crossed. Cost reduction comes from Omnigent expensive-model policy decisions, explicit model-service traffic policy, or adaptive QPM/TPM.

### Optional Zerobus event path

Install `.[zerobus]` and use `ZerobusUsageEventSink` for ACKed JSON ingestion when sub-minute event visibility is required. This is optional because Zerobus requires a pre-created Unity Catalog managed Delta table, a regional Zerobus endpoint, and explicit `SELECT` and `MODIFY` grants for the producer service principal. System tables remain the authoritative reconciliation source.

### Threat model notes

- Governor never mutates budgets or unrelated AI Gateway settings; only managed rate limits change via read-merge-write.
- Baseline limits are captured before the first throttle and restored after cooldown + sustained recovery.
- Session tokens are HMAC-signed opaque values (`gpst_...`) containing only session ID and expiry.

## Limitations

- General Unity AI Gateway budgets: alerts only (hard block is Genie-only in current Databricks docs).
- Budgets track PAYGO + `ai_query`; not provisioned throughput or external-model inference.
- Budgets API is Public Preview; some console fields (multi-threshold nuances) may differ from API payloads.
- Workspace IDs are inferred from `host` (`adb-<workspaceId>...`) or numeric workspace names.

## Staged rollout

1. `validate` + offline `plan` in CI
2. Live `plan` in staging account
3. `apply --yes` for budgets first
4. `apply --yes` for rate limits per workspace
5. Enable `--prune` only after bundle ownership tags are confirmed in account console
