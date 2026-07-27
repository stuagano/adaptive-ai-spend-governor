from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import click
import uvicorn
from rich.console import Console
from rich.table import Table

from gateway_policy.clients import build_client_bundle
from gateway_policy.config import PolicyConfigError, load_policy_file, policy_to_dict
from gateway_policy.governor import SpendSnapshot
from gateway_policy.governor.engine import GovernorEngine
from gateway_policy.governor.predictor import (
    DeterministicForecastProvider,
    ForecastProvider,
    ModelServingForecastProvider,
)
from gateway_policy.governor.telemetry import (
    FakeTelemetryProvider,
    SqlTelemetryConfig,
    SqlTelemetryProvider,
    TelemetryProvider,
)
from gateway_policy.omnigent import render_managed_omnigent_yaml
from gateway_policy.planner import Applier, Planner
from gateway_policy.proxy.app import create_app
from gateway_policy.proxy.session import SessionManager
from gateway_policy.runtime import (
    build_runtime_clients,
    load_runtime_bundle,
    open_governor_state_store,
    open_state_store,
    session_policy_map,
)

console = Console()
DEFAULT_STATE_PATH = Path(".gateway-policy/state.db")
DEFAULT_SESSION_SECRET = "dev-only-change-me"


@click.group()
@click.version_option(package_name="gateway-policy")
def main() -> None:
    """Declarative policy management for Unity AI Gateway budgets and rate limits."""


@main.group("governor")
def governor_group() -> None:
    """Adaptive burn-rate governor commands."""


@governor_group.command("status")
@click.argument("policy_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--name", "governor_name", required=True, help="Governor policy name.")
@click.option("--state-path", type=click.Path(path_type=Path), default=DEFAULT_STATE_PATH)
@click.option("--offline", is_flag=True, help="Use fake telemetry snapshot.")
@click.option("--json", "as_json", is_flag=True)
@click.option("--profile", default=None)
def governor_status_cmd(
    policy_file: Path,
    governor_name: str,
    state_path: Path,
    offline: bool,
    as_json: bool,
    profile: str | None,
) -> None:
    engine = _build_governor_engine(policy_file, state_path, offline, profile)
    payload = engine.status(governor_name)
    _emit(payload, as_json)


@governor_group.command("evaluate")
@click.argument("policy_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--name", "governor_name", default=None, help="Evaluate one governor.")
@click.option("--apply", "apply_changes", is_flag=True, help="Apply selected stage to rate limits.")
@click.option("--state-path", type=click.Path(path_type=Path), default=DEFAULT_STATE_PATH)
@click.option("--offline", is_flag=True, help="Use fake telemetry snapshot.")
@click.option("--json", "as_json", is_flag=True)
@click.option("--profile", default=None)
def governor_evaluate_cmd(
    policy_file: Path,
    governor_name: str | None,
    apply_changes: bool,
    state_path: Path,
    offline: bool,
    as_json: bool,
    profile: str | None,
) -> None:
    if offline and apply_changes:
        raise click.ClickException("--offline cannot be combined with --apply")
    engine = _build_governor_engine(policy_file, state_path, offline, profile)
    if governor_name:
        results = [engine.evaluate(governor_name, apply=apply_changes)]
    else:
        results = engine.run_once(apply=apply_changes)
    payload = [result.__dict__ for result in results]
    _emit(payload if governor_name is None else payload[0], as_json)


@governor_group.command("run")
@click.argument("policy_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--apply", "apply_changes", is_flag=True, help="Apply stage changes while polling.")
@click.option("--state-path", type=click.Path(path_type=Path), default=DEFAULT_STATE_PATH)
@click.option("--offline", is_flag=True, help="Use fake telemetry snapshot.")
@click.option("--profile", default=None)
def governor_run_cmd(
    policy_file: Path,
    apply_changes: bool,
    state_path: Path,
    offline: bool,
    profile: str | None,
) -> None:
    if offline and apply_changes:
        raise click.ClickException("--offline cannot be combined with --apply")
    engine = _build_governor_engine(policy_file, state_path, offline, profile)
    engine.run_daemon(apply=apply_changes)


@main.group("omnigent")
def omnigent_group() -> None:
    """Managed Omnigent built-in policy configuration."""


