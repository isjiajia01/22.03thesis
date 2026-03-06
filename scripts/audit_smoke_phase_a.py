#!/usr/bin/env python3
"""
Phase A Smoke Test Audit - Verify sweep parameters propagated correctly
"""

import os
import json
import csv
import math
from datetime import datetime
from pathlib import Path

BASE_DIR = Path("/zhome/2a/1/202283/thesis")
RESULTS_DIR = BASE_DIR / "data/results"
AUDITS_DIR = BASE_DIR / "data/audits"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M")

# Expected smoke cases
SMOKE_CASES = [
    ("EXP05", "max_trips_2", {"max_trips": 2}),
    ("EXP05", "max_trips_3", {"max_trips": 3}),
    ("EXP06", "ratio_0.58", {"ratio": 0.58}),
    ("EXP06", "ratio_0.59", {"ratio": 0.59}),
    ("EXP07", "ratio_0.60_risk_off", {"ratio": 0.60, "use_risk_model": False}),
    ("EXP07", "ratio_0.60_risk_on", {"ratio": 0.60, "use_risk_model": True}),
    ("EXP08", "delta_on_0.6", {"risk_threshold_on": 0.6, "risk_threshold_off": 0.36}),
    ("EXP08", "delta_on_0.9", {"risk_threshold_on": 0.9, "risk_threshold_off": 0.54}),
    ("EXP09", "two_wave_risk_off", {"use_risk_model": False}),
    ("EXP09", "two_wave_risk_on", {"use_risk_model": True}),
]

