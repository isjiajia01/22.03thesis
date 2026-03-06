#!/usr/bin/env python3
"""
Completion Audit Script - Generates completion matrix and gap report
"""
import os
import json
import csv
from datetime import datetime
from pathlib import Path

# Timestamp for all output files
TS = datetime.now().strftime("%Y%m%d_%H%M%S")

BASE_DIR = Path("/zhome/2a/1/202283/thesis")
RESULTS_DIR = BASE_DIR / "data" / "results"
AUDITS_DIR = BASE_DIR / "data" / "audits"
AUDITS_DIR.mkdir(parents=True, exist_ok=True)

# Define expected matrix based on experiment_definitions.py
EXPERIMENTS = {
    "EXP00": {
        "endpoints": ["baseline"],  # No endpoint key, direct Seed_N
        "seeds": list(range(1, 11)),
        "has_endpoint_dir": False,
    },
    "EXP01": {
        "endpoints": ["baseline"],
        "seeds": list(range(1, 11)),
        "has_endpoint_dir": False,
    },
    "EXP02": {
        "endpoints": ["baseline"],
        "seeds": list(range(1, 11)),
        "has_endpoint_dir": False,
    },
    "EXP03": {
        "endpoints": ["baseline"],
        "seeds": list(range(1, 11)),
        "has_endpoint_dir": False,
    },
    "EXP04": {
        "endpoints": ["baseline"],
        "seeds": list(range(1, 11)),
        "has_endpoint_dir": False,
    },
    "EXP05": {
        "endpoints": ["max_trips_2", "max_trips_3"],
        "seeds": list(range(1, 11)),
        "has_endpoint_dir": True,
    },
    "EXP06": {
        "endpoints": ["ratio_0.58", "ratio_0.59"],
        "seeds": list(range(1, 11)),
        "has_endpoint_dir": True,
    },
    "EXP07": {
        "endpoints": [
            "ratio_0.6_risk_False", "ratio_0.6_risk_True",
            "ratio_0.61_risk_False", "ratio_0.61_risk_True"
        ],
        "seeds": list(range(1, 11)),
        "has_endpoint_dir": True,
    },
    "EXP08": {
        "endpoints": ["delta_0.6", "delta_0.7", "delta_0.826", "delta_0.9"],
        "seeds": list(range(1, 6)),  # 5 seeds
        "has_endpoint_dir": True,
    },
    "EXP09": {
        "endpoints": ["risk_False", "risk_True"],
        "seeds": list(range(1, 11)),
        "has_endpoint_dir": True,
    },
    "EXP10": {
        "endpoints": [f"ratio_{r}" for r in ["0.55", "0.56", "0.57", "0.58", "0.59",
                                              "0.6", "0.61", "0.62", "0.63", "0.64", "0.65"]],
        "seeds": list(range(1, 4)),  # 3 seeds
        "has_endpoint_dir": True,
    },
    "EXP11": {
        "endpoints": [
            f"risk_{risk}_tl_{tl}"
            for risk in ["False", "True"]
            for tl in [30, 60, 120, 300]
        ],
        "seeds": list(range(1, 11)),
        "has_endpoint_dir": True,
    },
}

def get_expected_dir(exp_id, endpoint_key, seed, has_endpoint_dir):
    """Get expected directory path for a run"""
    exp_dir = RESULTS_DIR / f"EXP_{exp_id}"
    if has_endpoint_dir:
        return exp_dir / endpoint_key / f"Seed_{seed}"
    else:
        return exp_dir / f"Seed_{seed}"

