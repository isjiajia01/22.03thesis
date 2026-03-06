#!/usr/bin/env python3
"""Audit MVT artifacts and emit traffic-light outputs."""

from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass
class Finding:
    severity: str
    case_name: str
    seed: int
    run_serial: int
    check_name: str
    message: str
    evidence_path: str
    counterexample: str


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_latest_index() -> Path:
    files = sorted(glob.glob(str(ROOT / "data" / "audits" / "mvt_index_*.csv")))
    if not files:
        raise FileNotFoundError("No mvt_index_*.csv found. Run scripts/mvt/run_mvt.py first.")
    return Path(files[-1])


def check_artifacts(run_dir: Path) -> Tuple[bool, str]:
    required = ["config_dump.json", "simulation_results.json", "summary_final.json"]
    missing = [x for x in required if not (run_dir / x).exists()]
    if missing:
        return False, f"Missing artifacts: {missing}"
    return True, "all required artifacts present"


def check_days(sim: Dict[str, Any], expected_days: int) -> Tuple[bool, str]:
    actual = len(sim.get("daily_stats", []))
    ok = actual == expected_days
    return ok, f"expected_days={expected_days}, actual_days={actual}"


def first_violation_vrp_timewindow(vrp_traces: List[Dict[str, Any]]) -> Optional[str]:
    for d in vrp_traces:
        day = d.get("day_idx")
        for route in d.get("routes", []) or []:
            vid = route.get("vehicle_id")
            for st in route.get("stop_details", []) or []:
                arr = st.get("arrival_min")
                tws = st.get("time_window_start_min")
                twe = st.get("time_window_end_min")
                oid = st.get("order_id")
                if arr is None or tws is None or twe is None:
                    continue
                if not (float(tws) <= float(arr) <= float(twe)):
                    return f"day={day}, vehicle={vid}, order={oid}, arrival={arr}, tw=[{tws},{twe}]"
    return None


def summarize_tw_coverage(vrp_traces: List[Dict[str, Any]]) -> Tuple[int, int, Optional[str]]:
    checked = 0
    violations = 0
    first_violation = None
    for d in vrp_traces:
        day = d.get("day_idx")
        for route in d.get("routes", []) or []:
            vid = route.get("vehicle_id")
            for st in route.get("stop_details", []) or []:
                arr = st.get("arrival_cumul_min", st.get("arrival_min"))
                tws = st.get("time_window_start_min")
                twe = st.get("time_window_end_min")
                oid = st.get("order_id")
                if arr is None or tws is None or twe is None:
                    continue
                checked += 1
                if not (float(tws) <= float(arr) <= float(twe)):
                    violations += 1
                    if first_violation is None:
                        first_violation = (
                            f"day={day}, vehicle={vid}, order={oid}, arrival={arr}, tw=[{tws},{twe}]"
                        )
    return checked, violations, first_violation


def first_violation_vrp_capacity(vrp_traces: List[Dict[str, Any]]) -> Optional[str]:
    dims = ["colli", "volume", "weight"]
    for d in vrp_traces:
        day = d.get("day_idx")
        for route in d.get("routes", []) or []:
            vid = route.get("vehicle_id")
            load = route.get("route_load", {})
            cap = route.get("vehicle_capacity", {})
            for dim in dims:
                lv = float(load.get(dim, 0.0))
                cv = float(cap.get(dim, 0.0))
                if lv > cv + 1e-9:
                    return f"day={day}, vehicle={vid}, dim={dim}, load={lv}, cap={cv}"
    return None


