#!/usr/bin/env python3
"""
EXP15: OOD Robustness Evaluation for EXP13b

Track A (Mainline OOD):
- EXP15a: Capacity ratio sweep + window shift
- EXP15b: Order volume and spatial noise perturbation
- EXP15c: Day-index feature ablation

Track B (Optional):
- EXP15d: Percentile-based sparse fail-safe

This script does NOT modify EXP13b logic; it only varies scenario parameters.
"""

import os
import sys
import json
import argparse
import subprocess
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from itertools import product

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


# =============================================================================
# EXP15a: Ratio Sweep OOD
# =============================================================================

EXP15A_GRID = {
    "crunch_ratio": [0.45, 0.50, 0.55, 0.59, 0.60, 0.62, 0.65, 0.70],
    "crunch_window_shift": [-2, -1, 0, 1, 2],
}

def build_capacity_profile_15a(ratio: float, window_shift: int, total_days: int = 12):
    """Build capacity profile with shifted crunch window."""
    base_start, base_end = 5, 10
    crunch_start = max(0, base_start + window_shift)
    crunch_end = min(total_days - 1, base_end + window_shift)

    profile = {}
    for day in range(total_days):
        if crunch_start <= day <= crunch_end:
            profile[str(day)] = ratio
        else:
            profile[str(day)] = 1.0
    return profile, crunch_start, crunch_end


def build_exp13b_config(q_model_path: Path, epsilon_schedule: Optional[Dict] = None) -> Dict:
    """Build EXP13b configuration (frozen, no modifications)."""
    eps_schedule = epsilon_schedule or {
        "kind": "piecewise", "warmup_days": 2, "eps_start": 0.15, "eps_end": 0.03
    }
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
        "allocator_type": "bandit_augmented",
        "allocator_model_path": str(q_model_path),
        "allocator_lambda": 0.05,
        "allocator_policy": "epsilon_greedy",
        "epsilon_schedule": eps_schedule,
        "enable_guardrails": False,
        "guardrails": {"enabled": False},
    }


def run_single_15a(ratio: float, window_shift: int, seed: int, run_dir: Path, git_hash: str):
    """Run single EXP15a experiment."""
    run_dir.mkdir(parents=True, exist_ok=True)

    with open(DATA_PATH, 'r') as f:
        data = json.load(f)

    capacity_profile, crunch_start, crunch_end = build_capacity_profile_15a(ratio, window_shift)
    data["metadata"]["capacity_profile"] = capacity_profile

    config = build_exp13b_config(DEFAULT_Q_MODEL)

    # Add OOD labels for logging
    ood_labels = {
        "scenario_variant_id": f"ratio_{ratio}_shift_{window_shift}",
        "crunch_ratio_setting": ratio,
        "crunch_window_shift_setting": window_shift,
        "crunch_start": crunch_start,
        "crunch_end": crunch_end,
    }

    sim = Simulator(
        data_source=data,
        strategy_config=config,
        seed=seed,
        verbose=False,
        base_dir=str(run_dir),
        scenario_name="DEFAULT",
        strategy_name="EXP15a",
    )

    metrics = sim.run_simulation()

    # Save OOD labels
    with open(run_dir / "DEFAULT" / "EXP15a" / "ood_labels.json", 'w') as f:
        json.dump(ood_labels, f, indent=2)

    if sim.bandit_allocator is not None:
        sim.bandit_allocator.save_config_dump(git_hash=git_hash)

    return metrics, sim.daily_stats, ood_labels


