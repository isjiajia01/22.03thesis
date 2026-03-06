#!/usr/bin/env python3
"""
EXP13: Bandit-Augmented Allocator (BAA) Evaluation

This experiment extends EXP12 with a contextual bandit layer for online adaptation:
- EXP13a: BAA with epsilon-greedy + guardrails
- EXP13b: BAA with epsilon-greedy, NO guardrails (ablation)

Compares against:
- EXP01: Fixed 60s baseline
- EXP04: Risk gate (60s/300s)
- EXP12: Fitted-Q learned allocator

Key features:
- Uses EXP12's Q-model as warm-start prior
- Epsilon-greedy exploration with schedule
- Safety guardrails to prevent failures
- Full audit trail for reproducibility

Usage:
    # Single run (local testing)
    python exp13_bandit_allocator.py --test --seeds 2

    # Full experiment
    python exp13_bandit_allocator.py --seeds 10

    # Generate HPC job scripts
    python exp13_bandit_allocator.py --generate-hpc
"""

import os
import sys
import json
import argparse
import subprocess
import shutil
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Set default max_trips to 2 (consistent with EXP01-EXP04)
os.environ.setdefault("VRP_MAX_TRIPS_PER_VEHICLE", "2")

# Add project root to path
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_CODE_DIR = _PROJECT_ROOT / "code"
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

from simulation.rolling_horizon_integrated import RollingHorizonIntegrated as RollingHorizonSimulator


# =============================================================================
# Configuration
# =============================================================================

DATA_PATH = _PROJECT_ROOT / "data" / "processed" / "multiday_benchmark_herlev.json"
RESULTS_DIR = _PROJECT_ROOT / "data" / "results"
MODELS_DIR = _PROJECT_ROOT / "data" / "allocator" / "models"
RISK_MODEL_PATH = _PROJECT_ROOT / "models" / "risk_model.joblib"

# Default Q-model (from EXP12)
DEFAULT_Q_MODEL = MODELS_DIR / "allocator_Q_lambda_0.05_hgb_no_calendar.joblib"

# Crunch scenario configurations
SCENARIOS = {
    "crunch_d5_d10": {
        "ratio": 0.59,
        "crunch_start": 5,
        "crunch_end": 10,
        "total_days": 12,
    },
    "crunch_d3_d6": {
        "ratio": 0.59,
        "crunch_start": 3,
        "crunch_end": 6,
        "total_days": 12,
    },
    "crunch_d6_d9": {
        "ratio": 0.59,
        "crunch_start": 6,
        "crunch_end": 9,
        "total_days": 12,
    },
}

# Ratio sweep for phase transition analysis
RATIO_SWEEP = [0.55, 0.59, 0.60, 0.65]

DEFAULT_SEEDS = list(range(1, 11))


# =============================================================================
# Git Hash Utility
# =============================================================================