def load_json(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return None

def find_output_dir(exp_id, overrides):
    """Find output directory matching the overrides."""
    exp_base = RESULTS_DIR / f"EXP_{exp_id}"
    if not exp_base.exists():
        return None

    for subdir in exp_base.iterdir():
        if not subdir.is_dir():
            continue
        seed_dir = subdir / "Seed_1" if (subdir / "Seed_1").exists() else None
        if not seed_dir:
            # Maybe it's directly in subdir
            if (subdir / "config_dump.json").exists():
                seed_dir = subdir
            else:
                continue

        config = load_json(seed_dir / "config_dump.json")
        if not config:
            continue

        params = config.get("parameters", {})
        overrides_applied = config.get("overrides_applied", {})

        # Check if this matches our overrides
        match = True
        for key, expected in overrides.items():
            actual = params.get(key)
            if actual != expected:
                match = False
                break

        if match:
            return seed_dir

    return None

def audit_case(exp_id, label, overrides):
    """Audit a single smoke case."""
    result = {
        "exp_id": exp_id,
        "label": label,
        "output_dir": "",
        "config_found": False,
        "daily_found": False,
        "days_12": False,
        "sweep_in_config": False,
        "behavior_ok": False,
        "details": "",
        "overall": "FAIL"
    }

    output_dir = find_output_dir(exp_id, overrides)
    if not output_dir:
        result["details"] = "Output directory not found"
        return result

    result["output_dir"] = str(output_dir)

    # Load config
    config = load_json(output_dir / "config_dump.json")
    if config:
        result["config_found"] = True
        params = config.get("parameters", {})

        # Check sweep params in config
        all_match = True
        for key, expected in overrides.items():
            actual = params.get(key)
            if actual != expected:
                all_match = False
                result["details"] += f"{key}: expected={expected}, got={actual}; "
        result["sweep_in_config"] = all_match

    # Load simulation results
    sim = load_json(output_dir / "simulation_results.json")
    if sim:
        daily = sim.get("daily_stats", [])
        if daily:
            result["daily_found"] = True
            result["days_12"] = len(daily) == 12

            # Behavior checks based on experiment type
            if "ratio" in overrides:
                # Check capacity_ratio in crunch window (days 5-10, index 4-9)
                crunch_ratios = [d.get("capacity_ratio", 1.0) for d in daily[4:10]]
                min_ratio = min(crunch_ratios) if crunch_ratios else 1.0
                expected = overrides["ratio"]
                result["behavior_ok"] = abs(min_ratio - expected) < 0.01
                result["details"] += f"crunch_ratio={min_ratio:.4f} (expected {expected}); "

            if "use_risk_model" in overrides:
                expected_risk = overrides["use_risk_model"]
                risk_loaded = [d.get("risk_model_loaded", 0) for d in daily]
                unique_loaded = set(risk_loaded)
                if expected_risk:
                    result["behavior_ok"] = unique_loaded == {1}
                else:
                    result["behavior_ok"] = 1 not in unique_loaded
                result["details"] += f"risk_loaded={unique_loaded} (expected {'all 1' if expected_risk else 'no 1'}); "

            if "risk_threshold_on" in overrides:
                expected_delta = overrides["risk_threshold_on"]
                actual_delta = daily[0].get("risk_delta_on", params.get("risk_threshold_on", 0.826))
                result["behavior_ok"] = abs(actual_delta - expected_delta) < 0.01
                result["details"] += f"delta_on={actual_delta} (expected {expected_delta}); "

            if "max_trips" in overrides:
                # For max_trips, just verify config propagated - behavior diff needs comparison
                result["behavior_ok"] = result["sweep_in_config"]
                vrp_dropped = sum(d.get("vrp_dropped", 0) for d in daily)
                result["details"] += f"vrp_dropped={vrp_dropped}; "

    # Overall
    if (result["config_found"] and result["daily_found"] and
        result["days_12"] and result["sweep_in_config"] and result["behavior_ok"]):
        result["overall"] = "PASS"

    return result

def main():
    print(f"Phase A Smoke Test Audit - {TIMESTAMP}")
    print("=" * 70)

    results = []
    for exp_id, label, overrides in SMOKE_CASES:
        result = audit_case(exp_id, label, overrides)
        results.append(result)
        status = "✅" if result["overall"] == "PASS" else "❌"
        print(f"{status} {exp_id} {label}: {result['overall']}")

    # Write traffic light CSV
    tl_path = AUDITS_DIR / f"smoke_traffic_light_{TIMESTAMP}.csv"
    with open(tl_path, 'w', newline='') as f:
        fieldnames = ["exp_id", "label", "config_found", "daily_found", "days_12",
                      "sweep_in_config", "behavior_ok", "overall"]
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)

    # Write detailed TXT
    txt_path = AUDITS_DIR / f"smoke_audit_detail_{TIMESTAMP}.txt"
    lines = []
    lines.append("=" * 70)
    lines.append(f"PHASE A SMOKE TEST AUDIT")
    lines.append(f"Generated: {TIMESTAMP}")
    lines.append("=" * 70)

    for r in results:
        lines.append("")
        lines.append(f"{'-'*50}")
        lines.append(f"{r['exp_id']} - {r['label']}: {r['overall']}")
        lines.append(f"{'-'*50}")
        lines.append(f"  output_dir: {r['output_dir']}")
        lines.append(f"  config_found: {r['config_found']}")
        lines.append(f"  daily_found: {r['daily_found']}")
        lines.append(f"  days_12: {r['days_12']}")
        lines.append(f"  sweep_in_config: {r['sweep_in_config']}")
        lines.append(f"  behavior_ok: {r['behavior_ok']}")
        lines.append(f"  details: {r['details']}")

    # Comparison section for max_trips
    lines.append("")
    lines.append("=" * 70)
    lines.append("MAX_TRIPS COMPARISON (EXP05)")
    lines.append("=" * 70)

    for trips in [2, 3]:
        output_dir = find_output_dir("EXP05", {"max_trips": trips})
        if output_dir:
            sim = load_json(output_dir / "simulation_results.json")
            summary = load_json(output_dir / "summary_final.json")
            if sim and summary:
                daily = sim.get("daily_stats", [])
                vrp_dropped = sum(d.get("vrp_dropped", 0) for d in daily)
                sr = summary.get("service_rate_within_window", summary.get("service_rate", 0))
                fail = summary.get("deadline_failure_count", 0)
                lines.append(f"  max_trips={trips}: SR={sr:.4f}, failures={fail}, vrp_dropped={vrp_dropped}")

    # Summary
    lines.append("")
    lines.append("=" * 70)
    lines.append("SUMMARY")
    lines.append("=" * 70)
    pass_count = sum(1 for r in results if r["overall"] == "PASS")
    fail_count = len(results) - pass_count
    lines.append(f"  PASS: {pass_count}/{len(results)}")
    lines.append(f"  FAIL: {fail_count}/{len(results)}")
    lines.append(f"  OVERALL: {'PASS - Ready for Phase B' if fail_count == 0 else 'FAIL - Fix issues before Phase B'}")

    with open(txt_path, 'w') as f:
        f.write("\n".join(lines))

    print()
    print(f"Audit files:")
    print(f"  {tl_path}")
    print(f"  {txt_path}")
    print()
    print(f"OVERALL: {'PASS' if fail_count == 0 else 'FAIL'} ({pass_count}/{len(results)})")

    return 0 if fail_count == 0 else 1

if __name__ == "__main__":
    exit(main())