def first_violation_vrp_integrity(vrp_traces: List[Dict[str, Any]]) -> Optional[str]:
    for d in vrp_traces:
        day = d.get("day_idx")
        planned = set(d.get("planned_order_ids", []) or [])
        delivered = []
        for route in d.get("routes", []) or []:
            delivered.extend(route.get("stops", []) or [])
        dropped = set(d.get("vrp_dropped_order_ids", []) or [])
        day_capacity = float(d.get("daily_capacity_colli", 0.0))

        # If no capacity exists for the day, no VRP solve is expected; dropped integrity is N/A.
        if day_capacity <= 0 and not delivered and not dropped:
            continue

        seen = set()
        for oid in delivered:
            if oid in seen:
                return f"day={day}, duplicate_delivered_order={oid}"
            seen.add(oid)

        inter = set(delivered) & dropped
        if inter:
            oid = sorted(inter)[0]
            return f"day={day}, delivered_and_dropped_overlap_order={oid}"

        outside = set(delivered) - planned
        if outside:
            oid = sorted(outside)[0]
            return f"day={day}, delivered_not_in_planned_order={oid}"

        if planned:
            expected_dropped = planned - set(delivered)
            if expected_dropped != dropped:
                only_left = sorted(expected_dropped - dropped)
                only_right = sorted(dropped - expected_dropped)
                return (
                    f"day={day}, dropped_definition_mismatch, "
                    f"planned_minus_delivered_only={only_left[:1]}, dropped_only={only_right[:1]}"
                )
    return None


def check_compute_gate(daily: List[Dict[str, Any]]) -> Tuple[bool, str, Optional[str]]:
    violations = []
    risk_days = 0
    for i, d in enumerate(daily):
        base = int(d.get("compute_base_seconds", d.get("compute_limit_seconds", 0)))
        high = int(d.get("compute_high_seconds", base))
        actual = int(d.get("compute_limit_seconds", base))
        risk = int(d.get("risk_mode_on", 0))
        if actual not in {base, high}:
            violations.append(f"day={i}, compute={actual}, allowed={{base:{base}, high:{high}}}")
            continue
        if risk == 1:
            risk_days += 1
            if actual != high:
                violations.append(f"day={i}, risk_mode_on=1 but compute={actual} != high={high}")
        else:
            if actual != base:
                violations.append(f"day={i}, risk_mode_on=0 but compute={actual} != base={base}")

    if violations:
        return False, f"compute gate violations={len(violations)}", violations[0]
    return True, f"compute gate aligned; risk_mode_on_days={risk_days}", None


def check_metrics_consistency(
    cfg: Dict[str, Any],
    sim: Dict[str, Any],
    summary: Dict[str, Any],
) -> Tuple[bool, str, Optional[str]]:
    daily = sim.get("daily_stats", [])
    sum_fail = int(sum(int(d.get("failures", 0)) for d in daily))
    sum_drop = int(sum(int(d.get("vrp_dropped", 0)) for d in daily))
    delivered = int(summary.get("delivered_within_window_count", summary.get("delivered_count", 0)))
    failures = int(summary.get("deadline_failure_count", 0))
    eligible = int(summary.get("eligible_count", 0))

    if failures != sum_fail:
        msg = f"summary_failures={failures}, daily_sum_failures={sum_fail}"
        return False, "summary/daily mismatch", msg

    if int(summary.get("failed_orders", failures)) != failures:
        msg = f"failed_orders={summary.get('failed_orders')} vs deadline_failure_count={failures}"
        return False, "summary internal mismatch", msg

    dataset_path = ROOT / cfg.get("dataset_path", "")
    if dataset_path.exists():
        dataset = read_json(dataset_path)
        orders = dataset.get("orders", [])
        horizon_end = dataset.get("metadata", {}).get("horizon_end")
        out_window = 0
        for o in orders:
            fds = o.get("feasible_dates", [])
            if fds and fds[-1] > horizon_end:
                out_window += 1
        lhs = delivered + failures + out_window
        if lhs != eligible:
            msg = f"eligible={eligible}, delivered={delivered}, failures={failures}, out_window={out_window}"
            return False, "eligible decomposition mismatch", msg

    sr = float(summary.get("service_rate_within_window", 0.0))
    sr_calc = (delivered / eligible) if eligible > 0 else 0.0
    if abs(sr - sr_calc) > 1e-9:
        msg = f"service_rate={sr}, delivered/eligible={sr_calc}"
        return False, "service_rate mismatch", msg

    return True, f"metrics consistent; total_vrp_dropped={sum_drop}", None


