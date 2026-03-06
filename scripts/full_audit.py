#!/usr/bin/env python3
"""
Full Audit Script for EXP01-04
Generates all audit files as specified in the audit protocol.
"""

import os
import json
import csv
from datetime import datetime
from pathlib import Path
import math

BASE_DIR = Path("/zhome/2a/1/202283/thesis")
RESULTS_DIR = BASE_DIR / "data/results"
AUDITS_DIR = BASE_DIR / "data/audits"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M")

# Expected configurations per CLAUDE.md
EXPECTED_CONFIG = {
    "EXP01": {"ratio": 0.59, "use_risk_model": False, "base_compute": 60, "high_compute": 60},
    "EXP02": {"ratio": 0.59, "use_risk_model": False, "base_compute": 300, "high_compute": 300},
    "EXP03": {"ratio": 0.59, "use_risk_model": True, "base_compute": 60, "high_compute": 60},
    "EXP04": {"ratio": 0.59, "use_risk_model": True, "base_compute": 60, "high_compute": 300},
}

def load_json(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return None

def get_daily_stats(sim_results):
    """Extract daily_stats from simulation_results.json"""
    if not sim_results:
        return []
    return sim_results.get("daily_stats", [])

def step0_audit_index():
    """Step 0: Build audit index"""
    rows = []
    exps = ["EXP01", "EXP02", "EXP03", "EXP04"]

    for exp in exps:
        exp_dir = RESULTS_DIR / f"EXP_{exp}"
        if not exp_dir.exists():
            continue
        for seed_dir in sorted(exp_dir.glob("Seed_*")):
            seed_num = seed_dir.name.split("_")[1]
            config_path = seed_dir / "config_dump.json"
            sim_path = seed_dir / "simulation_results.json"
            summary_path = seed_dir / "summary_final.json"

            has_config = config_path.exists()
            has_summary = summary_path.exists()

            # Check for daily_stats (inside simulation_results.json)
            has_daily = False
            if sim_path.exists():
                sim = load_json(sim_path)
                if sim and "daily_stats" in sim and len(sim["daily_stats"]) > 0:
                    has_daily = True

            mtime_summary = ""
            if has_summary:
                mtime_summary = datetime.fromtimestamp(summary_path.stat().st_mtime).isoformat()

            rows.append({
                "exp": exp,
                "seed": seed_num,
                "path": str(seed_dir),
                "has_config": int(has_config),
                "has_daily": int(has_daily),
                "has_summary": int(has_summary),
                "mtime_summary": mtime_summary
            })

    out_path = AUDITS_DIR / f"audit_index_{TIMESTAMP}.csv"
    with open(out_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["exp", "seed", "path", "has_config", "has_daily", "has_summary", "mtime_summary"])
        writer.writeheader()
        writer.writerows(rows)

    return rows, out_path

def step1_config_matrix(index_rows):
    """Step 1: Config review from config_dump.json"""
    rows = []

    for idx in index_rows:
        if not idx["has_config"]:
            continue
        config_path = Path(idx["path"]) / "config_dump.json"
        config = load_json(config_path)
        if not config:
            continue

        params = config.get("parameters", config)

        # Also try to get delta_on/off from daily_stats if available
        delta_on = params.get("delta_on", "")
        delta_off = params.get("delta_off", "")

        if not delta_on or not delta_off:
            sim_path = Path(idx["path"]) / "simulation_results.json"
            sim = load_json(sim_path)
            if sim:
                daily = sim.get("daily_stats", [])
                if daily:
                    delta_on = daily[0].get("risk_delta_on", delta_on)
                    delta_off = daily[0].get("risk_delta_off", delta_off)

        rows.append({
            "exp": idx["exp"],
            "seed": idx["seed"],
            "ratio": params.get("ratio", ""),
            "crunch_start": params.get("crunch_start", ""),
            "crunch_end": params.get("crunch_end", ""),
            "total_days": params.get("total_days", ""),
            "use_risk_model": params.get("use_risk_model", params.get("use_risk", "")),
            "base_compute": params.get("base_compute", ""),
            "high_compute": params.get("high_compute", ""),
            "delta_on": delta_on,
            "delta_off": delta_off
        })

    out_path = AUDITS_DIR / f"audit_config_matrix_{TIMESTAMP}.csv"
    with open(out_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["exp", "seed", "ratio", "crunch_start", "crunch_end",
                                                "total_days", "use_risk_model", "base_compute",
                                                "high_compute", "delta_on", "delta_off"])
        writer.writeheader()
        writer.writerows(rows)

    # Generate summary
    summary = {}
    for row in rows:
        exp = row["exp"]
        if exp not in summary:
            summary[exp] = {"configs": [], "match": True}
        summary[exp]["configs"].append(row)

        expected = EXPECTED_CONFIG.get(exp, {})
        if expected:
            if row["base_compute"] != expected.get("base_compute"):
                summary[exp]["match"] = False
            if row["high_compute"] != expected.get("high_compute"):
                summary[exp]["match"] = False
            if row["use_risk_model"] != expected.get("use_risk_model"):
                summary[exp]["match"] = False

    return rows, out_path, summary

def step2_compute_gate(index_rows):
    """Step 2: Compute time limit audit"""
    rows = []
    violations = {"EXP02": 0, "EXP03": 0, "EXP04": 0}
    totals = {"EXP02": 0, "EXP03": 0, "EXP04": 0}

    for idx in index_rows:
        if not idx["has_daily"]:
            continue

        exp = idx["exp"]
        seed = idx["seed"]

        sim_path = Path(idx["path"]) / "simulation_results.json"
        sim = load_json(sim_path)
        if not sim:
            continue

        daily = sim.get("daily_stats", [])
        config_path = Path(idx["path"]) / "config_dump.json"
        config = load_json(config_path)
        params = config.get("parameters", {}) if config else {}

        base_compute = params.get("base_compute", 60)
        high_compute = params.get("high_compute", 60)

        for day_data in daily:
            day = day_data.get("day", day_data.get("date", ""))
            risk_mode_on = day_data.get("risk_mode_on", 0)
            compute_limit = day_data.get("compute_limit_seconds", "")

            # Determine expected compute
            if exp == "EXP02":
                expected = base_compute  # Should be 300 always
            elif exp == "EXP03":
                expected = base_compute  # Should be 60 always (even if risk_mode_on=1)
            elif exp == "EXP04":
                expected = high_compute if risk_mode_on == 1 else base_compute
            else:
                expected = base_compute

            match = (compute_limit == expected)

            if exp in totals:
                totals[exp] += 1
                if not match:
                    violations[exp] += 1

            rows.append({
                "exp": exp,
                "seed": seed,
                "day": day,
                "risk_mode_on": risk_mode_on,
                "compute_limit_seconds": compute_limit,
                "expected_compute": expected,
                "match": int(match)
            })

    out_path = AUDITS_DIR / f"audit_compute_gate_{TIMESTAMP}.csv"
    with open(out_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["exp", "seed", "day", "risk_mode_on",
                                                "compute_limit_seconds", "expected_compute", "match"])
        writer.writeheader()
        writer.writerows(rows)

    return rows, out_path, violations, totals

def step3_riskgate_behavior(index_rows):
    """Step 3: RiskGate behavior audit"""
    csv_rows = []
    txt_lines = []

    for idx in index_rows:
        if idx["exp"] not in ["EXP03", "EXP04"]:
            continue
        if not idx["has_daily"]:
            continue

        exp = idx["exp"]
        seed = idx["seed"]

        sim_path = Path(idx["path"]) / "simulation_results.json"
        sim = load_json(sim_path)
        if not sim:
            continue

        daily = sim.get("daily_stats", [])

        # Analyze risk gate behavior
        risk_model_loaded_all = all(d.get("risk_model_loaded", 0) == 1 for d in daily)

        # risk_p_valid coverage for day >= 2
        day2_plus = [d for d in daily if d.get("day", 0) >= 2 or (isinstance(d.get("date", ""), str) and d.get("date", "") > daily[0].get("date", ""))]
        if not day2_plus:
            day2_plus = daily[1:] if len(daily) > 1 else []

        valid_count = sum(1 for d in day2_plus if d.get("risk_p_valid", 0) == 1)
        valid_coverage = f"{valid_count}/{len(day2_plus)}" if day2_plus else "N/A"

        # risk_p stats
        risk_ps = [d.get("risk_p", float('nan')) for d in daily]
        valid_risk_ps = [p for p in risk_ps if not (isinstance(p, float) and math.isnan(p))]
        max_risk_p = max(valid_risk_ps) if valid_risk_ps else float('nan')

        # Find first day risk_p >= delta_on (0.826)
        delta_on = 0.826
        delta_off = 0.496
        first_trigger_day = None
        for i, d in enumerate(daily):
            rp = d.get("risk_p", float('nan'))
            if not math.isnan(rp) and rp >= delta_on:
                first_trigger_day = i + 1
                break

        # risk_mode_on transitions
        modes = [d.get("risk_mode_on", 0) for d in daily]
        first_on_day = None
        first_off_day = None
        on_days_count = sum(modes)

        for i, m in enumerate(modes):
            if m == 1 and first_on_day is None:
                first_on_day = i + 1
            if first_on_day and m == 0 and first_off_day is None:
                first_off_day = i + 1

        has_transition = first_on_day is not None and first_off_day is not None

        csv_rows.append({
            "exp": exp,
            "seed": seed,
            "risk_model_loaded_all": int(risk_model_loaded_all),
            "risk_p_valid_coverage": valid_coverage,
            "max_risk_p": f"{max_risk_p:.6f}" if not math.isnan(max_risk_p) else "NaN",
            "first_trigger_day": first_trigger_day or "N/A",
            "first_on_day": first_on_day or "N/A",
            "first_off_day": first_off_day or "N/A",
            "on_days_count": on_days_count,
            "has_0_1_0_transition": int(has_transition)
        })

        # Detailed txt output
        txt_lines.append(f"\n{'='*60}")
        txt_lines.append(f"{exp} Seed_{seed}")
        txt_lines.append(f"{'='*60}")
        txt_lines.append(f"risk_model_loaded: {'ALL 1' if risk_model_loaded_all else 'SOME 0'}")
        txt_lines.append(f"risk_p_valid coverage (day>=2): {valid_coverage}")
        txt_lines.append(f"max(risk_p): {max_risk_p:.6f}" if not math.isnan(max_risk_p) else "max(risk_p): NaN")
        txt_lines.append(f"First day risk_p >= {delta_on}: {first_trigger_day or 'Never'}")
        txt_lines.append(f"risk_mode_on: first_on={first_on_day}, first_off={first_off_day}, total_on_days={on_days_count}")
        txt_lines.append(f"\nDaily breakdown:")
        txt_lines.append(f"{'Day':<6} {'risk_p':<12} {'risk_p_valid':<12} {'risk_mode_on':<12}")
        txt_lines.append("-" * 50)
        for i, d in enumerate(daily):
            day_num = i + 1
            rp = d.get("risk_p", float('nan'))
            rpv = d.get("risk_p_valid", 0)
            rmo = d.get("risk_mode_on", 0)
            rp_str = f"{rp:.6f}" if not math.isnan(rp) else "NaN"
            txt_lines.append(f"{day_num:<6} {rp_str:<12} {rpv:<12} {rmo:<12}")

    csv_path = AUDITS_DIR / f"audit_riskgate_behavior_{TIMESTAMP}.csv"
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["exp", "seed", "risk_model_loaded_all",
                                                "risk_p_valid_coverage", "max_risk_p",
                                                "first_trigger_day", "first_on_day",
                                                "first_off_day", "on_days_count",
                                                "has_0_1_0_transition"])
        writer.writeheader()
        writer.writerows(csv_rows)

    txt_path = AUDITS_DIR / f"audit_riskgate_behavior_{TIMESTAMP}.txt"
    with open(txt_path, 'w') as f:
        f.write("\n".join(txt_lines))

    return csv_rows, csv_path, txt_path

