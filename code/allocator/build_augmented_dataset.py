#!/usr/bin/env python3
"""
Build augmented allocator dataset from EXP16b1 data collection runs.

Reads daily_stats.csv from each B1 run, applies lagged feature engineering,
converts to allocator_dataset format, and combines with the original dataset.

Output: data/allocator/allocator_dataset_aug.csv
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ORIGINAL_DATASET = PROJECT_ROOT / "data" / "allocator" / "allocator_dataset.csv"
B1_RESULTS_DIR = PROJECT_ROOT / "data" / "results" / "EXP16" / "EXP16b1"
OUTPUT_PATH = PROJECT_ROOT / "data" / "allocator" / "allocator_dataset_aug.csv"

# Column mapping: daily_stats column -> allocator_dataset column
FEATURE_MAP = {
    "capacity_ratio": "feat_capacity_ratio",
    "capacity_pressure": "feat_capacity_pressure",
    "pressure_k_star": "feat_pressure_k_star",
    "visible_open_orders": "feat_visible_open_orders",
    "mandatory_count": "feat_mandatory_count",
    "target_load": "feat_target_load",
    "risk_p": "feat_risk_p",
}

OUTCOME_MAP = {
    "served_colli": "outcome_served_colli",
    "vrp_dropped": "outcome_vrp_dropped",
    "failures": "outcome_failures",
    "delivered_today": "outcome_delivered_today",
}


def process_single_run(daily_stats_path: Path, condition_id: str, seed: int) -> pd.DataFrame:
    """Process a single B1 run's daily_stats.csv into allocator_dataset format."""
    df = pd.read_csv(daily_stats_path)

    records = []
    for i, row in df.iterrows():
        record = {}

        # Action
        record["action_T"] = row.get("compute_limit_seconds", row.get("allocator_action_final", 60))

        # Features (direct mapping)
        for src, dst in FEATURE_MAP.items():
            val = row.get(src, 0.0)
            record[dst] = float(val) if pd.notna(val) else 0.0

        # Lagged features
        if i == 0:
            record["feat_prev_drop_rate"] = 0.0
            record["feat_prev_failures"] = 0.0
            record["feat_served_colli_lag1"] = 0.0
            record["feat_vrp_dropped_lag1"] = 0.0
            record["feat_failures_lag1"] = 0.0
        else:
            prev = df.iloc[i - 1]
            planned = prev.get("planned_today", 0)
            dropped = prev.get("vrp_dropped", 0)
            record["feat_prev_drop_rate"] = dropped / planned if planned > 0 else 0.0
            record["feat_prev_failures"] = float(prev.get("failures", 0))
            record["feat_served_colli_lag1"] = float(prev.get("served_colli", 0.0))
            record["feat_vrp_dropped_lag1"] = float(prev.get("vrp_dropped", 0))
            record["feat_failures_lag1"] = float(prev.get("failures", 0))

        # Outcomes
        for src, dst in OUTCOME_MAP.items():
            val = row.get(src, 0)
            record[dst] = float(val) if pd.notna(val) else 0.0

        # Plan churn
        record["outcome_plan_churn"] = float(row.get("plan_churn_effective",
                                              row.get("plan_churn_raw", np.nan)))

        # Rewards
        failures = row.get("failures", 0)
        vrp_dropped = row.get("vrp_dropped", 0)
        served = row.get("served_colli", 0.0)
        T = record["action_T"]
        lambda_compute = 1.0  # Standard lambda for dataset; actual lambda applied at training time

        record["reward_v1"] = served - 1000 * failures - 50 * vrp_dropped - lambda_compute * (T / 60.0)
        record["reward_v2"] = -failures - 0.1 * vrp_dropped - lambda_compute * (T / 60.0)

        # Metadata
        record["meta_exp_id"] = "EXP16b1"
        record["meta_seed"] = seed
        record["meta_variant"] = condition_id
        record["meta_day_index"] = i
        record["meta_date"] = row.get("date", "")
        record["meta_capacity_ratio"] = float(row.get("capacity_ratio", np.nan))
        record["meta_mode_status"] = row.get("mode_status", "")

        records.append(record)

    return pd.DataFrame(records)


def main():
    # Load original dataset
    df_orig = pd.read_csv(ORIGINAL_DATASET)
    print(f"Original dataset: {len(df_orig)} rows")

    # Process all B1 runs
    all_new = []
    condition_dirs = sorted(B1_RESULTS_DIR.iterdir())

    for cond_dir in condition_dirs:
        if not cond_dir.is_dir():
            continue
        condition_id = cond_dir.name  # e.g. "ratio_0.55_shift_-2"

        seed_dirs = sorted(cond_dir.iterdir())
        for seed_dir in seed_dirs:
            if not seed_dir.is_dir() or not seed_dir.name.startswith("seed_"):
                continue

            # Extract seed number
            seed = int(seed_dir.name.split("_")[1])

            # Find daily_stats.csv
            ds_path = seed_dir / "DEFAULT" / "EXP16b1" / "daily_stats.csv"
            if not ds_path.exists():
                print(f"  WARNING: missing {ds_path}")
                continue

            df_run = process_single_run(ds_path, condition_id, seed)
            all_new.append(df_run)

    df_new = pd.concat(all_new, ignore_index=True)
    print(f"New B1 data: {len(df_new)} rows from {len(all_new)} runs")

    # Combine
    df_aug = pd.concat([df_orig, df_new], ignore_index=True)

    # Ensure column order matches original
    df_aug = df_aug[df_orig.columns]

    print(f"Augmented dataset: {len(df_aug)} rows")
    print(f"  Original: {len(df_orig)}")
    print(f"  New (B1): {len(df_new)}")

    # Action distribution in new data
    print(f"\nAction distribution in B1 data:")
    action_counts = df_new["action_T"].value_counts().sort_index()
    for action, count in action_counts.items():
        print(f"  {int(action)}s: {count} ({100*count/len(df_new):.1f}%)")

    # Save
    df_aug.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
