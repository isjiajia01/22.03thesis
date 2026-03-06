# Figure Build Recipes

This file gives script-level instructions for rebuilding thesis figures from the actual experiment artifacts.

Rule:
- never read numbers back out of old LaTeX
- always start from `summary_final.json`, then drop to `simulation_results.json` only if daily detail is needed
- if a run is incomplete, do not fake the missing points

## 1. Environment

Work from repo root:

```bash
cd /zhome/2a/1/202283/active/projects/thesis
```

Recommended plotting stack:

```bash
/usr/bin/python3 - <<'PY'
import json, glob, os
import pandas as pd
import matplotlib.pyplot as plt
print('ok')
PY
```

If you want to save generated figures, use:
- `22.03thesis/paper/figures_generated/`

Create it first:

```bash
mkdir -p 22.03thesis/paper/figures_generated
```

## 2. Common Loader

Use this loader as the base for all figures.

```python
from pathlib import Path
import json
import pandas as pd


def load_summary_tree(root, exp_label, endpoint=None, mode=None):
    root = Path(root)
    rows = []
    if endpoint is None:
        seed_dirs = sorted(root.glob('Seed_*'))
    else:
        seed_dirs = sorted((root / endpoint).glob('Seed_*'))
    for sd in seed_dirs:
        fp = sd / 'summary_final.json'
        if not fp.exists():
            continue
        data = json.loads(fp.read_text())
        row = {'exp': exp_label, 'seed': sd.name}
        if endpoint is not None:
            row['endpoint'] = endpoint
        if mode is not None:
            row['mode'] = mode
        row.update(data)
        rows.append(row)
    return pd.DataFrame(rows)
```

Core numeric columns used throughout:
- `service_rate`
- `failed_orders`
- `deadline_failure_count`
- `cost_raw`
- `penalized_cost`
- `cost_per_order`
- `plan_churn`

## 3. Figure A: Main Result Bar Chart

Purpose:
- show the main thesis claim that `EXP04` is the best stressed configuration among completed core runs

Input paths:
- `22.03thesis/data/results/EXP_EXP00/`
- `22.03thesis/data/results/EXP_EXP01/`
- `22.03thesis/data/results/EXP_EXP03/`
- `22.03thesis/data/results/EXP_EXP04/`
- `22.03thesis/data/results/EXP_EXP09/`

Suggested panels:
- panel 1: `service_rate`
- panel 2: `failed_orders`
- panel 3: `penalized_cost`

Recipe:

```python
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

base = Path('22.03thesis/data/results')
dfs = [
    load_summary_tree(base / 'EXP_EXP00', 'EXP00'),
    load_summary_tree(base / 'EXP_EXP01', 'EXP01'),
    load_summary_tree(base / 'EXP_EXP03', 'EXP03'),
    load_summary_tree(base / 'EXP_EXP04', 'EXP04'),
    load_summary_tree(base / 'EXP_EXP09', 'EXP09'),
]
df = pd.concat(dfs, ignore_index=True)
agg = df.groupby('exp')[['service_rate', 'failed_orders', 'penalized_cost']].agg(['mean', 'std'])
order = ['EXP00', 'EXP01', 'EXP03', 'EXP04', 'EXP09']

fig, axes = plt.subplots(1, 3, figsize=(14, 4))
for ax, metric, title in zip(
    axes,
    ['service_rate', 'failed_orders', 'penalized_cost'],
    ['Service Rate', 'Failed Orders', 'Penalized Cost']
):
    means = [agg.loc[e, (metric, 'mean')] for e in order]
    stds = [agg.loc[e, (metric, 'std')] for e in order]
    ax.bar(order, means, yerr=stds, capsize=4)
    ax.set_title(title)
    ax.tick_params(axis='x', rotation=45)

plt.tight_layout()
plt.savefig('22.03thesis/paper/figures_generated/fig_main_results.png', dpi=220)
```

Caption guidance:
- `EXP04` improves stressed-horizon performance relative to `EXP01`
- `EXP03` helps only slightly
- `EXP09` stays close to `EXP01`, supporting the claim that the full coupled system matters more than isolated components

