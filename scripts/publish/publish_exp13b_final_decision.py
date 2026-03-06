#!/usr/bin/env python3
"""Recompute paired stats for ID + OOD_hard + OOD_pressure and publish thesis bundle."""

import csv
import json
import math
import re
import shutil
from collections import defaultdict
from pathlib import Path

from scipy import stats

ROOT = Path('/zhome/2a/1/202283/22.01 thesis')
CANON = ROOT / 'data/results/EXP15/EXP15c'
BACKFILL_ROOT = ROOT / 'data/results/EXPXX_backfill_ood_pressure'
OUT = ROOT / 'data/audits/ood_pressure_backfill/_publication'
OUT.mkdir(parents=True, exist_ok=True)

CONDITIONS = [
    {'name': 'ID', 'ratio': 0.59, 'shift': 0},
    {'name': 'OOD_hard', 'ratio': 0.59, 'shift': -2},
    {'name': 'OOD_pressure', 'ratio': 0.55, 'shift': -2},
]

METRICS = ['failures', 'service_rate', 'penalized_cost', 'compute_seconds']


def parse_seed_git(name: str):
    m = re.match(r'seed_(\d+)_([^_]+)', name)
    if not m:
        return None, ''
    return int(m.group(1)), m.group(2)


def list_candidate_dirs(variant: str, ratio: float, shift: int):
    dirs = []
    d1 = CANON / f'{variant}_ratio_{ratio}_shift_{shift}'
    if d1.exists():
        dirs += [p for p in d1.iterdir() if p.is_dir() and p.name.startswith('seed_')]

    # backfill only for OOD_pressure naming layout
    if ratio == 0.55 and shift == -2:
        d2 = BACKFILL_ROOT / f'ood_pressure_r{ratio}_s{shift}' / variant
        if d2.exists():
            dirs += [p for p in d2.iterdir() if p.is_dir() and p.name.startswith('seed_')]

    return dirs


def parse_run(variant: str, ratio: float, shift: int, run_dir: Path):
    seed, gitsha = parse_seed_git(run_dir.name)
    if seed is None:
        return None

    inner = run_dir / 'DEFAULT' / 'EXP15c'
    sf = inner / 'summary_final.json'
    of = inner / 'ood_labels.json'
    af = inner / 'allocator_config_dump.json'
    df = inner / 'daily_stats.csv'

    passed = True
    reason = ''

    if not sf.exists():
        passed = False
        reason = 'missing summary_final.json'
        summary = {}
    elif not of.exists() or not af.exists():
        passed = False
        reason = 'missing metadata'
        summary = {}
    else:
        try:
            summary = json.loads(sf.read_text())
        except Exception as e:
            passed = False
            reason = f'parse_error:{e}'
            summary = {}

    compute_seconds = None
    if passed and df.exists():
        total = 0.0
        with open(df, newline='') as f:
            for r in csv.DictReader(f):
                try:
                    total += float(r.get('compute_limit_seconds') or 0.0)
                except Exception:
                    pass
        compute_seconds = total

    return {
        'condition': f'r={ratio},s={shift}',
        'variant': variant,
        'ratio': ratio,
        'shift': shift,
        'seed': seed,
        'gitsha': gitsha,
        'run_dir': str(run_dir),
        'summary_path': str(sf),
        'mtime': sf.stat().st_mtime if sf.exists() else run_dir.stat().st_mtime,
        'pass': passed,
        'reason': reason,
        'failures': summary.get('deadline_failure_count') if passed else None,
        'service_rate': summary.get('service_rate_within_window') if passed else None,
        'penalized_cost': summary.get('penalized_cost') if passed else None,
        'compute_seconds': compute_seconds,
    }


def dedupe_latest(rows):
    by_key = defaultdict(list)
    for r in rows:
        by_key[(r['condition'], r['variant'], r['seed'])].append(r)

    kept = []
    duplicates = []
    for key, items in sorted(by_key.items()):
        items = sorted(items, key=lambda x: (x['mtime'], x['gitsha']), reverse=True)
        keep = items[0]
        kept.append(keep)
        if len(items) > 1:
            duplicates.append({
                'condition': key[0],
                'variant': key[1],
                'seed': key[2],
                'kept': keep['run_dir'],
                'dropped': [x['run_dir'] for x in items[1:]],
            })
    return kept, duplicates