def check_capacity_trace(cfg: Dict[str, Any], sim: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
    daily = sim.get("daily_stats", [])
    if cfg.get("source_run_dir"):
        sc = cfg.get("sim_config", {})
        ratio = float(sc.get("ratio", 1.0))
        cstart = sc.get("crunch_start")
        cend = sc.get("crunch_end")
        cwindows = sc.get("crunch_windows", [])
        for i, d in enumerate(daily):
            expected = 1.0
            if cwindows:
                expected = ratio if any(int(w[0]) <= i <= int(w[1]) for w in cwindows) else 1.0
            elif cstart is not None and cend is not None:
                expected = ratio if int(cstart) <= i <= int(cend) else 1.0
            actual = float(d.get("capacity_ratio", 1.0))
            if abs(expected - actual) > 1e-9:
                return False, "capacity_ratio mismatch", f"day={i}, expected={expected}, actual={actual}"
        return True, "capacity_ratio trace aligned with source-run config", None

    dataset_path = ROOT / cfg.get("dataset_path", "")
    if not dataset_path.exists():
        return False, "dataset missing for capacity trace", "dataset_path_missing"
    dataset = read_json(dataset_path)
    profile = dataset.get("metadata", {}).get("capacity_profile", {})

    for i, d in enumerate(daily):
        expected = float(profile.get(str(i), 1.0))
        actual = float(d.get("capacity_ratio", 1.0))
        if abs(expected - actual) > 1e-9:
            return False, "capacity_ratio mismatch", f"day={i}, expected={expected}, actual={actual}"
    return True, "capacity_ratio trace aligned with profile", None


def check_a2_has_failure(case_name: str, summary: Dict[str, Any]) -> Tuple[bool, str]:
    if "A2_" not in case_name:
        return True, "not applicable"
    fail = int(summary.get("deadline_failure_count", 0))
    if fail <= 0:
        return False, "A2 expected at least one failure but got 0"
    return True, f"A2 produced failures={fail}"


def collect_policy_table(rows: List[Dict[str, Any]], out_path: Path) -> None:
    # Build 12-day table for A5 proactive vs greedy.
    by_case = {}
    for r in rows:
        if r["case_name"] not in {"A5_Policy_Sanity_Proactive", "A5_Policy_Sanity_Greedy"}:
            continue
        sim = read_json(ROOT / r["simulation_results_path"])
        by_case[r["case_name"]] = sim.get("daily_stats", [])

    if len(by_case) < 2:
        return

    pro = by_case["A5_Policy_Sanity_Proactive"]
    gre = by_case["A5_Policy_Sanity_Greedy"]
    n = min(len(pro), len(gre), 12)
    out_rows = []
    for i in range(n):
        out_rows.append(
            {
                "day_idx": i,
                "proactive_planned_today": int(pro[i].get("planned_today", 0)),
                "greedy_planned_today": int(gre[i].get("planned_today", 0)),
                "proactive_vrp_dropped": int(pro[i].get("vrp_dropped", 0)),
                "greedy_vrp_dropped": int(gre[i].get("vrp_dropped", 0)),
                "proactive_failures": int(pro[i].get("failures", 0)),
                "greedy_failures": int(gre[i].get("failures", 0)),
            }
        )
    pd.DataFrame(out_rows).to_csv(out_path, index=False)


def check_determinism(rows: List[Dict[str, Any]]) -> Tuple[bool, str, Optional[str]]:
    runs = [r for r in rows if r["case_name"] == "A6_Determinism_Guard"]
    if len(runs) < 2:
        return False, "A6 determinism requires two runs", "insufficient_runs"

    runs = sorted(runs, key=lambda x: int(x["run_serial"]))
    sim1 = read_json(ROOT / runs[0]["simulation_results_path"])
    sim2 = read_json(ROOT / runs[1]["simulation_results_path"])
    s1 = read_json(ROOT / runs[0]["summary_path"])
    s2 = read_json(ROOT / runs[1]["summary_path"])

    keys = ["eligible_count", "delivered_within_window_count", "deadline_failure_count", "service_rate_within_window", "penalized_cost"]
    for k in keys:
        if s1.get(k) != s2.get(k):
            return False, "summary metrics not identical", f"key={k}, run1={s1.get(k)}, run2={s2.get(k)}"

    d1 = sim1.get("daily_stats", [])
    d2 = sim2.get("daily_stats", [])
    if len(d1) != len(d2):
        return False, "daily_stats length mismatch", f"len1={len(d1)}, len2={len(d2)}"

    cols = ["planned_today", "delivered_today", "vrp_dropped", "failures", "compute_limit_seconds", "risk_mode_on"]
    for i in range(len(d1)):
        for c in cols:
            if d1[i].get(c) != d2[i].get(c):
                return False, "daily key mismatch", f"day={i}, key={c}, run1={d1[i].get(c)}, run2={d2[i].get(c)}"

    return True, "determinism exact match for key metrics", None


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit MVT outputs")
    ap.add_argument("--index", type=Path, default=None)
    args = ap.parse_args()

    index_path = args.index if args.index else load_latest_index()
    rows = pd.read_csv(index_path).to_dict("records")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    traffic_csv = ROOT / "data" / "audits" / f"mvt_traffic_light_{ts}.csv"
    report_md = ROOT / "data" / "audits" / f"mvt_report_{ts}.md"
    cex_txt = ROOT / "data" / "audits" / f"mvt_failure_minimal_counterexamples_{ts}.txt"
    one_page = ROOT / "data" / "audits" / f"mvt_one_page_summary_{ts}.md"
    policy_table = ROOT / "data" / "audits" / f"mvt_policy_sanity_12day_{ts}.csv"

    findings: List[Finding] = []
    traffic_rows: List[Dict[str, Any]] = []
    tw_checked_total = 0
    tw_violations_total = 0

    def push(
        ok: bool,
        case_name: str,
        seed: int,
        run_serial: int,
        check_name: str,
        detail: str,
        evidence: str,
        cex: str = "",
    ) -> None:
        status = "PASS" if ok else "FAIL"
        traffic_rows.append(
            {
                "case_name": case_name,
                "seed": seed,
                "run_serial": run_serial,
                "check_name": check_name,
                "status": status,
                "detail": detail,
                "evidence_path": evidence,
                "minimal_counterexample": cex,
            }
        )
        if not ok:
            findings.append(
                Finding(
                    severity="HIGH",
                    case_name=case_name,
                    seed=seed,
                    run_serial=run_serial,
                    check_name=check_name,
                    message=detail,
                    evidence_path=evidence,
                    counterexample=cex,
                )
            )

    for row in rows:
        case_name = str(row["case_name"])
        seed = int(row["seed"])
        run_serial = int(row["run_serial"])
        run_dir = ROOT / row["run_dir"]

        ok, detail = check_artifacts(run_dir)
        push(ok, case_name, seed, run_serial, "artifact_triple", detail, str(run_dir.relative_to(ROOT)), detail if not ok else "")
        if not ok:
            continue

        cfg = read_json(run_dir / "config_dump.json")
        sim = read_json(run_dir / "simulation_results.json")
        summary = read_json(run_dir / "summary_final.json")

        ok, detail = check_days(sim, int(cfg.get("expected_days", 0)))
        cex = "" if ok else detail
        push(ok, case_name, seed, run_serial, "days_expected", detail, str((run_dir / "simulation_results.json").relative_to(ROOT)), cex)

        tw_cex = first_violation_vrp_timewindow(sim.get("vrp_audit_traces", []))
        tw_checked, tw_violations, tw_first = summarize_tw_coverage(sim.get("vrp_audit_traces", []))
        tw_checked_total += tw_checked
        tw_violations_total += tw_violations
        push(tw_cex is None, case_name, seed, run_serial, "vrp_time_window", "all arrivals within time windows" if tw_cex is None else "time window violation", str((run_dir / "simulation_results.json").relative_to(ROOT)), tw_cex or "")

        cap_cex = first_violation_vrp_capacity(sim.get("vrp_audit_traces", []))
        push(cap_cex is None, case_name, seed, run_serial, "vrp_capacity", "all route loads within vehicle capacities" if cap_cex is None else "capacity violation", str((run_dir / "simulation_results.json").relative_to(ROOT)), cap_cex or "")

        int_cex = first_violation_vrp_integrity(sim.get("vrp_audit_traces", []))
        push(int_cex is None, case_name, seed, run_serial, "vrp_integrity", "delivered/dropped integrity holds" if int_cex is None else "route integrity violation", str((run_dir / "simulation_results.json").relative_to(ROOT)), int_cex or "")

        ok, detail, cex = check_compute_gate(sim.get("daily_stats", []))
        push(ok, case_name, seed, run_serial, "compute_gate", detail, str((run_dir / "simulation_results.json").relative_to(ROOT)), cex or "")

        ok, detail, cex = check_metrics_consistency(cfg, sim, summary)
        push(ok, case_name, seed, run_serial, "metrics_self_consistency", detail, str((run_dir / "summary_final.json").relative_to(ROOT)), cex or "")

        ok, detail, cex = check_capacity_trace(cfg, sim)
        push(ok, case_name, seed, run_serial, "capacity_ratio_trace", detail, str((run_dir / "simulation_results.json").relative_to(ROOT)), cex or "")

        ok, detail = check_a2_has_failure(case_name, summary)
        push(ok, case_name, seed, run_serial, "a2_infeasible_expectation", detail, str((run_dir / "summary_final.json").relative_to(ROOT)), "" if ok else detail)

    # Cross-run checks.
    det_ok, det_detail, det_cex = check_determinism(rows)
    traffic_rows.append(
        {
            "case_name": "A6_Determinism_Guard",
            "seed": 1,
            "run_serial": -1,
            "check_name": "determinism_guard_crossrun",
            "status": "PASS" if det_ok else "FAIL",
            "detail": det_detail,
            "evidence_path": str(index_path.relative_to(ROOT)),
            "minimal_counterexample": det_cex or "",
        }
    )
    if not det_ok:
        findings.append(
            Finding(
                severity="MEDIUM",
                case_name="A6_Determinism_Guard",
                seed=1,
                run_serial=-1,
                check_name="determinism_guard_crossrun",
                message=det_detail,
                evidence_path=str(index_path.relative_to(ROOT)),
                counterexample=det_cex or "",
            )
        )

    collect_policy_table(rows, policy_table)

    df_tl = pd.DataFrame(traffic_rows)
    df_tl.to_csv(traffic_csv, index=False)

    # Risk-trigger explanation for A4.
    a4_default = [r for r in rows if r["case_name"] == "A4_Crunch_Compute_Gate"]
    risk_trigger_default = False
    if a4_default:
        sim = read_json(ROOT / a4_default[0]["simulation_results_path"])
        risk_trigger_default = any(int(d.get("risk_mode_on", 0)) == 1 for d in sim.get("daily_stats", []))

    a4_alt = [r for r in rows if r["case_name"] == "A4_ALT_ForcedTrigger"]
    risk_trigger_alt = False
    alt_thr_on = None
    alt_thr_off = None
    if a4_alt:
        alt_cfg = read_json(ROOT / a4_alt[0]["config_path"])
        alt_sim_cfg = alt_cfg.get("sim_config", {})
        alt_thr_on = alt_sim_cfg.get("risk_threshold_on")
        alt_thr_off = alt_sim_cfg.get("risk_threshold_off")
        sim = read_json(ROOT / a4_alt[0]["simulation_results_path"])
        risk_trigger_alt = any(int(d.get("risk_mode_on", 0)) == 1 for d in sim.get("daily_stats", []))

    total_checks = len(df_tl)
    fail_checks = int((df_tl["status"] == "FAIL").sum())
    overall = "PASS" if fail_checks == 0 else "FAIL"

    lines = []
    lines.append("# MVT Audit Report")
    lines.append("")
    lines.append(f"- Overall: **{overall}**")
    lines.append(f"- Index file: `{index_path.relative_to(ROOT)}`")
    lines.append(f"- Total checks: {total_checks}")
    lines.append(f"- Failed checks: {fail_checks}")
    lines.append(f"- Traffic light CSV: `{traffic_csv.relative_to(ROOT)}`")
    lines.append(f"- Policy sanity table: `{policy_table.relative_to(ROOT)}`")
    lines.append("")
    lines.append("## Check Definitions")
    lines.append("")
    lines.append("- `artifact_triple`: Purpose = verify reproducible artifact inputs exist. Pass = config_dump/simulation_results/summary_final all present.")
    lines.append("- `days_expected`: Purpose = verify simulation horizon length. Pass = len(daily_stats) equals expected_days.")
    lines.append("- `vrp_time_window`: Purpose = verify arrival times remain inside order time windows. Pass = all stop_details arrival_min in [tw_start, tw_end].")
    lines.append("- `vrp_capacity`: Purpose = verify route load never exceeds vehicle capacity. Pass = route_load <= vehicle_capacity for colli/volume/weight.")
    lines.append("- `vrp_integrity`: Purpose = verify route integrity. Pass = each delivered order appears once; no delivered+dropped overlap; dropped == planned-delivered.")
    lines.append("- `compute_gate`: Purpose = verify risk/compute gating consistency. Pass = compute in {base,high}; risk_mode_on=1 implies compute==high.")
    lines.append("- `metrics_self_consistency`: Purpose = verify summary and daily_stats agree with dataset-level definitions.")
    lines.append("- `capacity_ratio_trace`: Purpose = verify crunch profile is actually applied in daily_stats.")
    lines.append("")
    lines.append("## A4 Risk Gate Note")
    lines.append("")
    if risk_trigger_default:
        lines.append("- Default A4 case triggered `risk_mode_on=1` at least once.")
    else:
        lines.append("- Default A4 case did **not** trigger `risk_mode_on=1`; likely due risk probabilities staying below `risk_threshold_on=0.826` under this tiny synthetic demand pattern.")
    lines.append(
        f"- Alternative trigger case (`A4_ALT_ForcedTrigger`) status: {'triggered' if risk_trigger_alt else 'not triggered'} "
        f"with lowered thresholds (`delta_on={alt_thr_on}`, `delta_off={alt_thr_off}`) for test-only reproducibility."
    )
    lines.append("")
    lines.append("## Global TW Coverage")
    lines.append("")
    lines.append(f"- Total stops checked across MVT suite: **{tw_checked_total}**")
    lines.append(f"- Total TW violations across MVT suite: **{tw_violations_total}**")
    lines.append("")

    if findings:
        lines.append("## Failures")
        lines.append("")
        for f in findings:
            lines.append(
                f"- [{f.severity}] {f.case_name} seed={f.seed} run={f.run_serial} check={f.check_name}: {f.message}; "
                f"counterexample={f.counterexample}; evidence=`{f.evidence_path}`"
            )
    else:
        lines.append("## Failures")
        lines.append("")
        lines.append("- No failing checks.")

    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with cex_txt.open("w", encoding="utf-8") as f:
        if findings:
            for item in findings:
                f.write(
                    f"case={item.case_name}; seed={item.seed}; run={item.run_serial}; "
                    f"check={item.check_name}; counterexample={item.counterexample}; evidence={item.evidence_path}\n"
                )
        else:
            f.write("NO_FAILURES\n")

    one_page_lines = [
        "# MVT One-Page Summary",
        "",
        f"Overall: **{overall}**",
        f"Total checks: {total_checks}",
        f"Failed checks: {fail_checks}",
        f"Index: `{index_path.relative_to(ROOT)}`",
        f"Traffic Light: `{traffic_csv.relative_to(ROOT)}`",
        f"Report: `{report_md.relative_to(ROOT)}`",
        f"Counterexamples: `{cex_txt.relative_to(ROOT)}`",
        f"Policy 12-day table: `{policy_table.relative_to(ROOT)}`",
        f"Total stops checked across MVT suite: **{tw_checked_total}**",
        f"Total TW violations across MVT suite: **{tw_violations_total}**",
    ]
    one_page.write_text("\n".join(one_page_lines) + "\n", encoding="utf-8")

    print(f"MVT audit complete. Report: {report_md.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