def run_exp15a(ratio: float, window_shift: int, seeds: List[int]):
    """Run EXP15a for a specific ratio and window shift."""
    import numpy as np

    git_hash = get_git_hash()
    variant_id = f"ratio_{ratio}_shift_{window_shift}"

    print(f"\n{'='*50}")
    print(f"EXP15a: {variant_id}")
    print(f"Seeds: {seeds}, Git: {git_hash}")
    print(f"{'='*50}")

    results = []
    for seed in seeds:
        run_uuid = str(uuid.uuid4())[:8]
        run_dir = RESULTS_DIR / "EXP15" / "EXP15a" / variant_id / f"seed_{seed}_{git_hash}_{run_uuid}"

        print(f"  Seed {seed}...", end=" ", flush=True)
        metrics, daily_stats, ood_labels = run_single_15a(ratio, window_shift, seed, run_dir, git_hash)

        failures = sum(d["failures"] for d in daily_stats)
        compute = sum(d["compute_limit_seconds"] for d in daily_stats)
        print(f"Failures: {failures}, Compute: {compute}s")

        results.append((metrics, daily_stats, ood_labels))

    # Summary
    failures_list = [sum(d["failures"] for d in ds) for _, ds, _ in results]
    compute_list = [sum(d["compute_limit_seconds"] for d in ds) for _, ds, _ in results]

    print(f"\n{variant_id} Summary:")
    print(f"  Failures: {np.mean(failures_list):.1f} ± {np.std(failures_list):.1f}")
    print(f"  Compute:  {np.mean(compute_list):.0f}s ± {np.std(compute_list):.0f}s")

    return results


# =============================================================================
# EXP15b: Order Volume and Spatial Noise
# =============================================================================

EXP15B_GRID = {
    "order_count_multiplier": [0.9, 1.0, 1.1, 1.2],
    "spatial_jitter_km": [0, 1, 3, 5],
}


def apply_order_perturbations(data: Dict, multiplier: float, jitter_km: float, seed: int) -> Dict:
    """Apply order count and spatial perturbations to data."""
    import random
    import copy

    rng = random.Random(seed)
    data = copy.deepcopy(data)

    # Apply order count multiplier (subsample or duplicate orders)
    if multiplier != 1.0:
        for day_key in data.get("days", {}):
            day_data = data["days"][day_key]
            if "orders" in day_data:
                orders = day_data["orders"]
                target_count = int(len(orders) * multiplier)

                if multiplier < 1.0:
                    # Subsample
                    day_data["orders"] = rng.sample(orders, min(target_count, len(orders)))
                else:
                    # Duplicate some orders with new IDs
                    extra_needed = target_count - len(orders)
                    extra_orders = []
                    for i in range(extra_needed):
                        orig = rng.choice(orders)
                        new_order = copy.deepcopy(orig)
                        new_order["order_id"] = f"{orig['order_id']}_dup_{i}"
                        extra_orders.append(new_order)
                    day_data["orders"] = orders + extra_orders

    # Apply spatial jitter
    if jitter_km > 0:
        for day_key in data.get("days", {}):
            day_data = data["days"][day_key]
            if "orders" in day_data:
                for order in day_data["orders"]:
                    if "latitude" in order and "longitude" in order:
                        # ~0.009 degrees per km at Danish latitudes
                        lat_jitter = rng.gauss(0, jitter_km * 0.009)
                        lon_jitter = rng.gauss(0, jitter_km * 0.009)
                        order["latitude"] += lat_jitter
                        order["longitude"] += lon_jitter

    return data


def run_single_15b(multiplier: float, jitter_km: float, seed: int, run_dir: Path, git_hash: str):
    """Run single EXP15b experiment."""
    run_dir.mkdir(parents=True, exist_ok=True)

    with open(DATA_PATH, 'r') as f:
        data = json.load(f)

    # Apply perturbations
    data = apply_order_perturbations(data, multiplier, jitter_km, seed)

    # Use default crunch scenario
    capacity_profile, _, _ = build_capacity_profile_15a(0.59, 0)
    data["metadata"]["capacity_profile"] = capacity_profile

    config = build_exp13b_config(DEFAULT_Q_MODEL)

    ood_labels = {
        "scenario_variant_id": f"mult_{multiplier}_jitter_{jitter_km}",
        "order_count_multiplier": multiplier,
        "spatial_jitter_km": jitter_km,
    }

    sim = Simulator(
        data_source=data,
        strategy_config=config,
        seed=seed,
        verbose=False,
        base_dir=str(run_dir),
        scenario_name="DEFAULT",
        strategy_name="EXP15b",
    )

    metrics = sim.run_simulation()

    with open(run_dir / "DEFAULT" / "EXP15b" / "ood_labels.json", 'w') as f:
        json.dump(ood_labels, f, indent=2)

    if sim.bandit_allocator is not None:
        sim.bandit_allocator.save_config_dump(git_hash=git_hash)

    return metrics, sim.daily_stats, ood_labels