## 4. Figure B: Proactive vs Greedy Comparison

Purpose:
- show that proactive planning dominates greedy under pressure

Input paths:
- `22.03thesis/data/results/EXP_EXP01/`
- `22.03thesis/data/results/EXP_EXP01/mode_greedy/`
- `22.03thesis/data/results/EXP_EXP04/`
- `22.03thesis/data/results/EXP_EXP04/mode_greedy/`

Suggested metrics:
- `service_rate`
- `failed_orders`
- `penalized_cost`

Recipe:

```python
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

base = Path('22.03thesis/data/results')
df = pd.concat([
    load_summary_tree(base / 'EXP_EXP01', 'EXP01', mode='proactive'),
    load_summary_tree(base / 'EXP_EXP01' / 'mode_greedy', 'EXP01', mode='greedy'),
    load_summary_tree(base / 'EXP_EXP04', 'EXP04', mode='proactive'),
    load_summary_tree(base / 'EXP_EXP04' / 'mode_greedy', 'EXP04', mode='greedy'),
], ignore_index=True)

summary = df.groupby(['exp', 'mode'])[['service_rate', 'failed_orders', 'penalized_cost']].mean().reset_index()

fig, axes = plt.subplots(1, 3, figsize=(14, 4))
for ax, metric in zip(axes, ['service_rate', 'failed_orders', 'penalized_cost']):
    pivot = summary.pivot(index='exp', columns='mode', values=metric).loc[['EXP01', 'EXP04']]
    pivot.plot(kind='bar', ax=ax)
    ax.set_title(metric)
    ax.tick_params(axis='x', rotation=0)

plt.tight_layout()
plt.savefig('22.03thesis/paper/figures_generated/fig_proactive_vs_greedy.png', dpi=220)
```

Caption guidance:
- greedy lowers raw cost by leaving many more orders unserved
- proactive is better on the paper-critical metrics: service rate, failures, penalized cost

## 5. Figure C: `EXP06` Boundary Comparison (`22.03` vs `22.01`)

Purpose:
- show that the old boundary direction still holds after the 22.03 rebuild

Input paths:
- `22.03thesis/data/results/EXP_EXP06/ratio_0.58/`
- `22.03thesis/data/results/EXP_EXP06/ratio_0.59/`
- `22.01thesis/data/audits/greedy/greedy_proactive_metrics_by_run_20260202_130935.csv`

Recipe:

```python
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

base = Path('22.03thesis/data/results/EXP_EXP06')
df_2303 = pd.concat([
    load_summary_tree(base, '22.03', endpoint='ratio_0.58').assign(ratio=0.58),
    load_summary_tree(base, '22.03', endpoint='ratio_0.59').assign(ratio=0.59),
], ignore_index=True)

old = pd.read_csv('22.01thesis/data/audits/greedy/greedy_proactive_metrics_by_run_20260202_130935.csv')
old = old[old['ratio'].isin([0.58, 0.59])].copy()
old['version'] = '22.01'

new = df_2303[['ratio', 'service_rate', 'failed_orders', 'penalized_cost']].copy()
new['version'] = '22.03'

agg_old = old.groupby(['version', 'ratio'])[['service_rate_within_window', 'sum_failures', 'penalized_cost']].mean().reset_index()
agg_old = agg_old.rename(columns={'service_rate_within_window': 'service_rate', 'sum_failures': 'failed_orders'})
agg_new = new.groupby(['version', 'ratio'])[['service_rate', 'failed_orders', 'penalized_cost']].mean().reset_index()
plot_df = pd.concat([agg_old, agg_new], ignore_index=True)

fig, axes = plt.subplots(1, 3, figsize=(14, 4))
for ax, metric in zip(axes, ['service_rate', 'failed_orders', 'penalized_cost']):
    for version, sub in plot_df.groupby('version'):
        sub = sub.sort_values('ratio')
        ax.plot(sub['ratio'], sub[metric], marker='o', label=version)
    ax.set_title(metric)
    ax.set_xlabel('ratio')
    ax.legend()

plt.tight_layout()
plt.savefig('22.03thesis/paper/figures_generated/fig_exp06_boundary_2201_vs_2203.png', dpi=220)
```

