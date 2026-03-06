#!/usr/bin/env python3
"""
EXP14: Sparse Fail-Safe Bandit (SFB) Evaluation

Extends EXP13b with sparse fail-safe logic:
- EXP14a: Default thresholds
- EXP14b: Stricter thresholds (rarer firing)
- EXP14c: Looser thresholds (more protective)

Key differences from EXP13a:
- No crunch_guard (bandit handles crunch)
- One-step escalation only (30->60->120->300)
- Sparse triggering based on observed degradation
"""

import os
import sys
import json
import argparse
import subprocess
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

os.environ.setdefault("VRP_MAX_TRIPS_PER_VEHICLE", "2")

_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_CODE_DIR = _PROJECT_ROOT / "code"
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

from simulation.rolling_horizon_integrated import RollingHorizonIntegrated as Simulator

# Paths
DATA_PATH = _PROJECT_ROOT / "data" / "processed" / "multiday_benchmark_herlev.json"
RESULTS_DIR = _PROJECT_ROOT / "data" / "results"
MODELS_DIR = _PROJECT_ROOT / "data" / "allocator" / "models"
RISK_MODEL_PATH = _PROJECT_ROOT / "models" / "risk_model.joblib"
DEFAULT_Q_MODEL = MODELS_DIR / "allocator_Q_lambda_0.05_hgb.joblib"

# Scenarios
SCENARIOS = {
    "crunch_d5_d10": {"ratio": 0.59, "crunch_start": 5, "crunch_end": 10, "total_days": 12},
}

DEFAULT_SEEDS = list(range(1, 11))


def get_git_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(_PROJECT_ROOT)
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def build_capacity_profile(total_days, crunch_start, crunch_end, ratio):
    profile = {}
    for day in range(total_days):
        if crunch_start <= day <= crunch_end:
            profile[str(day)] = ratio
        else:
            profile[str(day)] = 1.0
    return profile


# EXP14 variant configurations
FAIL_SAFE_CONFIGS = {
    "EXP14a": {  # Default thresholds
        "prev_failures_ge": 1,
        "prev_drop_rate_ge": 0.25,
        "prev_vrp_dropped_ge": 10,
        "mandatory_count_ge": 80,
        "mandatory_ratio_ge": 0.20,
        "consecutive_bad_days_ge": 2,
    },
    "EXP14b": {  # Stricter (rarer firing)
        "prev_failures_ge": 2,
        "prev_drop_rate_ge": 0.30,
        "prev_vrp_dropped_ge": 15,
        "mandatory_count_ge": 100,
        "mandatory_ratio_ge": 0.25,
        "consecutive_bad_days_ge": 2,
    },
    "EXP14c": {  # Looser (more protective)
        "prev_failures_ge": 1,
        "prev_drop_rate_ge": 0.20,
        "prev_vrp_dropped_ge": 8,
        "mandatory_count_ge": 60,
        "mandatory_ratio_ge": 0.15,
        "consecutive_bad_days_ge": 1,
    },
}


def build_exp14_config(variant: str, q_model_path: Path, scenario_config: Dict) -> Dict:
    """Build EXP14 configuration."""
    capacity_profile = build_capacity_profile(
        scenario_config["total_days"],
        scenario_config["crunch_start"],
        scenario_config["crunch_end"],
        scenario_config["ratio"]
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
        "use_learned_allocator": True,
        "allocator_type": "sparse_fail_safe",
        "allocator_model_path": str(q_model_path),
        "allocator_lambda": 0.05,
        "allocator_policy": "epsilon_greedy",
        "epsilon_schedule": {"kind": "piecewise", "warmup_days": 2, "eps_start": 0.15, "eps_end": 0.03},
        "fail_safe": FAIL_SAFE_CONFIGS.get(variant, FAIL_SAFE_CONFIGS["EXP14a"]),
        "capacity_profile": capacity_profile,
    }


def run_single(config: Dict, seed: int, variant: str, run_dir: Path, git_hash: str):
    """Run single experiment."""
    run_dir.mkdir(parents=True, exist_ok=True)

    with open(DATA_PATH, 'r') as f:
        data = json.load(f)

    capacity_profile = config.pop("capacity_profile", {})
    data["metadata"]["capacity_profile"] = capacity_profile

    sim = Simulator(
        data_source=data,
        strategy_config=config,
        seed=seed,
        verbose=False,
        base_dir=str(run_dir),
        scenario_name="DEFAULT",
        strategy_name=variant,
    )

    metrics = sim.run_simulation()

    if sim.bandit_allocator is not None:
        sim.bandit_allocator.save_config_dump(git_hash=git_hash)

    config["capacity_profile"] = capacity_profile
    return metrics, sim.daily_stats