def run_exp15b(multiplier: float, jitter_km: float, seeds: List[int]):
    """Run EXP15b for specific perturbation settings."""
    import numpy as np

    git_hash = get_git_hash()
    variant_id = f"mult_{multiplier}_jitter_{jitter_km}"

    print(f"\n{'='*50}")
    print(f"EXP15b: {variant_id}")
    print(f"Seeds: {seeds}, Git: {git_hash}")
    print(f"{'='*50}")

    results = []
    for seed in seeds:
        run_uuid = str(uuid.uuid4())[:8]
        run_dir = RESULTS_DIR / "EXP15" / "EXP15b" / variant_id / f"seed_{seed}_{git_hash}_{run_uuid}"

        print(f"  Seed {seed}...", end=" ", flush=True)
        metrics, daily_stats, ood_labels = run_single_15b(multiplier, jitter_km, seed, run_dir, git_hash)

        failures = sum(d["failures"] for d in daily_stats)
        compute = sum(d["compute_limit_seconds"] for d in daily_stats)
        print(f"Failures: {failures}, Compute: {compute}s")

        results.append((metrics, daily_stats, ood_labels))

    failures_list = [sum(d["failures"] for d in ds) for _, ds, _ in results]
    compute_list = [sum(d["compute_limit_seconds"] for d in ds) for _, ds, _ in results]

    print(f"\n{variant_id} Summary:")
    print(f"  Failures: {np.mean(failures_list):.1f} ± {np.std(failures_list):.1f}")
    print(f"  Compute:  {np.mean(compute_list):.0f}s ± {np.std(compute_list):.0f}s")

    return results


# =============================================================================
# EXP15c: Day-Index Feature Ablation
# =============================================================================

EXP15C_VARIANTS = {
    "full": MODELS_DIR / "allocator_Q_lambda_0.05_hgb.joblib",
    "no_ratio": MODELS_DIR / "allocator_Q_lambda_0.05_hgb_no_ratio.joblib",
    "no_calendar": MODELS_DIR / "allocator_Q_lambda_0.05_hgb_no_calendar.joblib",
    "no_calendar_aug": MODELS_DIR / "allocator_Q_lambda_0.05_hgb_no_calendar_aug.joblib",
}

EXP15C_CONDITIONS = [
    {"ratio": 0.59, "shift": 0},    # ID sanity
    {"ratio": 0.59, "shift": -2},   # Hardest OOD
    {"ratio": 0.55, "shift": -2},   # Pressure + early crunch
    {"ratio": 0.50, "shift": -1},   # Trend validation
    {"ratio": 0.65, "shift": -2},   # Does extra capacity mask leakage?
]


def run_single_15c(variant: str, ratio: float, shift: int, seed: int, run_dir: Path, git_hash: str):
    """Run single EXP15c experiment with a specific model variant and OOD condition."""
    run_dir.mkdir(parents=True, exist_ok=True)

    with open(DATA_PATH, 'r') as f:
        data = json.load(f)

    capacity_profile, crunch_start, crunch_end = build_capacity_profile_15a(ratio, shift)
    data["metadata"]["capacity_profile"] = capacity_profile

    q_model_path = EXP15C_VARIANTS[variant]
    config = build_exp13b_config(q_model_path)

    ood_labels = {
        "scenario_variant_id": f"{variant}_ratio_{ratio}_shift_{shift}",
        "feature_variant": variant,
        "crunch_ratio_setting": ratio,
        "crunch_window_shift_setting": shift,
        "crunch_start": crunch_start,
        "crunch_end": crunch_end,
        "q_model_path": str(q_model_path),
    }

    sim = Simulator(
        data_source=data,
        strategy_config=config,
        seed=seed,
        verbose=False,
        base_dir=str(run_dir),
        scenario_name="DEFAULT",
        strategy_name="EXP15c",
    )

    metrics = sim.run_simulation()

    with open(run_dir / "DEFAULT" / "EXP15c" / "ood_labels.json", 'w') as f:
        json.dump(ood_labels, f, indent=2)

    if sim.bandit_allocator is not None:
        sim.bandit_allocator.save_config_dump(git_hash=git_hash)

    return metrics, sim.daily_stats, ood_labels