@omnigent_group.command("render")
@click.argument("policy_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--output", type=click.Path(path_type=Path), default=None)
def omnigent_render_cmd(policy_file: Path, output: Path | None) -> None:
    bundle = load_policy_file(policy_file)
    if bundle.spec.omnigent is None:
        raise click.ClickException("policy bundle does not define spec.omnigent")
    rendered = render_managed_omnigent_yaml(bundle.spec.omnigent)
    if output is None:
        click.echo(rendered, nl=False)
        return
    output.write_text(rendered, encoding="utf-8")
    click.echo(f"Wrote managed Omnigent policy to {output}")


@main.group("session")
def session_group() -> None:
    """Session budget lifecycle commands."""


@session_group.command("create")
@click.argument("policy_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--policy-name", required=True)
@click.option("--identity", required=True)
@click.option("--project", default=None)
@click.option("--state-path", type=click.Path(path_type=Path), default=DEFAULT_STATE_PATH)
@click.option("--session-secret", default=DEFAULT_SESSION_SECRET)
@click.option("--json", "as_json", is_flag=True)
def session_create_cmd(
    policy_file: Path,
    policy_name: str,
    identity: str,
    project: str | None,
    state_path: Path,
    session_secret: str,
    as_json: bool,
) -> None:
    manager = _build_session_manager(policy_file, state_path, session_secret)
    session = manager.create_session(policy_name, identity, project)
    payload = manager.remaining_budget(session.session_id)
    payload["session_token"] = manager.issue_token(session.session_id)
    _emit(payload, as_json)


@session_group.command("show")
@click.argument("policy_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--session-id", required=True)
@click.option("--state-path", type=click.Path(path_type=Path), default=DEFAULT_STATE_PATH)
@click.option("--session-secret", default=DEFAULT_SESSION_SECRET)
@click.option("--json", "as_json", is_flag=True)
def session_show_cmd(
    policy_file: Path,
    session_id: str,
    state_path: Path,
    session_secret: str,
    as_json: bool,
) -> None:
    manager = _build_session_manager(policy_file, state_path, session_secret)
    _emit(manager.remaining_budget(session_id), as_json)


@session_group.command("close")
@click.argument("policy_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--session-id", required=True)
@click.option("--state-path", type=click.Path(path_type=Path), default=DEFAULT_STATE_PATH)
@click.option("--session-secret", default=DEFAULT_SESSION_SECRET)
@click.option("--json", "as_json", is_flag=True)
def session_close_cmd(
    policy_file: Path,
    session_id: str,
    state_path: Path,
    session_secret: str,
    as_json: bool,
) -> None:
    manager = _build_session_manager(policy_file, state_path, session_secret)
    manager.close_session(session_id)
    _emit({"status": "closed", "session_id": session_id}, as_json)


@main.group("proxy")
def proxy_group() -> None:
    """Session budget proxy commands."""


@proxy_group.command("run")
@click.argument("policy_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--policy-name", required=True, help="Session budget policy name.")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8080, show_default=True)
@click.option("--state-path", type=click.Path(path_type=Path), default=DEFAULT_STATE_PATH)
@click.option("--session-secret", default=None)
def proxy_run_cmd(
    policy_file: Path,
    policy_name: str,
    host: str,
    port: int,
    state_path: Path,
    session_secret: str | None,
) -> None:
    bundle = load_policy_file(policy_file)
    policy = next(
        (item for item in bundle.spec.session_budgets if item.name == policy_name),
        None,
    )
    if policy is None:
        raise click.ClickException(f"unknown session budget policy: {policy_name}")

    secret = session_secret or os.environ.get(
        "GATEWAY_POLICY_SESSION_SECRET",
        DEFAULT_SESSION_SECRET,
    )
    store = open_state_store(state_path)
    manager = _build_session_manager(policy_file, state_path, secret)
    app = create_app(
        session_manager=manager,
        store=store,
        upstream_headers={},
        default_upstream_base_url=policy.upstream_base_url,
        session_policies={policy.name: policy},
        session_token_secret=secret,
    )
    uvicorn.run(app, host=host, port=port)