def step4_metrics(index_rows):
    """Step 4: Result metrics comparison"""
    seed_rows = []

    for idx in index_rows:
        if not idx["has_summary"]:
            continue

        exp = idx["exp"]
        seed = idx["seed"]

        summary_path = Path(idx["path"]) / "summary_final.json"
        summary = load_json(summary_path)
        if not summary:
            continue

        # Also get vrp_dropped from daily_stats if needed
        vrp_dropped_sum = summary.get("vrp_dropped_sum", 0)
        if not vrp_dropped_sum:
            sim_path = Path(idx["path"]) / "simulation_results.json"
            sim = load_json(sim_path)
            if sim:
                daily = sim.get("daily_stats", [])
                vrp_dropped_sum = sum(d.get("vrp_dropped", 0) for d in daily)

        cost_sum = summary.get("cost_sum", summary.get("total_cost", 0))
        if not cost_sum:
            sim_path = Path(idx["path"]) / "simulation_results.json"
            sim = load_json(sim_path)
            if sim:
                daily = sim.get("daily_stats", [])
                cost_sum = sum(d.get("cost", 0) for d in daily)

        seed_rows.append({
            "exp": exp,
            "seed": seed,
            "service_rate": summary.get("service_rate_within_window", summary.get("service_rate", "")),
            "eligible_count": summary.get("eligible_count", ""),
            "delivered_count": summary.get("delivered_within_window_count", summary.get("delivered_count", "")),
            "deadline_failure_count": summary.get("deadline_failure_count", ""),
            "vrp_dropped_sum": vrp_dropped_sum,
            "cost_sum": cost_sum
        })

    seed_path = AUDITS_DIR / f"audit_metrics_by_seed_{TIMESTAMP}.csv"
    with open(seed_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["exp", "seed", "service_rate", "eligible_count",
                                                "delivered_count", "deadline_failure_count",
                                                "vrp_dropped_sum", "cost_sum"])
        writer.writeheader()
        writer.writerows(seed_rows)

    # Aggregate by exp
    agg_rows = []
    from collections import defaultdict
    exp_data = defaultdict(lambda: {"sr": [], "eligible": [], "delivered": [], "dl_fail": [], "vrp_drop": [], "cost": []})

    for row in seed_rows:
        exp = row["exp"]
        if row["service_rate"]:
            exp_data[exp]["sr"].append(float(row["service_rate"]))
        if row["eligible_count"]:
            exp_data[exp]["eligible"].append(float(row["eligible_count"]))
        if row["delivered_count"]:
            exp_data[exp]["delivered"].append(float(row["delivered_count"]))
        if row["deadline_failure_count"]:
            exp_data[exp]["dl_fail"].append(float(row["deadline_failure_count"]))
        if row["vrp_dropped_sum"]:
            exp_data[exp]["vrp_drop"].append(float(row["vrp_dropped_sum"]))
        if row["cost_sum"]:
            exp_data[exp]["cost"].append(float(row["cost_sum"]))

    def calc_stats(arr):
        if not arr:
            return {"mean": "", "std": "", "min": "", "max": ""}
        n = len(arr)
        mean = sum(arr) / n
        if n > 1:
            std = (sum((x - mean) ** 2 for x in arr) / (n - 1)) ** 0.5
        else:
            std = 0
        return {"mean": f"{mean:.6f}", "std": f"{std:.6f}", "min": f"{min(arr):.6f}", "max": f"{max(arr):.6f}"}

    for exp in ["EXP01", "EXP02", "EXP03", "EXP04"]:
        data = exp_data[exp]
        sr_stats = calc_stats(data["sr"])
        agg_rows.append({
            "exp": exp,
            "metric": "service_rate",
            "mean": sr_stats["mean"],
            "std": sr_stats["std"],
            "min": sr_stats["min"],
            "max": sr_stats["max"],
            "n": len(data["sr"])
        })
        dl_stats = calc_stats(data["dl_fail"])
        agg_rows.append({
            "exp": exp,
            "metric": "deadline_failure_count",
            "mean": dl_stats["mean"],
            "std": dl_stats["std"],
            "min": dl_stats["min"],
            "max": dl_stats["max"],
            "n": len(data["dl_fail"])
        })
        vrp_stats = calc_stats(data["vrp_drop"])
        agg_rows.append({
            "exp": exp,
            "metric": "vrp_dropped_sum",
            "mean": vrp_stats["mean"],
            "std": vrp_stats["std"],
            "min": vrp_stats["min"],
            "max": vrp_stats["max"],
            "n": len(data["vrp_drop"])
        })

    agg_path = AUDITS_DIR / f"audit_metrics_agg_{TIMESTAMP}.csv"
    with open(agg_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["exp", "metric", "mean", "std", "min", "max", "n"])
        writer.writeheader()
        writer.writerows(agg_rows)

    return seed_rows, seed_path, agg_rows, agg_path, exp_data

