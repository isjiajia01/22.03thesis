#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EXP03 — Time-window relaxation ablation (B1)

Story role:
- Test whether failures under extreme crunch are mainly caused by tight customer time windows.
- We relax ALL order time windows to [tw_start, tw_end] and rerun the same crunch scenario.

Outputs (under <runs_dir>/<run_id>/_analysis):
- exp03_relax_tw_summary_per_seed.csv
- exp03_relax_tw_summary_agg.csv (mean±std)
- exp03_*.png (mean±std bars)

Notes:
- Uses exp_utils.run_batch() so it automatically produces simulator outputs under:
    <runs_dir>/<run_id>/<scenario>/<strategy>/(daily_stats.csv, failed_orders.csv, summary_final.json)
"""

from pathlib import Path
import sys

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
    relax_time_windows,
    run_batch,
    save_summary,
)
from src.experiments.plot_utils import plot_bars


def _agg_mean_std(df: pd.DataFrame) -> pd.DataFrame:
    agg = (
        df.groupby(["strategy"])  # two strategies only
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
        .reset_index()
    )
    # std can be NaN if only 1 seed
    for c in agg.columns:
        if c.endswith("_std"):
            agg[c] = agg[c].fillna(0.0)
    return agg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DEFAULT_DATA_FILE)
    ap.add_argument("--runs_dir", default=DEFAULT_RUNS_DIR)
    ap.add_argument("--run_id", default=None, help="Reuse an existing run_id folder if provided.")
    ap.add_argument("--seeds", nargs="+", type=int, default=[123, 456, 789])

    ap.add_argument("--ratio", type=float, default=0.40)
    ap.add_argument("--crunch_start", type=int, default=5)
    ap.add_argument("--crunch_end", type=int, default=8)
    ap.add_argument("--horizon_days", type=int, default=12)

    ap.add_argument("--tw_start", type=int, default=360)
    ap.add_argument("--tw_end", type=int, default=1020)

    ap.add_argument("--penalty", type=float, default=10000.0)
    ap.add_argument("--time_limit", type=int, default=60)
    ap.add_argument("--max_trips", type=int, default=2)

    # Proactive knobs (kept consistent across storyline)
    ap.add_argument("--buffer_ratio", type=float, default=0.75)
    ap.add_argument("--guardrail_days", type=int, default=1)

    args = ap.parse_args()

    base = load_json(args.data)
    variant = build_capacity_crunch(
        base,
        crunch_ratio=float(args.ratio),
        crunch_start=int(args.crunch_start),
        crunch_end=int(args.crunch_end),
        horizon_days=int(args.horizon_days),
    )
    variant = relax_time_windows(variant, tw_start=int(args.tw_start), tw_end=int(args.tw_end))

    scenario_name = (
        f"Capacity_Crunch_r{args.ratio:.2f}_d{args.crunch_start}-{args.crunch_end}"
        f"_relaxTW_{args.tw_start}-{args.tw_end}"
    )

    run_id = args.run_id or timestamp_id("exp03_relax_tw")
    analysis_dir = ensure_dir(os.path.join(args.runs_dir, run_id, "_analysis"))

    df = run_batch(
        data_variant=variant,
        run_id=run_id,
        runs_dir=args.runs_dir,
        scenario_name=scenario_name,
        seeds=args.seeds,
        penalty_per_fail=float(args.penalty),
        vrp_time_limit_s=int(args.time_limit),
        max_trips=int(args.max_trips),
        proactive_buffer_ratio=float(args.buffer_ratio),
        proactive_guardrail_days=int(args.guardrail_days),
    )

    save_summary(df, analysis_dir, "exp03_relax_tw_summary_per_seed.csv")
    agg = _agg_mean_std(df)
    save_summary(agg, analysis_dir, "exp03_relax_tw_summary_agg.csv")

    # Plots (mean±std)
    plot_bars(
        df=agg,
        x="strategy",
        y="service_rate_mean",
        yerr="service_rate_std",
        title=f"Relax TW: Service Rate (mean±std)\n{scenario_name}",
        out_path=os.path.join(analysis_dir, "exp03_service_rate.png"),
        xlabel="strategy",
        ylabel="service_rate",
    )

    plot_bars(
        df=agg,
        x="strategy",
        y="failed_orders_mean",
        yerr="failed_orders_std",
        title=f"Relax TW: Failed Orders (mean±std)\n{scenario_name}",
        out_path=os.path.join(analysis_dir, "exp03_failed_orders.png"),
        xlabel="strategy",
        ylabel="failed_orders",
    )

    plot_bars(
        df=agg,
        x="strategy",
        y="plan_churn_mean",
        yerr="plan_churn_std",
        title=f"Relax TW: Plan Churn (mean±std)\n{scenario_name}",
        out_path=os.path.join(analysis_dir, "exp03_plan_churn.png"),
        xlabel="strategy",
        ylabel="plan_churn",
    )

    plot_bars(
        df=agg,
        x="strategy",
        y="load_mse_mean",
        yerr="load_mse_std",
        title=f"Relax TW: Load MSE (mean±std)\n{scenario_name}",
        out_path=os.path.join(analysis_dir, "exp03_load_mse.png"),
        xlabel="strategy",
        ylabel="load_mse",
    )

    print("\n=== EXP03 Relax TW summary (per seed) ===")
    print(df.to_string(index=False))
    print("\n=== EXP03 Relax TW summary (mean±std across seeds) ===")
    print(agg.to_string(index=False))

    print("\n✅ Done.")
    print(f"Outputs under: {os.path.join(args.runs_dir, run_id)}")
    print(f"Analysis under: {analysis_dir}")


if __name__ == "__main__":
    main()