def run_exp15c(variant: str, ratio: float, shift: int, seeds: List[int]):
    """Run EXP15c for a specific variant and OOD condition."""
    import numpy as np

    git_hash = get_git_hash()
    variant_id = f"{variant}_ratio_{ratio}_shift_{shift}"

    print(f"\n{'='*50}")
    print(f"EXP15c: {variant_id}")
    print(f"Seeds: {seeds}, Git: {git_hash}")
    print(f"Model: {EXP15C_VARIANTS[variant]}")
    print(f"{'='*50}")

    results = []
    for seed in seeds:
        run_uuid = str(uuid.uuid4())[:8]
        run_dir = RESULTS_DIR / "EXP15" / "EXP15c" / variant_id / f"seed_{seed}_{git_hash}_{run_uuid}"

        print(f"  Seed {seed}...", end=" ", flush=True)
        metrics, daily_stats, ood_labels = run_single_15c(
            variant, ratio, shift, seed, run_dir, git_hash
        )

        failures = sum(d["failures"] for d in daily_stats)
        compute = sum(d["compute_limit_seconds"] for d in daily_stats)
        print(f"Failures: {failures}, Compute: {compute}s")

        results.append((metrics, daily_stats, ood_labels))

    failures_list = [sum(d["failures"] for d in ds) for _, ds, _ in results]
    compute_list = [sum(d["compute_limit_seconds"] for d in ds) for _, ds, _ in results]

    print(f"\n{variant_id} Summary:")
    print(f"  Failures: {np.mean(failures_list):.1f} ± {np.std(failures_list):.1f}")
    print(f"  Compute:  {np.mean(compute_list):.0f}s ± {np.std(compute_list):.0f}s")

    return results


# =============================================================================
# EXP16 Phase B1: Scenario Augmentation Data Collection
# =============================================================================

EXP16B1_GRID = {
    "ratios": [0.55, 0.59, 0.65],
    "shifts": [-2, 0, 2],
    "seeds_per_condition": 5,
}


def run_single_16b1(ratio: float, shift: int, seed: int, epsilon: float,
                    run_dir: Path, git_hash: str):
    """Run single EXP16b1 data collection run with high exploration."""
    run_dir.mkdir(parents=True, exist_ok=True)

    with open(DATA_PATH, 'r') as f:
        data = json.load(f)

    capacity_profile, crunch_start, crunch_end = build_capacity_profile_15a(ratio, shift)
    data["metadata"]["capacity_profile"] = capacity_profile

    q_model_path = EXP15C_VARIANTS["no_calendar"]
    eps_schedule = {"kind": "constant", "eps_start": epsilon, "eps_end": epsilon}
    config = build_exp13b_config(q_model_path, epsilon_schedule=eps_schedule)

    ood_labels = {
        "experiment": "EXP16b1",
        "purpose": "scenario_augmentation_data_collection",
        "feature_variant": "no_calendar",
        "crunch_ratio_setting": ratio,
        "crunch_window_shift_setting": shift,
        "crunch_start": crunch_start,
        "crunch_end": crunch_end,
        "epsilon": epsilon,
        "q_model_path": str(q_model_path),
    }

    sim = Simulator(
        data_source=data,
        strategy_config=config,
        seed=seed,
        verbose=False,
        base_dir=str(run_dir),
        scenario_name="DEFAULT",
        strategy_name="EXP16b1",
    )

    metrics = sim.run_simulation()

    with open(run_dir / "DEFAULT" / "EXP16b1" / "ood_labels.json", 'w') as f:
        json.dump(ood_labels, f, indent=2)

    if sim.bandit_allocator is not None:
        sim.bandit_allocator.save_config_dump(git_hash=git_hash)

    return metrics, sim.daily_stats, ood_labels