@main.command("validate")
@click.argument("policy_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Emit validation result as JSON.")
def validate_cmd(policy_file: Path, as_json: bool) -> None:
    """Validate a policy YAML file."""
    try:
        bundle = load_policy_file(policy_file)
    except PolicyConfigError as exc:
        _fail(str(exc), as_json=as_json)

    result = {
        "valid": True,
        "bundle": bundle.metadata.name,
        "budgets": len(bundle.spec.budgets),
        "rate_limits": len(bundle.spec.rate_limits),
        "governors": len(bundle.spec.governors),
        "session_budgets": len(bundle.spec.session_budgets),
        "omnigent": int(bundle.spec.omnigent is not None),
    }
    if as_json:
        click.echo(json.dumps(result, indent=2))
        return
    console.print(f"[green]Valid[/green] policy bundle [bold]{bundle.metadata.name}[/bold]")
    console.print(
        "Budgets: {budgets} | Rate limits: {rate_limits} | Governors: {governors} | "
        "Session budgets: {session_budgets} | Omnigent: {omnigent}".format(**result)
    )


@main.command("plan")
@click.argument("policy_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Emit plan as JSON.")
@click.option("--offline", is_flag=True, help="Plan without calling Databricks APIs.")
@click.option("--prune", is_flag=True, help="Include delete actions for managed drift.")
@click.option("--profile", default=None, help="Override account profile from policy file.")
def plan_cmd(
    policy_file: Path,
    as_json: bool,
    offline: bool,
    prune: bool,
    profile: str | None,
) -> None:
    """Compute create/update/delete actions for the policy file."""
    bundle, clients = _load_bundle_and_clients(policy_file, offline=offline, profile=profile)
    planner = Planner(
        bundle,
        budget_client=clients["budget_client"] if clients else None,
        rate_limit_clients=clients["rate_limit_clients"] if clients else None,
    )
    plan = planner.plan(prune=prune)
    if as_json:
        click.echo(plan.model_dump_json(indent=2))
        return
    _render_plan(plan.model_dump(mode="json"))


@main.command("apply")
@click.argument("policy_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--yes", is_flag=True, help="Apply changes without interactive confirmation.")
@click.option("--json", "as_json", is_flag=True, help="Emit apply results as JSON.")
@click.option("--offline", is_flag=True, help="Validate and plan only; never mutate remote state.")
@click.option("--prune", is_flag=True, help="Delete managed resources removed from policy.")
@click.option("--profile", default=None, help="Override account profile from policy file.")
def apply_cmd(
    policy_file: Path,
    as_json: bool,
    yes: bool,
    offline: bool,
    prune: bool,
    profile: str | None,
) -> None:
    """Apply policy changes to Databricks."""
    bundle, clients = _load_bundle_and_clients(policy_file, offline=offline, profile=profile)
    if clients is None:
        _fail("apply requires live Databricks credentials; remove --offline", as_json=as_json)
        raise AssertionError("unreachable")

    planner = Planner(
        bundle,
        budget_client=clients["budget_client"],
        rate_limit_clients=clients["rate_limit_clients"],
    )
    plan = planner.plan(prune=prune)

    if not yes:
        if as_json:
            click.echo(
                json.dumps(
                    {
                        "applied": False,
                        "reason": "confirmation_required",
                        "plan": plan.model_dump(mode="json"),
                    },
                    indent=2,
                )
            )
        else:
            console.print("[yellow]Refusing to apply without --yes[/yellow]")
            _render_plan(plan.model_dump(mode="json"))
        raise SystemExit(1)

    applier = Applier(
        bundle,
        budget_client=clients["budget_client"],
        rate_limit_clients=clients["rate_limit_clients"],
    )
    results = applier.apply(plan)
    payload = {"applied": True, "results": results, "summary": plan.summary}
    if as_json:
        click.echo(json.dumps(payload, indent=2))
        return
    console.print("[green]Apply complete[/green]")
    for result in results:
        console.print(f"- {result['resource']}: {result['status']}")


@main.command("show")
@click.argument("policy_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Emit normalized policy as JSON.")
def show_cmd(policy_file: Path, as_json: bool) -> None:
    """Print the normalized policy bundle."""
    bundle = load_policy_file(policy_file)
    payload = policy_to_dict(bundle)
    if as_json:
        click.echo(json.dumps(payload, indent=2))
        return
    click.echo(json.dumps(payload, indent=2))


