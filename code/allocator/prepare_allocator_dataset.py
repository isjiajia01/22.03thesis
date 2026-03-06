#!/usr/bin/env python3
"""
Prepare training dataset for Learned Compute Allocator.

This script extracts (features_t, action_T, outcomes) records from experiment logs
to train a compute budget allocator that replaces the binary risk gate.

Usage:
    python prepare_allocator_dataset.py [--lambda_compute 1.0] [--output_dir ./output]

Output:
    - allocator_dataset.parquet: Training dataset
    - schema.json: Column definitions
    - data_report.md: Data quality report
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import argparse
from datetime import datetime

import pandas as pd
import numpy as np


# =============================================================================
# Configuration
# =============================================================================

# Experiments to include (EXP00-EXP04 + EXP11)
TARGET_EXPERIMENTS = ["EXP00", "EXP01", "EXP02", "EXP03", "EXP04", "EXP11"]

# Valid action set for compute allocator
VALID_ACTIONS = {30, 60, 120, 300}

# Risk model's 7 features (in order)
RISK_MODEL_FEATURES = [
    "capacity_ratio",
    "capacity_pressure",
    "pressure_k_star",
    "visible_open_orders",
    "mandatory_count",
    "prev_drop_rate",
    "prev_failures",
]

# Additional features from daily_stats
ADDITIONAL_FEATURES = [
    "target_load",
    "risk_p",  # optional: for comparison version
]

# Lagged features (computed from t-1)
LAGGED_FEATURES = [
    "served_colli_lag1",
    "vrp_dropped_lag1",
    "failures_lag1",
]


# =============================================================================
# Data Loading
# =============================================================================

def find_experiment_dirs(results_dir: Path) -> Dict[str, List[Path]]:
    """Find all experiment directories matching target experiments."""
    exp_dirs = {}

    for exp_name in TARGET_EXPERIMENTS:
        exp_pattern = f"EXP_{exp_name}"
        exp_path = results_dir / exp_pattern

        if exp_path.exists():
            # Find all seed/variant directories
            subdirs = []
            for item in exp_path.iterdir():
                if item.is_dir():
                    # Check if it's a seed directory (Seed_X) or variant (e.g., risk_False_tl_30)
                    subdirs.append(item)
            exp_dirs[exp_name] = subdirs
        else:
            print(f"Warning: Experiment directory not found: {exp_path}")

    return exp_dirs


def load_simulation_results(json_path: Path) -> Optional[Dict]:
    """Load simulation_results.json file."""
    try:
        with open(json_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {json_path}: {e}")
        return None


def extract_exp_seed_from_path(path: Path) -> Tuple[str, str, Optional[str]]:
    """Extract experiment ID, seed, and variant from path.

    Examples:
        EXP_EXP04/Seed_1 -> ("EXP04", "1", None)
        EXP_EXP11/risk_False_tl_30/Seed_1 -> ("EXP11", "1", "risk_False_tl_30")
    """
    parts = path.parts

    # Find EXP_EXPXX part
    exp_id = None
    for p in parts:
        if p.startswith("EXP_EXP"):
            exp_id = p.replace("EXP_", "")
            break

    # Find Seed_X part
    seed = None
    for p in parts:
        if p.startswith("Seed_"):
            seed = p.replace("Seed_", "")
            break

    # Find variant (anything between EXP_EXPXX and Seed_X)
    variant = None
    if exp_id and seed:
        exp_idx = parts.index(f"EXP_{exp_id}")
        seed_idx = parts.index(f"Seed_{seed}")
        if seed_idx - exp_idx > 1:
            variant = parts[exp_idx + 1]

    return exp_id or "UNKNOWN", seed or "0", variant


# =============================================================================
# Feature Engineering
# =============================================================================

def compute_lagged_features(daily_stats: List[Dict]) -> List[Dict]:
    """Add lagged features (t-1 values) to each day's record."""
    enriched = []

    for i, day in enumerate(daily_stats):
        day_copy = day.copy()

        if i == 0:
            # First day: no history available
            day_copy["served_colli_lag1"] = 0.0
            day_copy["vrp_dropped_lag1"] = 0.0
            day_copy["failures_lag1"] = 0.0
            day_copy["prev_drop_rate"] = 0.0
            day_copy["prev_failures"] = 0.0
        else:
            prev = daily_stats[i - 1]
            day_copy["served_colli_lag1"] = prev.get("served_colli", 0.0)
            day_copy["vrp_dropped_lag1"] = prev.get("vrp_dropped", 0.0)
            day_copy["failures_lag1"] = prev.get("failures", 0.0)

            # Compute prev_drop_rate if not present
            if "prev_drop_rate" not in day_copy or pd.isna(day_copy.get("prev_drop_rate")):
                planned = prev.get("planned_today", 0)
                dropped = prev.get("vrp_dropped", 0)
                day_copy["prev_drop_rate"] = dropped / planned if planned > 0 else 0.0

            # prev_failures
            if "prev_failures" not in day_copy or pd.isna(day_copy.get("prev_failures")):
                day_copy["prev_failures"] = prev.get("failures", 0)

        enriched.append(day_copy)

    return enriched