def run_exp16b1(ratio: float, shift: int, seed: int, epsilon: float = 0.2):
    """Run EXP16b1 for a specific ratio, shift, and seed."""
    git_hash = get_git_hash()
    variant_id = f"ratio_{ratio}_shift_{shift}"

    run_uuid = str(uuid.uuid4())[:8]
    run_dir = RESULTS_DIR / "EXP16" / "EXP16b1" / variant_id / f"seed_{seed}_{git_hash}_{run_uuid}"

    print(f"EXP16b1: {variant_id}, seed={seed}, epsilon={epsilon}, git={git_hash}")
    metrics, daily_stats, ood_labels = run_single_16b1(
        ratio, shift, seed, epsilon, run_dir, git_hash
    )

    failures = sum(d["failures"] for d in daily_stats)
    compute = sum(d["compute_limit_seconds"] for d in daily_stats)
    print(f"  Failures: {failures}, Compute: {compute}s")

    return metrics, daily_stats, ood_labels


# =============================================================================
# HPC Script Generation
# =============================================================================

def generate_hpc_scripts_15a(seeds: List[int]):
    """Generate HPC scripts for EXP15a ratio sweep."""
    scripts_dir = _PROJECT_ROOT / "hpc_scripts" / "exp15"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    # Create job array for all ratio x shift combinations
    combos = list(product(EXP15A_GRID["crunch_ratio"], EXP15A_GRID["crunch_window_shift"]))

    script_path = scripts_dir / "run_exp15a.sh"
    script_content = f'''#!/bin/bash
set -euo pipefail
#BSUB -J EXP15a[1-{len(combos) * len(seeds)}]
#BSUB -q hpc
#BSUB -W 4:00
#BSUB -n 4
#BSUB -R "rusage[mem=8GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o "{_PROJECT_ROOT}/hpc_logs/exp15/EXP15a_%J_%I.out"
#BSUB -e "{_PROJECT_ROOT}/hpc_logs/exp15/EXP15a_%J_%I.err"

PYTHON_BIN="${{PYTHON_BIN:-python3}}"
export PYTHONPATH="{_PROJECT_ROOT}:{_PROJECT_ROOT}/code:${{PYTHONPATH:-}}"
export VRP_MAX_TRIPS_PER_VEHICLE=2

RATIOS=({' '.join(str(r) for r in EXP15A_GRID["crunch_ratio"])})
SHIFTS=({' '.join(str(s) for s in EXP15A_GRID["crunch_window_shift"])})
SEEDS=({' '.join(str(s) for s in seeds)})

NUM_RATIOS={len(EXP15A_GRID["crunch_ratio"])}
NUM_SHIFTS={len(EXP15A_GRID["crunch_window_shift"])}
NUM_SEEDS={len(seeds)}

IDX=$((LSB_JOBINDEX - 1))
COMBO_IDX=$((IDX / NUM_SEEDS))
SEED_IDX=$((IDX % NUM_SEEDS))

RATIO_IDX=$((COMBO_IDX / NUM_SHIFTS))
SHIFT_IDX=$((COMBO_IDX % NUM_SHIFTS))

RATIO=${{RATIOS[$RATIO_IDX]}}
SHIFT=${{SHIFTS[$SHIFT_IDX]}}
SEED=${{SEEDS[$SEED_IDX]}}

cd "{_PROJECT_ROOT}"
"$PYTHON_BIN" "{_THIS_FILE}" --exp 15a --ratio $RATIO --shift $SHIFT --seed $SEED
'''
    with open(script_path, 'w') as f:
        f.write(script_content)
    print(f"Generated: {script_path}")