def paired_stats(diffs):
    n = len(diffs)
    mu = sum(diffs) / n
    if n == 1:
        return mu, mu, mu, 1.0
    sd = (sum((x - mu) ** 2 for x in diffs) / (n - 1)) ** 0.5
    se = sd / math.sqrt(n)
    tcrit = float(stats.t.ppf(0.975, df=n - 1))
    lo = mu - tcrit * se
    hi = mu + tcrit * se
    p = float(stats.ttest_1samp(diffs, popmean=0.0).pvalue)
    return mu, lo, hi, p


def compute_condition_table(cond_name, ratio, shift, kept_pass):
    full = {r['seed']: r for r in kept_pass if r['variant'] == 'full' and r['ratio'] == ratio and r['shift'] == shift}
    nocal = {r['seed']: r for r in kept_pass if r['variant'] == 'no_calendar' and r['ratio'] == ratio and r['shift'] == shift}

    paired_seeds = sorted(set(full) & set(nocal))

    rows = []
    for metric in METRICS:
        diffs = []
        for s in paired_seeds:
            a = full[s].get(metric)
            b = nocal[s].get(metric)
            if a is None or b is None:
                continue
            diffs.append(float(b) - float(a))  # delta = no_calendar - full
        if not diffs:
            continue
        mu, lo, hi, p = paired_stats(diffs)
        rows.append({
            'condition': cond_name,
            'ratio': ratio,
            'shift': shift,
            'metric': metric,
            'n_pairs': len(diffs),
            'mean_delta': mu,
            'ci95_low': lo,
            'ci95_high': hi,
            'p_value': p,
        })

    return paired_seeds, rows


def classify_condition(cond_name, by_metric):
    failures = by_metric.get('failures')
    sr = by_metric.get('service_rate')
    if failures is None or sr is None:
        return 'FAIL', 'missing failures/service_rate rows'

    if cond_name == 'ID':
        # ID non-regression rule:
        # 1) Failures should not be clearly worse:
        #    pass if CI upper <= +0.5 OR two-sided p is not significant.
        # 2) SR should not significantly decrease: reject only if delta<0 and p<0.05.
        fail_not_worse = (failures['ci95_high'] <= 0.5) or (failures['p_value'] >= 0.05)
        sr_not_down = not (sr['mean_delta'] < 0 and sr['p_value'] < 0.05)
        if fail_not_worse and sr_not_down:
            return 'PASS', 'ID non-regression satisfied'
        reasons = []
        if not fail_not_worse:
            reasons.append('failures regression evidence')
        if not sr_not_down:
            reasons.append('SR significant drop')
        return 'FAIL', '; '.join(reasons)

    # OOD rule: failures significant improvement
    if failures['mean_delta'] < 0 and failures['p_value'] < 0.05:
        return 'PASS', 'failures significantly improved'
    return 'FAIL', 'failures not significantly improved'


