#!/usr/bin/env python3
"""
EXP12: Learned Compute Allocator Evaluation

This experiment compares the learned compute allocator against:
- EXP01: Crunch baseline (fixed 60s)
- EXP04: Risk gate with dynamic compute (60s/300s)
- EXP02: Static high compute (fixed 300s)

The learned allocator uses a Fitted-Q model to select compute budget
from {30, 60, 120, 300}s based on daily state features.

Usage:
    python exp12_learned_allocator.py [--lambda 0.01] [--seeds 10]
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from multiprocessing import Pool, cpu_count

# Set default max_trips to 2 (consistent with EXP01-EXP04)
os.environ.setdefault("VRP_MAX_TRIPS_PER_VEHICLE", "2")

# Add project root to path
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Also add code directory for imports
_CODE_DIR = _PROJECT_ROOT / "code"
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

from simulation.rolling_horizon_integrated import RollingHorizonIntegrated as RollingHorizonSimulator


# =============================================================================
# Configuration
# =============================================================================

# Default paths
DATA_PATH = _PROJECT_ROOT / "data" / "processed" / "multiday_benchmark_herlev.json"
RESULTS_DIR = _PROJECT_ROOT / "data" / "results"
MODELS_DIR = _PROJECT_ROOT / "data" / "allocator" / "models"
RISK_MODEL_PATH = _PROJECT_ROOT / "models" / "risk_model.joblib"

# Crunch scenario configuration (same as EXP01/EXP04)
CRUNCH_CONFIG = {
    "ratio": 0.59,           # Capacity ratio during crunch
    "crunch_start": 5,       # Day index when crunch starts (0-indexed: day 6)
    "crunch_end": 10,        # Day index when crunch ends (0-indexed: day 11)
    "total_days": 12,        # Total simulation days
}

# Seeds to run (same as EXP01/EXP04 for paired comparison)
DEFAULT_SEEDS = list(range(1, 11))  # Seeds 1-10


# =============================================================================
# Scenario Building
# =============================================================================

def build_capacity_profile(total_days, crunch_start, crunch_end, ratio):
    """Build capacity profile with crunch window."""
    profile = {}
    for day in range(total_days):
        if crunch_start <= day <= crunch_end:
            profile[str(day)] = ratio
        else:
            profile[str(day)] = 1.0
    return profile


def build_exp12_config(allocator_model_path, lambda_value):
    """Build configuration for EXP12 (learned allocator)."""
    capacity_profile = build_capacity_profile(
        CRUNCH_CONFIG["total_days"],
        CRUNCH_CONFIG["crunch_start"],
        CRUNCH_CONFIG["crunch_end"],
        CRUNCH_CONFIG["ratio"]
    )

    return {
        "mode": "proactive_quota",
        "lookahead_days": 3,
        "buffer_ratio": 1.05,
        "weights": {"urgency": 20.0, "profile": 2.0},
        "penalty_per_fail": 150.0,
        # Risk model (needed for risk_mode_on signal used in guardrails)
        "use_risk_model": True,
        "risk_model_path": str(RISK_MODEL_PATH),
        "delta_on": 0.826,
        "delta_off": 0.496,
        # Compute settings (fallback values)
        "base_compute": 60,
        "high_compute": 300,
        # Learned allocator
        "use_learned_allocator": True,
        "allocator_model_path": str(allocator_model_path),
        "allocator_lambda": lambda_value,
        # Capacity profile
        "capacity_profile": capacity_profile,
    }


def build_exp01_config():
    """Build configuration for EXP01 (crunch baseline, fixed 60s)."""
    capacity_profile = build_capacity_profile(
        CRUNCH_CONFIG["total_days"],
        CRUNCH_CONFIG["crunch_start"],
        CRUNCH_CONFIG["crunch_end"],
        CRUNCH_CONFIG["ratio"]
    )

    return {
        "mode": "proactive_quota",
        "lookahead_days": 3,
        "buffer_ratio": 1.05,
        "weights": {"urgency": 20.0, "profile": 2.0},
        "penalty_per_fail": 150.0,
        "use_risk_model": False,
        "base_compute": 60,
        "high_compute": 60,
        "use_learned_allocator": False,
        "capacity_profile": capacity_profile,
    }


def build_exp04_config():
    """Build configuration for EXP04 (risk gate, dynamic 60s/300s)."""
    capacity_profile = build_capacity_profile(
        CRUNCH_CONFIG["total_days"],
        CRUNCH_CONFIG["crunch_start"],
        CRUNCH_CONFIG["crunch_end"],
        CRUNCH_CONFIG["ratio"]
    )

    return {
        "mode": "proactive_quota",
        "lookahead_days": 3,
        "buffer_ratio": 1.05,
        "weights": {"urgency": 20.0, "profile": 2.0},
        "penalty_per_fail": 150.0,
        "use_risk_model": True,
        "risk_model_path": str(RISK_MODEL_PATH),
        "delta_on": 0.826,
        "delta_off": 0.496,
        "base_compute": 60,
        "high_compute": 300,
        "use_learned_allocator": False,
        "capacity_profile": capacity_profile,
    }


# =============================================================================
# Experiment Runner
# =============================================================================

def _run_experiment_worker(args):
    """Worker function for parallel execution."""
    config, seed, exp_name, results_base_dir = args
    config = config.copy()  # Avoid modifying shared config
    metrics, daily_stats = run_single_experiment(config, seed, exp_name, results_base_dir)
    sr = metrics.get("service_rate_within_window", 0) * 100
    failures = metrics.get("deadline_failure_count", 0)
    compute = sum(d.get("compute_limit_seconds", 60) for d in daily_stats)
    return seed, metrics, daily_stats, sr, failures, compute

def run_single_experiment(config, seed, exp_name, results_base_dir):
    """Run a single experiment with given config and seed."""
    run_dir = results_base_dir / f"Seed_{seed}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Load data and inject capacity_profile into metadata
    with open(DATA_PATH, 'r') as f:
        data = json.load(f)

    # Inject capacity_profile into data metadata
    capacity_profile = config.pop("capacity_profile", {})
    if "metadata" not in data:
        data["metadata"] = {}
    data["metadata"]["capacity_profile"] = capacity_profile

    sim = RollingHorizonSimulator(
        data_source=data,  # Pass modified data dict directly
        strategy_config=config,
        seed=seed,
        verbose=False,
        base_dir=str(run_dir),
        scenario_name="DEFAULT",
        strategy_name=exp_name,
    )

    metrics = sim.run_simulation()

    # Save results
    results = {
        "experiment": exp_name,
        "seed": seed,
        "config": {k: v for k, v in config.items()},
        "capacity_profile": capacity_profile,
        "metrics": metrics,
        "daily_stats": sim.daily_stats,
    }

    results_path = run_dir / "simulation_results.json"
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    # Also save config dump
    config_path = run_dir / "config_dump.json"
    with open(config_path, 'w') as f:
        json.dump({
            "experiment_id": exp_name,
            "seed": seed,
            "timestamp": datetime.now().isoformat(),
            "parameters": config,
            "capacity_profile": capacity_profile,
        }, f, indent=2)

    # Restore capacity_profile to config for next run
    config["capacity_profile"] = capacity_profile

    return metrics, sim.daily_stats


def aggregate_results(all_results):
    """Aggregate results across seeds."""
    if not all_results:
        return {}

    metrics_keys = all_results[0][0].keys()
    agg = {}

    # Keys to skip (non-numeric)
    skip_keys = {"run_id", "scenario", "strategy", "base_dir", "run_dir"}

    for key in metrics_keys:
        if key in skip_keys:
            continue
        values = [r[0].get(key, 0) for r in all_results if r[0].get(key) is not None]
        if values and all(isinstance(v, (int, float)) for v in values):
            import numpy as np
            agg[key] = {
                "mean": float(np.mean(values)),
                "std": float(np.std(values)),
                "min": float(np.min(values)),
                "max": float(np.max(values)),
            }

    # Compute total compute budget
    compute_totals = []
    for _, daily_stats in all_results:
        total = sum(d.get("compute_limit_seconds", 60) for d in daily_stats)
        compute_totals.append(total)

    if compute_totals:
        import numpy as np
        agg["compute_total"] = {
            "mean": float(np.mean(compute_totals)),
            "std": float(np.std(compute_totals)),
        }

    # Count risk mode days
    risk_days = []
    for _, daily_stats in all_results:
        count = sum(1 for d in daily_stats if d.get("risk_mode_on", 0) == 1)
        risk_days.append(count)

    if risk_days:
        import numpy as np
        agg["risk_mode_days"] = {
            "mean": float(np.mean(risk_days)),
            "std": float(np.std(risk_days)),
        }

    return agg


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="EXP12: Learned Allocator Evaluation")
    parser.add_argument("--lambda", dest="lambda_val", type=float, default=0.01,
                        help="Lambda value for allocator model (default: 0.01)")
    parser.add_argument("--seeds", type=int, default=10,
                        help="Number of seeds to run (default: 10)")
    parser.add_argument("--seed-start", type=int, default=1,
                        help="Start seed (default: 1)")
    parser.add_argument("--seed-end", type=int, default=None,
                        help="End seed (default: same as --seeds)")
    parser.add_argument("--run_baselines", action="store_true",
                        help="Also run EXP01 and EXP04 baselines for comparison")
    parser.add_argument("--exp12-only", action="store_true",
                        help="Only run EXP12 (learned allocator)")
    parser.add_argument("--exp01-only", action="store_true",
                        help="Only run EXP01 baseline")
    parser.add_argument("--exp04-only", action="store_true",
                        help="Only run EXP04 baseline")
    parser.add_argument("--output_dir", type=str, default=None,
                        help="Output directory (default: data/results/EXP_EXP12)")
    parser.add_argument("--parallel", type=int, default=1,
                        help="Number of parallel workers (default: 1, use 0 for auto)")
    args = parser.parse_args()

    # Find allocator model
    lambda_val = args.lambda_val
    model_filename = f"allocator_Q_lambda_{lambda_val}_hgb.joblib"
    allocator_model_path = MODELS_DIR / model_filename

    if not allocator_model_path.exists():
        print(f"Error: Allocator model not found: {allocator_model_path}")
        print(f"Available models in {MODELS_DIR}:")
        for f in MODELS_DIR.glob("*.joblib"):
            print(f"  - {f.name}")
        sys.exit(1)

    print(f"=" * 60)
    print(f"EXP12: Learned Compute Allocator Evaluation")
    print(f"=" * 60)
    print(f"Allocator model: {allocator_model_path.name}")
    print(f"Lambda: {lambda_val}")

    # Determine seed range
    seed_start = args.seed_start
    seed_end = args.seed_end if args.seed_end else args.seeds
    seeds = list(range(seed_start, seed_end + 1))
    print(f"Seeds: {seed_start}-{seed_end}")
    print(f"Crunch config: ratio={CRUNCH_CONFIG['ratio']}, days {CRUNCH_CONFIG['crunch_start']}-{CRUNCH_CONFIG['crunch_end']}")

    # Determine which experiments to run
    run_exp12 = not (args.exp01_only or args.exp04_only)
    run_exp01 = args.run_baselines or args.exp01_only
    run_exp04 = args.run_baselines or args.exp04_only
    print(f"Running: EXP12={run_exp12}, EXP01={run_exp01}, EXP04={run_exp04}")
    print()

    # Parallel workers
    n_workers = args.parallel
    if n_workers == 0:
        n_workers = min(cpu_count(), len(seeds))
    use_parallel = n_workers > 1

    # Output directory
    output_base = Path(args.output_dir) if args.output_dir else RESULTS_DIR / "EXP_EXP12"
    output_base.mkdir(parents=True, exist_ok=True)

    exp12_agg = None
    exp01_agg = None
    exp04_agg = None

    # Run EXP12 (learned allocator)
    if run_exp12:
        print("Running EXP12 (Learned Allocator)...")
        if use_parallel:
            print(f"  Using {n_workers} parallel workers")
        exp12_config = build_exp12_config(allocator_model_path, lambda_val)
        exp12_results = []

        if use_parallel:
            work_items = [(exp12_config.copy(), seed, "EXP12_Learned",
                           output_base / f"lambda_{lambda_val}") for seed in seeds]
            with Pool(n_workers) as pool:
                for seed, metrics, daily_stats, sr, failures, compute in pool.imap_unordered(_run_experiment_worker, work_items):
                    exp12_results.append((metrics, daily_stats))
                    print(f"  Seed {seed}: SR={sr:.2f}%, Failures={failures}, Compute={compute}s")
        else:
            for seed in seeds:
                print(f"  Seed {seed}...", end=" ", flush=True)
                metrics, daily_stats = run_single_experiment(
                    exp12_config, seed, "EXP12_Learned",
                    output_base / f"lambda_{lambda_val}"
                )
                exp12_results.append((metrics, daily_stats))
                sr = metrics.get("service_rate_within_window", 0) * 100
                failures = metrics.get("deadline_failure_count", 0)
                compute = sum(d.get("compute_limit_seconds", 60) for d in daily_stats)
                print(f"SR={sr:.2f}%, Failures={failures}, Compute={compute}s")

        exp12_agg = aggregate_results(exp12_results)

    # Run EXP01 baseline
    if run_exp01:
        print("\nRunning EXP01 (Crunch Baseline, 60s)...")
        exp01_config = build_exp01_config()
        exp01_results = []

        if use_parallel:
            work_items = [(exp01_config.copy(), seed, "EXP01_Baseline",
                           output_base / "baseline_exp01") for seed in seeds]
            with Pool(n_workers) as pool:
                for seed, metrics, daily_stats, sr, failures, compute in pool.imap_unordered(_run_experiment_worker, work_items):
                    exp01_results.append((metrics, daily_stats))
                    print(f"  Seed {seed}: SR={sr:.2f}%, Failures={failures}")
        else:
            for seed in seeds:
                print(f"  Seed {seed}...", end=" ", flush=True)
                metrics, daily_stats = run_single_experiment(
                    exp01_config, seed, "EXP01_Baseline",
                    output_base / "baseline_exp01"
                )
                exp01_results.append((metrics, daily_stats))
                sr = metrics.get("service_rate_within_window", 0) * 100
                failures = metrics.get("deadline_failure_count", 0)
                print(f"SR={sr:.2f}%, Failures={failures}")

        exp01_agg = aggregate_results(exp01_results)

    # Run EXP04 baseline
    if run_exp04:
        print("\nRunning EXP04 (Risk Gate, 60s/300s)...")
        exp04_config = build_exp04_config()
        exp04_results = []

        if use_parallel:
            work_items = [(exp04_config.copy(), seed, "EXP04_RiskGate",
                           output_base / "baseline_exp04") for seed in seeds]
            with Pool(n_workers) as pool:
                for seed, metrics, daily_stats, sr, failures, compute in pool.imap_unordered(_run_experiment_worker, work_items):
                    exp04_results.append((metrics, daily_stats))
                    print(f"  Seed {seed}: SR={sr:.2f}%, Failures={failures}, Compute={compute}s")
        else:
            for seed in seeds:
                print(f"  Seed {seed}...", end=" ", flush=True)
                metrics, daily_stats = run_single_experiment(
                    exp04_config, seed, "EXP04_RiskGate",
                    output_base / "baseline_exp04"
                )
                exp04_results.append((metrics, daily_stats))
                sr = metrics.get("service_rate_within_window", 0) * 100
                failures = metrics.get("deadline_failure_count", 0)
                compute = sum(d.get("compute_limit_seconds", 60) for d in daily_stats)
                print(f"SR={sr:.2f}%, Failures={failures}, Compute={compute}s")

        exp04_agg = aggregate_results(exp04_results)

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    def print_exp_summary(name, agg):
        if agg is None:
            return
        sr = agg.get("service_rate_within_window", {}).get("mean", 0) * 100
        sr_std = agg.get("service_rate_within_window", {}).get("std", 0) * 100
        failures = agg.get("deadline_failure_count", {}).get("mean", 0)
        failures_std = agg.get("deadline_failure_count", {}).get("std", 0)
        compute = agg.get("compute_total", {}).get("mean", 0)
        compute_std = agg.get("compute_total", {}).get("std", 0)
        risk_days = agg.get("risk_mode_days", {}).get("mean", 0)

        print(f"\n{name}:")
        print(f"  Service Rate: {sr:.2f}% ± {sr_std:.2f}%")
        print(f"  Failures: {failures:.1f} ± {failures_std:.1f}")
        print(f"  Compute Total: {compute:.0f}s ± {compute_std:.0f}s")
        print(f"  Risk Mode Days: {risk_days:.1f}")

    print_exp_summary("EXP12 (Learned Allocator)", exp12_agg)
    print_exp_summary("EXP01 (Baseline 60s)", exp01_agg)
    print_exp_summary("EXP04 (Risk Gate 60s/300s)", exp04_agg)

    # Comparison
    if exp04_agg:
        print("\n" + "-" * 40)
        print("EXP12 vs EXP04 (paired comparison):")

        exp12_sr = exp12_agg.get("service_rate_within_window", {}).get("mean", 0) * 100
        exp04_sr = exp04_agg.get("service_rate_within_window", {}).get("mean", 0) * 100
        exp12_fail = exp12_agg.get("deadline_failure_count", {}).get("mean", 0)
        exp04_fail = exp04_agg.get("deadline_failure_count", {}).get("mean", 0)
        exp12_compute = exp12_agg.get("compute_total", {}).get("mean", 0)
        exp04_compute = exp04_agg.get("compute_total", {}).get("mean", 0)

        print(f"  ΔSR: {exp12_sr - exp04_sr:+.2f}%")
        print(f"  ΔFailures: {exp12_fail - exp04_fail:+.1f}")
        print(f"  ΔCompute: {exp12_compute - exp04_compute:+.0f}s ({100*(exp12_compute/exp04_compute - 1):+.1f}%)")

        # Success criteria
        print("\n" + "-" * 40)
        print("Success Criteria Check:")
        if exp12_fail <= exp04_fail:
            print(f"  ✓ Failures not increased ({exp12_fail:.1f} <= {exp04_fail:.1f})")
        else:
            print(f"  ✗ Failures increased ({exp12_fail:.1f} > {exp04_fail:.1f})")

        if exp12_compute < exp04_compute:
            print(f"  ✓ Compute reduced ({exp12_compute:.0f}s < {exp04_compute:.0f}s)")
        else:
            print(f"  ✗ Compute not reduced ({exp12_compute:.0f}s >= {exp04_compute:.0f}s)")

    # Save summary
    summary = {
        "experiment": "EXP12",
        "timestamp": datetime.now().isoformat(),
        "lambda": lambda_val,
        "allocator_model": str(allocator_model_path),
        "seeds": seeds,
        "crunch_config": CRUNCH_CONFIG,
        "results": {
            "exp12": exp12_agg,
            "exp01": exp01_agg,
            "exp04": exp04_agg,
        }
    }

    summary_path = output_base / f"exp12_summary_lambda_{lambda_val}.json"
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary saved: {summary_path}")


if __name__ == "__main__":
    main()
