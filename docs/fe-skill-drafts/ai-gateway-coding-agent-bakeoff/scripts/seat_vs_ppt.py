#!/usr/bin/env python3
"""Seat vs pay-per-token break-even helpers for coding-agent Gateway bake-offs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass


def monthly_from_weekly(weekly: float) -> float:
    return weekly * 4.3


def single_user_verdict(ppt_monthly: float, seat: float) -> str:
    if ppt_monthly > seat * 1.1:
        return "seat wins on $"
    if ppt_monthly < seat * 0.9:
        return "PPT wins on $"
    return "roughly tie on $"


@dataclass
class OrgResult:
    seat_all: float
    ppt_all: float
    hybrid: float
    ppt_blended: float


def org_costs(
    n: int,
    seat: float,
    pct_power: float,
    ppt_power: float,
    ppt_median: float,
    ppt_light: float,
    pct_median: float | None = None,
    hybrid_seat_pct: float | None = None,
) -> OrgResult:
    p = pct_power / 100.0
    if pct_median is None:
        rem = 1.0 - p
        m, light = rem / 3.0, 2.0 * rem / 3.0
    else:
        m = pct_median / 100.0
        light = 1.0 - p - m
        if light < -1e-9:
            raise SystemExit("pct_power + pct_median exceed 100")
    blended = p * ppt_power + m * ppt_median + light * ppt_light
    seat_all = n * seat
    ppt_all = n * blended
    # Hybrid default: put power cohort on seats; median+light on PPT
    hs = (hybrid_seat_pct / 100.0) if hybrid_seat_pct is not None else p
    rest = 1.0 - hs
    # Approximate non-seat blended as median/light mix scaled to remaining mass
    if rest > 1e-12:
        non_seat_blended = (m * ppt_median + light * ppt_light) / max(m + light, 1e-12)
    else:
        non_seat_blended = 0.0
    hybrid = n * hs * seat + n * rest * non_seat_blended
    return OrgResult(seat_all, ppt_all, hybrid, blended)


def sonnet5_intro_ppt_usd(
    input_tokens: float,
    output_tokens: float,
    cache_hit: float,
) -> float:
    """Directional Sonnet 5 intro list USD from gross input/output token counts."""
    i_m = input_tokens / 1e6
    o_m = output_tokens / 1e6
    fresh = i_m * (1.0 - cache_hit)
    cache_r = i_m * cache_hit
    return fresh * 2.0 + cache_r * 0.20 + o_m * 10.0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--weekly-ppt", type=float, help="Known Gateway/API USD for one week")
    p.add_argument("--monthly-ppt", type=float, help="Known Gateway/API USD for one month")
    p.add_argument("--seat", type=float, default=100.0, help="Seat USD per user-month")
    p.add_argument("--n", type=int, default=0, help="Org headcount for cohort model")
    p.add_argument("--pct-power", type=float, default=10.0)
    p.add_argument("--pct-median", type=float, default=None)
    p.add_argument("--ppt-power", type=float, default=800.0)
    p.add_argument("--ppt-median", type=float, default=40.0)
    p.add_argument("--ppt-light", type=float, default=8.0)
    p.add_argument("--hybrid-seat-pct", type=float, default=None)
    p.add_argument("--input-tokens", type=float, help="Gross input tokens (period)")
    p.add_argument("--output-tokens", type=float, help="Output tokens (period)")
    p.add_argument("--cache-hit", type=float, default=0.75, help="0-1 cache read share of input")
    p.add_argument("--period-days", type=float, default=7.0, help="Days covered by token counts")
    args = p.parse_args()

    print("=== Economics snapshot (verify seat list with customer) ===")

    ppt_m = args.monthly_ppt
    if ppt_m is None and args.weekly_ppt is not None:
        ppt_m = monthly_from_weekly(args.weekly_ppt)
        print(f"Weekly PPT: ${args.weekly_ppt:,.2f} → monthly ≈ ${ppt_m:,.2f}")
    if ppt_m is None and args.input_tokens is not None and args.output_tokens is not None:
        period = sonnet5_intro_ppt_usd(args.input_tokens, args.output_tokens, args.cache_hit)
        ppt_m = period * (30.0 / args.period_days)
        print(
            f"Token forecast (Sonnet5 intro, cache_hit={args.cache_hit:.0%}): "
            f"${period:,.2f} / {args.period_days:g}d → monthly ≈ ${ppt_m:,.2f}"
        )

    if ppt_m is not None:
        print(f"Seat under consideration: ${args.seat:,.2f} / mo")
        print(f"For this power user on $: {single_user_verdict(ppt_m, args.seat)}")
        print(f"Ratio PPT/seat: {ppt_m / args.seat:,.1f}x")

    if args.n > 0:
        org = org_costs(
            args.n,
            args.seat,
            args.pct_power,
            args.ppt_power,
            args.ppt_median,
            args.ppt_light,
            args.pct_median,
            args.hybrid_seat_pct,
        )
        print()
        print(f"=== Org N={args.n} (blended PPT ${org.ppt_blended:,.2f}/user-mo) ===")
        print(f"Seat-all:  ${org.seat_all:,.0f} / mo")
        print(f"PPT-all:   ${org.ppt_all:,.0f} / mo")
        print(f"Hybrid:    ${org.hybrid:,.0f} / mo")
        winner = min(
            ("seat-all", org.seat_all),
            ("PPT-all", org.ppt_all),
            ("hybrid", org.hybrid),
            key=lambda x: x[1],
        )
        print(f"Cheapest on $: {winner[0]}")
        if ppt_m is not None and ppt_m > args.seat * 1.1:
            print(
                "Implication: power user alone → seats win; "
                "bake-off should be org mix + governance, not Max death-match."
            )


if __name__ == "__main__":
    main()