def extract_features(day: Dict) -> Dict:
    """Extract feature vector from a day's record."""
    features = {}

    # Risk model's 7 features
    for feat in RISK_MODEL_FEATURES:
        val = day.get(feat, 0.0)
        features[feat] = float(val) if not pd.isna(val) else 0.0

    # Additional features
    for feat in ADDITIONAL_FEATURES:
        val = day.get(feat, np.nan)
        features[feat] = float(val) if not pd.isna(val) else np.nan

    # Lagged features
    for feat in LAGGED_FEATURES:
        val = day.get(feat, 0.0)
        features[feat] = float(val) if not pd.isna(val) else 0.0

    return features


def compute_rewards(day: Dict, lambda_compute: float = 1.0) -> Dict:
    """Compute reward values for a day.

    reward_v1 = served_colli - 1000*failures - 50*vrp_dropped - lambda*(T/60)
    reward_v2 = -failures - 0.1*vrp_dropped - lambda*(T/60)
    """
    served = day.get("served_colli", 0.0)
    failures = day.get("failures", 0)
    vrp_dropped = day.get("vrp_dropped", 0)
    T = day.get("compute_limit_seconds", 60)

    compute_cost = lambda_compute * (T / 60.0)

    reward_v1 = served - 1000 * failures - 50 * vrp_dropped - compute_cost
    reward_v2 = -failures - 0.1 * vrp_dropped - compute_cost

    return {
        "reward_v1": reward_v1,
        "reward_v2": reward_v2,
    }


# =============================================================================
# Dataset Construction
# =============================================================================

def process_single_run(
    json_path: Path,
    exp_id: str,
    seed: str,
    variant: Optional[str],
    lambda_compute: float
) -> List[Dict]:
    """Process a single simulation run and extract day-level records."""
    data = load_simulation_results(json_path)
    if data is None:
        return []

    daily_stats = data.get("daily_stats", [])
    if not daily_stats:
        return []

    # Add lagged features
    enriched_stats = compute_lagged_features(daily_stats)

    records = []
    for day_idx, day in enumerate(enriched_stats):
        # Extract action (compute_limit_seconds)
        action_T = day.get("compute_limit_seconds", 60)

        # Extract features
        features = extract_features(day)

        # Compute rewards
        rewards = compute_rewards(day, lambda_compute)

        # Outcomes
        outcomes = {
            "served_colli": day.get("served_colli", 0.0),
            "vrp_dropped": day.get("vrp_dropped", 0),
            "failures": day.get("failures", 0),
            "plan_churn": day.get("plan_churn_effective", day.get("plan_churn_raw", np.nan)),
            "delivered_today": day.get("delivered_today", 0),
        }

        # Meta information
        meta = {
            "exp_id": exp_id,
            "seed": seed,
            "variant": variant or "",
            "day_index": day_idx,
            "date": day.get("date", ""),
            "capacity_ratio": day.get("capacity_ratio", np.nan),
            "mode_status": day.get("mode_status", ""),
        }

        # Combine into single record
        record = {
            "action_T": action_T,
            **{f"feat_{k}": v for k, v in features.items()},
            **{f"outcome_{k}": v for k, v in outcomes.items()},
            **rewards,
            **{f"meta_{k}": v for k, v in meta.items()},
        }

        records.append(record)

    return records


