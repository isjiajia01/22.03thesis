#!/usr/bin/env python3
"""
Minimal Regression Test for Risk Gate Integration

Tests:
1. TEST_BAU: risk_p all NaN, risk_mode_on all 0, capacity_ratio all 1.0
2. TEST_CRUNCH: risk_p rises during crunch, falls after, risk_mode transitions 0→1→0

Auto pass/fail with evidence-based validation.
"""

import sys
import os
import json
from pathlib import Path
import pandas as pd
import numpy as np

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.simulation.rolling_horizon_integrated import RollingHorizonIntegrated
from src.experiments.exp_utils import build_bau, build_capacity_crunch


def load_base_data():
    """Load base dataset."""
    data_path = REPO_ROOT / "data" / "processed" / "multiday_benchmark_herlev.json"
    with open(data_path, 'r') as f:
        return json.load(f)


def run_test_bau():
    """
    TEST_BAU: Baseline with no risk model

    Expected:
    - risk_p: all NaN
    - risk_mode_on: all 0
    - capacity_ratio: all 1.0
    """
    print("\n" + "="*70)
    print("TEST_BAU: Baseline Validation")
    print("="*70)

    base_data = load_base_data()
    data = build_bau(base_data, horizon_days=12)

    # Verify capacity_profile in config
    capacity_profile = data.get("metadata", {}).get("capacity_profile", {})
    print(f"\n📋 Config - capacity_profile: {capacity_profile}")

    config = {
        'mode': 'proactive_quota',
        'use_risk_model': False,  # CRITICAL: No risk model
        'base_compute': 60,
        'high_compute': 60,
    }

    output_dir = REPO_ROOT / "data" / "results" / "REGRESSION_TEST_BAU"
    output_dir.mkdir(parents=True, exist_ok=True)

    sim = RollingHorizonIntegrated(
        data_source=data,
        strategy_config=config,
        seed=1,
        verbose=False,
        base_dir=str(output_dir),
        scenario_name="BAU",
        strategy_name="Proactive"
    )

    # Limit to 2 days by modifying end_date
    from datetime import timedelta
    sim.end_date = sim.start_date + timedelta(days=1)  # 2 days (day 0 and day 1)

    print("\n🔄 Running simulation (2 days)...")
    results = sim.run_simulation()

    # Load daily_stats
    stats_path = output_dir / "BAU" / "Proactive" / "daily_stats.csv"
    df = pd.read_csv(stats_path)

    print(f"\n📊 Daily Stats Shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")

    # Dump config
    config_dump = {
        "scenario_spec": data.get("metadata", {}).get("scenario_spec", {}),
        "capacity_profile": capacity_profile,
        "risk_gate_enabled": False,
        "base_compute": 60,
        "high_compute": 60,
    }

    config_path = output_dir / "BAU" / "Proactive" / "config_dump.json"
    with open(config_path, 'w') as f:
        json.dump(config_dump, f, indent=2)

    print(f"\n✅ Config dump: {config_path}")

    # Validation
    print("\n" + "="*70)
    print("VALIDATION RESULTS")
    print("="*70)

    passed = True

    # Check 1: risk_p should be NaN
    risk_p_values = df['risk_p'].values
    all_nan = np.all(np.isnan(risk_p_values))
    print(f"\n✓ Check 1: risk_p all NaN")
    print(f"  Result: {all_nan}")
    print(f"  Values: {risk_p_values}")
    if not all_nan:
        print(f"  ❌ FAIL: Expected all NaN, got non-NaN values")
        passed = False

    # Check 2: BAU Stability - risk_p should be low mean and non-zero variance
    risk_p_values_bau = df['risk_p'].values
    # Filter out NaN values for statistics
    risk_p_valid_bau = risk_p_values_bau[~np.isnan(risk_p_values_bau)]

    if len(risk_p_valid_bau) > 0:
        bau_mean = np.mean(risk_p_valid_bau)
        bau_std = np.std(risk_p_valid_bau)
        print(f"\n✓ Check 2: BAU Stability")
        print(f"  Mean risk_p: {bau_mean:.6f} (should be < 0.05)")
        print(f"  Std risk_p: {bau_std:.6f} (should be > 1e-6)")
        if bau_mean >= 0.05:
            print(f"  ❌ FAIL: BAU mean too high (>= 0.05)")
            passed = False
        if bau_std <= 1e-6:
            print(f"  ❌ FAIL: BAU std too low (<= 1e-6, indicates no variation)")
            passed = False
    else:
        print(f"\n✓ Check 2: BAU Stability")
        print(f"  ⚠️  WARNING: No valid risk_p values to check")

    # Check 2b: risk_mode_on should be all 0
    risk_mode_values = df['risk_mode_on'].values
    all_zero = np.all(risk_mode_values == 0)
    print(f"\n✓ Check 2b: risk_mode_on all 0")
    print(f"  Result: {all_zero}")
    print(f"  Values: {risk_mode_values}")
    if not all_zero:
        print(f"  ❌ FAIL: Expected all 0, got non-zero values")
        passed = False

    # Check 3: capacity_ratio should be all 1.0
    cap_ratio_values = df['capacity_ratio'].values
    all_one = np.all(cap_ratio_values == 1.0)
    print(f"\n✓ Check 3: capacity_ratio all 1.0")
    print(f"  Result: {all_one}")
    print(f"  Values: {cap_ratio_values}")
    if not all_one:
        print(f"  ❌ FAIL: Expected all 1.0, got: {cap_ratio_values}")
        passed = False

    return passed, df


