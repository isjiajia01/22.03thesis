#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EXP07 — Fleet parallelism ablation at extreme crunch (default r=0.40)

Story role:
- Hold (approx) *active total colli capacity* constant at ratio r, but change parallelism:
  fewer bigger vehicles vs. more smaller vehicles.
- Test whether increased parallelism helps or hurts (fragmentation / search difficulty).

Runs:
- Baseline fleet (as in dataset)
- Fleet variant with active_target vehicles at ratio r (default 9),
  created by fleet_variant_same_total_capacity()

Outputs (under <runs_dir>/<run_id>/_analysis):
- exp07_fleet_ablation_long.csv
- exp07_fleet_ablation_agg.csv            (mean±std: fleet_variant × active_vehicles × strategy)
- exp07_sr_vs_active_vehicles.png
- exp07_failed_vs_active_vehicles.png

Notes:
- Writes checkpoint CSV after each fleet block.
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
    load_json, build_capacity_crunch, fleet_variant_same_total_capacity, run_batch, save_summary,
)
from src.experiments.plot_utils import plot_lines


def _infer_baseline_active_vehicles(base_data: dict, ratio: float, vehicle_type_name: str) -> int:
    for v in base_data.get("vehicles", []):
        if v.get("type_name") == vehicle_type_name:
            return int(int(v.get("count", 0)) * float(ratio))
    # If not found, just return -1 (will still run; plot x will be missing)
    return -1


def _agg_mean_std(long: pd.DataFrame) -> pd.DataFrame:
    agg = (long.groupby(["fleet_variant", "active_vehicles", "strategy"])
               .agg(
                   service_rate_mean=("service_rate", "mean"),
                   service_rate_std=("service_rate", "std"),
                   failed_orders_mean=("failed_orders", "mean"),
                   failed_orders_std=("failed_orders", "std"),
                   plan_churn_mean=("plan_churn", "mean"),
                   plan_churn_std=("plan_churn", "std"),
               )
               .reset_index()
               .sort_values(["active_vehicles", "fleet_variant", "strategy"])
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

    ap.add_argument("--ratio", type=float, default=0.40)
    ap.add_argument("--crunch_start", type=int, default=5)
    ap.add_argument("--crunch_end", type=int, default=8)
    ap.add_argument("--horizon_days", type=int, default=12)

    ap.add_argument("--active_target", type=int, default=9)
    ap.add_argument("--vehicle_type_name", type=str, default="Lift")

    ap.add_argument("--time_limit", type=int, default=60)
    ap.add_argument("--max_trips", type=int, default=2)
    ap.add_argument("--penalty", type=float, default=10000.0)

    ap.add_argument("--buffer_ratio", type=float, default=0.75)
    ap.add_argument("--guardrail_days", type=int, default=1)

    args = ap.parse_args()

    base = load_json(args.data)

    # Baseline crunch dataset
    baseline = build_capacity_crunch(base, args.ratio, args.crunch_start, args.crunch_end, args.horizon_days)

    # Fleet-variant crunch dataset
    fleet_var = fleet_variant_same_total_capacity(
        base_data=base,
        ratio=float(args.ratio),
        active_target=int(args.active_target),
        vehicle_type_name=str(args.vehicle_type_name),
    )
    fleet_var = build_capacity_crunch(fleet_var, args.ratio, args.crunch_start, args.crunch_end, args.horizon_days)

    run_id = args.run_id or timestamp_id("exp07_fleet")
    analysis_dir = ensure_dir(os.path.join(args.runs_dir, run_id, "_analysis"))

    baseline_active = _infer_baseline_active_vehicles(base, args.ratio, args.vehicle_type_name)
    print(f"[EXP07] ratio          = {args.ratio}")
    print(f"[EXP07] baseline_active= {baseline_active} ({args.vehicle_type_name})")
    print(f"[EXP07] active_target  = {args.active_target}")
    print(f"[EXP07] run_id         = {run_id}")

    all_rows = []
    checkpoint_path = os.path.join(analysis_dir, "exp07_fleet_ablation_long_checkpoint.csv")

    scenarios = [
        ("baseline", baseline, baseline_active),
        (f"active{int(args.active_target)}", fleet_var, int(args.active_target)),
    ]

    scenario_base = f"Capacity_Crunch_r{args.ratio:.2f}_d{args.crunch_start}-{args.crunch_end}"

    for idx, (fleet_label, data_variant, active_n) in enumerate(scenarios, start=1):
        print(f"\n[EXP07 {idx}/{len(scenarios)}] Running fleet={fleet_label} (active={active_n}) ...")

        scenario_name = f"{scenario_base}_fleet_{fleet_label}"
        df = run_batch(
            data_variant=data_variant,
            run_id=run_id,
            runs_dir=args.runs_dir,
            scenario_name=scenario_name,
            seeds=args.seeds,
            penalty_per_fail=args.penalty,
            vrp_time_limit_s=args.time_limit,
            max_trips=args.max_trips,
            proactive_buffer_ratio=args.buffer_ratio,
            proactive_guardrail_days=args.guardrail_days,
        )
        df["fleet_variant"] = fleet_label
        df["active_vehicles"] = int(active_n)
        all_rows.append(df)

        pd.concat(all_rows, ignore_index=True).to_csv(checkpoint_path, index=False)

    long = pd.concat(all_rows, ignore_index=True)
    save_summary(long, analysis_dir, "exp07_fleet_ablation_long.csv")

    agg = _agg_mean_std(long)
    save_summary(agg, analysis_dir, "exp07_fleet_ablation_agg.csv")

    # Plot mean vs active vehicles (numeric x)
    sr_mean = agg.rename(columns={"service_rate_mean": "service_rate"})
    plot_lines(
        sr_mean,
        x="active_vehicles",
        y="service_rate",
        group="strategy",
        title=f"EXP07: Service Rate vs Active Vehicles (r={args.ratio:.2f})",
        out_path=os.path.join(analysis_dir, "exp07_sr_vs_active_vehicles.png"),
        xlabel="active_vehicles_at_ratio",
        ylabel="service_rate",
    )

    fail_mean = agg.rename(columns={"failed_orders_mean": "failed_orders"})
    plot_lines(
        fail_mean,
        x="active_vehicles",
        y="failed_orders",
        group="strategy",
        title=f"EXP07: Failed Orders vs Active Vehicles (r={args.ratio:.2f})",
        out_path=os.path.join(analysis_dir, "exp07_failed_vs_active_vehicles.png"),
        xlabel="active_vehicles_at_ratio",
        ylabel="failed_orders",
    )

    print("\n=== EXP07 Fleet ablation (long) ===")
    print(long.to_string(index=False))
    print("\n=== EXP07 mean±std across seeds ===")
    print(agg.to_string(index=False))
    print("\n✅ Done.")
    print(f"Outputs under: {os.path.join(args.runs_dir, run_id)}")
    print(f"Analysis under: {analysis_dir}")


if __name__ == "__main__":
    main()