def build_dataset(
    results_dir: Path,
    lambda_compute: float = 1.0
) -> pd.DataFrame:
    """Build the complete allocator dataset."""
    exp_dirs = find_experiment_dirs(results_dir)

    all_records = []

    for exp_name, subdirs in exp_dirs.items():
        print(f"Processing {exp_name}: {len(subdirs)} subdirectories")

        for subdir in subdirs:
            # Find simulation_results.json
            # Could be directly in subdir or in a nested Seed_X directory
            json_candidates = list(subdir.rglob("simulation_results.json"))

            for json_path in json_candidates:
                exp_id, seed, variant = extract_exp_seed_from_path(json_path)

                records = process_single_run(
                    json_path, exp_id, seed, variant, lambda_compute
                )
                all_records.extend(records)

    df = pd.DataFrame(all_records)
    return df


# =============================================================================
# Quality Checks
# =============================================================================

def check_action_validity(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Check if all actions are in the valid set {30, 60, 120, 300}."""
    valid_mask = df["action_T"].isin(VALID_ACTIONS)

    valid_df = df[valid_mask].copy()
    invalid_df = df[~valid_mask].copy()

    return valid_df, invalid_df


def check_day_continuity(df: pd.DataFrame) -> List[Dict]:
    """Check for missing days within each exp+seed+variant run."""
    issues = []

    grouped = df.groupby(["meta_exp_id", "meta_seed", "meta_variant"])

    for (exp_id, seed, variant), group in grouped:
        day_indices = sorted(group["meta_day_index"].unique())
        expected = list(range(min(day_indices), max(day_indices) + 1))
        missing = set(expected) - set(day_indices)

        if missing:
            issues.append({
                "exp_id": exp_id,
                "seed": seed,
                "variant": variant,
                "missing_days": sorted(missing),
            })

    return issues


# =============================================================================
# Output Generation
# =============================================================================

def generate_schema(df: pd.DataFrame) -> Dict:
    """Generate schema.json describing all columns."""
    schema = {
        "description": "Allocator training dataset schema",
        "generated_at": datetime.now().isoformat(),
        "columns": {}
    }

    for col in df.columns:
        col_info = {
            "dtype": str(df[col].dtype),
            "non_null_count": int(df[col].notna().sum()),
            "null_count": int(df[col].isna().sum()),
        }

        # Categorize columns
        if col == "action_T":
            col_info["category"] = "action"
            col_info["description"] = "Compute time limit in seconds (target variable for allocator)"
            col_info["use_for_features"] = False
        elif col.startswith("feat_"):
            col_info["category"] = "feature"
            feat_name = col.replace("feat_", "")
            col_info["description"] = f"Feature: {feat_name}"
            col_info["use_for_features"] = True
            # Mark risk_p as optional
            if feat_name == "risk_p":
                col_info["use_for_features"] = "optional (for comparison)"
        elif col.startswith("outcome_"):
            col_info["category"] = "outcome"
            col_info["description"] = f"Outcome: {col.replace('outcome_', '')}"
            col_info["use_for_features"] = False
        elif col.startswith("reward_"):
            col_info["category"] = "reward"
            col_info["description"] = f"Reward signal: {col}"
            col_info["use_for_features"] = False
        elif col.startswith("meta_"):
            col_info["category"] = "metadata"
            col_info["description"] = f"Metadata: {col.replace('meta_', '')}"
            col_info["use_for_features"] = False

        schema["columns"][col] = col_info

    return schema


def generate_report(
    df: pd.DataFrame,
    invalid_df: pd.DataFrame,
    continuity_issues: List[Dict],
    lambda_compute: float
) -> str:
    """Generate data_report.md."""
    lines = [
        "# Allocator Dataset Report",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Summary",
        "",
        f"- **Total samples (valid)**: {len(df):,}",
        f"- **Total samples (invalid action)**: {len(invalid_df):,}",
        f"- **Lambda (compute cost)**: {lambda_compute}",
        "",
        "## Experiment Coverage",
        "",
    ]

    # Coverage by experiment
    exp_counts = df.groupby("meta_exp_id").size().sort_index()
    lines.append("| Experiment | Samples |")
    lines.append("|------------|---------|")
    for exp_id, count in exp_counts.items():
        lines.append(f"| {exp_id} | {count:,} |")
    lines.append("")

    # Coverage by experiment + variant (for EXP11)
    if "EXP11" in df["meta_exp_id"].values:
        lines.append("### EXP11 Variants (Time Limit Sweep)")
        lines.append("")
        exp11_df = df[df["meta_exp_id"] == "EXP11"]
        variant_counts = exp11_df.groupby("meta_variant").size().sort_index()
        lines.append("| Variant | Samples |")
        lines.append("|---------|---------|")
        for variant, count in variant_counts.items():
            lines.append(f"| {variant} | {count:,} |")
        lines.append("")

    # Action distribution
    lines.append("## Action Distribution")
    lines.append("")
    action_counts = df["action_T"].value_counts().sort_index()
    lines.append("| Action (seconds) | Count | Percentage |")
    lines.append("|------------------|-------|------------|")
    for action, count in action_counts.items():
        pct = 100 * count / len(df)
        lines.append(f"| {int(action)} | {count:,} | {pct:.1f}% |")
    lines.append("")

    # Invalid actions
    if len(invalid_df) > 0:
        lines.append("### Invalid Actions (excluded)")
        lines.append("")
        invalid_actions = invalid_df["action_T"].value_counts().sort_index()
        lines.append("| Action (seconds) | Count |")
        lines.append("|------------------|-------|")
        for action, count in invalid_actions.items():
            lines.append(f"| {int(action)} | {count:,} |")
        lines.append("")

    # Feature statistics
    lines.append("## Feature Statistics")
    lines.append("")
    feat_cols = [c for c in df.columns if c.startswith("feat_")]
    lines.append("| Feature | Mean | Std | Min | Max | Missing |")
    lines.append("|---------|------|-----|-----|-----|---------|")
    for col in feat_cols:
        feat_name = col.replace("feat_", "")
        mean = df[col].mean()
        std = df[col].std()
        min_val = df[col].min()
        max_val = df[col].max()
        missing = df[col].isna().sum()
        missing_pct = 100 * missing / len(df)
        lines.append(f"| {feat_name} | {mean:.2f} | {std:.2f} | {min_val:.2f} | {max_val:.2f} | {missing} ({missing_pct:.1f}%) |")
    lines.append("")

    # Outcome statistics
    lines.append("## Outcome Statistics")
    lines.append("")
    outcome_cols = [c for c in df.columns if c.startswith("outcome_")]
    lines.append("| Outcome | Mean | Std | Min | Max |")
    lines.append("|---------|------|-----|-----|-----|")
    for col in outcome_cols:
        outcome_name = col.replace("outcome_", "")
        mean = df[col].mean()
        std = df[col].std()
        min_val = df[col].min()
        max_val = df[col].max()
        lines.append(f"| {outcome_name} | {mean:.2f} | {std:.2f} | {min_val:.2f} | {max_val:.2f} |")
    lines.append("")

    # Reward statistics
    lines.append("## Reward Statistics")
    lines.append("")
    lines.append("| Reward | Mean | Std | Min | Max |")
    lines.append("|--------|------|-----|-----|-----|")
    for col in ["reward_v1", "reward_v2"]:
        mean = df[col].mean()
        std = df[col].std()
        min_val = df[col].min()
        max_val = df[col].max()
        lines.append(f"| {col} | {mean:.2f} | {std:.2f} | {min_val:.2f} | {max_val:.2f} |")
    lines.append("")

    # Reward by action
    lines.append("### Reward by Action")
    lines.append("")
    lines.append("| Action | reward_v1 (mean) | reward_v2 (mean) | Count |")
    lines.append("|--------|------------------|------------------|-------|")
    for action in sorted(df["action_T"].unique()):
        subset = df[df["action_T"] == action]
        r1_mean = subset["reward_v1"].mean()
        r2_mean = subset["reward_v2"].mean()
        count = len(subset)
        lines.append(f"| {int(action)}s | {r1_mean:.2f} | {r2_mean:.2f} | {count:,} |")
    lines.append("")

    # Continuity issues
    lines.append("## Data Quality")
    lines.append("")
    if continuity_issues:
        lines.append(f"### Day Continuity Issues ({len(continuity_issues)} runs)")
        lines.append("")
        for issue in continuity_issues[:10]:  # Show first 10
            lines.append(f"- {issue['exp_id']}/Seed_{issue['seed']}/{issue['variant']}: missing days {issue['missing_days']}")
        if len(continuity_issues) > 10:
            lines.append(f"- ... and {len(continuity_issues) - 10} more")
        lines.append("")
    else:
        lines.append("- **Day continuity**: All runs have continuous day indices ✓")
        lines.append("")

    # Seeds per experiment
    lines.append("### Seeds per Experiment")
    lines.append("")
    seed_counts = df.groupby("meta_exp_id")["meta_seed"].nunique()
    lines.append("| Experiment | Unique Seeds |")
    lines.append("|------------|--------------|")
    for exp_id, count in seed_counts.items():
        lines.append(f"| {exp_id} | {count} |")
    lines.append("")

    return "\n".join(lines)


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Prepare allocator training dataset")
    parser.add_argument(
        "--lambda_compute", type=float, default=1.0,
        help="Lambda coefficient for compute cost in reward (default: 1.0)"
    )
    parser.add_argument(
        "--output_dir", type=str, default=None,
        help="Output directory (default: data/allocator/)"
    )
    parser.add_argument(
        "--results_dir", type=str, default=None,
        help="Results directory (default: data/results/)"
    )
    args = parser.parse_args()

    # Determine paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent  # code/allocator -> project root

    results_dir = Path(args.results_dir) if args.results_dir else project_root / "data" / "results"
    output_dir = Path(args.output_dir) if args.output_dir else project_root / "data" / "allocator"

    print(f"Results directory: {results_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Lambda (compute cost): {args.lambda_compute}")
    print()

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build dataset
    print("Building dataset...")
    df = build_dataset(results_dir, args.lambda_compute)
    print(f"Total records extracted: {len(df):,}")
    print()

    # Quality checks
    print("Running quality checks...")
    valid_df, invalid_df = check_action_validity(df)
    print(f"  Valid actions: {len(valid_df):,}")
    print(f"  Invalid actions: {len(invalid_df):,}")

    continuity_issues = check_day_continuity(valid_df)
    print(f"  Continuity issues: {len(continuity_issues)}")
    print()

    # Generate outputs
    print("Generating outputs...")

    # Save dataset as CSV (primary format)
    csv_path = output_dir / "allocator_dataset.csv"
    valid_df.to_csv(csv_path, index=False)
    print(f"  Saved: {csv_path}")

    # Try to save as parquet if available
    try:
        parquet_path = output_dir / "allocator_dataset.parquet"
        valid_df.to_parquet(parquet_path, index=False)
        print(f"  Saved: {parquet_path}")
    except ImportError:
        print("  Skipped parquet (pyarrow not installed)")

    # Save invalid records separately
    if len(invalid_df) > 0:
        invalid_path = output_dir / "invalid_actions.csv"
        invalid_df.to_csv(invalid_path, index=False)
        print(f"  Saved: {invalid_path}")

    # Generate schema
    schema = generate_schema(valid_df)
    schema_path = output_dir / "schema.json"
    with open(schema_path, 'w') as f:
        json.dump(schema, f, indent=2)
    print(f"  Saved: {schema_path}")

    # Generate report
    report = generate_report(valid_df, invalid_df, continuity_issues, args.lambda_compute)
    report_path = output_dir / "data_report.md"
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"  Saved: {report_path}")

    print()
    print("Done!")
    print(f"\nDataset path: {parquet_path}")
    print(f"Report path: {report_path}")


if __name__ == "__main__":
    main()