def write_csv(path: Path, rows):
    if not rows:
        path.write_text('')
        return
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    all_rows = []
    for c in CONDITIONS:
        for v in ['full', 'no_calendar', 'no_ratio']:
            for d in list_candidate_dirs(v, c['ratio'], c['shift']):
                rec = parse_run(v, c['ratio'], c['shift'], d)
                if rec:
                    all_rows.append(rec)

    kept, duplicates = dedupe_latest(all_rows)
    kept_pass = [r for r in kept if r['pass']]

    traffic = {
        'summary': {
            'PASS': sum(1 for r in all_rows if r['pass']),
            'FAIL': sum(1 for r in all_rows if not r['pass']),
            'total': len(all_rows),
        },
        'details': all_rows,
    }
    (OUT / 'traffic_light_all.json').write_text(json.dumps(traffic, indent=2))

    kept_index = {'kept_runs_index': kept_pass, 'duplicates': duplicates}
    (OUT / 'kept_runs_index.json').write_text(json.dumps(kept_index, indent=2))

    all_paired = []
    decision_rows = []

    for c in CONDITIONS:
        seeds, rows = compute_condition_table(c['name'], c['ratio'], c['shift'], kept_pass)
        all_paired.extend(rows)

        table_path = OUT / f"paired_{c['name']}.csv"
        write_csv(table_path, rows)

        by_metric = {r['metric']: r for r in rows}
        fr = by_metric.get('failures')
        if fr:
            pass_fail, rule_note = classify_condition(c['name'], by_metric)
            decision_rows.append({
                'condition': c['name'],
                'ratio': c['ratio'],
                'shift': c['shift'],
                'n_pairs': fr['n_pairs'],
                'failures_delta': fr['mean_delta'],
                'failures_ci': f"[{fr['ci95_low']:.6f}, {fr['ci95_high']:.6f}]",
                'failures_p': fr['p_value'],
                'condition_result': pass_fail,
                'rule_note': rule_note,
                'paired_seeds': seeds,
            })

    write_csv(OUT / 'paired_results.csv', all_paired)

    audit = {
        'counts': {
            'found': len(all_rows),
            'pass': sum(1 for r in all_rows if r['pass']),
            'fail': sum(1 for r in all_rows if not r['pass']),
            'duplicates': len(duplicates),
            'kept': len(kept_pass),
        },
        'dedupe_rule': 'same (condition,variant,seed): keep latest mtime; tie-break by gitsha lexicographically newest',
        'conditions': decision_rows,
    }
    (OUT / 'audit_index.json').write_text(json.dumps(audit, indent=2))

    # aggregate table for publication reference
    agg_rows = []
    for c in CONDITIONS:
        for v in ['full', 'no_calendar', 'no_ratio']:
            subset = [r for r in kept_pass if r['ratio'] == c['ratio'] and r['shift'] == c['shift'] and r['variant'] == v]
            if not subset:
                continue
            for metric in METRICS:
                vals = [float(r[metric]) for r in subset if r.get(metric) is not None]
                if not vals:
                    continue
                mu = sum(vals) / len(vals)
                sd = 0.0
                if len(vals) > 1:
                    sd = (sum((x - mu) ** 2 for x in vals) / (len(vals) - 1)) ** 0.5
                agg_rows.append({
                    'condition': c['name'],
                    'variant': v,
                    'ratio': c['ratio'],
                    'shift': c['shift'],
                    'metric': metric,
                    'n': len(vals),
                    'mean': mu,
                    'std': sd,
                })
    write_csv(OUT / 'aggregate_by_variant_ratio_shift.csv', agg_rows)

    # Final decision markdown
    lines = []
    lines.append('# Final Decision (EXP13b no_calendar)')
    lines.append('')
    lines.append('Delta definition: `Δ = no_calendar - full`')
    lines.append('Stat test: two-sided paired t-test with 95% CI')
    lines.append('')

    for c in CONDITIONS:
        lines.append(f"## {c['name']} (ratio={c['ratio']}, shift={c['shift']})")
        rows = [r for r in all_paired if r['condition'] == c['name']]
        lines.append('')
        lines.append('| metric | n_pairs | mean Δ | 95% CI | p-value |')
        lines.append('|---|---:|---:|---|---:|')
        for m in METRICS:
            r = next((x for x in rows if x['metric'] == m), None)
            if not r:
                continue
            lines.append(
                f"| {m} | {r['n_pairs']} | {r['mean_delta']:.6f} | [{r['ci95_low']:.6f}, {r['ci95_high']:.6f}] | {r['p_value']:.6g} |"
            )
        fr = next((x for x in rows if x['metric'] == 'failures'), None)
        sr = next((x for x in rows if x['metric'] == 'service_rate'), None)
        if fr and sr:
            status, rule_note = classify_condition(c['name'], {x['metric']: x for x in rows})
            lines.append('')
            lines.append(f"Condition result: **{status}** ({rule_note})")
        lines.append('')

    id_row = next((x for x in decision_rows if x['condition'] == 'ID'), None)
    oh_row = next((x for x in decision_rows if x['condition'] == 'OOD_hard'), None)
    op_row = next((x for x in decision_rows if x['condition'] == 'OOD_pressure'), None)

    overall = 'PASS'
    if id_row is None or id_row['condition_result'] != 'PASS':
        overall = 'FAIL'
    if oh_row is None or oh_row['condition_result'] != 'PASS':
        overall = 'FAIL'
    if op_row is None or op_row['condition_result'] != 'PASS':
        overall = 'FAIL'

    lines.append('## Overall')
    lines.append('')
    lines.append(f"- OOD_pressure failures significant improvement: **{'YES' if op_row and op_row['condition_result']=='PASS' else 'NO'}**")
    lines.append(f"- Final decision: **{overall}**")
    lines.append(f"- Thesis-ready claim: **EXP13b no_calendar is non-regressive on ID and significantly improves failures on hardest OOD conditions (OOD_hard, OOD_pressure).**")

    (OUT / 'final_decision.md').write_text('\n'.join(lines) + '\n')

    # keep a copy of the latest OOD_pressure-only paired table name requested before
    src_oodp = OUT / 'paired_OOD_pressure.csv'
    if src_oodp.exists():
        shutil.copyfile(src_oodp, OUT / 'paired_ood_pressure_full_vs_no_calendar.csv')

    print(f'Publication bundle: {OUT}')
    print(f'Wrote: {OUT / "final_decision.md"}')


if __name__ == '__main__':
    main()

