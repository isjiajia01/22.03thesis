#!/usr/bin/env python3
"""Audit EXP21 completeness and paired-by-seed preset comparisons."""

import csv
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path

from scipy import stats

ROOT = Path('/zhome/2a/1/202283/22.01 thesis')
BASE = ROOT / 'data' / 'results' / 'EXP21'
AUDIT = BASE / '_audit'
PUB = AUDIT / '_publication'
AUDIT.mkdir(parents=True, exist_ok=True)
PUB.mkdir(parents=True, exist_ok=True)

CONDITIONS = ['ID', 'OOD_hard', 'OOD_pressure']
PRESETS = ['baseline_default', 'fss_christofides', 'gls_001', 'fss_parallel']
SEEDS = list(range(1, 11))
METRICS = ['failures', 'service_rate', 'penalized_cost', 'compute_seconds']


def parse_seed_git(name: str):
    parts = name.split('_')
    if len(parts) < 3 or parts[0] != 'seed':
        return None, ''
    try:
        seed = int(parts[1])
    except Exception:
        return None, ''
    gitsha = parts[2]
    return seed, gitsha


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
    p = float(stats.ttest_1samp(diffs, 0.0).pvalue)
    return mu, lo, hi, p


def write_csv(path: Path, rows):
    if not rows:
        path.write_text('')
        return
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    all_runs = []

    for cond in CONDITIONS:
        for preset in PRESETS:
            label = f'{cond}_{preset}'
            label_dir = BASE / label
            if not label_dir.exists():
                continue
            for run_dir in sorted(label_dir.iterdir()):
                if not run_dir.is_dir() or not run_dir.name.startswith('seed_'):
                    continue
                seed, gitsha = parse_seed_git(run_dir.name)
                if seed is None:
                    continue

                inner = run_dir / 'DEFAULT' / 'EXP21'
                sf = inner / 'summary_final.json'
                cf = inner / 'config_dump.json'
                of = inner / 'ood_labels.json'
                af = inner / 'allocator_config_dump.json'
                df = inner / 'daily_stats.csv'
                ssf = inner / 'solver_config_dump.json'

                passed = True
                reason = ''
                summary = {}
                if not sf.exists():
                    passed = False
                    reason = 'missing summary_final.json'
                elif not cf.exists() or not of.exists() or not af.exists() or not ssf.exists():
                    passed = False
                    reason = 'missing required metadata'
                else:
                    try:
                        summary = json.loads(sf.read_text())
                    except Exception as e:
                        passed = False
                        reason = f'parse_error:{e}'

                compute = None
                solver_preset_day = None
                if passed and df.exists():
                    total = 0.0
                    with open(df, newline='') as f:
                        rows = list(csv.DictReader(f))
                    for r in rows:
                        try:
                            total += float(r.get('compute_limit_seconds') or 0.0)
                        except Exception:
                            pass
                    compute = total
                    if rows:
                        solver_preset_day = rows[0].get('solver_search_preset')

                solver_preset_summary = summary.get('solver_search_preset') if passed else None

                all_runs.append({
                    'condition': cond,
                    'preset': preset,
                    'label': label,
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
                    'compute_seconds': compute,
                    'solver_search_preset_daily': solver_preset_day,
                    'solver_search_preset_summary': solver_preset_summary,
                })

    # traffic light (raw)
    traffic = {
        'summary': {
            'PASS': sum(1 for r in all_runs if r['pass']),
            'FAIL': sum(1 for r in all_runs if not r['pass']),
            'total': len(all_runs),
        },
        'details': all_runs,
    }
    (AUDIT / 'traffic_light_all.json').write_text(json.dumps(traffic, indent=2))

    # dedupe
    by_key = defaultdict(list)
    for r in all_runs:
        by_key[(r['condition'], r['preset'], r['seed'])].append(r)

    kept = []
    duplicates = []
    for key, items in sorted(by_key.items()):
        items = sorted(items, key=lambda x: (x['mtime'], x['gitsha']), reverse=True)
        keep = items[0]
        kept.append(keep)
        if len(items) > 1:
            duplicates.append({
                'condition': key[0],
                'preset': key[1],
                'seed': key[2],
                'kept': keep['run_dir'],
                'dropped': [x['run_dir'] for x in items[1:]],
            })

    kept_pass = [r for r in kept if r['pass']]
    (AUDIT / 'kept_runs_index.json').write_text(json.dumps({'kept_runs_index': kept_pass, 'duplicates': duplicates}, indent=2))

    # completeness matrix
    missing = []
    for cond in CONDITIONS:
        for preset in PRESETS:
            have = {r['seed'] for r in kept_pass if r['condition'] == cond and r['preset'] == preset}
            for s in SEEDS:
                if s not in have:
                    missing.append({'condition': cond, 'preset': preset, 'seed': s})

    # freeze checks
    freeze_issues = []
    for r in kept_pass:
        if r.get('solver_search_preset_daily') and r['solver_search_preset_daily'] != r['preset']:
            freeze_issues.append({'type': 'daily_preset_mismatch', 'run_dir': r['run_dir'], 'expected': r['preset'], 'actual': r['solver_search_preset_daily']})
        if r.get('solver_search_preset_summary') and r['solver_search_preset_summary'] != r['preset']:
            freeze_issues.append({'type': 'summary_preset_mismatch', 'run_dir': r['run_dir'], 'expected': r['preset'], 'actual': r['solver_search_preset_summary']})

    # paired results: each preset vs baseline_default within condition
    paired_rows = []
    for cond in CONDITIONS:
        baseline = {r['seed']: r for r in kept_pass if r['condition'] == cond and r['preset'] == 'baseline_default'}
        for preset in [p for p in PRESETS if p != 'baseline_default']:
            comp = {r['seed']: r for r in kept_pass if r['condition'] == cond and r['preset'] == preset}
            paired_seeds = sorted(set(baseline) & set(comp))
            for metric in METRICS:
                diffs = []
                for s in paired_seeds:
                    b = baseline[s].get(metric)
                    t = comp[s].get(metric)
                    if b is None or t is None:
                        continue
                    diffs.append(float(t) - float(b))
                if not diffs:
                    continue
                mu, lo, hi, p = paired_stats(diffs)
                paired_rows.append({
                    'condition': cond,
                    'preset': preset,
                    'baseline': 'baseline_default',
                    'metric': metric,
                    'n_pairs': len(diffs),
                    'mean_delta': mu,
                    'ci95_low': lo,
                    'ci95_high': hi,
                    'p_value': p,
                })

    write_csv(AUDIT / 'paired_results.csv', paired_rows)

    # aggregate table
    agg_rows = []
    for cond in CONDITIONS:
        for preset in PRESETS:
            subset = [r for r in kept_pass if r['condition'] == cond and r['preset'] == preset]
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
                    'condition': cond,
                    'preset': preset,
                    'metric': metric,
                    'n': len(vals),
                    'mean': mu,
                    'std': sd,
                })
    write_csv(AUDIT / 'aggregate_by_condition_preset.csv', agg_rows)

    # decision markdown
    lines = []
    lines.append('# EXP21 Final Decision')
    lines.append('')
    lines.append('Paired comparisons are preset - baseline_default within each condition.')
    lines.append('Delta definition: Δ = preset - baseline_default')
    lines.append('')

    for cond in CONDITIONS:
        lines.append(f'## {cond}')
        rows = [r for r in paired_rows if r['condition'] == cond and r['metric'] == 'failures']
        if not rows:
            lines.append('- No paired data available.')
            lines.append('')
            continue
        for r in rows:
            lines.append(
                f"- {r['preset']}: failures Δ={r['mean_delta']:.4f}, CI=[{r['ci95_low']:.4f}, {r['ci95_high']:.4f}], p={r['p_value']:.4g}, n={r['n_pairs']}"
            )
        lines.append('')

    lines.append('## Audit')
    lines.append(f"- Found runs: {len(all_runs)}")
    lines.append(f"- Kept PASS runs: {len(kept_pass)}")
    lines.append(f"- Missing expected entries: {len(missing)}")
    lines.append(f"- Freeze issues: {len(freeze_issues)}")

    (AUDIT / 'final_decision.md').write_text('\n'.join(lines) + '\n')

    audit_index = {
        'counts': {
            'found': len(all_runs),
            'pass': sum(1 for r in all_runs if r['pass']),
            'fail': sum(1 for r in all_runs if not r['pass']),
            'duplicates': len(duplicates),
            'kept': len(kept_pass),
            'missing_expected': len(missing),
        },
        'missing_expected': missing,
        'freeze_issues': freeze_issues,
        'dedupe_rule': 'same (condition,preset,seed): keep latest mtime; tie-break by gitsha lexicographically newest',
    }
    (AUDIT / 'audit_index.json').write_text(json.dumps(audit_index, indent=2))

    # publication copy
    for name in [
        'audit_index.json',
        'traffic_light_all.json',
        'kept_runs_index.json',
        'paired_results.csv',
        'aggregate_by_condition_preset.csv',
        'final_decision.md',
    ]:
        src = AUDIT / name
        dst = PUB / name
        if src.exists():
            shutil.copyfile(src, dst)

    print(f'Audit outputs written to: {AUDIT}')


if __name__ == '__main__':
    main()