def run_test_crunch():
    """
    TEST_CRUNCH: Crunch scenario with RiskGate

    Expected:
    - risk_p rises during crunch (days 5-8)
    - risk_p falls after crunch ends
    - risk_mode_on transitions: 0 → 1 → 0
    """
    print("\n" + "="*70)
    print("TEST_CRUNCH: Risk Gate Behavior Validation")
    print("="*70)

    base_data = load_base_data()
    data = build_capacity_crunch(
        base_data,
        crunch_ratio=0.70,
        crunch_start=5,
        crunch_end=8,
        horizon_days=12
    )

    # Verify capacity_profile in config
    capacity_profile = data.get("metadata", {}).get("capacity_profile", {})
    print(f"\n📋 Config - capacity_profile: {capacity_profile}")

    config = {
        'mode': 'proactive_quota',
        'use_risk_model': True,  # CRITICAL: Enable risk model
        'risk_model_path': 'models/risk_model.joblib',
        'risk_threshold_on': 0.826,
        'risk_threshold_off': 0.496,
        'base_compute': 60,
        'high_compute': 180,
    }

    output_dir = REPO_ROOT / "data" / "results" / "REGRESSION_TEST_CRUNCH"
    output_dir.mkdir(parents=True, exist_ok=True)

    sim = RollingHorizonIntegrated(
        data_source=data,
        strategy_config=config,
        seed=1,
        verbose=False,
        base_dir=str(output_dir),
        scenario_name="Crunch",
        strategy_name="ProactiveRisk"
    )

    # Limit to 10 days by modifying end_date
    from datetime import timedelta
    sim.end_date = sim.start_date + timedelta(days=9)  # 10 days (day 0-9)

    print("\n🔄 Running simulation (10 days)...")
    results = sim.run_simulation()

    # Load daily_stats
    stats_path = output_dir / "Crunch" / "ProactiveRisk" / "daily_stats.csv"
    df = pd.read_csv(stats_path)

    print(f"\n📊 Daily Stats Shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")

    # Dump config
    config_dump = {
        "scenario_spec": data.get("metadata", {}).get("scenario_spec", {}),
        "capacity_profile": capacity_profile,
        "risk_gate_enabled": True,
        "risk_threshold_on": 0.826,
        "risk_threshold_off": 0.496,
        "base_compute": 60,
        "high_compute": 180,
    }

    config_path = output_dir / "Crunch" / "ProactiveRisk" / "config_dump.json"
    with open(config_path, 'w') as f:
        json.dump(config_dump, f, indent=2)

    print(f"\n✅ Config dump: {config_path}")

    # Validation
    print("\n" + "="*70)
    print("VALIDATION RESULTS")
    print("="*70)

    # Track individual check results
    check1_ok = True
    check2_ok = True
    check25_ok = True
    check3_ok = True
    check4_ok = True

    # Extract key days
    df['day_idx'] = range(len(df))
    pre_crunch = df[df['day_idx'] < 5]
    during_crunch = df[(df['day_idx'] >= 5) & (df['day_idx'] <= 8)]
    post_crunch = df[df['day_idx'] > 8]

    print(f"\nPre-crunch days: {list(pre_crunch['day_idx'].values)}")
    print(f"During crunch days: {list(during_crunch['day_idx'].values)}")
    print(f"Post-crunch days: {list(post_crunch['day_idx'].values)}")

    # Check 0: HARD ASSERTION - Crunch must actually reduce capacity
    # This validates that crunch_start/end + capacity_ratio are properly applied
    cap_ratio_values = df['capacity_ratio'].values
    min_cap_ratio = np.min(cap_ratio_values)
    crunch_days_with_reduced_cap = np.sum(cap_ratio_values < 0.95)

    print(f"\n✓ Check 0: CRUNCH EFFECTIVENESS (HARD ASSERTION)")
    print(f"  min(capacity_ratio): {min_cap_ratio:.4f} (MUST be < 0.95)")
    print(f"  Days with capacity_ratio < 0.95: {crunch_days_with_reduced_cap}")
    print(f"  capacity_ratio by day: {list(cap_ratio_values)}")

    check0_ok = True
    if min_cap_ratio >= 0.95:
        print(f"  ❌ HARD FAIL: Crunch not applied! min(capacity_ratio) >= 0.95")
        print(f"  This indicates crunch_start/end parameters are not being passed correctly.")
        check0_ok = False

    # Verify crunch covers expected days (5-8 for this test)
    crunch_day_ratios = cap_ratio_values[5:9] if len(cap_ratio_values) > 8 else []
    if len(crunch_day_ratios) > 0:
        all_crunch_days_reduced = np.all(np.array(crunch_day_ratios) < 0.95)
        print(f"  Crunch days (5-8) ratios: {list(crunch_day_ratios)}")
        if not all_crunch_days_reduced:
            print(f"  ❌ HARD FAIL: Not all crunch days have reduced capacity")
            check0_ok = False
    else:
        print(f"  ❌ HARD FAIL: Simulation too short to verify crunch days 5-8")
        check0_ok = False

    # Check 0.5: HARD ASSERTION - Risk model must be loaded when use_risk_model=True
    # This prevents silent degradation where model fails to load but job continues
    check05_ok = True
    if 'risk_model_loaded' in df.columns:
        model_loaded_values = df['risk_model_loaded'].values
        print(f"\n✓ Check 0.5: RISK MODEL LOADED (HARD ASSERTION)")
        print(f"  risk_model_loaded values: {list(model_loaded_values)}")

        if not np.all(model_loaded_values == 1):
            print(f"  ❌ HARD FAIL: Risk model not loaded!")
            print(f"  This indicates joblib/sklearn dependency missing or model file not found.")
            print(f"  FIX: Run preflight_check.py and ensure venv is activated in job script.")
            check05_ok = False
        else:
            print(f"  ✅ Risk model loaded successfully on all days")

        # Also verify risk_p_valid is 1 for day >= 2 (day 1 has no history)
        day2_plus = df[df['day_idx'] >= 2]
        if len(day2_plus) > 0:
            risk_p_valid_day2plus = day2_plus['risk_p_valid'].values
            if not np.any(risk_p_valid_day2plus == 1):
                print(f"  ❌ HARD FAIL: No valid risk predictions after day 1!")
                print(f"  risk_p_valid for day>=2: {list(risk_p_valid_day2plus)}")
                check05_ok = False
            else:
                valid_count = np.sum(risk_p_valid_day2plus == 1)
                print(f"  ✅ Valid risk predictions (day>=2): {valid_count}/{len(risk_p_valid_day2plus)}")
    else:
        print(f"\n✓ Check 0.5: RISK MODEL LOADED (HARD ASSERTION)")
        print(f"  ⚠️  WARNING: risk_model_loaded column not found in daily_stats")
        print(f"  This may indicate an older version of the simulation code.")
        # Don't fail for backward compatibility, but warn

    # Check 1: risk_p during crunch (INFORMATIONAL ONLY - not a failure condition)
    if len(during_crunch) > 0:
        risk_p_crunch = during_crunch['risk_p'].values
        mean_risk_crunch = np.nanmean(risk_p_crunch)
        print(f"\n✓ Check 1: risk_p during crunch (informational)")
        print(f"  Mean risk_p: {mean_risk_crunch:.3f}")
        print(f"  Values: {risk_p_crunch}")
        if mean_risk_crunch < 0.1:
            print(f"  ℹ️  INFO: Risk values are low during crunch (mean < 0.1)")
        # NOTE: This check is informational only - we validate triggering in Check 2.5

    # Check 2: risk_p should fall after crunch
    if len(post_crunch) > 0:
        risk_p_post = post_crunch['risk_p'].values
        mean_risk_post = np.nanmean(risk_p_post)
        print(f"\n✓ Check 2: risk_p after crunch")
        print(f"  Mean risk_p: {mean_risk_post:.3f}")
        print(f"  Values: {risk_p_post}")
        if mean_risk_post > 0.826:
            print(f"  ❌ FAIL: Expected risk to fall after crunch, still high")
            check2_ok = False

    # Check 2.5: Cross-scenario Separation (gate triggering capability)
    # Gate enters when risk_p >= delta_on (0.826), so we check:
    # - Pre-crunch: mean < 0.05 (low baseline)
    # - During-crunch: max >= 0.826 (at least one trigger)
    # - Post-crunch: mean < 0.05 (recovery)
    if len(pre_crunch) > 0 and len(during_crunch) > 0:
        risk_p_pre = pre_crunch['risk_p'].values
        mean_risk_pre = np.nanmean(risk_p_pre)
        max_risk_during = np.nanmax(during_crunch['risk_p'].values)

        print(f"\n✓ Check 2.5: Cross-scenario Separation (Gate Triggering)")
        print(f"  Pre-crunch mean: {mean_risk_pre:.3f} (should be < 0.05)")
        print(f"  During-crunch mean: {mean_risk_crunch:.3f} (informational)")
        print(f"  During-crunch max: {max_risk_during:.3f} (should be >= 0.826 to trigger gate)")

        if mean_risk_pre >= 0.05:
            print(f"  ❌ FAIL: Pre-crunch mean too high (>= 0.05)")
            check25_ok = False
        if max_risk_during < 0.826:
            print(f"  ❌ FAIL: During-crunch max too low (< 0.826), gate never triggered")
            check25_ok = False

        # Also check post-crunch recovery if available
        if len(post_crunch) > 0:
            risk_p_post = post_crunch['risk_p'].values
            mean_risk_post = np.nanmean(risk_p_post)
            print(f"  Post-crunch mean: {mean_risk_post:.3f} (should be < 0.05)")
            if mean_risk_post >= 0.05:
                print(f"  ❌ FAIL: Post-crunch mean too high (>= 0.05), no recovery")
                check25_ok = False

    # Check 3: risk_mode_on should transition 0→1→0
    risk_mode_values = df['risk_mode_on'].values
    has_zero = np.any(risk_mode_values == 0)
    has_one = np.any(risk_mode_values == 1)

    # Check for transition: find first 1, then check if there's a 0 after it
    first_one_idx = np.where(risk_mode_values == 1)[0]
    transitions_back = False
    if len(first_one_idx) > 0:
        after_first_one = risk_mode_values[first_one_idx[0]+1:]
        transitions_back = np.any(after_first_one == 0)

    print(f"\n✓ Check 3: risk_mode_on transitions")
    print(f"  Has 0: {has_zero}")
    print(f"  Has 1: {has_one}")
    print(f"  Transitions back to 0: {transitions_back}")
    print(f"  Values: {risk_mode_values}")

    if not (has_zero and has_one):
        print(f"  ❌ FAIL: Expected both 0 and 1 states")
        check3_ok = False

    if not transitions_back:
        print(f"  ❌ FAIL: Risk gate never turned off after activation")
        check3_ok = False

    # Check 4: Hysteresis state columns exist
    required_cols = ['risk_exit_counter', 'risk_delta_on', 'risk_delta_off']
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        print(f"\n✓ Check 4: Hysteresis state columns")
        print(f"  ❌ FAIL: Missing columns: {missing_cols}")
        check4_ok = False
    else:
        print(f"\n✓ Check 4: Hysteresis state columns present")
        print(f"  exit_counter values: {df['risk_exit_counter'].values}")

    # Summary of all checks
    print("\n" + "="*70)
    print("CHECK SUMMARY")
    print("="*70)
    print(f"  Check 0 (CRUNCH EFFECTIVENESS): {'✅ PASS' if check0_ok else '❌ HARD FAIL'}")
    print(f"  Check 0.5 (RISK MODEL LOADED): {'✅ PASS' if check05_ok else '❌ HARD FAIL'}")
    print(f"  Check 1 (informational): N/A (informational only)")
    print(f"  Check 2 (post-crunch recovery): {'✅ PASS' if check2_ok else '❌ FAIL'}")
    print(f"  Check 2.5 (gate triggering): {'✅ PASS' if check25_ok else '❌ FAIL'}")
    print(f"  Check 3 (mode transitions): {'✅ PASS' if check3_ok else '❌ FAIL'}")
    print(f"  Check 4 (hysteresis columns): {'✅ PASS' if check4_ok else '❌ FAIL'}")

    # Overall pass/fail - Check 0 and Check 0.5 are HARD requirements
    passed = all([check0_ok, check05_ok, check2_ok, check25_ok, check3_ok, check4_ok])

    if not passed:
        print(f"\n❌ FAILED CHECKS: {[name for name, ok in [('Check0_CRUNCH', check0_ok), ('Check0.5_MODEL', check05_ok), ('Check2', check2_ok), ('Check2.5', check25_ok), ('Check3', check3_ok), ('Check4', check4_ok)] if not ok]}")

    return passed, df


def main():
    print("="*70)
    print("MOVER RISK GATE REGRESSION TEST")
    print("="*70)

    # Run tests
    test1_passed, df_bau = run_test_bau()
    test2_passed, df_crunch = run_test_crunch()

    # Final verdict
    print("\n" + "="*70)
    print("FINAL VERDICT")
    print("="*70)

    print(f"\nTEST_BAU:    {'✅ PASS' if test1_passed else '❌ FAIL'}")
    print(f"TEST_CRUNCH: {'✅ PASS' if test2_passed else '❌ FAIL'}")

    if test1_passed and test2_passed:
        print("\n✅ ALL REGRESSION TESTS PASSED")
        print("\nPipeline is ready for HPC deployment!")
        return 0
    else:
        print("\n❌ REGRESSION TESTS FAILED")
        print("\nDO NOT submit to HPC until all tests pass!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