def generate_hpc_scripts_15b(seeds: List[int]):
    """Generate HPC scripts for EXP15b perturbation sweep."""
    scripts_dir = _PROJECT_ROOT / "hpc_scripts" / "exp15"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    combos = list(product(EXP15B_GRID["order_count_multiplier"], EXP15B_GRID["spatial_jitter_km"]))

    script_path = scripts_dir / "run_exp15b.sh"
    script_content = f'''#!/bin/bash
set -euo pipefail
#BSUB -J EXP15b[1-{len(combos) * len(seeds)}]
#BSUB -q hpc
#BSUB -W 4:00
#BSUB -n 4
#BSUB -R "rusage[mem=8GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o "{_PROJECT_ROOT}/hpc_logs/exp15/EXP15b_%J_%I.out"
#BSUB -e "{_PROJECT_ROOT}/hpc_logs/exp15/EXP15b_%J_%I.err"

PYTHON_BIN="${{PYTHON_BIN:-python3}}"
export PYTHONPATH="{_PROJECT_ROOT}:{_PROJECT_ROOT}/code:${{PYTHONPATH:-}}"
export VRP_MAX_TRIPS_PER_VEHICLE=2

MULTS=({' '.join(str(m) for m in EXP15B_GRID["order_count_multiplier"])})
JITTERS=({' '.join(str(j) for j in EXP15B_GRID["spatial_jitter_km"])})
SEEDS=({' '.join(str(s) for s in seeds)})

NUM_MULTS={len(EXP15B_GRID["order_count_multiplier"])}
NUM_JITTERS={len(EXP15B_GRID["spatial_jitter_km"])}
NUM_SEEDS={len(seeds)}

IDX=$((LSB_JOBINDEX - 1))
COMBO_IDX=$((IDX / NUM_SEEDS))
SEED_IDX=$((IDX % NUM_SEEDS))

MULT_IDX=$((COMBO_IDX / NUM_JITTERS))
JITTER_IDX=$((COMBO_IDX % NUM_JITTERS))

MULT=${{MULTS[$MULT_IDX]}}
JITTER=${{JITTERS[$JITTER_IDX]}}
SEED=${{SEEDS[$SEED_IDX]}}

cd "{_PROJECT_ROOT}"
"$PYTHON_BIN" "{_THIS_FILE}" --exp 15b --multiplier $MULT --jitter $JITTER --seed $SEED
'''
    with open(script_path, 'w') as f:
        f.write(script_content)
    print(f"Generated: {script_path}")


def generate_hpc_scripts_15c(seeds: List[int]):
    """Generate HPC scripts for EXP15c feature ablation."""
    scripts_dir = _PROJECT_ROOT / "hpc_scripts" / "exp15"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    variants = list(EXP15C_VARIANTS.keys())
    conditions = EXP15C_CONDITIONS
    n_variants = len(variants)
    n_conditions = len(conditions)
    n_seeds = len(seeds)
    total_jobs = n_variants * n_conditions * n_seeds

    # Build bash arrays for conditions
    ratios_str = ' '.join(str(c["ratio"]) for c in conditions)
    shifts_str = ' '.join(str(c["shift"]) for c in conditions)
    variants_str = ' '.join(variants)
    seeds_str = ' '.join(str(s) for s in seeds)

    script_path = scripts_dir / "run_exp15c.sh"
    script_content = f'''#!/bin/bash
set -euo pipefail
#BSUB -J EXP15c[1-{total_jobs}]
#BSUB -q hpc
#BSUB -W 4:00
#BSUB -n 4
#BSUB -R "rusage[mem=8GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o "{_PROJECT_ROOT}/hpc_logs/exp15/EXP15c_%J_%I.out"
#BSUB -e "{_PROJECT_ROOT}/hpc_logs/exp15/EXP15c_%J_%I.err"

PYTHON_BIN="${{PYTHON_BIN:-python3}}"
export PYTHONPATH="{_PROJECT_ROOT}:{_PROJECT_ROOT}/code:${{PYTHONPATH:-}}"
export VRP_MAX_TRIPS_PER_VEHICLE=2

VARIANTS=({variants_str})
RATIOS=({ratios_str})
SHIFTS=({shifts_str})
SEEDS=({seeds_str})

NUM_VARIANTS={n_variants}
NUM_CONDITIONS={n_conditions}
NUM_SEEDS={n_seeds}

IDX=$((LSB_JOBINDEX - 1))
VARIANT_IDX=$((IDX / (NUM_CONDITIONS * NUM_SEEDS)))
REMAINDER=$((IDX % (NUM_CONDITIONS * NUM_SEEDS)))
COND_IDX=$((REMAINDER / NUM_SEEDS))
SEED_IDX=$((REMAINDER % NUM_SEEDS))

VARIANT=${{VARIANTS[$VARIANT_IDX]}}
RATIO=${{RATIOS[$COND_IDX]}}
SHIFT=${{SHIFTS[$COND_IDX]}}
SEED=${{SEEDS[$SEED_IDX]}}

cd "{_PROJECT_ROOT}"
"$PYTHON_BIN" "{_THIS_FILE}" --exp 15c --variant $VARIANT --ratio $RATIO --shift $SHIFT --seed $SEED
'''
    with open(script_path, 'w') as f:
        f.write(script_content)
    print(f"Generated: {script_path} ({total_jobs} jobs)")


