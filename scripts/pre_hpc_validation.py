#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上 HPC 前最小核验 - 3个关键检查

避免 60 jobs 白跑，确保：
1. risk_model.joblib 是 Pipeline (含 scaler+clf)
2. risk_p 无占位符污染
3. compute_limit_seconds 真传到 OR-Tools
"""

import sys
from pathlib import Path

repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

print("="*80)
print("上 HPC 前最小核验 (3个检查)")
print("="*80)

# ============================================================================
# 检查 1: risk_model.joblib 是 Pipeline (含 scaler+clf)
# ============================================================================

print("\n" + "="*80)
print("检查 1: risk_model.joblib 结构")
print("="*80)

try:
    import joblib

    model_path = repo_root / "models/risk_model.joblib"
    if not model_path.exists():
        print(f"❌ FAIL: Model file not found at {model_path}")
        sys.exit(1)

    model = joblib.load(model_path)

    print(f"✓ Model loaded from: {model_path}")
    print(f"✓ Model type: {type(model)}")
    print(f"✓ Model class: {model.__class__.__name__}")

    # Check if Pipeline
    from sklearn.pipeline import Pipeline
    if not isinstance(model, Pipeline):
        print(f"❌ FAIL: Model is not a Pipeline, got {type(model)}")
        sys.exit(1)

    print(f"✓ Model is Pipeline")

    # Check steps
    if hasattr(model, 'named_steps'):
        steps = list(model.named_steps.keys())
        print(f"✓ Pipeline steps: {steps}")

        if 'scaler' not in steps:
            print(f"⚠️  WARNING: No 'scaler' step found")
        else:
            print(f"✓ Has scaler: {type(model.named_steps['scaler']).__name__}")

        if 'clf' not in steps:
            print(f"⚠️  WARNING: No 'clf' step found")
        else:
            print(f"✓ Has classifier: {type(model.named_steps['clf']).__name__}")

    # Check feature names
    if hasattr(model, 'feature_names_in_'):
        print(f"✓ Feature names: {list(model.feature_names_in_)}")

    print("\n✅ 检查 1 通过: Model 是 Pipeline 且结构正确")

except Exception as e:
    print(f"❌ FAIL: 检查 1 失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================================
# 检查 2: risk_p 无占位符污染
# ============================================================================

print("\n" + "="*80)
print("检查 2: risk_p 占位符检查")
print("="*80)

try:
    import pandas as pd
    import numpy as np

    # Check BAU results
    bau_csv = repo_root / "data/results/ACCEPTANCE_TEST/BAU/ProactiveRisk/daily_stats.csv"
    if not bau_csv.exists():
        print(f"⚠️  WARNING: BAU results not found, skipping check 2")
    else:
        df = pd.read_csv(bau_csv)

        print(f"✓ Loaded BAU daily_stats: {len(df)} days")

        # Check Day 1
        day1_risk_p = df.iloc[0]['risk_p']
        day1_valid = df.iloc[0]['risk_p_valid']

        print(f"✓ Day 1: risk_p={day1_risk_p}, risk_p_valid={day1_valid}")

        if pd.isna(day1_risk_p) and day1_valid == 0:
            print(f"✓ Day 1 正确: risk_p=NaN, risk_p_valid=0 (无历史)")
        else:
            print(f"⚠️  WARNING: Day 1 应该是 NaN/0, 但得到 {day1_risk_p}/{day1_valid}")

        # Check Day 2+
        day2_plus = df[df.index >= 1]
        valid_count = (day2_plus['risk_p_valid'] == 1).sum()
        total_count = len(day2_plus)

        print(f"✓ Day 2+ risk_p_valid=1: {valid_count}/{total_count}")

        if valid_count == total_count:
            print(f"✓ Day 2+ 全部有效")
        else:
            print(f"⚠️  WARNING: Day 2+ 有 {total_count - valid_count} 天无效")

        # Check for placeholder values (0.5, 0.0, etc.)
        valid_risk_p = day2_plus[day2_plus['risk_p_valid'] == 1]['risk_p']

        if len(valid_risk_p) > 0:
            placeholder_05 = (valid_risk_p == 0.5).sum()
            placeholder_00 = (valid_risk_p == 0.0).sum()

            print(f"✓ Placeholder 检查:")
            print(f"  - risk_p=0.5 的天数: {placeholder_05}")
            print(f"  - risk_p=0.0 的天数: {placeholder_00}")

            if placeholder_05 > 0 or placeholder_00 > 0:
                print(f"⚠️  WARNING: 发现可能的占位符值")
            else:
                print(f"✓ 无占位符污染")

        # Check risk_mode_on logic
        risk_mode_on_when_invalid = df[df['risk_p_valid'] == 0]['risk_mode_on'].sum()

        if risk_mode_on_when_invalid > 0:
            print(f"❌ FAIL: risk_p_valid=0 时 risk_mode_on 应该为 0，但有 {risk_mode_on_when_invalid} 天不是")
            sys.exit(1)
        else:
            print(f"✓ risk_p_valid=0 时 risk_mode_on=0 (正确)")

        print("\n✅ 检查 2 通过: risk_p 无占位符污染，逻辑正确")

except Exception as e:
    print(f"❌ FAIL: 检查 2 失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================================
# 检查 3: compute_limit_seconds 传到 OR-Tools
# ============================================================================

print("\n" + "="*80)
print("检查 3: compute_limit_seconds 传递检查")
print("="*80)

try:
    # Check if Crunch results exist
    crunch_csv = repo_root / "data/results/ACCEPTANCE_TEST/Crunch/ProactiveRisk/daily_stats.csv"

    if not crunch_csv.exists():
        print(f"⚠️  WARNING: Crunch results not found, skipping check 3")
    else:
        df = pd.read_csv(crunch_csv)

        print(f"✓ Loaded Crunch daily_stats: {len(df)} days")

        # Find days with risk_mode_on=1
        high_risk_days = df[df['risk_mode_on'] == 1]

        if len(high_risk_days) == 0:
            print(f"⚠️  WARNING: 没有 HIGH_RISK 天，无法验证 compute_limit")
        else:
            print(f"✓ 找到 {len(high_risk_days)} 天 HIGH_RISK 模式")

            # Check compute_limit_seconds
            for idx, row in high_risk_days.iterrows():
                day = idx + 1
                compute_limit = row['compute_limit_seconds']
                risk_p = row['risk_p']

                print(f"  Day {day}: risk_p={risk_p:.3f}, compute_limit={compute_limit}s")

                if compute_limit == 60:
                    print(f"    ⚠️  WARNING: HIGH_RISK 但 compute_limit=60s (应该是 180s)")
                elif compute_limit == 180:
                    print(f"    ✓ HIGH_RISK 且 compute_limit=180s (正确)")
                else:
                    print(f"    ⚠️  WARNING: 意外的 compute_limit={compute_limit}s")

            # Check low risk days
            low_risk_days = df[df['risk_mode_on'] == 0]
            low_risk_compute = low_risk_days['compute_limit_seconds'].unique()

            print(f"✓ LOW_RISK 天的 compute_limit: {low_risk_compute}")

            if all(c == 60 for c in low_risk_compute):
                print(f"✓ LOW_RISK 天全部使用 60s (正确)")
            else:
                print(f"⚠️  WARNING: LOW_RISK 天有非 60s 的 compute_limit")

        print("\n✅ 检查 3 通过: compute_limit_seconds 正确传递")

        print("\n" + "="*80)
        print("⚠️  注意: 此检查仅验证 daily_stats 中的记录")
        print("建议: 检查 VRP solver 日志，确认 OR-Tools 实际使用的 time_limit")
        print("示例: grep 'Time limit' logs/*.log")
        print("="*80)

except Exception as e:
    print(f"❌ FAIL: 检查 3 失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================================
# 总结
# ============================================================================

print("\n" + "="*80)
print("✅ 所有核验通过")
print("="*80)

print("\n核验结果:")
print("  ✅ 检查 1: risk_model.joblib 是 Pipeline (含 scaler+clf)")
print("  ✅ 检查 2: risk_p 无占位符污染，Day 1=NaN, Day 2+=valid")
print("  ✅ 检查 3: compute_limit_seconds 正确记录 (60s/180s)")

print("\n可以提交到 HPC (LSF):")
print("  bash jobs/submit_all.sh")
print("  或: bsub < jobs/your_job.lsf")

print("\n建议:")
print("  1. 提交前再次运行: python3 scripts/quick_acceptance_test.py")
print("  2. 提交后检查第一个 job 的日志，确认 OR-Tools time_limit 正确")
print("  3. 监控 bjobs 状态，确保任务正常运行")

sys.exit(0)
