#!/usr/bin/env python3
"""
Train Learned Compute Allocator using Fitted-Q approach.

For each action a ∈ {30, 60, 120, 300}, we fit a regression model:
    Q_a(x) ≈ E[U | x, a]

At inference time:
    a*(x) = argmax_a Q_a(x)

Reward function:
    U = -failures - 0.1 * vrp_dropped - λ * (T / 60)

Usage:
    python train_allocator.py [--data_path ...] [--output_dir ...]
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import joblib
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_squared_error, mean_absolute_error


# =============================================================================
# Configuration
# =============================================================================

ACTIONS = [30, 60, 120, 300]

# Lambda values to sweep
LAMBDA_VALUES = [0.01, 0.05, 0.1, 0.2, 0.5, 1.0]

# Features to use (excluding risk_p due to 57.7% missing)
FEATURE_COLS = [
    "feat_capacity_ratio",
    "feat_capacity_pressure",
    "feat_pressure_k_star",
    "feat_visible_open_orders",
    "feat_mandatory_count",
    "feat_prev_drop_rate",
    "feat_prev_failures",
    "feat_target_load",
    "feat_served_colli_lag1",
    "feat_vrp_dropped_lag1",
    "feat_failures_lag1",
]

# Feature subsets for ablation (EXP15c)
FEATURE_SETS = {
    "full": FEATURE_COLS,
    "no_ratio": [
        "feat_visible_open_orders",
        "feat_mandatory_count",
        "feat_prev_drop_rate",
        "feat_prev_failures",
        "feat_target_load",
        "feat_served_colli_lag1",
        "feat_vrp_dropped_lag1",
        "feat_failures_lag1",
        "feat_capacity_pressure",
        "feat_pressure_k_star",
    ],
    "no_calendar": [
        "feat_visible_open_orders",
        "feat_mandatory_count",
        "feat_prev_drop_rate",
        "feat_prev_failures",
        "feat_target_load",
        "feat_served_colli_lag1",
        "feat_vrp_dropped_lag1",
        "feat_failures_lag1",
    ],
}

# Model types to train
MODEL_TYPES = ["ridge", "hgb"]  # ridge=baseline, hgb=main


# =============================================================================
# Data Preparation
# =============================================================================

def load_dataset(data_path: Path) -> pd.DataFrame:
    """Load the allocator dataset."""
    df = pd.read_csv(data_path)
    print(f"Loaded {len(df)} samples from {data_path}")
    return df


def compute_reward(df: pd.DataFrame, lambda_compute: float) -> pd.Series:
    """Compute reward with given lambda.

    U = -failures - 0.1 * vrp_dropped - λ * (T / 60)
    """
    failures = df["outcome_failures"]
    vrp_dropped = df["outcome_vrp_dropped"]
    T = df["action_T"]

    reward = -failures - 0.1 * vrp_dropped - lambda_compute * (T / 60.0)
    return reward


def create_group_ids(df: pd.DataFrame) -> np.ndarray:
    """Create group IDs for GroupKFold split.

    Groups by (exp_id, seed, variant) to avoid trajectory leakage.
    """
    group_str = df["meta_exp_id"] + "_" + df["meta_seed"].astype(str) + "_" + df["meta_variant"]
    # Convert to integer IDs
    unique_groups = group_str.unique()
    group_map = {g: i for i, g in enumerate(unique_groups)}
    return group_str.map(group_map).values


# =============================================================================
# Model Training
# =============================================================================

def train_q_models(
    df: pd.DataFrame,
    lambda_compute: float,
    model_type: str = "hgb",
    feature_cols: List[str] = None,
) -> Dict[int, object]:
    """Train Q-function for each action.

    Returns dict: {action: fitted_model}
    """
    if feature_cols is None:
        feature_cols = FEATURE_COLS

    # Compute reward with this lambda
    df = df.copy()
    df["reward"] = compute_reward(df, lambda_compute)

    X = df[feature_cols].values

    q_models = {}

    for action in ACTIONS:
        # Filter to samples where this action was taken
        mask = df["action_T"] == action
        X_a = X[mask]
        y_a = df.loc[mask, "reward"].values

        if len(X_a) < 10:
            print(f"  Warning: Only {len(X_a)} samples for action={action}, skipping")
            continue

        # Create model
        if model_type == "ridge":
            model = Ridge(alpha=1.0)
        elif model_type == "hgb":
            model = HistGradientBoostingRegressor(
                max_iter=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )
        elif model_type == "rf":
            model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                n_jobs=-1
            )
        else:
            raise ValueError(f"Unknown model type: {model_type}")

        model.fit(X_a, y_a)
        q_models[action] = model

    return q_models


def predict_best_action(q_models: Dict[int, object], X: np.ndarray) -> np.ndarray:
    """Predict best action for each sample using argmax over Q-values."""
    n_samples = X.shape[0]
    q_values = np.full((n_samples, len(ACTIONS)), -np.inf)

    for i, action in enumerate(ACTIONS):
        if action in q_models:
            q_values[:, i] = q_models[action].predict(X)

    best_action_idx = np.argmax(q_values, axis=1)
    best_actions = np.array([ACTIONS[i] for i in best_action_idx])

    return best_actions


def get_q_values(q_models: Dict[int, object], X: np.ndarray) -> Dict[int, np.ndarray]:
    """Get Q-values for all actions."""
    q_values = {}
    for action in ACTIONS:
        if action in q_models:
            q_values[action] = q_models[action].predict(X)
        else:
            q_values[action] = np.full(X.shape[0], -np.inf)
    return q_values


# =============================================================================
# Evaluation
# =============================================================================

def evaluate_policy(
    df: pd.DataFrame,
    q_models: Dict[int, object],
    lambda_compute: float,
    policy_name: str = "learned",
    feature_cols: List[str] = None,
) -> Dict:
    """Evaluate a policy on the dataset.

    For learned policy: use argmax Q
    For baseline policies: use fixed action or risk gate logic
    """
    if feature_cols is None:
        feature_cols = FEATURE_COLS

    X = df[feature_cols].values

    if policy_name == "learned":
        selected_actions = predict_best_action(q_models, X)
    elif policy_name == "fixed_60":
        selected_actions = np.full(len(df), 60)
    elif policy_name == "fixed_300":
        selected_actions = np.full(len(df), 300)
    elif policy_name == "risk_gate":
        # Simulate risk gate: 300s if risk_mode_on else 60s
        # We don't have risk_mode_on directly, but we can approximate
        # using the actual action from EXP04 data
        # For simplicity, use: 300s if prev_failures > 0 or prev_drop_rate > 0.05
        risk_signal = (df["feat_prev_failures"] > 0) | (df["feat_prev_drop_rate"] > 0.05)
        selected_actions = np.where(risk_signal, 300, 60)
    elif policy_name == "actual":
        selected_actions = df["action_T"].values
    else:
        raise ValueError(f"Unknown policy: {policy_name}")

    # Compute counterfactual reward for selected actions
    # Note: This is an approximation - we use the Q-model predictions
    # For "actual" policy, we use the observed outcomes

    if policy_name == "actual":
        # Use actual observed outcomes
        failures = df["outcome_failures"].values
        vrp_dropped = df["outcome_vrp_dropped"].values
        T = df["action_T"].values
    else:
        # Use Q-model predictions as proxy for expected outcomes
        # This is the Direct Method approximation
        q_values = get_q_values(q_models, X)

        # Get predicted reward for selected actions
        predicted_rewards = np.zeros(len(df))
        for i, action in enumerate(selected_actions):
            if action in q_values:
                predicted_rewards[i] = q_values[action][i]
            else:
                predicted_rewards[i] = -np.inf

        # For metrics, we need to decompose reward back to components
        # U = -failures - 0.1*dropped - λ*(T/60)
        # We can't perfectly decompose, so we report the aggregate reward
        T = selected_actions

        # Estimate failures and dropped from Q-value
        # Q = -failures - 0.1*dropped - λ*(T/60)
        # failures + 0.1*dropped = -Q - λ*(T/60)
        # This is approximate; for actual metrics we'd need the real outcomes
        failures = None
        vrp_dropped = None

    # Compute reward
    if failures is not None:
        reward = -failures - 0.1 * vrp_dropped - lambda_compute * (T / 60.0)
        mean_failures = np.mean(failures)
        mean_dropped = np.mean(vrp_dropped)
    else:
        reward = predicted_rewards
        mean_failures = None
        mean_dropped = None

    # Action distribution
    action_counts = pd.Series(selected_actions).value_counts().sort_index()
    action_dist = {int(a): int(c) for a, c in action_counts.items()}

    # Compute budget
    mean_compute = np.mean(T)
    total_compute = np.sum(T)

    return {
        "policy": policy_name,
        "lambda": lambda_compute,
        "mean_reward": float(np.mean(reward)),
        "std_reward": float(np.std(reward)),
        "mean_compute": float(mean_compute),
        "total_compute": float(total_compute),
        "mean_failures": float(mean_failures) if mean_failures is not None else None,
        "mean_dropped": float(mean_dropped) if mean_dropped is not None else None,
        "action_distribution": action_dist,
        "n_samples": len(df),
    }


def cross_validate_policy(
    df: pd.DataFrame,
    lambda_compute: float,
    model_type: str = "hgb",
    n_splits: int = 5,
    feature_cols: List[str] = None,
) -> Dict:
    """Cross-validate the learned policy using GroupKFold."""
    if feature_cols is None:
        feature_cols = FEATURE_COLS

    groups = create_group_ids(df)
    gkf = GroupKFold(n_splits=n_splits)

    X = df[feature_cols].values

    fold_results = []
    all_test_rewards = []
    all_test_actions = []
    all_baseline_rewards = {
        "fixed_60": [],
        "fixed_300": [],
        "actual": [],
    }

    for fold_idx, (train_idx, test_idx) in enumerate(gkf.split(X, groups=groups)):
        train_df = df.iloc[train_idx]
        test_df = df.iloc[test_idx]

        # Train Q-models on training set
        q_models = train_q_models(train_df, lambda_compute, model_type, feature_cols=feature_cols)

        # Evaluate on test set
        learned_eval = evaluate_policy(test_df, q_models, lambda_compute, "learned", feature_cols=feature_cols)

        # Baseline evaluations (using same Q-models for consistency)
        fixed_60_eval = evaluate_policy(test_df, q_models, lambda_compute, "fixed_60", feature_cols=feature_cols)
        fixed_300_eval = evaluate_policy(test_df, q_models, lambda_compute, "fixed_300", feature_cols=feature_cols)
        actual_eval = evaluate_policy(test_df, q_models, lambda_compute, "actual", feature_cols=feature_cols)

        fold_results.append({
            "fold": fold_idx,
            "learned": learned_eval,
            "fixed_60": fixed_60_eval,
            "fixed_300": fixed_300_eval,
            "actual": actual_eval,
        })

        # Collect test set predictions for aggregate stats
        X_test = test_df[feature_cols].values
        test_actions = predict_best_action(q_models, X_test)
        all_test_actions.extend(test_actions)

        # Compute actual rewards for test set under learned policy
        # (using Q-model predictions as proxy)
        q_values = get_q_values(q_models, X_test)
        for i, action in enumerate(test_actions):
            if action in q_values:
                all_test_rewards.append(q_values[action][i])

    # Aggregate results
    learned_rewards = [f["learned"]["mean_reward"] for f in fold_results]
    fixed_60_rewards = [f["fixed_60"]["mean_reward"] for f in fold_results]
    fixed_300_rewards = [f["fixed_300"]["mean_reward"] for f in fold_results]
    actual_rewards = [f["actual"]["mean_reward"] for f in fold_results]

    # Action distribution across all folds
    action_counts = pd.Series(all_test_actions).value_counts().sort_index()
    action_dist = {int(a): int(c) for a, c in action_counts.items()}

    return {
        "lambda": lambda_compute,
        "model_type": model_type,
        "n_splits": n_splits,
        "learned": {
            "mean_reward": float(np.mean(learned_rewards)),
            "std_reward": float(np.std(learned_rewards)),
            "fold_rewards": learned_rewards,
        },
        "fixed_60": {
            "mean_reward": float(np.mean(fixed_60_rewards)),
            "std_reward": float(np.std(fixed_60_rewards)),
        },
        "fixed_300": {
            "mean_reward": float(np.mean(fixed_300_rewards)),
            "std_reward": float(np.std(fixed_300_rewards)),
        },
        "actual": {
            "mean_reward": float(np.mean(actual_rewards)),
            "std_reward": float(np.std(actual_rewards)),
        },
        "action_distribution": action_dist,
        "total_test_samples": len(all_test_actions),
    }


# =============================================================================
# Model Saving
# =============================================================================

def save_model(
    q_models: Dict[int, object],
    lambda_compute: float,
    model_type: str,
    feature_cols: List[str],
    output_dir: Path,
    cv_results: Dict,
    feature_set_name: str = "full",
):
    """Save trained Q-models to disk."""
    model_data = {
        "version": "1.0",
        "created_at": datetime.now().isoformat(),
        "lambda_compute": lambda_compute,
        "model_type": model_type,
        "feature_set_name": feature_set_name,
        "actions": ACTIONS,
        "feature_cols": feature_cols,
        "q_models": q_models,
        "cv_results": cv_results,
    }

    if feature_set_name != "full":
        filename = f"allocator_Q_lambda_{lambda_compute}_{model_type}_{feature_set_name}.joblib"
    else:
        filename = f"allocator_Q_lambda_{lambda_compute}_{model_type}.joblib"
    filepath = output_dir / filename
    joblib.dump(model_data, filepath)
    print(f"  Saved: {filepath}")

    return filepath


# =============================================================================
# Report Generation
# =============================================================================

def generate_report(
    all_results: List[Dict],
    recommended_lambda: float,
    recommended_model: str,
    output_dir: Path
) -> str:
    """Generate Step 2 report."""
    lines = [
        "# Allocator Step 2 Report: Fitted-Q Training",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Method",
        "",
        "**Approach**: Fitted-Q (Direct Method)",
        "- For each action a ∈ {30, 60, 120, 300}, train a regression model Q_a(x) ≈ E[U | x, a]",
        "- At inference: a*(x) = argmax_a Q_a(x)",
        "",
        "**Reward function**:",
        "```",
        "U = -failures - 0.1 * vrp_dropped - λ * (T / 60)",
        "```",
        "",
        "**Features used** (11 dimensions):",
    ]

    for feat in FEATURE_COLS:
        lines.append(f"- `{feat}`")

    lines.extend([
        "",
        "**Validation**: 5-fold GroupKFold (grouped by exp_id + seed + variant)",
        "",
        "---",
        "",
        "## Results by Lambda",
        "",
    ])

    # Group results by lambda
    results_by_lambda = {}
    for r in all_results:
        lam = r["lambda"]
        if lam not in results_by_lambda:
            results_by_lambda[lam] = {}
        results_by_lambda[lam][r["model_type"]] = r

    # Summary table
    lines.extend([
        "### Summary Table (HGB model)",
        "",
        "| λ | Learned E[U] | Fixed-60 E[U] | Fixed-300 E[U] | Actual E[U] | Δ vs Fixed-60 | Δ vs Fixed-300 |",
        "|---|--------------|---------------|----------------|-------------|---------------|----------------|",
    ])

    for lam in sorted(results_by_lambda.keys()):
        if "hgb" in results_by_lambda[lam]:
            r = results_by_lambda[lam]["hgb"]
            learned = r["learned"]["mean_reward"]
            fixed_60 = r["fixed_60"]["mean_reward"]
            fixed_300 = r["fixed_300"]["mean_reward"]
            actual = r["actual"]["mean_reward"]
            delta_60 = learned - fixed_60
            delta_300 = learned - fixed_300

            marker = " **←**" if lam == recommended_lambda else ""
            lines.append(
                f"| {lam}{marker} | {learned:.3f} | {fixed_60:.3f} | {fixed_300:.3f} | "
                f"{actual:.3f} | {delta_60:+.3f} | {delta_300:+.3f} |"
            )

    lines.append("")

    # Detailed results per lambda
    lines.extend([
        "---",
        "",
        "## Detailed Results by Lambda",
        "",
    ])

    for lam in sorted(results_by_lambda.keys()):
        lines.extend([
            f"### λ = {lam}",
            "",
        ])

        for model_type in ["ridge", "hgb"]:
            if model_type not in results_by_lambda[lam]:
                continue

            r = results_by_lambda[lam][model_type]

            lines.extend([
                f"#### Model: {model_type.upper()}",
                "",
                "**Policy Comparison (5-fold CV)**:",
                "",
                "| Policy | Mean E[U] | Std |",
                "|--------|-----------|-----|",
                f"| Learned | {r['learned']['mean_reward']:.4f} | {r['learned']['std_reward']:.4f} |",
                f"| Fixed-60 | {r['fixed_60']['mean_reward']:.4f} | {r['fixed_60']['std_reward']:.4f} |",
                f"| Fixed-300 | {r['fixed_300']['mean_reward']:.4f} | {r['fixed_300']['std_reward']:.4f} |",
                f"| Actual | {r['actual']['mean_reward']:.4f} | {r['actual']['std_reward']:.4f} |",
                "",
                "**Action Distribution (learned policy)**:",
                "",
                "| Action | Count | % |",
                "|--------|-------|---|",
            ])

            total = sum(r["action_distribution"].values())
            for action in ACTIONS:
                count = r["action_distribution"].get(action, 0)
                pct = 100 * count / total if total > 0 else 0
                lines.append(f"| {action}s | {count} | {pct:.1f}% |")

            lines.append("")

    # Recommendation
    lines.extend([
        "---",
        "",
        "## Recommendation",
        "",
        f"**Recommended λ**: `{recommended_lambda}`",
        "",
        f"**Recommended model**: `{recommended_model}`",
        "",
        "**Rationale**:",
        "",
    ])

    # Add rationale based on results
    if recommended_lambda in results_by_lambda and recommended_model in results_by_lambda[recommended_lambda]:
        r = results_by_lambda[recommended_lambda][recommended_model]
        learned = r["learned"]["mean_reward"]
        fixed_60 = r["fixed_60"]["mean_reward"]
        fixed_300 = r["fixed_300"]["mean_reward"]

        lines.extend([
            f"1. At λ={recommended_lambda}, the learned policy achieves E[U]={learned:.4f}",
            f"2. This is {learned - fixed_60:+.4f} better than Fixed-60 ({fixed_60:.4f})",
            f"3. This is {learned - fixed_300:+.4f} better than Fixed-300 ({fixed_300:.4f})",
            "",
            "**Action distribution analysis**:",
            "",
        ])

        total = sum(r["action_distribution"].values())
        for action in ACTIONS:
            count = r["action_distribution"].get(action, 0)
            pct = 100 * count / total if total > 0 else 0
            lines.append(f"- {action}s: {pct:.1f}%")

        lines.append("")

        # Compute expected compute savings
        expected_compute = sum(
            action * r["action_distribution"].get(action, 0) / total
            for action in ACTIONS
        )
        lines.extend([
            f"**Expected compute per day**: {expected_compute:.1f}s",
            f"- vs Fixed-60: {expected_compute - 60:+.1f}s",
            f"- vs Fixed-300: {expected_compute - 300:+.1f}s",
            "",
        ])

    lines.extend([
        "---",
        "",
        "## Model Files",
        "",
        f"Models saved to: `{output_dir}/`",
        "",
        "| File | Description |",
        "|------|-------------|",
    ])

    for lam in sorted(results_by_lambda.keys()):
        for model_type in ["ridge", "hgb"]:
            filename = f"allocator_Q_lambda_{lam}_{model_type}.joblib"
            lines.append(f"| `{filename}` | λ={lam}, {model_type.upper()} |")

    lines.extend([
        "",
        "---",
        "",
        "## Next Steps",
        "",
        "1. Integrate the recommended model into the simulator",
        "2. Run EXP12 to compare against EXP04 (risk gate) in closed-loop simulation",
        "3. Validate that failures do not increase while compute decreases",
        "",
    ])

    return "\n".join(lines)


# =============================================================================
# Main
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Train Learned Compute Allocator")
    parser.add_argument("--data-path", type=str, default=None,
                        help="Path to dataset CSV (default: data/allocator/allocator_dataset.csv)")
    parser.add_argument("--feature-set", type=str, default=None,
                        choices=list(FEATURE_SETS.keys()),
                        help="Feature set to use (default: train all sets)")
    parser.add_argument("--lambda-only", type=float, default=None,
                        help="Train only this lambda value")
    parser.add_argument("--model-type-only", type=str, default=None,
                        choices=["ridge", "hgb", "rf"],
                        help="Train only this model type")
    parser.add_argument("--save-name", type=str, default=None,
                        help="Override feature_set_name in saved filename (e.g. 'no_calendar_aug')")
    args = parser.parse_args()

    # Paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent

    data_path = Path(args.data_path) if args.data_path else project_root / "data" / "allocator" / "allocator_dataset.csv"
    output_dir = project_root / "data" / "allocator" / "models"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine what to train
    feature_set_names = [args.feature_set] if args.feature_set else ["full"]
    lambda_values = [args.lambda_only] if args.lambda_only else LAMBDA_VALUES
    model_types = [args.model_type_only] if args.model_type_only else MODEL_TYPES

    print(f"Data path: {data_path}")
    print(f"Output dir: {output_dir}")
    print(f"Feature sets: {feature_set_names}")
    print(f"Lambda values: {lambda_values}")
    print(f"Model types: {model_types}")
    print()

    # Load data
    df = load_dataset(data_path)
    print()

    # Train and evaluate
    all_results = []
    all_models = {}

    for fs_name in feature_set_names:
        feature_cols = FEATURE_SETS[fs_name]
        print(f"{'='*60}")
        print(f"Feature set: {fs_name} ({len(feature_cols)} features)")
        print(f"  Columns: {feature_cols}")
        print(f"{'='*60}")

        for lambda_compute in lambda_values:
            print(f"\n=== Lambda = {lambda_compute} ===")

            for model_type in model_types:
                print(f"  Training {model_type.upper()}...")

                # Cross-validate
                cv_results = cross_validate_policy(
                    df, lambda_compute, model_type, n_splits=5,
                    feature_cols=feature_cols,
                )
                all_results.append(cv_results)

                print(f"    Learned E[U]: {cv_results['learned']['mean_reward']:.4f} "
                      f"± {cv_results['learned']['std_reward']:.4f}")
                print(f"    Fixed-60 E[U]: {cv_results['fixed_60']['mean_reward']:.4f}")
                print(f"    Fixed-300 E[U]: {cv_results['fixed_300']['mean_reward']:.4f}")
                print(f"    Action dist: {cv_results['action_distribution']}")

                # Train final model on full data
                q_models = train_q_models(
                    df, lambda_compute, model_type, feature_cols=feature_cols,
                )

                # Save model
                save_name = args.save_name or fs_name
                model_path = save_model(
                    q_models, lambda_compute, model_type, feature_cols,
                    output_dir, cv_results, feature_set_name=save_name,
                )
                all_models[(lambda_compute, model_type, fs_name)] = model_path

            print()

    # Skip report/recommendation when running ablation subsets
    if args.feature_set or args.lambda_only or args.model_type_only or args.save_name:
        print("Ablation training complete.")
        return

    # Determine recommended lambda (full sweep only)
    best_lambda = None
    best_score = -np.inf

    for r in all_results:
        if r["model_type"] != "hgb":
            continue

        lam = r["lambda"]
        learned = r["learned"]["mean_reward"]
        fixed_60 = r["fixed_60"]["mean_reward"]
        fixed_300 = r["fixed_300"]["mean_reward"]

        dist = r["action_distribution"]
        total = sum(dist.values())
        max_pct = max(dist.values()) / total if total > 0 else 1.0

        improvement_60 = learned - fixed_60
        improvement_300 = learned - fixed_300

        if improvement_60 > 0 and improvement_300 > 0:
            diversity_bonus = 1.0 - max_pct
            score = min(improvement_60, improvement_300) + 0.1 * diversity_bonus

            if score > best_score:
                best_score = score
                best_lambda = lam

    if best_lambda is None:
        hgb_results = [r for r in all_results if r["model_type"] == "hgb"]
        best_lambda = max(hgb_results, key=lambda r: r["learned"]["mean_reward"])["lambda"]

    recommended_lambda = best_lambda
    recommended_model = "hgb"

    print(f"Recommended lambda: {recommended_lambda}")
    print(f"Recommended model: {recommended_model}")
    print()

    # Generate report
    report = generate_report(all_results, recommended_lambda, recommended_model, output_dir)
    report_path = output_dir.parent / "allocator_step2_report.md"
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"Report saved: {report_path}")

    # Save results JSON
    results_path = output_dir.parent / "step2_results.json"
    with open(results_path, 'w') as f:
        json.dump({
            "all_results": all_results,
            "recommended_lambda": recommended_lambda,
            "recommended_model": recommended_model,
        }, f, indent=2)
    print(f"Results saved: {results_path}")


if __name__ == "__main__":
    main()