def step4_determinism():
    """Check for determinism evidence"""
    lines = []
    lines.append("DETERMINISM ANALYSIS")
    lines.append("=" * 60)
    lines.append("")
    lines.append("Checking OR-Tools solver configuration for random seed settings...")
    lines.append("")

    # Search for solver configuration
    solver_file = BASE_DIR / "src/solvers/alns_solver.py"
    if solver_file.exists():
        with open(solver_file, 'r') as f:
            content = f.read()

        lines.append(f"File: {solver_file}")
        lines.append("-" * 40)

        # Look for search_parameters and random_seed
        if "random_seed" in content.lower():
            lines.append("Found: random_seed configuration present")
            # Extract relevant lines
            for i, line in enumerate(content.split('\n')):
                if 'random_seed' in line.lower():
                    lines.append(f"  Line {i+1}: {line.strip()}")
        else:
            lines.append("NOT FOUND: random_seed not explicitly set")
            lines.append("This may explain deterministic behavior if OR-Tools uses default seed")

        if "search_parameters" in content.lower():
            lines.append("")
            lines.append("search_parameters configuration found:")
            in_params = False
            for i, line in enumerate(content.split('\n')):
                if 'search_parameters' in line.lower():
                    in_params = True
                if in_params:
                    lines.append(f"  Line {i+1}: {line.strip()}")
                    if line.strip().endswith(')') or (in_params and line.strip() == ''):
                        if 'search_parameters' not in line.lower():
                            in_params = False
    else:
        lines.append(f"Solver file not found: {solver_file}")

    lines.append("")
    lines.append("=" * 60)
    lines.append("CONCLUSION:")
    lines.append("If std ≈ 0 across seeds, likely causes:")
    lines.append("1. OR-Tools GLS solver is deterministic by default")
    lines.append("2. No random_seed variation configured")
    lines.append("3. Same input data + same algorithm = same output")

    det_path = AUDITS_DIR / f"audit_determinism_{TIMESTAMP}.txt"
    with open(det_path, 'w') as f:
        f.write("\n".join(lines))

    return det_path

