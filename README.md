# Gateway Policy-as-Code Toolkit

Declarative policy management for **Databricks Unity AI Gateway** spend controls:

- Account **budgets** (shared + per-user thresholds, Genie hard caps)
- Serving endpoint **AI Gateway rate limits** (QPM/TPM by endpoint/user/group/service principal)

Inspired by prior art in [`AI-GATEWAY-COST-PRIOR-ART.md`](AI-GATEWAY-COST-PRIOR-ART.md).

## Install

```bash
cd "gateway api"
python -m pip install -e ".[dev]"
```

Authenticate with Databricks (OAuth recommended):

```bash
databricks auth login --account-id <account-id>
databricks auth login --host https://<workspace-host>
```

## Quick start

```bash
# Validate policy schema and semantics
gateway-policy validate gateway-policy.example.yaml

# Inspect normalized policy JSON
gateway-policy show gateway-policy.example.yaml --json

# Dry-run plan (offline)
gateway-policy plan gateway-policy.example.yaml --offline

# Live drift plan
gateway-policy plan gateway-policy.example.yaml --json

# Apply (requires explicit confirmation)
gateway-policy apply gateway-policy.example.yaml --yes
```

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

All production model traffic goes through the App URL rather than directly to the
governed endpoint:

1. Create a session with `POST /sessions`. In Databricks Apps, the proxy takes the
   authenticated identity from `X-Forwarded-Email`; a caller cannot select another
   identity in the JSON body.
2. Use the returned `gpst_...` token as `Authorization: Bearer gpst_...`.
3. Call `/v1/chat/completions`, `/v1/responses`, or `/v1/embeddings`.

Unsigned `X-Session-Id` values and requests without a valid session token are rejected.
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
