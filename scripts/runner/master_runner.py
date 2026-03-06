#!/usr/bin/env python3
"""
Master experiment runner with override support for sweep experiments.
Supports per-run parameter overrides for all sweep dimensions.

Dependency: requires the ``src`` package (see scripts/__init__.py A1 contract).
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from datetime import datetime

# scripts.__init__ auto-injects REPO_ROOT into sys.path
import scripts  # noqa: F401 — triggers path setup
from scripts import ensure_src

REPO_ROOT = scripts.REPO_ROOT

from scripts.experiment_definitions import EXPERIMENTS

# Lazy-import src at module level with a clear guard.
# The actual ``run_rolling_horizon`` is used only inside run_simulation(),
# but importing it here gives an immediate, readable error if src is missing.
ensure_src()
from src.simulation.rolling_horizon_integrated import run_rolling_horizon


def _is_lsf_job() -> bool:
    return bool(os.environ.get("LSB_JOBID"))


def _allow_local_run() -> bool:
    return os.environ.get("ALLOW_LOCAL_EXPERIMENT_RUN", "").strip() == "1"


def _cleanup_failed_run(output_dir: Path) -> None:
    """Remove incomplete outputs so failed experiments do not pollute results."""
    if output_dir.exists():
        shutil.rmtree(output_dir, ignore_errors=True)


def parse_overrides(override_args):
    """Parse override arguments in key=value format."""
    overrides = {}
    if not override_args:
        return overrides

    for arg in override_args:
        if '=' not in arg:
            print(f"⚠️  Invalid override format: {arg} (expected key=value)")
            continue

        key, value = arg.split('=', 1)

        # Type conversion
        if value.lower() == 'true':
            value = True
        elif value.lower() == 'false':
            value = False
        elif value.lower() == 'none':
            value = None
        else:
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    pass  # Keep as string

        overrides[key] = value

    return overrides


def merge_config(base_params, overrides):
    """
    Merge override parameters into base config.
    Rule: experiment_definition (base) < job_override (overrides)
    """
    merged = base_params.copy()
    merged.update(overrides)

    # If a concrete sweep value is provided, drop the corresponding list-based
    # sweep key so the config becomes one executable variant.
    concrete_to_sweep = {
        "ratio": "ratios",
        "max_trips": "max_trips_list",
        "use_risk_model": "use_risk_model_list",
        "risk_threshold_on": "delta_on_list",
        "base_compute": "time_limits",
    }
    for concrete_key, sweep_key in concrete_to_sweep.items():
        if concrete_key in overrides and sweep_key in merged:
            merged.pop(sweep_key, None)

    return merged


def validate_concrete_params(exp_id, exp_config, params):
    """Fail fast if a sweep experiment has not been materialized to one variant."""
    unresolved = [
        key for key in (
            "ratios",
            "max_trips_list",
            "use_risk_model_list",
            "delta_on_list",
            "time_limits",
        )
        if key in params
    ]
    if unresolved:
        raise ValueError(
            f"{exp_id} is a sweep experiment but still has unresolved sweep keys: {unresolved}. "
            "Materialize one concrete variant via HPC job generation / overrides before running."
        )


def create_output_dir(exp_id, seed, overrides=None):
    """Create output directory with override info in name if needed."""
    base_dir = Path("data/results") / f"EXP_{exp_id}"

    # Add override suffix if present
    if overrides:
        endpoint_key = overrides.get("endpoint_key")
        if endpoint_key:
            base_dir = base_dir / str(endpoint_key)
        # Create a short suffix from key overrides
        # Include all sweep-relevant keys to ensure unique directories
        else:
            suffix_parts = []
            for key in ['ratio', 'max_trips', 'risk_threshold_on', 'use_risk_model', 'base_compute', 'mode']:
                if key in overrides:
                    val = overrides[key]
                    short_key = {
                        'ratio': 'ratio',
                        'max_trips': 'max_trips',
                        'risk_threshold_on': 'delta',
                        'use_risk_model': 'risk',
                        'base_compute': 'tl',
                        'mode': 'mode'
                    }.get(key, key)
                    suffix_parts.append(f"{short_key}_{val}")

            if suffix_parts:
                suffix = "_".join(suffix_parts)
                base_dir = base_dir / suffix

    output_dir = base_dir / f"Seed_{seed}"
    output_dir.mkdir(parents=True, exist_ok=True)

    return output_dir


def save_config_dump(output_dir, exp_id, seed, params, overrides):
    """Save configuration dump with full traceability."""
    config_dump = {
        "experiment_id": exp_id,
        "seed": seed,
        "timestamp": datetime.now().isoformat(),
        "parameters": params,
        "overrides_applied": overrides if overrides else {},
        "merge_rule": "experiment_definition < job_override"
    }

    config_path = output_dir / "config_dump.json"
    with open(config_path, 'w') as f:
        json.dump(config_dump, f, indent=2)

    print(f"✓ Config saved: {config_path}")
    return config_path


def run_simulation(exp_id, seed, params, output_dir):
    """Run simulation with given parameters."""

    # Get compute limits from params (single source of truth)
    base_compute = params.get('base_compute', 60)
    high_compute = params.get('high_compute', 60)

    # Build config for run_rolling_horizon
    # Pass base_compute/high_compute directly in config (preferred over env vars)
    config = {
        'capacity_ratio': params.get('ratio', 1.0),
        'total_days': params.get('total_days', 12),
        'use_risk_model': params.get('use_risk_model', False),
        'risk_model_path': 'models/risk_model.joblib',
        'risk_threshold_on': params.get('risk_threshold_on', 0.826),
        'risk_threshold_off': params.get('risk_threshold_off', 0.496),
        'seed': seed,
        'results_dir': 'data/results',
        'base_compute': base_compute,   # Pass directly to rolling_horizon
        'high_compute': high_compute,   # Pass directly to rolling_horizon
        'mode': params.get('mode', 'proactive'),  # Policy mode: 'greedy' or 'proactive'
        'max_trips_per_vehicle': int(params.get('max_trips', 2)),
    }

    # Add crunch period if specified (single window)
    if params.get('crunch_start') is not None:
        config['crunch_start'] = params['crunch_start']
        config['crunch_end'] = params['crunch_end']

    # Add crunch_windows if specified (multi-window, e.g., EXP09)
    if params.get('crunch_windows'):
        config['crunch_windows'] = params['crunch_windows']

    # Also set environment variables as fallback for solver
    os.environ["VRP_TIME_LIMIT_SECONDS"] = str(base_compute)
    os.environ["VRP_HIGH_COMPUTE_LIMIT"] = str(high_compute)

    # Default operational rule: each vehicle may run up to two trips per day.
    os.environ["VRP_MAX_TRIPS_PER_VEHICLE"] = str(int(params.get('max_trips', 2)))

    print(f"\n{'=' * 70}")
    print(f"Running: {exp_id} - Seed {seed}")
    print(f"Ratio: {params.get('ratio')}, Days: {params.get('total_days')}")
    print(f"Compute: base={base_compute}s, high={high_compute}s")
    print(f"Output: {output_dir}")
    print(f"{'=' * 70}\n")

    # Run simulation
    try:
        results = run_rolling_horizon(config)

        # Save results
        results_path = output_dir / "simulation_results.json"
        with open(results_path, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"✓ Results saved: {results_path}")
        return results

    except Exception as e:
        print(f"✗ Simulation failed: {e}")
        import traceback
        traceback.print_exc()
        _cleanup_failed_run(output_dir)
        return None


def extract_summary(output_dir, results):
    """Extract summary metrics (simplified version)."""
    if results is None:
        return None

    # Use summary from results
    if 'summary' in results:
        summary = results['summary']
    else:
        summary = {}

    # Save summary
    summary_path = output_dir / "summary_final.json"
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"✓ Summary saved: {summary_path}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="MOVER Master Thesis Runner with Override Support")
    parser.add_argument("--exp", type=str, required=True, help="Experiment ID (e.g., EXP00)")
    parser.add_argument("--seed", type=int, default=1, help="Random seed")
    parser.add_argument("--override", action='append', help="Override parameter (key=value, can be repeated)")
    parser.add_argument("--override_json", type=str, help="Path to JSON file with overrides")
    parser.add_argument("--dry-run", action="store_true", help="Print config without running")

    args = parser.parse_args()

    if not args.dry_run and not _is_lsf_job() and not _allow_local_run():
        print("❌ Refusing to run experiment locally.")
        print("Submit through HPC (LSF / bsub) instead.")
        print("Use --dry-run for config inspection only.")
        print("Escape hatch for maintenance only: ALLOW_LOCAL_EXPERIMENT_RUN=1")
        return 2

    # Validate experiment ID
    exp_id = args.exp.upper()
    if exp_id not in EXPERIMENTS:
        print(f"❌ Unknown experiment: {exp_id}")
        print(f"Available: {', '.join(EXPERIMENTS.keys())}")
        return 1

    exp_config = EXPERIMENTS[exp_id]
    base_params = exp_config["params"].copy()

    # Parse overrides
    overrides = {}

    if args.override_json:
        with open(args.override_json) as f:
            overrides.update(json.load(f))

    if args.override:
        overrides.update(parse_overrides(args.override))

    # Merge config
    params = merge_config(base_params, overrides)
    validate_concrete_params(exp_id, exp_config, params)

    print("=" * 70)
    print(f"EXPERIMENT: {exp_id} - {exp_config['name']}")
    print("=" * 70)
    print(f"Description: {exp_config['description']}")
    print(f"Seed: {args.seed}")
    print(f"Resource: {exp_config['resource']}")

    if overrides:
        print(f"\n⚙️  Overrides applied:")
        for key, value in overrides.items():
            print(f"  {key}: {value}")

    print("=" * 70)
    print()

    # Create output directory
    output_dir = create_output_dir(exp_id, args.seed, overrides)

    # Save config dump
    save_config_dump(output_dir, exp_id, args.seed, params, overrides)

    if args.dry_run:
        print("✓ Dry run complete. Config saved.")
        return 0

    # Run simulation
    results = run_simulation(exp_id, args.seed, params, output_dir)

    # Extract summary
    if results:
        summary = extract_summary(output_dir, results)

        # Print summary
        print(f"\n✅ Experiment complete: {exp_id} - Seed {args.seed}")
        if summary:
            sr = summary.get('service_rate_within_window', summary.get('service_rate', 0))
            revenue = summary.get('cost_raw', 0)
            avg_risk = summary.get('avg_risk_p', 0) if 'avg_risk_p' in summary else 0

            print(f"   Service Rate: {sr:.2%}")
            print(f"   Revenue: ${revenue:.2f}")
            print(f"   Avg Risk P: {avg_risk:.3f}")
    else:
        print(f"\n✗ Experiment failed: {exp_id} - Seed {args.seed}")
        _cleanup_failed_run(output_dir)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
