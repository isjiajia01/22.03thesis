#!/usr/bin/env python3
"""
HPC Acceptance Test - Minimal validation for RiskGate path.

This script validates that the full RiskGate pipeline works correctly:
1. Crunch window has min(capacity_ratio) == target (e.g., 0.59)
2. max(risk_p) >= delta_on (0.826) at least once
3. risk_mode_on == 1 appears at least once
4. compute_limit_seconds > base (60) appears at least once

Run this with a single seed to validate before full HPC sweep.

Usage:
    python3 scripts/hpc_acceptance_test.py [--seed 1] [--ratio 0.59]
"""

import sys
import os
import json
import math
from pathlib import Path
from datetime import datetime

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def run_acceptance_test(seed: int = 1, crunch_ratio: float = 0.59):
    """
    Run minimal acceptance test for RiskGate path.
    """
    print("=" * 70)
    print("HPC ACCEPTANCE TEST - RiskGate Path Validation")
    print("=" * 70)
    print(f"Seed: {seed}")
    print(f"Crunch ratio: {crunch_ratio}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()

    # Import after path setup
    from src.simulation.rolling_horizon_integrated import run_rolling_horizon

    # Config matching EXP04 (full RiskGate + dynamic compute)
    config = {
        'capacity_ratio': crunch_ratio,
        'total_days': 12,
        'crunch_start': 5,
        'crunch_end': 10,
        'use_risk_model': True,
        'risk_model_path': 'models/risk_model.joblib',
        'risk_threshold_on': 0.826,
        'risk_threshold_off': 0.496,
        'seed': seed,
        'results_dir': str(REPO_ROOT / 'data' / 'results' / 'HPC_ACCEPTANCE_TEST'),
    }

    print("Config:")
    for k, v in config.items():
        print(f"  {k}: {v}")
    print()

    # Run simulation
    print("Running simulation...")
    try:
        results = run_rolling_horizon(config)
    except Exception as e:
        print(f"❌ SIMULATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    daily_stats = results.get('daily_stats', [])
    print(f"Simulation complete. Days: {len(daily_stats)}")
    print()

    # Extract metrics
    cap_ratios = [d.get('capacity_ratio', 1.0) for d in daily_stats]
    risk_ps = [d.get('risk_p') for d in daily_stats]
    risk_mode_ons = [d.get('risk_mode_on', 0) for d in daily_stats]
    compute_limits = [d.get('compute_limit_seconds', 60) for d in daily_stats]
    risk_model_loaded = [d.get('risk_model_loaded', 0) for d in daily_stats]

    # Filter valid risk_p values (not NaN)
    valid_risk_ps = [r for r in risk_ps if r is not None and not (isinstance(r, float) and math.isnan(r))]

    # Print daily summary
    print("Daily Summary:")
    print("-" * 70)
    print(f"{'Day':<5} {'CapRatio':<10} {'risk_p':<10} {'mode_on':<8} {'compute':<10} {'loaded':<8}")
    print("-" * 70)
    for i, d in enumerate(daily_stats):
        rp = d.get('risk_p')
        rp_str = f"{rp:.4f}" if rp is not None and not (isinstance(rp, float) and math.isnan(rp)) else "NaN"
        print(f"{i:<5} {d.get('capacity_ratio', 1.0):<10.2f} {rp_str:<10} {d.get('risk_mode_on', 0):<8} {d.get('compute_limit_seconds', 60):<10} {d.get('risk_model_loaded', 0):<8}")
    print()

    # Validation checks
    print("=" * 70)
    print("VALIDATION CHECKS")
    print("=" * 70)

    all_passed = True

    # Check 1: Crunch effectiveness
    min_cap_ratio = min(cap_ratios)
    crunch_window_ratios = cap_ratios[config['crunch_start']:config['crunch_end']+1]
    check1_pass = min_cap_ratio <= crunch_ratio + 0.01  # Allow small tolerance

    print(f"\n[1] CRUNCH EFFECTIVENESS")
    print(f"    min(capacity_ratio): {min_cap_ratio:.4f}")
    print(f"    Expected: <= {crunch_ratio}")
    print(f"    Crunch window ratios: {[f'{r:.2f}' for r in crunch_window_ratios]}")
    print(f"    Result: {'✅ PASS' if check1_pass else '❌ FAIL'}")
    if not check1_pass:
        all_passed = False

    # Check 2: Risk model loaded
    check2_pass = all(m == 1 for m in risk_model_loaded)
    print(f"\n[2] RISK MODEL LOADED")
    print(f"    risk_model_loaded values: {risk_model_loaded}")
    print(f"    Result: {'✅ PASS' if check2_pass else '❌ FAIL'}")
    if not check2_pass:
        print(f"    ❌ Model failed to load - check joblib/sklearn installation")
        all_passed = False

    # Check 3: max(risk_p) >= delta_on
    max_risk_p = max(valid_risk_ps) if valid_risk_ps else 0.0
    delta_on = config['risk_threshold_on']
    check3_pass = max_risk_p >= delta_on

    print(f"\n[3] RISK THRESHOLD REACHED")
    print(f"    max(risk_p): {max_risk_p:.4f}")
    print(f"    delta_on threshold: {delta_on}")
    print(f"    Result: {'✅ PASS' if check3_pass else '❌ FAIL'}")
    if not check3_pass:
        print(f"    ❌ Risk never reached threshold - gate never triggered")
        all_passed = False

    # Check 4: risk_mode_on == 1 at least once
    risk_mode_on_count = sum(risk_mode_ons)
    check4_pass = risk_mode_on_count > 0

    print(f"\n[4] RISK MODE ACTIVATED")
    print(f"    Days with risk_mode_on=1: {risk_mode_on_count}")
    print(f"    risk_mode_on values: {risk_mode_ons}")
    print(f"    Result: {'✅ PASS' if check4_pass else '❌ FAIL'}")
    if not check4_pass:
        print(f"    ❌ Risk mode never activated")
        all_passed = False

    # Check 5: compute_limit_seconds > 60 at least once
    high_compute_count = sum(1 for c in compute_limits if c > 60)
    check5_pass = high_compute_count > 0

    print(f"\n[5] DYNAMIC COMPUTE TRIGGERED")
    print(f"    Days with compute > 60s: {high_compute_count}")
    print(f"    compute_limit values: {compute_limits}")
    print(f"    Result: {'✅ PASS' if check5_pass else '❌ FAIL'}")
    if not check5_pass:
        print(f"    ❌ High compute mode never triggered")
        all_passed = False

    # Final verdict
    print("\n" + "=" * 70)
    if all_passed:
        print("✅ HPC ACCEPTANCE TEST PASSED")
        print("   RiskGate path is fully validated!")
        print("   Safe to proceed with full HPC sweep.")
    else:
        print("❌ HPC ACCEPTANCE TEST FAILED")
        print("   RiskGate path NOT validated!")
        print("   DO NOT proceed with full HPC sweep until all checks pass.")
    print("=" * 70)

    return all_passed


def main():
    import argparse
    parser = argparse.ArgumentParser(description="HPC Acceptance Test")
    parser.add_argument("--seed", type=int, default=1, help="Random seed")
    parser.add_argument("--ratio", type=float, default=0.59, help="Crunch capacity ratio")
    args = parser.parse_args()

    passed = run_acceptance_test(seed=args.seed, crunch_ratio=args.ratio)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