def check_artifacts(run_dir):
    """Check for the three required artifacts"""
    config_path = run_dir / "config_dump.json"
    sim_path = run_dir / "simulation_results.json"
    summary_path = run_dir / "summary_final.json"

    dir_exists = run_dir.exists()
    config_exists = config_path.exists()
    sim_exists = sim_path.exists()
    summary_exists = summary_path.exists()

    sim_size = sim_path.stat().st_size if sim_exists else 0
    summary_size = summary_path.stat().st_size if summary_exists else 0
    mtime_sim = datetime.fromtimestamp(sim_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if sim_exists else ""

    return {
        "dir_exists": dir_exists,
        "config_exists": config_exists,
        "sim_exists": sim_exists,
        "summary_exists": summary_exists,
        "sim_size": sim_size,
        "summary_size": summary_size,
        "mtime_sim": mtime_sim,
    }

def determine_reason(artifacts):
    """Determine the reason for incompleteness"""
    if not artifacts["dir_exists"]:
        return "no_dir"
    if not artifacts["config_exists"] and not artifacts["sim_exists"] and not artifacts["summary_exists"]:
        return "empty_dir"
    if artifacts["config_exists"] and not artifacts["sim_exists"] and not artifacts["summary_exists"]:
        return "config_only"
    if not artifacts["summary_exists"]:
        return "missing_summary"
    if not artifacts["sim_exists"]:
        return "missing_sim"
    if not artifacts["config_exists"]:
        return "missing_config"
    return "unknown"

def main():
    print(f"Starting completion audit at {TS}")

    # Generate expected matrix
    expected_rows = []
    for exp_id, exp_def in EXPERIMENTS.items():
        for endpoint_key in exp_def["endpoints"]:
            for seed in exp_def["seeds"]:
                expected_dir = get_expected_dir(exp_id, endpoint_key, seed, exp_def["has_endpoint_dir"])
                expected_rows.append({
                    "exp_id": exp_id,
                    "endpoint_key": endpoint_key,
                    "seed": seed,
                    "expected_dir": str(expected_dir),
                })

    # Write expected matrix
    expected_file = AUDITS_DIR / f"completion_expected_matrix_{TS}.csv"
    with open(expected_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["exp_id", "endpoint_key", "seed", "expected_dir"])
        writer.writeheader()
        writer.writerows(expected_rows)
    print(f"Written: {expected_file}")

    # Check actual artifacts
    actual_rows = []
    gap_rows = []

    for row in expected_rows:
        run_dir = Path(row["expected_dir"])
        artifacts = check_artifacts(run_dir)

        actual_row = {
            "exp_id": row["exp_id"],
            "endpoint_key": row["endpoint_key"],
            "seed": row["seed"],
            **artifacts,
        }
        actual_rows.append(actual_row)

        # Check if complete (all three artifacts exist)
        is_complete = artifacts["config_exists"] and artifacts["sim_exists"] and artifacts["summary_exists"]

        if not is_complete:
            gap_row = {
                "exp_id": row["exp_id"],
                "endpoint_key": row["endpoint_key"],
                "seed": row["seed"],
                "dir_exists": artifacts["dir_exists"],
                "config_exists": artifacts["config_exists"],
                "sim_exists": artifacts["sim_exists"],
                "summary_exists": artifacts["summary_exists"],
                "reason": determine_reason(artifacts),
            }
            gap_rows.append(gap_row)

    # Write actual artifacts
    actual_file = AUDITS_DIR / f"completion_actual_artifacts_{TS}.csv"
    with open(actual_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "exp_id", "endpoint_key", "seed", "dir_exists", "config_exists",
            "sim_exists", "summary_exists", "sim_size", "summary_size", "mtime_sim"
        ])
        writer.writeheader()
        writer.writerows(actual_rows)
    print(f"Written: {actual_file}")

    # Write gap report
    gap_file = AUDITS_DIR / f"completion_gap_report_{TS}.csv"
    with open(gap_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "exp_id", "endpoint_key", "seed", "dir_exists", "config_exists",
            "sim_exists", "summary_exists", "reason"
        ])
        writer.writeheader()
        writer.writerows(gap_rows)
    print(f"Written: {gap_file}")

    # Calculate summary statistics
    total_expected = len(expected_rows)
    total_complete = total_expected - len(gap_rows)
    incomplete_count = len(gap_rows)

    # Group gaps by experiment
    gap_by_exp = {}
    for row in gap_rows:
        exp_id = row["exp_id"]
        if exp_id not in gap_by_exp:
            gap_by_exp[exp_id] = 0
        gap_by_exp[exp_id] += 1

    # Write summary
    summary_file = AUDITS_DIR / f"completion_summary_{TS}.txt"
    with open(summary_file, "w") as f:
        f.write("=" * 60 + "\n")
        f.write("COMPLETION AUDIT SUMMARY\n")
        f.write(f"Generated: {TS}\n")
        f.write("=" * 60 + "\n\n")

        f.write(f"total_expected_runs: {total_expected}\n")
        f.write(f"total_complete_runs: {total_complete}\n")
        f.write(f"incomplete_runs_count: {incomplete_count}\n\n")

        if incomplete_count > 0:
            f.write("STATUS: NOT COMPLETE\n\n")
        else:
            f.write("STATUS: COMPLETE\n\n")

        f.write("-" * 60 + "\n")
        f.write("GAPS BY EXPERIMENT:\n")
        f.write("-" * 60 + "\n")
        f.write(f"{'EXP_ID':<10} {'EXPECTED':<10} {'MISSING':<10} {'COMPLETE':<10}\n")
        f.write("-" * 60 + "\n")

        for exp_id in sorted(EXPERIMENTS.keys()):
            exp_def = EXPERIMENTS[exp_id]
            expected = len(exp_def["endpoints"]) * len(exp_def["seeds"])
            missing = gap_by_exp.get(exp_id, 0)
            complete = expected - missing
            f.write(f"{exp_id:<10} {expected:<10} {missing:<10} {complete:<10}\n")

        f.write("-" * 60 + "\n")
        f.write(f"{'TOTAL':<10} {total_expected:<10} {incomplete_count:<10} {total_complete:<10}\n")
        f.write("=" * 60 + "\n")

    print(f"Written: {summary_file}")

    # Print summary to stdout
    print("\n" + "=" * 60)
    print(f"total_expected_runs: {total_expected}")
    print(f"total_complete_runs: {total_complete}")
    print(f"incomplete_runs_count: {incomplete_count}")
    print("=" * 60)

    return {
        "total_expected": total_expected,
        "total_complete": total_complete,
        "incomplete_count": incomplete_count,
        "gap_file": str(gap_file),
        "summary_file": str(summary_file),
        "ts": TS,
    }

if __name__ == "__main__":
    result = main()
    print(f"\nTimestamp: {result['ts']}")
