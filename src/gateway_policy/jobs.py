from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from gateway_policy.native_runtime import build_native_governor_runtime


def reconcile_main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconcile spend forecasts into Unity AI Gateway controls."
    )
    parser.add_argument("--policy-file", type=Path, required=True)
    parser.add_argument("--lakebase-endpoint")
    parser.add_argument("--lakebase-database", default="databricks_postgres")
    parser.add_argument("--warehouse-id", required=True)
    parser.add_argument("--governed-endpoint", required=True)
    parser.add_argument("--forecast-endpoint", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.lakebase_endpoint:
        os.environ["LAKEBASE_ENDPOINT"] = args.lakebase_endpoint
        os.environ["PGDATABASE"] = args.lakebase_database
    os.environ["DATABRICKS_WAREHOUSE_ID"] = args.warehouse_id
    os.environ["GOVERNED_ENDPOINT"] = args.governed_endpoint
    os.environ["FORECAST_ENDPOINT"] = args.forecast_endpoint

    runtime = build_native_governor_runtime(policy_file=args.policy_file)
    results = runtime.engine.run_once(apply=not args.dry_run)
    print(
        json.dumps(
            [asdict(result) for result in results],
            indent=2,
            default=str,
        )
    )
    if any(not result.healthy for result in results):
        raise SystemExit("governor reconciliation skipped because telemetry was stale")


if __name__ == "__main__":
    reconcile_main()
