#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local Smoke Test - 30-Minute Validation
Tests EXP00 (1 day) + EXP01 (1 day) to verify pipeline before HPC submission
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Add repo root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

print("="*70)
print("MOVER LOCAL SMOKE TEST")
print("="*70)
print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# Import after path setup
from src.simulation.rolling_horizon_integrated import RollingHorizonIntegrated
from src.experiments import exp_utils

# ============================================================================
# TEST 1: EXP00 - BAU Baseline (1 day, no risk model)
# ============================================================================

print("\n" + "="*70)
print("TEST 1: EXP00 - BAU Baseline")
print("="*70)

test1_passed = False

try:
    # Load base data
    data_file = "data/processed/multiday_benchmark_herlev.json"
    base_data = exp_utils.load_json(data_file)

    # Create 1-day scenario
    data_exp00 = base_data.copy()
    data_exp00["metadata"]["capacity_profile"] = {"0": 0.85}  # Day 0 at r=0.85

    # Strategy config (no risk model)
    strategy_config = exp_utils.strategy_proactive_smooth(
        penalty_per_fail=10000,
        buffer_ratio=0.75,
        lookahead_days=3,
        crunch_aware=False,
    )

    output_dir_exp00 = Path("data/results/SMOKE_TEST_EXP00")
    output_dir_exp00.mkdir(parents=True, exist_ok=True)

    print(f"Running EXP00 (1 day, r=0.85, no risk model)...")
    print(f"Output: {output_dir_exp00}")

    os.environ["VRP_TIME_LIMIT_SECONDS"] = "60"

    sim = RollingHorizonIntegrated(
        data_source=data_exp00,
        strategy_config=strategy_config,
        seed=999,
        run_context={"run_id": "SMOKE_EXP00", "scenario": "BAU", "strategy": "Proactive", "seed": 999},
        results_dir=str(output_dir_exp00.parent),
        run_id="SMOKE_EXP00",
        verbose=False,
    )

    results_exp00 = sim.run_simulation()

    # Verify daily_stats.csv exists
    csv_path = output_dir_exp00 / "BAU" / "Proactive" / "daily_stats.csv"
    if not csv_path.exists():
        print(f"✗ FAIL: daily_stats.csv not found at {csv_path}")
    else:
        print(f"✓ daily_stats.csv created at {csv_path}")

        # Check if it has expected columns
        import pandas as pd
        df = pd.read_csv(csv_path)
        if 'capacity_ratio' in df.columns:
            print(f"✓ CSV has capacity_ratio column")
        else:
            print(f"⚠️  CSV missing capacity_ratio column")

    # Extract summary
    if results_exp00:
        print(f"✓ Simulation completed")

        summary = {
            "service_rate": results_exp00.get('service_rate', 0.0),
            "total_cost": results_exp00.get('total_cost', 0.0),
            "delivered_count": results_exp00.get('delivered_count', 0),
            "failed_count": results_exp00.get('failed_count', 0),
        }

        summary_path = output_dir_exp00 / "summary_final.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)

        print(f"✓ summary_final.json created")
        print(f"  Service Rate: {summary['service_rate']:.2%}")
        print(f"  Delivered: {summary['delivered_count']}")

        test1_passed = True
    else:
        print(f"✗ FAIL: Simulation returned None")

except Exception as e:
    print(f"✗ FAIL: EXP00 crashed with error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# TEST 2: EXP01 - Crunch Baseline (1 day with crunch, risk model)
# ============================================================================

print("\n" + "="*70)
print("TEST 2: EXP01 - Crunch Baseline (with RiskGate)")
print("="*70)

test2_passed = False

try:
    # Create 1-day crunch scenario
    data_exp01 = base_data.copy()
    data_exp01["metadata"]["capacity_profile"] = {"0": 0.70}  # Day 0 at r=0.70 (crunch)

    # Strategy config WITH risk model
    strategy_config_risk = exp_utils.strategy_proactive_smooth(
        penalty_per_fail=10000,
        buffer_ratio=0.75,
        lookahead_days=3,
        crunch_aware=True,
    )
    strategy_config_risk.update({
        "use_risk_model": True,
        "risk_model_path": "models/risk_model.joblib",
        "risk_threshold_on": 0.826,
        "risk_threshold_off": 0.496,
    })

    output_dir_exp01 = Path("data/results/SMOKE_TEST_EXP01")
    output_dir_exp01.mkdir(parents=True, exist_ok=True)

    print(f"Running EXP01 (1 day, r=0.70, crunch, risk model)...")
    print(f"Output: {output_dir_exp01}")

    os.environ["VRP_TIME_LIMIT_SECONDS"] = "60"

    sim = RollingHorizonIntegrated(
        data_source=data_exp01,
        strategy_config=strategy_config_risk,
        seed=999,
        run_context={"run_id": "SMOKE_EXP01", "scenario": "Crunch", "strategy": "ProactiveRisk", "seed": 999},
        results_dir=str(output_dir_exp01.parent),
        run_id="SMOKE_EXP01",
        verbose=False,
    )

    results_exp01 = sim.run_simulation()

    # Verify risk_p is recorded
    csv_path = output_dir_exp01 / "Crunch" / "ProactiveRisk" / "daily_stats.csv"
    if csv_path.exists():
        import pandas as pd
        df = pd.read_csv(csv_path)

        if 'risk_p' in df.columns:
            risk_p = df['risk_p'].iloc[0] if len(df) > 0 else 0.0
            print(f"✓ risk_p recorded: {risk_p:.3f}")

            if risk_p > 0.5:
                print(f"✓ Risk model is active (risk_p > 0.5)")
            else:
                print(f"⚠️  Risk model returned low risk (risk_p = {risk_p:.3f})")
        else:
            print(f"⚠️  risk_p column not found in CSV")

        if 'compute_limit_seconds' in df.columns:
            compute_limit = df['compute_limit_seconds'].iloc[0] if len(df) > 0 else 60
            print(f"✓ compute_limit_seconds recorded: {compute_limit}s")
        else:
            print(f"⚠️  compute_limit_seconds not recorded")

    # Extract summary
    if results_exp01:
        print(f"✓ Simulation completed")

        summary = {
            "service_rate": results_exp01.get('service_rate', 0.0),
            "total_cost": results_exp01.get('total_cost', 0.0),
            "delivered_count": results_exp01.get('delivered_count', 0),
            "failed_count": results_exp01.get('failed_count', 0),
        }

        summary_path = output_dir_exp01 / "summary_final.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)

        print(f"✓ summary_final.json created")
        print(f"  Service Rate: {summary['service_rate']:.2%}")

        test2_passed = True
    else:
        print(f"✗ FAIL: Simulation returned None")

except Exception as e:
    print(f"✗ FAIL: EXP01 crashed with error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# FINAL VERDICT
# ============================================================================

print("\n" + "="*70)
print("SMOKE TEST RESULTS")
print("="*70)

print(f"TEST 1 (EXP00 - BAU Baseline):        {'✅ PASS' if test1_passed else '❌ FAIL'}")
print(f"TEST 2 (EXP01 - Crunch + RiskGate):   {'✅ PASS' if test2_passed else '❌ FAIL'}")

print()

if test1_passed and test2_passed:
    print("✅ ALL SMOKE TESTS PASSED")
    print()
    print("Pipeline is ready for HPC submission!")
    print("Next step: Generate HPC job scripts")
    sys.exit(0)
else:
    print("❌ SMOKE TESTS FAILED")
    print()
    print("DO NOT submit to HPC until all tests pass!")
    print("Review error messages above and fix issues.")
    sys.exit(1)
