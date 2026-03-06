#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EXP06 — Multi-trip sweep (mt in [2,1,3]) for BAU + mid-crunch (default r=0.80)

Story role:
- Align with ops: vehicles can do multiple trips per day.
- Show whether the policy gap changes when operational flexibility increases.

Runs:
- BAU (no crunch) with penalty_bau
- Capacity_Crunch at ratio r (default 0.80 on days d5–d8) with penalty_crunch
- For each max_trips in max_trips_list, run both strategies over all seeds.

Outputs (under <runs_dir>/<run_id>/_analysis):
- exp06_multitrip_sweep_long.csv                (all runs: scenario × mt × seed × strategy)
- exp06_multitrip_sweep_agg.csv                 (mean±std: scenario_group × mt × strategy)
- exp06_bau_sr_vs_mt.png / exp06_bau_failed_vs_mt.png
- exp06_crunch_sr_vs_mt.png / exp06_crunch_failed_vs_mt.png

Notes:
- Writes a checkpoint CSV after each mt block so _analysis is not empty during long runs.
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
    load_json, build_bau, build_capacity_crunch, run_batch, save_summary,
)
from src.experiments.plot_utils import plot_lines


def _agg_mean_std(long: pd.DataFrame) -> pd.DataFrame:
    agg = (long.groupby(["scenario_group", "max_trips", "strategy"])
               .agg(
                   service_rate_mean=("service_rate", "mean"),
                   service_rate_std=("service_rate", "std"),
                   failed_orders_mean=("failed_orders", "mean"),
                   failed_orders_std=("failed_orders", "std"),
                   plan_churn_mean=("plan_churn", "mean"),
                   plan_churn_std=("plan_churn", "std"),
               )
               .reset_index()
               .sort_values(["scenario_group", "max_trips", "strategy"])
               .reset_index(drop=True))
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

    # crunch spec for the mid-pressure scenario
    ap.add_argument("--ratio", type=float, default=0.80)
    ap.add_argument("--crunch_start", type=int, default=5)
    ap.add_argument("--crunch_end", type=int, default=8)
    ap.add_argument("--horizon_days", type=int, default=12)

    # sweep mt
    ap.add_argument("--max_trips_list", nargs="+", type=int, default=[2, 1, 3])
    ap.add_argument("--time_limit", type=int, default=60)

    # penalties (keep BAU and Crunch comparable to earlier experiments)
    ap.add_argument("--penalty_bau", type=float, default=150.0)
    ap.add_argument("--penalty_crunch", type=float, default=10000.0)

    # proactive knobs
    ap.add_argument("--buffer_ratio", type=float, default=0.75)
    ap.add_argument("--guardrail_days", type=int, default=1)

    args = ap.parse_args()

    base = load_json(args.data)
    bau = build_bau(base)
    crunch = build_capacity_crunch(base, args.ratio, args.crunch_start, args.crunch_end, args.horizon_days)

    run_id = args.run_id or timestamp_id("exp06_multitrip")
    analysis_dir = ensure_dir(os.path.join(args.runs_dir, run_id, "_analysis"))

    print(f"[EXP06] max_trips_list = {args.max_trips_list}")
    print(f"[EXP06] seeds         = {args.seeds}")
    print(f"[EXP06] run_id        = {run_id}")

    all_rows = []
    checkpoint_path = os.path.join(analysis_dir, "exp06_multitrip_sweep_long_checkpoint.csv")

    for idx, mt in enumerate(args.max_trips_list, start=1):
        print(f"\n[EXP06 {idx}/{len(args.max_trips_list)}] Running max_trips={mt} ...")

        # BAU
        df_bau = run_batch(
            data_variant=bau,
            run_id=run_id,
            runs_dir=args.runs_dir,
            scenario_name=f"BAU_Daily_mt{mt}",
            seeds=args.seeds,
            penalty_per_fail=args.penalty_bau,
            vrp_time_limit_s=args.time_limit,
            max_trips=int(mt),
            proactive_buffer_ratio=args.buffer_ratio,
            proactive_guardrail_days=args.guardrail_days,
        )
        df_bau["scenario_group"] = "BAU"
        df_bau["ratio"] = 1.0
        all_rows.append(df_bau)

        # Crunch (mid pressure)
        scenario_base = f"Capacity_Crunch_r{args.ratio:.2f}_d{args.crunch_start}-{args.crunch_end}"
        df_cr = run_batch(
            data_variant=crunch,
            run_id=run_id,
            runs_dir=args.runs_dir,
            scenario_name=f"{scenario_base}_mt{mt}",
            seeds=args.seeds,
            penalty_per_fail=args.penalty_crunch,
            vrp_time_limit_s=args.time_limit,
            max_trips=int(mt),
            proactive_buffer_ratio=args.buffer_ratio,
            proactive_guardrail_days=args.guardrail_days,
        )
        df_cr["scenario_group"] = "Crunch_r{:.2f}".format(args.ratio)
        df_cr["ratio"] = float(args.ratio)
        all_rows.append(df_cr)

        # checkpoint
        pd.concat(all_rows, ignore_index=True).to_csv(checkpoint_path, index=False)

    long = pd.concat(all_rows, ignore_index=True)
    save_summary(long, analysis_dir, "exp06_multitrip_sweep_long.csv")

    agg = _agg_mean_std(long)
    save_summary(agg, analysis_dir, "exp06_multitrip_sweep_agg.csv")

    # Plot means by mt for BAU and Crunch separately
    for scenario_group in ["BAU", "Crunch_r{:.2f}".format(args.ratio)]:
        sub = agg[agg["scenario_group"] == scenario_group].copy()
        if sub.empty:
            continue

        # Service rate
        sr_mean = sub.rename(columns={"service_rate_mean": "service_rate"})
        out_sr = os.path.join(
            analysis_dir,
            "exp06_{}_sr_vs_mt.png".format("bau" if scenario_group == "BAU" else "crunch"),
        )
        plot_lines(
            sr_mean,
            x="max_trips",
            y="service_rate",
            group="strategy",
            title=f"EXP06: {scenario_group} Service Rate vs max_trips (mean across seeds)",
            out_path=out_sr,
            xlabel="max_trips",
            ylabel="service_rate",
        )

        # Failed orders
        fail_mean = sub.rename(columns={"failed_orders_mean": "failed_orders"})
        out_fail = os.path.join(
            analysis_dir,
            "exp06_{}_failed_vs_mt.png".format("bau" if scenario_group == "BAU" else "crunch"),
        )
        plot_lines(
            fail_mean,
            x="max_trips",
            y="failed_orders",
            group="strategy",
            title=f"EXP06: {scenario_group} Failed Orders vs max_trips (mean across seeds)",
            out_path=out_fail,
            xlabel="max_trips",
            ylabel="failed_orders",
        )

    print("\n=== EXP06 Multi-trip sweep (long) ===")
    print(long.to_string(index=False))
    print("\n=== EXP06 mean±std across seeds ===")
    print(agg.to_string(index=False))
    print("\n✅ Done.")
    print(f"Outputs under: {os.path.join(args.runs_dir, run_id)}")
    print(f"Analysis under: {analysis_dir}")


if __name__ == "__main__":
    main()