Caption guidance:
- `0.58` remains better than `0.59`
- the whole curve moved toward fewer failures / lower penalized cost in 22.03
- churn got worse, so the boundary result is not the whole story

## 6. Figure D: `EXP07` Collapse Stress Figure

Purpose:
- compare `0.60` vs `0.61` and risk off/on under deeper stress

Input paths:
- `22.03thesis/data/results/EXP_EXP07/ratio_0.6_risk_False/`
- `22.03thesis/data/results/EXP_EXP07/ratio_0.6_risk_True/`
- `22.03thesis/data/results/EXP_EXP07/ratio_0.61_risk_False/`
- `22.03thesis/data/results/EXP_EXP07/ratio_0.61_risk_True/`

Status guard:
- only build the final figure after all four endpoints have `summary_final.json`
- if only the `risk_False` endpoints are complete, generate a partial diagnostic figure and label it clearly

Recipe:

```python
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

base = Path('22.03thesis/data/results/EXP_EXP07')
parts = []
for endpoint in ['ratio_0.6_risk_False', 'ratio_0.6_risk_True', 'ratio_0.61_risk_False', 'ratio_0.61_risk_True']:
    ratio = 0.60 if 'ratio_0.6_' in endpoint else 0.61
    risk = 'True' if endpoint.endswith('True') else 'False'
    df = load_summary_tree(base, 'EXP07', endpoint=endpoint)
    if len(df) == 0:
        continue
    df['ratio'] = ratio
    df['risk'] = risk
    parts.append(df)

df = pd.concat(parts, ignore_index=True)
agg = df.groupby(['ratio', 'risk'])[['failed_orders', 'penalized_cost', 'service_rate']].mean().reset_index()

fig, axes = plt.subplots(1, 3, figsize=(14, 4))
for ax, metric in zip(axes, ['failed_orders', 'penalized_cost', 'service_rate']):
    for risk, sub in agg.groupby('risk'):
        sub = sub.sort_values('ratio')
        ax.plot(sub['ratio'], sub[metric], marker='o', label=f'risk={risk}')
    ax.set_title(metric)
    ax.legend()

plt.tight_layout()
plt.savefig('22.03thesis/paper/figures_generated/fig_exp07_collapse.png', dpi=220)
```

Caption guidance:
- collapse steepens as ratio worsens from `0.60` to `0.61`
- whether risk logic changes that slope is the central interpretation

## 7. Figure E: `EXP05` Physical Bottleneck Figure

Purpose:
- show what changes when max trips go from 2 to 3

Input paths:
- `22.03thesis/data/results/EXP_EXP05/max_trips_2/`
- `22.03thesis/data/results/EXP_EXP05/max_trips_3/`

Status guard:
- do not build final figure until `summary_final.json` exists for both endpoints

Recipe:

```python
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

base = Path('22.03thesis/data/results/EXP_EXP05')
df = pd.concat([
    load_summary_tree(base, 'EXP05', endpoint='max_trips_2').assign(max_trips=2),
    load_summary_tree(base, 'EXP05', endpoint='max_trips_3').assign(max_trips=3),
], ignore_index=True)

agg = df.groupby('max_trips')[['service_rate', 'failed_orders', 'penalized_cost']].mean().reset_index()

fig, axes = plt.subplots(1, 3, figsize=(14, 4))
for ax, metric in zip(axes, ['service_rate', 'failed_orders', 'penalized_cost']):
    ax.bar(agg['max_trips'].astype(str), agg[metric])
    ax.set_title(metric)
    ax.set_xlabel('max_trips')

plt.tight_layout()
plt.savefig('22.03thesis/paper/figures_generated/fig_exp05_multitrip.png', dpi=220)
```

Caption guidance:
- this is the cleanest physical-capacity intervention in the matrix
- it should be discussed separately from compute improvements

