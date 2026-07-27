from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from gateway_policy.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_validate_success() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["validate", str(FIXTURES / "valid-policy.yaml"), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["valid"] is True


def test_cli_validate_failure() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["validate", str(FIXTURES / "invalid-block-policy.yaml")])
    assert result.exit_code == 1


def test_cli_apply_requires_yes_or_live_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeBudgetClient:
        def list_managed(self, bundle_name: str) -> list[dict[str, object]]:
            return []

    class FakeRateLimitClient:
        pass

    def fake_build_client_bundle(**kwargs: object) -> object:
        from gateway_policy.clients import ClientBundle

        return ClientBundle(
            account=object(),
            account_id="11111111-1111-1111-1111-111111111111",
            workspaces={},
            budgets=FakeBudgetClient(),
            rate_limits={"prod": FakeRateLimitClient()},
        )

    monkeypatch.setattr("gateway_policy.cli.build_client_bundle", fake_build_client_bundle)

    runner = CliRunner()
    result = runner.invoke(main, ["apply", str(FIXTURES / "valid-policy.yaml")])
    assert result.exit_code == 1
    assert "Refusing to apply without --yes" in result.output


def test_cli_validate_example_policy() -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["validate", "gateway-policy.example.yaml", "--json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["governors"] == 1
    assert payload["session_budgets"] == 1


def test_cli_governor_evaluate_offline(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "governor",
            "evaluate",
            str(FIXTURES / "governor-policy.yaml"),
            "--name",
            "monthly-burn",
            "--offline",
            "--json",
            "--state-path",
            str(tmp_path / "state.db"),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["governor_name"] == "monthly-burn"


def test_cli_plan_offline_json() -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["plan", str(FIXTURES / "valid-policy.yaml"), "--offline", "--json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["bundle_name"] == "test-bundle"
    assert "actions" in payload