def run_exp14(variant: str, seeds: List[int], scenario_id: str = "crunch_d5_d10"):
    """Run EXP14 variant."""
    import numpy as np

    git_hash = get_git_hash()
    scenario = SCENARIOS.get(scenario_id, SCENARIOS["crunch_d5_d10"])

    print(f"\n{'='*50}")
    print(f"Running {variant} - {scenario_id}")
    print(f"Seeds: {seeds}, Git: {git_hash}")
    print(f"{'='*50}")

    results = []
    for seed in seeds:
        config = build_exp14_config(variant, DEFAULT_Q_MODEL, scenario)
        run_uuid = str(uuid.uuid4())[:8]
        run_dir = RESULTS_DIR / "EXP14" / variant / scenario_id / f"seed_{seed}_{git_hash}_{run_uuid}"

        print(f"  Seed {seed}...", end=" ")
        try:
            metrics, daily_stats = run_single(config, seed, variant, run_dir, git_hash)
        except Exception:
            if run_dir.exists():
                import shutil
                shutil.rmtree(run_dir, ignore_errors=True)
            raise

        failures = sum(d["failures"] for d in daily_stats)
        compute = sum(d["compute_limit_seconds"] for d in daily_stats)
        print(f"Failures: {failures}, Compute: {compute}s")

        results.append((metrics, daily_stats))

    # Summary
    failures_list = [sum(d["failures"] for d in ds) for _, ds in results]
    compute_list = [sum(d["compute_limit_seconds"] for d in ds) for _, ds in results]

    print(f"\n{variant} Summary:")
    print(f"  Failures: {np.mean(failures_list):.1f} ± {np.std(failures_list):.1f}")
    print(f"  Compute:  {np.mean(compute_list):.0f}s ± {np.std(compute_list):.0f}s")

    return results


def generate_hpc_scripts(variants: List[str], seeds: List[int], scenario_id: str = "crunch_d5_d10"):
    """Generate HPC job scripts for EXP14."""
    scripts_dir = _PROJECT_ROOT / "hpc_scripts" / "exp14"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    for variant in variants:
        script_path = scripts_dir / f"run_{variant.lower()}_{scenario_id}.sh"
        script_content = f'''#!/bin/bash
set -euo pipefail
#BSUB -J {variant}_{scenario_id}[1-{len(seeds)}]
#BSUB -q hpc
#BSUB -W 4:00
#BSUB -n 4
#BSUB -R "rusage[mem=8GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o "{_PROJECT_ROOT}/hpc_logs/exp14/{variant}_%J_%I.out"
#BSUB -e "{_PROJECT_ROOT}/hpc_logs/exp14/{variant}_%J_%I.err"

# EXP14: {variant} - Sparse Fail-Safe Bandit
# Scenario: {scenario_id}

PROJECT_ROOT="{_PROJECT_ROOT}"
PYTHON_BIN="${{PYTHON_BIN:-/usr/bin/python3}}"
mkdir -p "${{PROJECT_ROOT}}/hpc_logs/exp14"
cd "${{PROJECT_ROOT}}"
export PYTHONPATH="${{PROJECT_ROOT}}:${{PROJECT_ROOT}}/code:${{PYTHONPATH:-}}"
export VRP_MAX_TRIPS_PER_VEHICLE=2

SEEDS=({' '.join(str(s) for s in seeds)})
SEED=${{SEEDS[$LSB_JOBINDEX-1]}}
"${{PYTHON_BIN}}" "{_THIS_FILE}" --variant {variant} --seed "$SEED" --scenario {scenario_id}
'''
        with open(script_path, 'w') as f:
            f.write(script_content)
        print(f"Generated: {script_path}")

    # Master submission script
    master_path = scripts_dir / f"submit_all_{scenario_id}.sh"
    master_content = f'''#!/bin/bash
# Submit all EXP14 variants for {scenario_id}

cd "{scripts_dir}"

'''
    for variant in variants:
        master_content += f'bsub < run_{variant.lower()}_{scenario_id}.sh\n'

    with open(master_path, 'w') as f:
        f.write(master_content)
    print(f"Generated master script: {master_path}")

    # Create log directory
    log_dir = _PROJECT_ROOT / "hpc_logs" / "exp14"
    log_dir.mkdir(parents=True, exist_ok=True)
    print(f"Log directory: {log_dir}")


def main():
    parser = argparse.ArgumentParser(description="EXP14: Sparse Fail-Safe Bandit")
    parser.add_argument("--variant", type=str, choices=["EXP14a", "EXP14b", "EXP14c", "all"],
                        default="all", help="Which variant to run")
    parser.add_argument("--seed", type=int, default=None, help="Single seed (for HPC array jobs)")
    parser.add_argument("--seeds", type=str, default=None, help="Comma-separated seeds")
    parser.add_argument("--scenario", type=str, default="crunch_d5_d10", help="Scenario ID")
    parser.add_argument("--generate-hpc", action="store_true", help="Generate HPC scripts only")
    args = parser.parse_args()

    # Determine seeds
    if args.seed is not None:
        seeds = [args.seed]
    elif args.seeds is not None:
        seeds = [int(s.strip()) for s in args.seeds.split(",")]
    else:
        seeds = DEFAULT_SEEDS

    # Determine variants
    if args.variant == "all":
        variants = ["EXP14a", "EXP14b", "EXP14c"]
    else:
        variants = [args.variant]

    # Generate HPC scripts only
    if args.generate_hpc:
        generate_hpc_scripts(variants, seeds, args.scenario)
        return

    # Run experiments
    for variant in variants:
        run_exp14(variant, seeds, args.scenario)


if __name__ == "__main__":
    main()
