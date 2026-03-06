#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""EXP01 — Crunch baseline (extreme capacity crunch).

Story role
----------
This experiment is the "hard stress" baseline:
- Apply a capacity crunch profile with ratio r (default r=0.40 on days 5–8).
- Run Greedy vs Proactive_Smooth under the ops-aware VRP (multi-trip supported).

What it answers
---------------
1) Under extreme crunch, what is the attainable service rate / failed orders?
2) Does Proactive still reduce plan churn (stability) even if SR saturates?

Outputs
-------
Creates:
  <runs_dir>/<run_id>/_analysis/
    - exp01_crunch_rXX_summary_per_seed.csv
    - exp01_crunch_rXX_summary_agg.csv
    - exp01_service_rate.png
    - exp01_failed_orders.png
    - exp01_plan_churn.png
    - exp01_load_mse.png

Notes
-----
- penalty=10000 is intentional for crunch: it makes penalized_cost reflect failures heavily.
  You can change it via --penalty.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure repo root is importable
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import os
import pandas as pd

from src.experiments.exp_utils import (
    DEFAULT_DATA_FILE,
    DEFAULT_RUNS_DIR,
    ensure_dir,
    timestamp_id,
    load_json,
    build_capacity_crunch,
    run_batch,
    save_summary,
)
from src.experiments.plot_utils import plot_bars


def _agg_mean_std(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate mean/std per strategy for plotting."""
    agg = (
        df.groupby(["strategy"], as_index=False)
        .agg(
            service_rate_mean=("service_rate", "mean"),
            service_rate_std=("service_rate", "std"),
            failed_orders_mean=("failed_orders", "mean"),
            failed_orders_std=("failed_orders", "std"),
            plan_churn_mean=("plan_churn", "mean"),
            plan_churn_std=("plan_churn", "std"),
            load_mse_mean=("load_mse", "mean"),
            load_mse_std=("load_mse", "std"),
            cost_raw_mean=("cost_raw", "mean"),
            penalized_cost_mean=("penalized_cost", "mean"),
        )
    )

    # std is NaN when only one seed
    for c in agg.columns:
        if c.endswith("_std"):
            agg[c] = agg[c].fillna(0.0)
    return agg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DEFAULT_DATA_FILE)
    ap.add_argument("--runs_dir", default=DEFAULT_RUNS_DIR)
    ap.add_argument(
        "--run_id", default=None, help="Reuse an existing run_id folder if provided."
    )
    ap.add_argument("--seeds", nargs="+", type=int, default=[123, 456, 789])

    # crunch settings
    ap.add_argument("--ratio", type=float, default=0.40)
    ap.add_argument("--crunch_start", type=int, default=5)
    ap.add_argument("--crunch_end", type=int, default=8)
    ap.add_argument("--horizon_days", type=int, default=12)

    # solver knobs
    ap.add_argument("--penalty", type=float, default=10000.0)
    ap.add_argument("--time_limit", type=int, default=60)
    ap.add_argument("--max_trips", type=int, default=2)

    # proactive knobs
    ap.add_argument("--buffer_ratio", type=float, default=0.75)
    ap.add_argument("--guardrail_days", type=int, default=1)

    args = ap.parse_args()

    base = load_json(args.data)
    variant = build_capacity_crunch(
        base,
        crunch_ratio=args.ratio,
        crunch_start=args.crunch_start,
        crunch_end=args.crunch_end,
        horizon_days=args.horizon_days,
    )

    scenario_name = f"Capacity_Crunch_r{args.ratio:.2f}_d{args.crunch_start}-{args.crunch_end}"
    run_id = args.run_id or timestamp_id("exp01_crunch")
    analysis_dir = ensure_dir(os.path.join(args.runs_dir, run_id, "_analysis"))

    df = run_batch(
        data_variant=variant,
        run_id=run_id,
        runs_dir=args.runs_dir,
        scenario_name=scenario_name,
        seeds=args.seeds,
        penalty_per_fail=args.penalty,
        vrp_time_limit_s=args.time_limit,
        max_trips=args.max_trips,
        proactive_buffer_ratio=args.buffer_ratio,
        proactive_guardrail_days=args.guardrail_days,
        verbose=False,
    )

    # save
    per_seed_path = save_summary(
        df, analysis_dir, f"exp01_crunch_r{args.ratio:.2f}_summary_per_seed.csv"
    )

    agg = _agg_mean_std(df)
    agg_path = save_summary(
        agg, analysis_dir, f"exp01_crunch_r{args.ratio:.2f}_summary_agg.csv"
    )

    # plots (mean±std)
    plot_bars(
        df=agg,
        x="strategy",
        y="service_rate_mean",
        yerr="service_rate_std",
        title=f"EXP01 Crunch r={args.ratio:.2f}: Service Rate (mean±std)",
        out_path=os.path.join(analysis_dir, "exp01_service_rate.png"),
        xlabel="strategy",
        ylabel="service_rate",
    )

    plot_bars(
        df=agg,
        x="strategy",
        y="failed_orders_mean",
        yerr="failed_orders_std",
        title=f"EXP01 Crunch r={args.ratio:.2f}: Failed Orders (mean±std)",
        out_path=os.path.join(analysis_dir, "exp01_failed_orders.png"),
        xlabel="strategy",
        ylabel="failed_orders",
    )

    plot_bars(
        df=agg,
        x="strategy",
        y="plan_churn_mean",
        yerr="plan_churn_std",
        title=f"EXP01 Crunch r={args.ratio:.2f}: Plan Churn (mean±std)",
        out_path=os.path.join(analysis_dir, "exp01_plan_churn.png"),
        xlabel="strategy",
        ylabel="plan_churn",
    )

    plot_bars(
        df=agg,
        x="strategy",
        y="load_mse_mean",
        yerr="load_mse_std",
        title=f"EXP01 Crunch r={args.ratio:.2f}: Load MSE (mean±std)",
        out_path=os.path.join(analysis_dir, "exp01_load_mse.png"),
        xlabel="strategy",
        ylabel="load_mse",
    )

    print("\n=== EXP01 Crunch summary (per seed) ===")
    print(df.to_string(index=False))
    print("\n=== EXP01 Crunch summary (mean±std across seeds) ===")
    print(agg.to_string(index=False))

    print("\n✅ Done.")
    print(f"Outputs under: {os.path.join(args.runs_dir, run_id)}")
    print(f"Analysis under: {analysis_dir}")
    print(f"  - {os.path.basename(per_seed_path)}")
    print(f"  - {os.path.basename(agg_path)}")
    print("  - exp01_*.png")


if __name__ == "__main__":
    main()