def get_git_hash() -> str:
    """Get current git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(_PROJECT_ROOT)
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


# =============================================================================
# Scenario Building
# =============================================================================

def build_capacity_profile(total_days: int, crunch_start: int, crunch_end: int, ratio: float) -> Dict:
    """Build capacity profile with crunch window."""
    profile = {}
    for day in range(total_days):
        if crunch_start <= day <= crunch_end:
            profile[str(day)] = ratio
        else:
            profile[str(day)] = 1.0
    return profile


def build_exp13_config(
    q_model_path: Path,
    lambda_value: float,
    guardrails_enabled: bool = True,
    epsilon_schedule: Optional[Dict] = None,
    scenario_config: Optional[Dict] = None
) -> Dict:
    """Build configuration for EXP13 (Bandit-Augmented Allocator)."""
    scenario = scenario_config or SCENARIOS["crunch_d5_d10"]
    capacity_profile = build_capacity_profile(
        scenario["total_days"],
        scenario["crunch_start"],
        scenario["crunch_end"],
        scenario["ratio"]
    )

    eps_schedule = epsilon_schedule or {
        "kind": "piecewise",
        "warmup_days": 2,
        "eps_start": 0.15,
        "eps_end": 0.03
    }

    return {
        "mode": "proactive_quota",
        "lookahead_days": 3,
        "buffer_ratio": 1.05,
        "weights": {"urgency": 20.0, "profile": 2.0},
        "penalty_per_fail": 150.0,
        # Risk model (for risk_mode_on signal)
        "use_risk_model": True,
        "risk_model_path": str(RISK_MODEL_PATH),
        "delta_on": 0.826,
        "delta_off": 0.496,
        # Compute settings (fallback)
        "base_compute": 60,
        "high_compute": 300,
        # EXP13: Bandit-Augmented Allocator
        "use_learned_allocator": True,
        "allocator_type": "bandit_augmented",
        "allocator_model_path": str(q_model_path),
        "allocator_lambda": lambda_value,
        "allocator_policy": "epsilon_greedy",
        "epsilon_schedule": eps_schedule,
        "guardrails": {"enabled": guardrails_enabled},
        # Capacity profile
        "capacity_profile": capacity_profile,
    }


# =============================================================================
# Run Directory Naming (Parallel-Safe)
# =============================================================================

def build_run_dir(
    base_results_dir: Path,
    exp_id: str,
    variant: str,
    scenario_id: str,
    seed: int,
    git_hash: str
) -> Path:
    """Build unique run directory path.

    Format: {base}/{exp_id}/{variant}/{scenario_id}/seed_{seed}_{git_hash}_{uuid}
    """
    run_uuid = str(uuid.uuid4())[:8]
    run_name = f"seed_{seed}_{git_hash}_{run_uuid}"
    return base_results_dir / exp_id / variant / scenario_id / run_name


# =============================================================================
# Single Experiment Runner
# =============================================================================

def run_single_experiment(
    config: Dict,
    seed: int,
    exp_name: str,
    run_dir: Path,
    git_hash: str
) -> Tuple[Dict, List[Dict]]:
    """Run a single experiment with given config and seed."""
    run_dir.mkdir(parents=True, exist_ok=True)
    capacity_profile = config.pop("capacity_profile", {})
    try:
        # Load data
        with open(DATA_PATH, 'r') as f:
            data = json.load(f)

        # Inject capacity_profile into data metadata
        if "metadata" not in data:
            data["metadata"] = {}
        data["metadata"]["capacity_profile"] = capacity_profile

        # Run simulation
        sim = RollingHorizonSimulator(
            data_source=data,
            strategy_config=config,
            seed=seed,
            verbose=False,
            base_dir=str(run_dir),
            scenario_name="DEFAULT",
            strategy_name=exp_name,
        )

        metrics = sim.run_simulation()

        # Save allocator config dump (EXP13 specific)
        if sim.bandit_allocator is not None:
            sim.bandit_allocator.save_config_dump(git_hash=git_hash)

        # Save results
        results = {
            "experiment": exp_name,
            "seed": seed,
            "git_hash": git_hash,
            "timestamp": datetime.now().isoformat(),
            "config": {k: v for k, v in config.items()},
            "capacity_profile": capacity_profile,
            "metrics": metrics,
        }

        results_path = run_dir / "DEFAULT" / exp_name / "simulation_results.json"
        results_path.parent.mkdir(parents=True, exist_ok=True)
        with open(results_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        return metrics, sim.daily_stats
    except Exception:
        # Keep failed learning-allocator runs from polluting the result tree.
        shutil.rmtree(run_dir, ignore_errors=True)
        raise
    finally:
        config["capacity_profile"] = capacity_profile


# =============================================================================
# Results Aggregation
# =============================================================================

def aggregate_results(all_results: List[Tuple[Dict, List[Dict]]]) -> Dict:
    """Aggregate results across seeds."""
    import numpy as np

    if not all_results:
        return {}

    agg = {}
    skip_keys = {"run_id", "scenario", "strategy", "base_dir", "run_dir"}

    # Aggregate metrics
    metrics_keys = all_results[0][0].keys()
    for key in metrics_keys:
        if key in skip_keys:
            continue
        values = [r[0].get(key, 0) for r in all_results if r[0].get(key) is not None]
        if values and all(isinstance(v, (int, float)) for v in values):
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
        agg["compute_total"] = {
            "mean": float(np.mean(compute_totals)),
            "std": float(np.std(compute_totals)),
        }

    # EXP13: Aggregate allocator-specific metrics
    guard_triggers = []
    exploration_rates = []
    action_distributions = {30: 0, 60: 0, 120: 0, 300: 0}
    total_days = 0

    for _, daily_stats in all_results:
        for d in daily_stats:
            total_days += 1
            action = d.get("allocator_action_final", -1)
            if action in action_distributions:
                action_distributions[action] += 1
            if d.get("allocator_exploration", 0):
                exploration_rates.append(1)
            else:
                exploration_rates.append(0)
            guards = d.get("allocator_triggered_guards", "")
            if guards:
                guard_triggers.append(guards)

    if total_days > 0:
        agg["action_distribution"] = {
            str(k): v / total_days for k, v in action_distributions.items()
        }
        agg["exploration_rate"] = float(np.mean(exploration_rates)) if exploration_rates else 0.0
        agg["guard_trigger_rate"] = len(guard_triggers) / total_days

    return agg


# =============================================================================
# Main Experiment Runner
# =============================================================================

def run_exp13_variant(
    variant: str,
    scenario_id: str,
    seeds: List[int],
    q_model_path: Path,
    lambda_value: float = 0.05,
    parallel: bool = True
) -> Dict:
    """Run EXP13 variant across all seeds."""
    import numpy as np
    from multiprocessing import Pool, cpu_count

    git_hash = get_git_hash()
    guardrails_enabled = (variant == "EXP13a")

    # Get scenario config
    if scenario_id.startswith("ratio_"):
        ratio = float(scenario_id.split("_")[1])
        scenario_config = {
            "ratio": ratio,
            "crunch_start": 5,
            "crunch_end": 10,
            "total_days": 12,
        }
    else:
        scenario_config = SCENARIOS.get(scenario_id, SCENARIOS["crunch_d5_d10"])

    print(f"\n{'='*60}")
    print(f"Running {variant} - {scenario_id}")
    print(f"  Guardrails: {guardrails_enabled}")
    print(f"  Seeds: {seeds}")
    print(f"  Git hash: {git_hash}")
    print(f"{'='*60}")

    all_results = []

    for seed in seeds:
        config = build_exp13_config(
            q_model_path=q_model_path,
            lambda_value=lambda_value,
            guardrails_enabled=guardrails_enabled,
            scenario_config=scenario_config
        )

        run_dir = build_run_dir(
            base_results_dir=RESULTS_DIR,
            exp_id="EXP13",
            variant=variant,
            scenario_id=scenario_id,
            seed=seed,
            git_hash=git_hash
        )

        print(f"  Seed {seed}: {run_dir}")
        metrics, daily_stats = run_single_experiment(
            config=config,
            seed=seed,
            exp_name=variant,
            run_dir=run_dir,
            git_hash=git_hash
        )

        sr = metrics.get("service_rate_within_window", 0) * 100
        failures = metrics.get("deadline_failure_count", 0)
        compute = sum(d.get("compute_limit_seconds", 60) for d in daily_stats)
        print(f"    SR: {sr:.2f}%, Failures: {failures}, Compute: {compute}s")

        all_results.append((metrics, daily_stats))

    # Aggregate
    agg = aggregate_results(all_results)
    return agg


# =============================================================================
# HPC Job Script Generator
# =============================================================================

def generate_hpc_scripts(output_dir: Path, seeds: List[int], scenarios: List[str]):
    """Generate HPC job array scripts for parallel execution."""
    output_dir.mkdir(parents=True, exist_ok=True)
    git_hash = get_git_hash()

    for variant in ["EXP13a", "EXP13b"]:
        script_path = output_dir / f"submit_{variant.lower()}.sh"

        # Calculate total jobs
        n_jobs = len(seeds) * len(scenarios)

        script_content = f'''#!/bin/bash
set -euo pipefail
#BSUB -J {variant}[1-{n_jobs}]
#BSUB -q hpc
#BSUB -W 2:00
#BSUB -n 4
#BSUB -R "rusage[mem=4GB]"
#BSUB -o logs/{variant}_%J_%I.out
#BSUB -e logs/{variant}_%J_%I.err

# EXP13: {variant} - Bandit-Augmented Allocator
# Git hash: {git_hash}
# Generated: {datetime.now().isoformat()}

PROJECT_ROOT="{_PROJECT_ROOT}"
PYTHON_BIN="${{PYTHON_BIN:-python3}}"

mkdir -p "${{PROJECT_ROOT}}/logs"
cd "${{PROJECT_ROOT}}"
export PYTHONPATH="${{PROJECT_ROOT}}:${{PROJECT_ROOT}}/code:${{PYTHONPATH:-}}"
export VRP_MAX_TRIPS_PER_VEHICLE=2

# Map job array index to (seed, scenario)
SEEDS=({' '.join(map(str, seeds))})
SCENARIOS=({' '.join(scenarios)})

N_SEEDS=${{#SEEDS[@]}}
N_SCENARIOS=${{#SCENARIOS[@]}}

IDX=$((LSB_JOBINDEX - 1))
SEED_IDX=$((IDX / N_SCENARIOS))
SCENARIO_IDX=$((IDX % N_SCENARIOS))

SEED=${{SEEDS[$SEED_IDX]}}
SCENARIO=${{SCENARIOS[$SCENARIO_IDX]}}

echo "Job $LSB_JOBINDEX: variant={variant}, seed=$SEED, scenario=$SCENARIO"

"$PYTHON_BIN" code/experiments/exp13_bandit_allocator.py \\
    --variant {variant} \\
    --scenario $SCENARIO \\
    --seed $SEED \\
    --single-run
'''
        with open(script_path, 'w') as f:
            f.write(script_content)

        print(f"Generated: {script_path}")

    # Also generate a master submit script
    master_path = output_dir / "submit_all_exp13.sh"
    master_content = f'''#!/bin/bash
# Submit all EXP13 jobs
# Git hash: {git_hash}

mkdir -p logs

echo "Submitting EXP13a (with guardrails)..."
bsub < submit_exp13a.sh

echo "Submitting EXP13b (no guardrails - ablation)..."
bsub < submit_exp13b.sh

echo "Done. Check job status with: bjobs -w"
'''
    with open(master_path, 'w') as f:
        f.write(master_content)

    print(f"Generated: {master_path}")


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="EXP13: Bandit-Augmented Allocator")
    parser.add_argument("--variant", type=str, choices=["EXP13a", "EXP13b"],
                        help="Experiment variant")
    parser.add_argument("--scenario", type=str, default="crunch_d5_d10",
                        help="Scenario ID")
    parser.add_argument("--seed", type=int, help="Single seed (for HPC array)")
    parser.add_argument("--seeds", type=int, default=10,
                        help="Number of seeds (1 to N)")
    parser.add_argument("--lambda", dest="lambda_val", type=float, default=0.05,
                        help="Lambda for compute cost")
    parser.add_argument("--q-model", type=str, default=None,
                        help="Path to Q-model")
    parser.add_argument("--single-run", action="store_true",
                        help="Run single seed (for HPC)")
    parser.add_argument("--test", action="store_true",
                        help="Quick test with 2 seeds")
    parser.add_argument("--generate-hpc", action="store_true",
                        help="Generate HPC job scripts")
    args = parser.parse_args()

    if args.generate_hpc:
        scenarios = list(SCENARIOS.keys()) + [f"ratio_{r}" for r in RATIO_SWEEP]
        generate_hpc_scripts(
            output_dir=_PROJECT_ROOT / "hpc_jobs" / "exp13",
            seeds=DEFAULT_SEEDS,
            scenarios=scenarios
        )
        return

    # Find Q-model
    q_model_path = Path(args.q_model) if args.q_model else DEFAULT_Q_MODEL
    if not q_model_path.exists():
        print(f"Error: Q-model not found: {q_model_path}")
        sys.exit(1)

    # Determine seeds
    if args.single_run and args.seed:
        seeds = [args.seed]
    elif args.test:
        seeds = [1, 2]
    else:
        seeds = list(range(1, args.seeds + 1))

    # Run experiments
    if args.single_run:
        # Single run mode (for HPC)
        variant = args.variant or "EXP13a"
        run_exp13_variant(
            variant=variant,
            scenario_id=args.scenario,
            seeds=seeds,
            q_model_path=q_model_path,
            lambda_value=args.lambda_val
        )
    else:
        # Full experiment mode
        results = {}
        for variant in ["EXP13a", "EXP13b"]:
            results[variant] = run_exp13_variant(
                variant=variant,
                scenario_id=args.scenario,
                seeds=seeds,
                q_model_path=q_model_path,
                lambda_value=args.lambda_val
            )

        # Print summary
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        for variant, agg in results.items():
            sr = agg.get("service_rate_within_window", {})
            failures = agg.get("deadline_failure_count", {})
            compute = agg.get("compute_total", {})
            print(f"\n{variant}:")
            print(f"  SR: {sr.get('mean', 0)*100:.2f}% ± {sr.get('std', 0)*100:.2f}%")
            print(f"  Failures: {failures.get('mean', 0):.1f} ± {failures.get('std', 0):.1f}")
            print(f"  Compute: {compute.get('mean', 0):.0f}s ± {compute.get('std', 0):.0f}s")


if __name__ == "__main__":
    main()