def main():
    print(f"Starting full audit at {TIMESTAMP}")
    print("=" * 60)

    # Step 0
    print("\nStep 0: Building audit index...")
    index_rows, index_path = step0_audit_index()
    print(f"  Output: {index_path}")
    print(f"  Total entries: {len(index_rows)}")

    # Step 1
    print("\nStep 1: Config matrix...")
    config_rows, config_path, config_summary = step1_config_matrix(index_rows)
    print(f"  Output: {config_path}")

    # Step 2
    print("\nStep 2: Compute gate audit...")
    compute_rows, compute_path, violations, totals = step2_compute_gate(index_rows)
    print(f"  Output: {compute_path}")
    for exp in ["EXP02", "EXP03", "EXP04"]:
        if totals[exp] > 0:
            print(f"  {exp}: {violations[exp]}/{totals[exp]} violations")
        else:
            print(f"  {exp}: NO DATA")

    # Step 3
    print("\nStep 3: RiskGate behavior audit...")
    rg_rows, rg_csv_path, rg_txt_path = step3_riskgate_behavior(index_rows)
    print(f"  CSV: {rg_csv_path}")
    print(f"  TXT: {rg_txt_path}")

    # Step 4
    print("\nStep 4: Metrics comparison...")
    seed_rows, seed_path, agg_rows, agg_path, exp_data = step4_metrics(index_rows)
    print(f"  By seed: {seed_path}")
    print(f"  Aggregated: {agg_path}")

    det_path = step4_determinism()
    print(f"  Determinism: {det_path}")

    # Final summary
    print("\n" + "=" * 60)
    print("AUDIT COMPLETE")
    print("=" * 60)
    print(f"\nAll files written to: {AUDITS_DIR}")
    print(f"Timestamp: {TIMESTAMP}")

if __name__ == "__main__":
    main()
