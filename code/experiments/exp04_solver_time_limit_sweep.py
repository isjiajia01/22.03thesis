#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""EXP04 — Solver time limit sweep (B2)

Story role:
- Quantify the "search gap": does giving OR-Tools more time meaningfully reduce failures?

Runs:
- Capacity Crunch at ratio r (default 0.40), solver time limits [20, 60, 300].

Outputs (under <runs_dir>/<run_id>/_analysis):
- exp04_time_limit_sweep_long.csv              (all runs: time_limit × seed × strategy)
- exp04_time_limit_sweep_agg.csv               (mean±std per time_limit × strategy)
- exp04_sr_vs_time_mean.png
- exp04_failed_vs_time_mean.png

Notes:
- Writes a checkpoint after each time-limit block:
    exp04_time_limit_sweep_long_checkpoint.csv
  so _analysis isn't empty while it runs.
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


def _agg_mean_std(long: pd.DataFrame) -> pd.DataFrame:
    agg = (
        long.groupby(["vrp_time_limit_s", "strategy"])
            .agg(
                service_rate_mean=("service_rate", "mean"),
                service_rate_std=("service_rate", "std"),
                failed_orders_mean=("failed_orders", "mean"),
                failed_orders_std=("failed_orders", "std"),
            )
            .reset_index()
            .sort_values(["vrp_time_limit_s", "strategy"])
            .reset_index(drop=True)
    )
    # std is NaN if only 1 seed; make it 0 for readability
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

    ap.add_argument("--time_limits", nargs="+", type=int, default=[20, 60, 300])
    ap.add_argument("--max_trips", type=int, default=2)

    ap.add_argument("--penalty", type=float, default=10000.0)
    ap.add_argument("--buffer_ratio", type=float, default=0.75)
    ap.add_argument("--guardrail_days", type=int, default=1)

    args = ap.parse_args()

    base = load_json(args.data)
    variant = build_capacity_crunch(base, args.ratio, args.crunch_start, args.crunch_end, args.horizon_days)

    scenario_base = f"Capacity_Crunch_r{args.ratio:.2f}_d{args.crunch_start}-{args.crunch_end}"
    run_id = args.run_id or timestamp_id("exp04_timeLimit")
    analysis_dir = ensure_dir(os.path.join(args.runs_dir, run_id, "_analysis"))

    print(f"\n[EXP04] time_limits = {list(args.time_limits)}")
    print(f"[EXP04] seeds       = {list(args.seeds)}")
    print(f"[EXP04] run_id      = {run_id}")

    all_rows = []
    checkpoint_path = os.path.join(analysis_dir, "exp04_time_limit_sweep_long_checkpoint.csv")

    for idx, tl in enumerate(args.time_limits, start=1):
        print(f"\n[EXP04 {idx}/{len(args.time_limits)}] Running time_limit={tl}s ...")
        scenario_name = f"{scenario_base}_t{tl}s"

        df = run_batch(
            data_variant=variant,
            run_id=run_id,
            runs_dir=args.runs_dir,
            scenario_name=scenario_name,
            seeds=args.seeds,
            penalty_per_fail=args.penalty,
            vrp_time_limit_s=tl,
            max_trips=args.max_trips,
            proactive_buffer_ratio=args.buffer_ratio,
            proactive_guardrail_days=args.guardrail_days,
        )
        all_rows.append(df)

        # checkpoint so _analysis isn't empty while long runs are still ongoing
        pd.concat(all_rows, ignore_index=True).to_csv(checkpoint_path, index=False)

    long = pd.concat(all_rows, ignore_index=True)
    save_summary(long, analysis_dir, "exp04_time_limit_sweep_long.csv")

    agg = _agg_mean_std(long)
    save_summary(agg, analysis_dir, "exp04_time_limit_sweep_agg.csv")

    # Plot means (std saved in CSV)
    sr_mean = agg[["vrp_time_limit_s", "strategy", "service_rate_mean"]].rename(
        columns={"service_rate_mean": "service_rate"}
    )
    fail_mean = agg[["vrp_time_limit_s", "strategy", "failed_orders_mean"]].rename(
        columns={"failed_orders_mean": "failed_orders"}
    )

    plot_lines(
        sr_mean,
        x="vrp_time_limit_s",
        y="service_rate",
        group="strategy",
        title="EXP04: Service Rate vs Solver Time Limit (mean across seeds)",
        out_path=os.path.join(analysis_dir, "exp04_sr_vs_time_mean.png"),
        xlabel="time_limit_s",
        ylabel="service_rate",
    )

    plot_lines(
        fail_mean,
        x="vrp_time_limit_s",
        y="failed_orders",
        group="strategy",
        title="EXP04: Failed Orders vs Solver Time Limit (mean across seeds)",
        out_path=os.path.join(analysis_dir, "exp04_failed_vs_time_mean.png"),
        xlabel="time_limit_s",
        ylabel="failed_orders",
    )

    print("\n=== EXP04 Solver time limit sweep (long) ===")
    print(long.to_string(index=False))
    print("\n=== EXP04 mean±std across seeds ===")
    print(agg.to_string(index=False))
    print("\n✅ Done.")
    print(f"Outputs under: {os.path.join(args.runs_dir, run_id)}")
    print(f"Analysis under: {analysis_dir}")


if __name__ == "__main__":
    main()