def generate_all_hpc_scripts(seeds: List[int]):
    """Generate all HPC scripts."""
    log_dir = _PROJECT_ROOT / "hpc_logs" / "exp15"
    log_dir.mkdir(parents=True, exist_ok=True)

    generate_hpc_scripts_15a(seeds)
    generate_hpc_scripts_15b(seeds)
    generate_hpc_scripts_15c(seeds)

    # Master submission script
    scripts_dir = _PROJECT_ROOT / "hpc_scripts" / "exp15"
    master_path = scripts_dir / "submit_all.sh"
    master_content = f'''#!/bin/bash
cd "{scripts_dir}"
bsub < run_exp15a.sh
bsub < run_exp15b.sh
bsub < run_exp15c.sh
'''
    with open(master_path, 'w') as f:
        f.write(master_content)
    print(f"Generated master: {master_path}")
    print(f"Log directory: {log_dir}")


def main():
    parser = argparse.ArgumentParser(description="EXP15: OOD Robustness Evaluation")
    parser.add_argument("--exp", type=str, choices=["15a", "15b", "15c", "16b1", "all"],
                        default="all", help="Which experiment to run")
    parser.add_argument("--seed", type=int, default=None, help="Single seed")
    parser.add_argument("--seeds", type=str, default=None, help="Comma-separated seeds")
    
    # EXP15a args
    parser.add_argument("--ratio", type=float, default=0.59, help="Crunch ratio")
    parser.add_argument("--shift", type=int, default=0, help="Window shift")
    
    # EXP15b args
    parser.add_argument("--multiplier", type=float, default=1.0, help="Order count multiplier")
    parser.add_argument("--jitter", type=float, default=0, help="Spatial jitter km")
    
    # EXP15c args
    parser.add_argument("--variant", type=str, default="full",
                        choices=list(EXP15C_VARIANTS.keys()),
                        help="Feature variant for EXP15c")

    # EXP16b1 args
    parser.add_argument("--epsilon", type=float, default=0.2,
                        help="Exploration epsilon for EXP16b1 data collection")
    
    parser.add_argument("--generate-hpc", action="store_true", help="Generate HPC scripts only")
    args = parser.parse_args()

    # Determine seeds
    if args.seed is not None:
        seeds = [args.seed]
    elif args.seeds is not None:
        seeds = [int(s.strip()) for s in args.seeds.split(",")]
    else:
        seeds = DEFAULT_SEEDS

    if args.generate_hpc:
        generate_all_hpc_scripts(seeds)
        return

    if args.exp == "15a":
        run_exp15a(args.ratio, args.shift, seeds)
    elif args.exp == "15b":
        run_exp15b(args.multiplier, args.jitter, seeds)
    elif args.exp == "15c":
        run_exp15c(args.variant, args.ratio, args.shift, seeds)
    elif args.exp == "16b1":
        for seed in seeds:
            run_exp16b1(args.ratio, args.shift, seed, epsilon=args.epsilon)
    elif args.exp == "all":
        # Run representative subset
        run_exp15a(0.59, 0, seeds)
        for variant in EXP15C_VARIANTS:
            run_exp15c(variant, 0.59, 0, seeds)


if __name__ == "__main__":
    main()
