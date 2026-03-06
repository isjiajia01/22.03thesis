#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOVER Master Thesis Runner
Unified entry point for all experiments (EXP00-EXP11)
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add repo root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))


# ============================================================================
# EXPERIMENT DEFINITIONS
# ============================================================================

EXPERIMENTS = {
    "EXP00": {
        "name": "BAU_Baseline",
        "description": "Baseline validation with no risk model",
        "params": {
            "ratio": 0.85,
            "total_days": 2,
            "crunch_start": None,
            "crunch_end": None,
            "use_risk_model": False,
            "base_compute": 60,
            "high_compute": 60,
        },
        "resource": "standard",
    },
    "EXP01": {
        "name": "Crunch_Baseline",
        "description": "Early policy failure scenario",
        "params": {
            "ratio": 0.70,
            "total_days": 10,
            "crunch_start": 5,
            "crunch_end": 8,
            "use_risk_model": True,
            "base_compute": 60,
            "high_compute": 180,
        },
        "resource": "heavy",
    },
    "EXP02": {
        "name": "Ablation_StopOnly",
        "description": "Ablation: Stop-only mode",
        "params": {
            "ratio": 0.65,
            "total_days": 10,
            "crunch_start": 5,
            "crunch_end": 10,
            "use_risk_model": True,
            "ablation_mode": "stop_only",
            "base_compute": 60,
            "high_compute": 180,
        },
        "resource": "heavy",
    },
    "EXP03": {
        "name": "Ablation_RouteOnly",
        "description": "Ablation: Route-only mode",
        "params": {
            "ratio": 0.65,
            "total_days": 10,
            "crunch_start": 5,
            "crunch_end": 10,
            "use_risk_model": True,
            "ablation_mode": "route_only",
            "base_compute": 60,
            "high_compute": 180,
        },
        "resource": "heavy",
    },
    "EXP04": {
        "name": "Ablation_Both",
        "description": "Ablation: Both stop and route",
        "params": {
            "ratio": 0.65,
            "total_days": 10,
            "crunch_start": 5,
            "crunch_end": 10,
            "use_risk_model": True,
            "ablation_mode": "both",
            "base_compute": 60,
            "high_compute": 180,
        },
        "resource": "heavy",
    },
    "EXP05": {
        "name": "Ratio_Sweep",
        "description": "Capacity ratio sweep to find phase transition",
        "params": {
            "ratios": [0.75, 0.65, 0.60, 0.55],
            "total_days": 10,
            "crunch_start": 5,
            "crunch_end": 10,
            "use_risk_model": True,
            "base_compute": 60,
            "high_compute": 180,
        },
        "resource": "heavy",
        "is_sweep": True,
    },
    "EXP06": {
        "name": "Duration_Scan",
        "description": "Long-duration high-pressure robustness",
        "params": {
            "ratio": 0.60,
            "total_days": 12,
            "crunch_configs": [(5, 9), (5, 11)],
            "use_risk_model": True,
            "base_compute": 60,
            "high_compute": 180,
        },
        "resource": "heavy",
        "is_sweep": True,
    },
    "EXP07": {
        "name": "Boundary_Point",
        "description": "Phase transition boundary at r=0.59",
        "params": {
            "ratio": 0.59,
            "total_days": 12,
            "crunch_start": 5,
            "crunch_end": 11,
            "use_risk_model": True,
            "base_compute": 60,
            "high_compute": 180,
        },
        "resource": "heavy",
    },
    "EXP09": {
        "name": "RiskGate_Smoke",
        "description": "Verify risk gate perception-control loop",
        "params": {
            "ratio": 0.60,
            "total_days": 10,
            "crunch_start": 5,
            "crunch_end": 10,
            "use_risk_model": True,
            "base_compute": 60,
            "high_compute": 180,
            "force_risk_on": True,  # Force 100% risk mode
        },
        "resource": "heavy",
    },
    "EXP10": {
        "name": "Compute_Power",
        "description": "Static vs Dynamic compute allocation",
        "params": {
            "ratio": 0.60,
            "total_days": 10,
            "crunch_start": 5,
            "crunch_end": 10,
            "configs": [
                {"name": "static_60", "use_risk_model": False, "base_compute": 60},
                {"name": "static_300", "use_risk_model": False, "base_compute": 300},
                {"name": "dynamic", "use_risk_model": True, "base_compute": 60, "high_compute": 180},
            ],
        },
        "resource": "heavy",
        "is_sweep": True,
    },
    "EXP11": {
        "name": "Physical_DoF",
        "description": "Trips=3 vs default to break physical limit",
        "params": {
            "ratio": 0.59,
            "total_days": 12,
            "crunch_start": 5,
            "crunch_end": 11,
            "trips_configs": [2, 3],
            "use_risk_model": True,
            "base_compute": 60,
            "high_compute": 180,
        },
        "resource": "heavy",
        "is_sweep": True,
    },
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_output_dir(exp_id, seed, sub_config=None):
    """Create output directory with proper structure."""
    if sub_config:
        path = Path(f"data/results/EXP_{exp_id}_{EXPERIMENTS[exp_id]['name']}/{sub_config}/Seed_{seed}")
    else:
        path = Path(f"data/results/EXP_{exp_id}_{EXPERIMENTS[exp_id]['name']}/Seed_{seed}")

    path.mkdir(parents=True, exist_ok=True)
    return path


def save_config_dump(output_dir, exp_id, seed, params):
    """Save configuration dump for reproducibility."""
    config_dump = {
        "experiment_id": exp_id,
        "experiment_name": EXPERIMENTS[exp_id]["name"],
        "seed": seed,
        "timestamp": datetime.now().isoformat(),
        "parameters": params,
    }

    config_path = output_dir / "config_dump.json"
    with open(config_path, 'w') as f:
        json.dump(config_dump, f, indent=2)

    print(f"✓ Config saved: {config_path}")


def run_simulation(exp_id, seed, params, output_dir):
    """Run a single simulation with given parameters."""
    from src.simulation.rolling_horizon_integrated import run_rolling_horizon
    from src.simulation.policies import ProactivePolicy

    # Build config
    config = {
        'capacity_ratio': params.get('ratio'),
        'total_days': params.get('total_days', 10),
        'use_risk_model': params.get('use_risk_model', False),
        'risk_model_path': 'models/risk_model.joblib',
        'risk_threshold_on': 0.826,
        'risk_threshold_off': 0.496,
        'seed': seed,
    }

    # Add crunch period if specified
    if params.get('crunch_start') is not None:
        config['crunch_start'] = params['crunch_start']
        config['crunch_end'] = params['crunch_end']

    # Set compute limits
    os.environ["VRP_TIME_LIMIT_SECONDS"] = str(params.get('base_compute', 60))

    print(f"\n{'='*70}")
    print(f"Running: {exp_id} - Seed {seed}")
    print(f"Ratio: {params.get('ratio')}, Days: {params.get('total_days')}")
    print(f"Output: {output_dir}")
    print(f"{'='*70}\n")

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
        return None


def extract_summary(output_dir, results):
    """Extract summary metrics for analysis."""
    if results is None:
        return None

    # Use the summary from run_rolling_horizon if available
    if 'summary' in results:
        base_summary = results['summary']
    else:
        base_summary = {}

    # Extract daily_stats for additional metrics
    daily_stats = results.get('daily_stats', [])

    # Calculate unique orders seen (de-duplicated by order_id)
    unique_order_ids = set()
    for d in daily_stats:
        # Collect order IDs from planned and delivered
        # Note: This is an approximation; actual order IDs not in daily_stats
        pass

    # Build summary with data from both sources
    summary = {
        # Use explicit names from base_summary
        "eligible_count": base_summary.get('eligible_count', 0),
        "delivered_within_window_count": base_summary.get('delivered_within_window_count', 0),
        "deadline_failure_count": base_summary.get('deadline_failure_count', 0),
        "service_rate_within_window": base_summary.get('service_rate_within_window', 0.0),

        # Renamed: total_orders -> total_planned_plus_delivered (to avoid confusion)
        "total_planned_plus_delivered": sum(d.get('planned_today', 0) + d.get('delivered_today', 0) for d in daily_stats),

        # Legacy fields for backward compatibility
        "failed_orders": base_summary.get('failed_orders', sum(d.get('failures', 0) for d in daily_stats)),
        "total_drops": sum(d.get('vrp_dropped', 0) for d in daily_stats),
        "revenue": sum(d.get('cost', 0) for d in daily_stats),  # Use cost as proxy for revenue
        "service_rate": base_summary.get('service_rate', 0.0),

        # Risk metrics
        "avg_risk_p": 0.0,
        "max_risk_p": 0.0,
        "risk_trigger_days": 0,
        "total_compute_time": sum(d.get('compute_limit_seconds', 60) for d in daily_stats),
        "avg_time_per_day": 0.0,
    }

    # Calculate risk metrics from daily_stats
    risk_ps = [d.get('risk_p', 0.0) for d in daily_stats if 'risk_p' in d and d.get('risk_p') == d.get('risk_p')]  # Filter NaN
    if risk_ps:
        summary["avg_risk_p"] = sum(risk_ps) / len(risk_ps)
        summary["max_risk_p"] = max(risk_ps)
        summary["risk_trigger_days"] = sum(1 for d in daily_stats if d.get('compute_limit_seconds', 60) > 60)

    if len(daily_stats) > 0:
        summary["avg_time_per_day"] = summary["total_compute_time"] / len(daily_stats)

    # Save summary
    summary_path = output_dir / "summary_final.json"
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"✓ Summary saved: {summary_path}")
    return summary


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="MOVER Master Thesis Runner")
    parser.add_argument("--exp", type=str, required=True, help="Experiment ID (e.g., EXP00)")
    parser.add_argument("--seed", type=int, default=1, help="Random seed (1-3)")
    parser.add_argument("--dry-run", action="store_true", help="Print config without running")

    args = parser.parse_args()

    # Validate experiment ID
    if args.exp not in EXPERIMENTS:
        print(f"✗ Unknown experiment: {args.exp}")
        print(f"Available: {', '.join(EXPERIMENTS.keys())}")
        sys.exit(1)

    exp_config = EXPERIMENTS[args.exp]
    params = exp_config["params"]

    print(f"\n{'='*70}")
    print(f"MOVER Master Runner - {args.exp}: {exp_config['name']}")
    print(f"{'='*70}")
    print(f"Description: {exp_config['description']}")
    print(f"Seed: {args.seed}")
    print(f"Resource: {exp_config['resource']}")
    print(f"{'='*70}\n")

    # Handle sweep experiments
    if exp_config.get("is_sweep"):
        print(f"⚠️  This is a sweep experiment. Use HPC job array instead.")
        print(f"   See jobs/submit_{args.exp.lower()}.sh")
        sys.exit(0)

    # Create output directory
    output_dir = create_output_dir(args.exp, args.seed)

    # Save config dump
    save_config_dump(output_dir, args.exp, args.seed, params)

    if args.dry_run:
        print("✓ Dry run complete. Config saved.")
        sys.exit(0)

    # Run simulation
    results = run_simulation(args.exp, args.seed, params, output_dir)

    # Extract summary
    if results:
        summary = extract_summary(output_dir, results)
        print(f"\n✅ Experiment complete: {args.exp} - Seed {args.seed}")
        print(f"   Service Rate: {summary['service_rate']:.2%}")
        print(f"   Revenue: ${summary['revenue']:.2f}")
        print(f"   Avg Risk P: {summary['avg_risk_p']:.3f}")
    else:
        print(f"\n✗ Experiment failed: {args.exp} - Seed {args.seed}")
        sys.exit(1)


if __name__ == "__main__":
    main()
