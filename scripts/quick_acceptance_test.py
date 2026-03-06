#!/usr/bin/env python3
"""
验收测试：确认 risk_p 在所有模式下都被计算

测试场景：
1. BAU (12天): 验证 Day2+ risk_p_valid=1, risk_p 低且变化, risk_mode_on 基本为 0
2. Crunch (12天): 验证 risk_p 在 crunch 前/中/后变化, risk_mode_on 有 0→1→0 转换
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import timedelta
import json

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.simulation.rolling_horizon_integrated import RollingHorizonIntegrated
from src.experiments.exp_utils import build_capacity_crunch

print("="*70)
print("验收测试：Risk Prediction 在所有模式下执行")
print("="*70)

# Load base data
data_path = REPO_ROOT / "data/processed/multiday_benchmark_herlev.json"
with open(data_path, 'r') as f:
    base_data = json.load(f)

# Config with RiskGate
config = {
    'mode': 'proactive_quota',
    'use_risk_model': True,
    'risk_model_path': 'models/risk_model.joblib',
    'risk_threshold_on': 0.826,
    'risk_threshold_off': 0.496,
    'base_compute': 60,
    'high_compute': 180,
}

output_dir = REPO_ROOT / "data/results/ACCEPTANCE_TEST"
output_dir.mkdir(parents=True, exist_ok=True)

# =========================================================================
# Test 1: BAU (12 days)
# =========================================================================
print("\n" + "="*70)
print("Test 1: BAU (12 天)")
print("="*70)

data_bau = build_capacity_crunch(
    base_data,
    crunch_ratio=1.0,  # No crunch
    crunch_start=999,
    crunch_end=999,
    horizon_days=12
)

sim_bau = RollingHorizonIntegrated(
    data_source=data_bau,
    strategy_config=config,
    seed=1,
    verbose=False,
    base_dir=str(output_dir),
    scenario_name="BAU",
    strategy_name="ProactiveRisk"
)

sim_bau.end_date = sim_bau.start_date + timedelta(days=11)  # 12 days

print("运行 BAU 仿真...")
results_bau = sim_bau.run_simulation()
print(f"✅ BAU 完成, Service rate: {results_bau.get('service_rate', 0):.2%}")

# Load BAU stats
stats_path_bau = output_dir / "BAU" / "ProactiveRisk" / "daily_stats.csv"
df_bau = pd.read_csv(stats_path_bau)
df_bau['day_idx'] = range(len(df_bau))

print("\n" + "-"*70)
print("BAU 前 12 天数据")
print("-"*70)
print(df_bau[['date', 'mode_status', 'capacity_ratio', 'risk_p', 'risk_p_valid',
              'risk_mode_on', 'compute_limit_seconds', 'failures']].head(12).to_string(index=False))

# =========================================================================
# Test 2: Crunch (12 days, crunch on days 5-7)
# =========================================================================
print("\n" + "="*70)
print("Test 2: Crunch (12 天, days 5-7 crunch)")
print("="*70)

data_crunch = build_capacity_crunch(
    base_data,
    crunch_ratio=0.60,  # Severe crunch
    crunch_start=5,
    crunch_end=7,
    horizon_days=12
)

sim_crunch = RollingHorizonIntegrated(
    data_source=data_crunch,
    strategy_config=config,
    seed=1,
    verbose=False,
    base_dir=str(output_dir),
    scenario_name="Crunch",
    strategy_name="ProactiveRisk"
)

sim_crunch.end_date = sim_crunch.start_date + timedelta(days=11)  # 12 days

print("运行 Crunch 仿真...")
results_crunch = sim_crunch.run_simulation()
print(f"✅ Crunch 完成, Service rate: {results_crunch.get('service_rate', 0):.2%}")

# Load Crunch stats
stats_path_crunch = output_dir / "Crunch" / "ProactiveRisk" / "daily_stats.csv"
df_crunch = pd.read_csv(stats_path_crunch)
df_crunch['day_idx'] = range(len(df_crunch))

print("\n" + "-"*70)
print("Crunch 前 12 天数据")
print("-"*70)
print(df_crunch[['date', 'mode_status', 'capacity_ratio', 'risk_p', 'risk_p_valid',
                 'risk_mode_on', 'compute_limit_seconds', 'failures']].head(12).to_string(index=False))

# =========================================================================
# Validation Checks
# =========================================================================
print("\n" + "="*70)
print("验收检查")
print("="*70)

# Check 1: BAU - Day 2+ should have risk_p_valid=1
bau_day2_plus = df_bau[df_bau['day_idx'] >= 1]
bau_valid_count = bau_day2_plus['risk_p_valid'].sum()
bau_total_days = len(bau_day2_plus)

print(f"\n✓ Check 1: BAU Day2+ risk_p_valid=1")
print(f"  Valid days: {bau_valid_count}/{bau_total_days}")
if bau_valid_count >= bau_total_days * 0.9:  # Allow 1 day tolerance
    print(f"  ✅ PASS")
else:
    print(f"  ❌ FAIL - Expected most days to have valid risk_p")

# Check 2: BAU - risk_p should be low and vary
bau_valid_risk = bau_day2_plus[bau_day2_plus['risk_p_valid'] == 1]['risk_p']
if len(bau_valid_risk) > 0:
    bau_mean_risk = bau_valid_risk.mean()
    bau_std_risk = bau_valid_risk.std()
    print(f"\n✓ Check 2: BAU risk_p 低且变化")
    print(f"  Mean risk_p: {bau_mean_risk:.4f}")
    print(f"  Std risk_p: {bau_std_risk:.4f}")
    if bau_mean_risk < 0.5 and bau_std_risk > 0.001:
        print(f"  ✅ PASS")
    else:
        print(f"  ❌ FAIL - Expected low mean (<0.5) and variation (>0.001)")

# Check 3: Crunch - Day 2+ should have risk_p_valid=1
crunch_day2_plus = df_crunch[df_crunch['day_idx'] >= 1]
crunch_valid_count = crunch_day2_plus['risk_p_valid'].sum()
crunch_total_days = len(crunch_day2_plus)

print(f"\n✓ Check 3: Crunch Day2+ risk_p_valid=1")
print(f"  Valid days: {crunch_valid_count}/{crunch_total_days}")
if crunch_valid_count >= crunch_total_days * 0.9:
    print(f"  ✅ PASS")
else:
    print(f"  ❌ FAIL - Expected most days to have valid risk_p")

# Check 4: Crunch - risk_p should vary (rise during crunch, fall after)
crunch_valid = df_crunch[df_crunch['risk_p_valid'] == 1]
if len(crunch_valid) > 0:
    pre_crunch = crunch_valid[crunch_valid['day_idx'] < 5]['risk_p']
    during_crunch = crunch_valid[(crunch_valid['day_idx'] >= 5) & (crunch_valid['day_idx'] <= 7)]['risk_p']
    post_crunch = crunch_valid[crunch_valid['day_idx'] > 7]['risk_p']

    print(f"\n✓ Check 4: Crunch risk_p 轨迹")
    if len(pre_crunch) > 0:
        print(f"  Pre-crunch (days 1-4): mean={pre_crunch.mean():.4f}")
    if len(during_crunch) > 0:
        print(f"  During-crunch (days 5-7): mean={during_crunch.mean():.4f}")
    if len(post_crunch) > 0:
        print(f"  Post-crunch (days 8+): mean={post_crunch.mean():.4f}")

    # Check if risk rises during crunch
    if len(during_crunch) > 0 and len(pre_crunch) > 0:
        if during_crunch.mean() > pre_crunch.mean():
            print(f"  ✅ PASS - Risk rises during crunch")
        else:
            print(f"  ⚠️  WARNING - Risk did not rise during crunch")

# Check 5: Crunch - risk_mode_on should have transitions
crunch_risk_mode = df_crunch['risk_mode_on'].values
has_zero = 0 in crunch_risk_mode
has_one = 1 in crunch_risk_mode

print(f"\n✓ Check 5: Crunch risk_mode_on 转换")
print(f"  Has 0: {has_zero}, Has 1: {has_one}")
if has_zero and has_one:
    print(f"  ✅ PASS - risk_mode_on has transitions")
else:
    print(f"  ⚠️  WARNING - risk_mode_on did not transition (may need stronger crunch)")

# Check 6: Crisis mode should still have risk_p
crisis_days_bau = df_bau[df_bau['mode_status'] == 'CRISIS_FILL']
crisis_days_crunch = df_crunch[df_crunch['mode_status'] == 'CRISIS_FILL']

print(f"\n✓ Check 6: CRISIS_FILL 期间仍有 risk_p")
print(f"  BAU crisis days: {len(crisis_days_bau)}")
print(f"  Crunch crisis days: {len(crisis_days_crunch)}")

if len(crisis_days_crunch) > 0:
    crisis_with_valid = crisis_days_crunch[crisis_days_crunch['risk_p_valid'] == 1]
    print(f"  Crisis days with valid risk_p: {len(crisis_with_valid)}/{len(crisis_days_crunch)}")
    if len(crisis_with_valid) > 0:
        print(f"  ✅ PASS - Crisis mode has risk_p")
    else:
        print(f"  ❌ FAIL - Crisis mode missing risk_p")

print("\n" + "="*70)
print("验收测试完成")
print("="*70)