## 8. Figure F: `EXP08` Threshold Sensitivity

Purpose:
- show whether threshold tuning changes the qualitative result or only nudges it

Input paths:
- `22.03thesis/data/results/EXP_EXP08/delta_0.6/`
- `22.03thesis/data/results/EXP_EXP08/delta_0.7/`
- `22.03thesis/data/results/EXP_EXP08/delta_0.826/`
- `22.03thesis/data/results/EXP_EXP08/delta_0.9/`

Status guard:
- do not build final figure until all endpoints have `summary_final.json`

Recipe:

```python
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

base = Path('22.03thesis/data/results/EXP_EXP08')
parts = []
for delta in [0.6, 0.7, 0.826, 0.9]:
    endpoint = f'delta_{delta}'
    df = load_summary_tree(base, 'EXP08', endpoint=endpoint)
    if len(df) == 0:
        continue
    df['delta_on'] = delta
    parts.append(df)

df = pd.concat(parts, ignore_index=True)
agg = df.groupby('delta_on')[['service_rate', 'failed_orders', 'penalized_cost']].mean().reset_index()

fig, axes = plt.subplots(1, 3, figsize=(14, 4))
for ax, metric in zip(axes, ['service_rate', 'failed_orders', 'penalized_cost']):
    ax.plot(agg['delta_on'], agg[metric], marker='o')
    ax.set_title(metric)
    ax.set_xlabel('delta_on')

plt.tight_layout()
plt.savefig('22.03thesis/paper/figures_generated/fig_exp08_threshold_sensitivity.png', dpi=220)
```

Caption guidance:
- the key question is robustness of the headline conclusion, not finding a magic threshold

## 9. Figure G: Chapter 9 Paired Results

Purpose:
- support the learning-augmented chapter using the current publication bundle

Input paths:
- `22.01thesis/data/audits/ch9/_publication/paired_results.csv`
- `22.01thesis/data/audits/ch9/_publication/final_decision.md`

Recipe:

```python
import pandas as pd
import matplotlib.pyplot as plt

paired = pd.read_csv('22.01thesis/data/audits/ch9/_publication/paired_results.csv')
fig, ax = plt.subplots(figsize=(9, 4))
sub = paired[paired['Metric'].isin(['Failures', 'Penalized cost'])].copy()
ax.bar(sub['Scenario'] + ' | ' + sub['Metric'], sub['Mean Δ'])
ax.axhline(0, color='black', linewidth=1)
ax.tick_params(axis='x', rotation=45)
plt.tight_layout()
plt.savefig('22.03thesis/paper/figures_generated/fig_ch9_paired_results.png', dpi=220)
```

## 10. Sanity Checklist Before Exporting Any Figure

1. Confirm every plotted endpoint has the expected number of finished seeds.
2. Confirm no figure mixes `config_dump.json`-only endpoints with completed endpoints unless it is explicitly labeled partial.
3. Confirm 22.01 comparisons cite the exact audit CSV path.
4. Confirm the caption states whether lower or higher is better for the metric.
5. Save a PNG for drafting and a PDF version if the figure is final.

## 11. Status Snapshot For `EXP05`, `EXP07`, `EXP08` On 2026-03-06

Based on live queue state and landed files:
- `EXP05`: job `27976934`, `20 RUN`, filesystem has `20 config_dump.json`, `0 simulation_results.json`, `0 summary_final.json`
- `EXP07`: job `27976932`, `20 DONE` and `20 RUN`, filesystem has:
  - `ratio_0.6_risk_False`: `10 summary_final.json`
  - `ratio_0.61_risk_False`: `10 summary_final.json`
  - `ratio_0.6_risk_True`: `0 summary_final.json`, `10 config_dump.json`
  - `ratio_0.61_risk_True`: `0 summary_final.json`, `10 config_dump.json`
- `EXP08`: job `27976933`, `20 RUN`, filesystem has `20 config_dump.json`, `0 simulation_results.json`, `0 summary_final.json`