def _build_governor_engine(
    policy_file: Path,
    state_path: Path,
    offline: bool,
    profile: str | None,
) -> GovernorEngine:
    bundle = load_runtime_bundle(policy_file)
    store = open_governor_state_store(state_path)
    telemetry: TelemetryProvider | dict[str, TelemetryProvider]
    forecast_provider: ForecastProvider | dict[str, ForecastProvider]
    rate_limit_clients: dict[str, Any]
    if offline:
        telemetry = FakeTelemetryProvider(
            SpendSnapshot(
                month_to_date_usd=Decimal("18000"),
                recent_window_usd=Decimal("500"),
                billing_closed_through=datetime.now(tz=UTC),
                telemetry_fresh_through=datetime.now(tz=UTC),
                daily_burn_rates=[Decimal("800"), Decimal("900"), Decimal("850")],
                is_stale=False,
            )
        )
        rate_limit_clients = {}
        forecast_provider = DeterministicForecastProvider()
    else:
        clients = build_runtime_clients(bundle, profile=profile)
        rate_limit_clients = clients.rate_limits
        rate_policy_lookup = {policy.name: policy for policy in bundle.spec.rate_limits}
        telemetry_by_governor: dict[str, TelemetryProvider] = {}
        forecast_by_governor: dict[str, ForecastProvider] = {}
        for governor in bundle.spec.governors:
            workspace = clients.workspaces[governor.workspace]
            rate_policy = rate_policy_lookup[governor.rate_limit_policy]
            telemetry_by_governor[governor.name] = SqlTelemetryProvider(
                workspace,
                SqlTelemetryConfig(
                    warehouse_id=governor.sql_warehouse_id,
                    account_id=bundle.spec.account.account_id,
                    endpoint_name=rate_policy.endpoint,
                ),
            )
            if governor.forecast_endpoint:
                forecast_by_governor[governor.name] = ModelServingForecastProvider(
                    workspace,
                    governor.forecast_endpoint,
                )
            else:
                forecast_by_governor[governor.name] = DeterministicForecastProvider()
        telemetry = telemetry_by_governor
        forecast_provider = forecast_by_governor
    return GovernorEngine(
        bundle,
        store,
        telemetry,
        rate_limit_clients,
        forecast_provider=forecast_provider,
    )


def _build_session_manager(
    policy_file: Path,
    state_path: Path,
    session_secret: str,
) -> SessionManager:
    bundle = load_runtime_bundle(policy_file)
    return SessionManager(open_state_store(state_path), session_policy_map(bundle), session_secret)


def _load_bundle_and_clients(
    policy_file: Path,
    offline: bool,
    profile: str | None,
) -> tuple[Any, dict[str, Any] | None]:
    bundle = load_policy_file(policy_file)
    if offline:
        return bundle, None

    account_profile = profile or bundle.spec.account.profile
    workspace_profiles = {workspace.name: workspace.profile for workspace in bundle.spec.workspaces}
    client_bundle = build_client_bundle(
        account_profile=account_profile,
        account_id=bundle.spec.account.account_id,
        workspace_profiles=workspace_profiles,
    )
    return bundle, {
        "budget_client": client_bundle.budgets,
        "rate_limit_clients": client_bundle.rate_limits,
    }


def _render_plan(plan: dict[str, Any]) -> None:
    table = Table(title=f"Plan for {plan['bundle_name']}")
    table.add_column("Action")
    table.add_column("Type")
    table.add_column("Name")
    table.add_column("Workspace")
    for action in plan["actions"]:
        table.add_row(
            action["action"],
            action["resource_type"],
            action["resource_name"],
            action.get("workspace") or "",
        )
    console.print(table)
    summary = plan.get("summary", {})
    console.print(
        "Summary: " + ", ".join(f"{key}={value}" for key, value in sorted(summary.items()))
    )


def _emit(payload: Any, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    click.echo(json.dumps(payload, indent=2, default=str))


def _fail(message: str, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps({"valid": False, "error": message}, indent=2))
    else:
        console.print(f"[red]Error:[/red] {message}")
    raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
