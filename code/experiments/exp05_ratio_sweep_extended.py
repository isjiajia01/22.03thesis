#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EXP05 — Ratio sweep (extended): r in [0.70, 0.80, 0.90, 1.00] (default)

Story role:
- Main "threshold left-shift" figure:
  Service Rate / Failed Orders vs capacity ratio, comparing Greedy vs Proactive_Smooth.
- Uses ops-aware VRP and your shared exp_utils + plot_utils.

Outputs (under <runs_dir>/<run_id>/_analysis):
- exp05_ratio_sweep_long.csv
- exp05_ratio_sweep_agg.csv  (mean±std across seeds, grouped by ratio & strategy)
- exp05_service_rate_vs_ratio.png
- exp05_failed_orders_vs_ratio.png
- exp05_plan_churn_vs_ratio.png
- exp05_load_mse_vs_ratio.png
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
    DEFAULT_DATA_FILE, DEFAULT_RUNS_DIR, ensure_dir, timestamp_id,
    load_json, build_capacity_crunch, run_batch, save_summary,
)
from src.experiments.plot_utils import plot_lines


def _agg_mean_std(long_df: pd.DataFrame) -> pd.DataFrame:
    agg = (
        long_df.groupby(["ratio", "strategy"])
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
        .sort_values(["ratio", "strategy"])
    )
    # std will be NaN if only 1 seed; keep files clean for plotting
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

    ap.add_argument("--ratios", nargs="+", type=float, default=[0.7, 0.8, 0.9, 1.0])
    ap.add_argument("--crunch_start", type=int, default=5)
    ap.add_argument("--crunch_end", type=int, default=8)
    ap.add_argument("--horizon_days", type=int, default=12)

    ap.add_argument("--penalty", type=float, default=10000.0)
    ap.add_argument("--time_limit", type=int, default=60)
    ap.add_argument("--max_trips", type=int, default=2)

    ap.add_argument("--buffer_ratio", type=float, default=0.75)
    ap.add_argument("--guardrail_days", type=int, default=1)

    args = ap.parse_args()

    base = load_json(args.data)

    run_id = args.run_id or timestamp_id("exp05_ratioSweep")
    analysis_dir = ensure_dir(os.path.join(args.runs_dir, run_id, "_analysis"))

    rows = []
    for r in args.ratios:
        variant = build_capacity_crunch(base, r, args.crunch_start, args.crunch_end, args.horizon_days)
        scenario_name = f"Capacity_Crunch_r{r:.2f}_d{args.crunch_start}-{args.crunch_end}"

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
        df["ratio"] = float(r)
        rows.append(df)

    long = pd.concat(rows, ignore_index=True)
    long = long.sort_values(["ratio", "seed", "strategy"]).reset_index(drop=True)

    save_summary(long, analysis_dir, "exp05_ratio_sweep_long.csv")

    agg = _agg_mean_std(long)
    save_summary(agg, analysis_dir, "exp05_ratio_sweep_agg.csv")

    # For plotting, keep only needed cols (plot_lines ignores extras)
    sr_plot = agg[["ratio", "strategy", "service_rate_mean"]].rename(columns={"service_rate_mean": "service_rate"})
    fo_plot = agg[["ratio", "strategy", "failed_orders_mean"]].rename(columns={"failed_orders_mean": "failed_orders"})
    ch_plot = agg[["ratio", "strategy", "plan_churn_mean"]].rename(columns={"plan_churn_mean": "plan_churn"})
    lm_plot = agg[["ratio", "strategy", "load_mse_mean"]].rename(columns={"load_mse_mean": "load_mse"})

    plot_lines(
        sr_plot, x="ratio", y="service_rate", group="strategy",
        title=f"EXP05: Service Rate vs Capacity Ratio (t={args.time_limit}s, mt={args.max_trips})",
        out_path=os.path.join(analysis_dir, "exp05_service_rate_vs_ratio.png"),
        xlabel="capacity_ratio", ylabel="service_rate", x_rotate=0
    )
    plot_lines(
        fo_plot, x="ratio", y="failed_orders", group="strategy",
        title=f"EXP05: Failed Orders vs Capacity Ratio (t={args.time_limit}s, mt={args.max_trips})",
        out_path=os.path.join(analysis_dir, "exp05_failed_orders_vs_ratio.png"),
        xlabel="capacity_ratio", ylabel="failed_orders", x_rotate=0
    )
    plot_lines(
        ch_plot, x="ratio", y="plan_churn", group="strategy",
        title=f"EXP05: Plan Churn vs Capacity Ratio (t={args.time_limit}s, mt={args.max_trips})",
        out_path=os.path.join(analysis_dir, "exp05_plan_churn_vs_ratio.png"),
        xlabel="capacity_ratio", ylabel="plan_churn", x_rotate=0
    )
    plot_lines(
        lm_plot, x="ratio", y="load_mse", group="strategy",
        title=f"EXP05: Load MSE vs Capacity Ratio (t={args.time_limit}s, mt={args.max_trips})",
        out_path=os.path.join(analysis_dir, "exp05_load_mse_vs_ratio.png"),
        xlabel="capacity_ratio", ylabel="load_mse", x_rotate=0
    )

    # Nice console pivots (same style as your earlier notes)
    print("\n=== EXP05 Ratio sweep (per seed, long) ===")
    print(long.to_string(index=False))

    print("\n=== Pivot: service_rate_mean by ratio ===")
    sr_pivot = agg.pivot(index="strategy", columns="ratio", values="service_rate_mean")
    print(sr_pivot.to_string())

    print("\n=== Pivot: failed_orders_mean by ratio ===")
    fo_pivot = agg.pivot(index="strategy", columns="ratio", values="failed_orders_mean")
    print(fo_pivot.to_string())

    print(f"\n✅ Done.\nOutputs under: {os.path.join(args.runs_dir, run_id)}")
    print(f"Analysis under: {analysis_dir}")
    print("  - exp05_ratio_sweep_long.csv")
    print("  - exp05_ratio_sweep_agg.csv")
    print("  - exp05_*.png")


if __name__ == "__main__":
    main()
