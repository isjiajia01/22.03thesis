# Thesis Experiment Writing Map

This file is the source of truth for rebuilding the paper after the LaTeX body was cleared.

Use this document, not the cleared chapter `.tex` files, to decide:
- what each chapter should argue
- which experiment supports which claim
- where the raw results live
- which tables/figures should be built
- which 22.01 results are the comparison baseline

## 1. Hard Rule

Do not recover numbers from old LaTeX prose.

Always rebuild tables and figures directly from:
- `22.03thesis/data/results/`
- `22.01thesis/data/audits/`
- `22.03thesis/scripts/experiment_definitions.py`
- `22.03thesis/scripts/runner/master_runner.py`
- `22.03thesis/scripts/runner/generate_hpc_jobs.py`

## 2. Paper Structure To Rebuild

| Chapter | Purpose | Primary experiments | Primary data source |
|---|---|---|---|
| Ch. 1 Introduction | Frame rolling-horizon delivery planning as sequential control under capacity and compute limits | no numeric claim needed | conceptual only |
| Ch. 2 Literature | VRP, dynamic VRP, ALNS/matheuristics, stability/churn, learning-augmented OR | no numeric claim needed | bibliography + method design |
| Ch. 3 Problem Setting | Define visible set, attempt set, carryover, deadlines, flexible service days, warehouse/resource constraints | no numeric claim needed | model docs + code |
| Ch. 4 Architecture | Explain simulator, policy layer, solver layer, HPC/audit chain | `EXP00`-`EXP11` machinery | `22.03thesis/scripts/`, `22.03thesis/code/`, `22.03thesis/src/` |
| Ch. 5 Policies and Gates | Greedy vs proactive, RiskGate, dynamic compute logic | `EXP01`, `EXP03`, `EXP04`, Greedy comparison | `22.03thesis/data/results/EXP_EXP01/`, `22.03thesis/data/results/EXP_EXP04/` |
| Ch. 6 Experimental Design | Define experiment matrix, seeds, sweep dimensions, HPC protocol, audit rules | `EXP00`-`EXP11`, `EXP12`-`EXP15c` | `22.03thesis/scripts/experiment_definitions.py`, `22.03thesis/experiments.md` |
| Ch. 7 Results | Main quantitative evidence | `EXP00`, `EXP01`, `EXP03`, `EXP04`, `EXP05`-`EXP11` | `22.03thesis/data/results/` + `22.01thesis/data/audits/` |
| Ch. 8 Discussion | Interpret trade-offs: failures vs raw cost, dynamic compute ROI, churn/stability | mainly `EXP04`, `EXP06`, `EXP07`, `EXP11` | aggregated tables rebuilt from result JSON |
| Ch. 9 Learning-Augmented Allocation | EXP12-EXP15c only | `EXP12`-`EXP15c` | `22.01thesis/data/audits/ch9/_publication/` for current publication bundle; `22.03thesis/code/experiments/` for rerun entrypoints |
| Ch. 10 Conclusion | Restate validated claims only | consolidated from Ch. 7-9 | derived from final rebuilt tables |

## 3. Exact Data Roots

### 3.1 22.03 main matrix
- Main result root: `22.03thesis/data/results/`
- Core experiments:
  - `22.03thesis/data/results/EXP_EXP00/`
  - `22.03thesis/data/results/EXP_EXP01/`
  - `22.03thesis/data/results/EXP_EXP03/`
  - `22.03thesis/data/results/EXP_EXP04/`
  - `22.03thesis/data/results/EXP_EXP09/`
- Corrected sweep experiments:
  - `22.03thesis/data/results/EXP_EXP05/`
  - `22.03thesis/data/results/EXP_EXP06/`
  - `22.03thesis/data/results/EXP_EXP07/`
  - `22.03thesis/data/results/EXP_EXP08/`
- Greedy comparison inside main matrix:
  - `22.03thesis/data/results/EXP_EXP01/mode_greedy/`
  - `22.03thesis/data/results/EXP_EXP04/mode_greedy/`

### 3.2 Per-seed artifacts
Each finished seed directory should contain:
- `config_dump.json`
- `simulation_results.json`
- `summary_final.json`

Use `summary_final.json` for paper tables first.
Use `simulation_results.json` for audit detail, daily traces, and deeper diagnostics.
Use `config_dump.json` to prove which configuration actually ran.

### 3.3 22.01 comparison baselines
- Main old aggregate: `22.01thesis/data/audits/final/metrics_agg_20260201_095507.csv`
- Greedy vs proactive baseline: `22.01thesis/data/audits/greedy/greedy_proactive_metrics_by_run_20260202_130935.csv`
- Greedy aggregate: `22.01thesis/data/audits/greedy/greedy_proactive_metrics_agg_20260202_130935.csv`
- Chapter 9 publication bundle:
  - `22.01thesis/data/audits/ch9/_publication/paired_results.csv`
  - `22.01thesis/data/audits/ch9/_publication/final_decision.md`
  - `22.01thesis/data/audits/ch9/_publication/audit_index.json`
  - `22.01thesis/data/audits/ch9/_publication/traffic_light_all.json`

## 4. Experiment Matrix And Writing Assignment

### 4.1 Main matrix: `EXP00`-`EXP11`

| Exp | Thesis role | Main claim | Exact result location | Writing destination |
|---|---|---|---|---|
| `EXP00` | BAU reference | no-stress floor/ceiling reference | `22.03thesis/data/results/EXP_EXP00/Seed_*/summary_final.json` | Ch. 6 design, Ch. 7 baseline table |
| `EXP01` | stressed baseline | crunch harms service and increases failures | `22.03thesis/data/results/EXP_EXP01/Seed_*/summary_final.json` | Ch. 5, Ch. 7 |
| `EXP02` | static high-compute upper comparison | tests brute-force compute spend | rerun/output path after completion under `22.03thesis/data/results/EXP_EXP02/` | Ch. 7, Ch. 8 ROI discussion |
| `EXP03` | risk gate only ablation | detection alone helps only marginally; main gain is not here | `22.03thesis/data/results/EXP_EXP03/Seed_*/summary_final.json` | Ch. 5, Ch. 7 |
| `EXP04` | main contribution | dynamic compute + RiskGate beats stressed baseline | `22.03thesis/data/results/EXP_EXP04/Seed_*/summary_final.json` | Ch. 5, Ch. 7, Ch. 8 |
| `EXP05` | physical bottleneck sweep | tests whether higher daily trip allowance changes the frontier; current 22.03 evidence shows only weak marginal effect | `22.03thesis/data/results/EXP_EXP05/max_trips_2/` and `22.03thesis/data/results/EXP_EXP05/max_trips_3/` | Ch. 7 sensitivity |
| `EXP06` | boundary probe | `ratio=0.58` is better than `ratio=0.59`; boundary direction is stable | `22.03thesis/data/results/EXP_EXP06/ratio_0.58/` and `22.03thesis/data/results/EXP_EXP06/ratio_0.59/` | Ch. 7 boundary section |
| `EXP07` | collapse stress | collapse worsens from `0.60` to `0.61`; compare with/without risk | `22.03thesis/data/results/EXP_EXP07/ratio_0.6_risk_False/`, `22.03thesis/data/results/EXP_EXP07/ratio_0.6_risk_True/`, `22.03thesis/data/results/EXP_EXP07/ratio_0.61_risk_False/`, `22.03thesis/data/results/EXP_EXP07/ratio_0.61_risk_True/` | Ch. 7 collapse section |
| `EXP08` | threshold sensitivity | threshold changes should not overturn headline conclusion | `22.03thesis/data/results/EXP_EXP08/delta_0.6/`, `delta_0.7/`, `delta_0.826/`, `delta_0.9/` | Ch. 7 robustness |
| `EXP09` | risk-model ablation | risk model has effect, but main strength is the coupled dynamic compute system | `22.03thesis/data/results/EXP_EXP09/Seed_*/summary_final.json` | Ch. 7 ablation |
| `EXP10` | phase diagram | map ratio frontier more finely | rerun/output path after completion under `22.03thesis/data/results/EXP_EXP10/` | Ch. 7 phase figure |
| `EXP11` | compute ROI curve | quantify value of 30/60/120/300 seconds with/without risk | rerun/output path after completion under `22.03thesis/data/results/EXP_EXP11/` | Ch. 7 ROI figure, Ch. 8 |

### 4.2 Greedy comparison

Greedy is not a thesis experiment number anymore. Treat it as a comparison baseline only.

| Comparison | Exact result location | Why it matters |
|---|---|---|
| `EXP01 proactive vs greedy` | `22.03thesis/data/results/EXP_EXP01/` and `22.03thesis/data/results/EXP_EXP01/mode_greedy/` | proves proactive planning dominates greedy under crunch |
| `EXP04 proactive vs greedy` | `22.03thesis/data/results/EXP_EXP04/` and `22.03thesis/data/results/EXP_EXP04/mode_greedy/` | proves the full system beats naive dispatch even more clearly |

### 4.3 Learning-augmented chain

`EXP12`-`EXP15c` should be written as a separate evidence stream in Chapter 9.

| Exp | Current code entrypoint | Current publication-grade evidence |
|---|---|---|
| `EXP12` | `22.03thesis/code/experiments/exp12_learned_allocator.py` | use current chapter-9 bundle paths under `22.01thesis/data/audits/ch9/_publication/` until 22.03 rerun bundle exists |
| `EXP13` | `22.03thesis/code/experiments/exp13_bandit_allocator.py` | same publication bundle as above |
| `EXP14` | `22.03thesis/code/experiments/exp14_sparse_failsafe.py` | same publication bundle as above |
| `EXP15` | `22.03thesis/code/experiments/exp15_ood_evaluation.py` | `22.01thesis/data/audits/ch9/_publication/paired_results.csv` and `final_decision.md` |

## 5. Writing-Ready Tables

These tables can be lifted directly into the rebuilt manuscript as Markdown drafts, then converted to LaTeX later.

### 5.1 Core baseline/ablation table from 22.03

Source:
- `22.03thesis/data/results/EXP_EXP00/Seed_*/summary_final.json`
- `22.03thesis/data/results/EXP_EXP01/Seed_*/summary_final.json`
- `22.03thesis/data/results/EXP_EXP03/Seed_*/summary_final.json`
- `22.03thesis/data/results/EXP_EXP04/Seed_*/summary_final.json`
- `22.03thesis/data/results/EXP_EXP09/Seed_*/summary_final.json`

| Exp | n | Service rate | Failed orders | Raw cost | Penalized cost | Cost/order | Plan churn |
|---|---:|---:|---:|---:|---:|---:|---:|
| `EXP00` | 10 | 0.993295 | 7.0 | 5901.895 | 6951.895 | 5.691316 | 0.243056 |
| `EXP01` | 10 | 0.974330 | 26.8 | 6352.986 | 10372.986 | 6.245565 | 0.573958 |
| `EXP03` | 10 | 0.975862 | 25.2 | 6332.386 | 10112.386 | 6.215537 | 0.582292 |
| `EXP04` | 10 | 0.977778 | 23.2 | 6163.570 | 9643.570 | 6.037866 | 0.549802 |
| `EXP09` | 10 | 0.974425 | 26.7 | 6349.468 | 10354.468 | 6.241504 | 0.573958 |

Use this table for the main result section.
Headline claim supported by this table:
- `EXP04` is the best stressed configuration among current finished 22.03 core runs.
- `EXP03` is not useless, but its effect is small relative to `EXP04`.

### 5.2 Proactive vs greedy table from 22.03

Source:
- `22.03thesis/data/results/EXP_EXP01/Seed_*/summary_final.json`
- `22.03thesis/data/results/EXP_EXP01/mode_greedy/Seed_*/summary_final.json`
- `22.03thesis/data/results/EXP_EXP04/Seed_*/summary_final.json`
- `22.03thesis/data/results/EXP_EXP04/mode_greedy/Seed_*/summary_final.json`

| Case | Mode | Service rate | Failed orders | Raw cost | Penalized cost | Cost/order | Plan churn |
|---|---|---:|---:|---:|---:|---:|---:|
| `EXP01` | proactive | 0.974330 | 26.8 | 6352.986 | 10372.986 | 6.245565 | 0.573958 |
| `EXP01` | greedy | 0.915326 | 88.4 | 5538.513 | 18798.513 | 5.795882 | 0.443251 |
| `EXP04` | proactive | 0.977778 | 23.2 | 6163.570 | 9643.570 | 6.037866 | 0.549802 |
| `EXP04` | greedy | 0.916379 | 87.3 | 5546.791 | 18641.791 | 5.797816 | 0.459493 |

Interpretation to write:
- greedy has lower raw cost because it simply fails many more orders
- proactive dominates on service rate, failed orders, and penalized cost
- this supports the main policy argument even before discussing dynamic compute

### 5.3 `EXP06` boundary table: 22.03 vs 22.01

22.03 source:
- `22.03thesis/data/results/EXP_EXP06/ratio_0.58/Seed_*/summary_final.json`
- `22.03thesis/data/results/EXP_EXP06/ratio_0.59/Seed_*/summary_final.json`

22.01 source:
- `22.01thesis/data/audits/greedy/greedy_proactive_metrics_by_run_20260202_130935.csv`

| Ratio | Version | Service rate | Failed orders | Raw cost | Penalized cost | Plan churn |
|---|---|---:|---:|---:|---:|---:|
| `0.58` | `22.01` | 0.973180 | 28.0 | 6191.806 | 10391.806 | 0.544357 |
| `0.58` | `22.03` | 0.975862 | 25.2 | 6333.582 | 10113.582 | 0.582292 |
| `0.59` | `22.01` | 0.972989 | 28.2 | 6220.336 | 10450.336 | 0.545234 |
| `0.59` | `22.03` | 0.974617 | 26.5 | 6351.268 | 10326.268 | 0.574851 |

Interpretation to write:
- the boundary direction still holds: `0.58` is better than `0.59`
- 22.03 moved the curve to better service / fewer failures / lower penalized cost
- 22.03 pays with higher raw cost and higher churn

## 6. Figure Plan With Exact Input Paths

### Figure A. Baseline vs stressed vs ablations
- X-axis: experiment ID `EXP00`, `EXP01`, `EXP03`, `EXP04`, `EXP09`
- Y-axis options: `service_rate`, `failed_orders`, `penalized_cost`
- Input: all `summary_final.json` under those experiment directories
- Best chapter: Ch. 7 main results

### Figure B. Proactive vs greedy paired comparison
- Two grouped bars or slope plots for `EXP01` and `EXP04`
- Metrics: `failed_orders`, `penalized_cost`, `service_rate`
- Input paths:
  - `22.03thesis/data/results/EXP_EXP01/Seed_*/summary_final.json`
  - `22.03thesis/data/results/EXP_EXP01/mode_greedy/Seed_*/summary_final.json`
  - `22.03thesis/data/results/EXP_EXP04/Seed_*/summary_final.json`
  - `22.03thesis/data/results/EXP_EXP04/mode_greedy/Seed_*/summary_final.json`
- Best chapter: Ch. 5 or early Ch. 7

### Figure C. Boundary figure for `EXP06`
- X-axis: ratio `0.58`, `0.59`
- Y-axis: `penalized_cost` or `failed_orders`
- Two lines: `22.01`, `22.03`
- Input paths:
  - `22.03thesis/data/results/EXP_EXP06/ratio_0.58/Seed_*/summary_final.json`
  - `22.03thesis/data/results/EXP_EXP06/ratio_0.59/Seed_*/summary_final.json`
  - `22.01thesis/data/audits/greedy/greedy_proactive_metrics_by_run_20260202_130935.csv`
- Best chapter: Ch. 7 boundary/sensitivity section

### Figure D. Collapse figure for `EXP07`
- X-axis: `ratio_0.6`, `ratio_0.61`
- Hue: `risk=False`, `risk=True`
- Y-axis: `failed_orders` and `penalized_cost`
- Input paths:
  - `22.03thesis/data/results/EXP_EXP07/ratio_0.6_risk_False/`
  - `22.03thesis/data/results/EXP_EXP07/ratio_0.6_risk_True/`
  - `22.03thesis/data/results/EXP_EXP07/ratio_0.61_risk_False/`
  - `22.03thesis/data/results/EXP_EXP07/ratio_0.61_risk_True/`
- Best chapter: Ch. 7 collapse section
- Status note: on 2026-03-06, `risk_False` endpoints were complete; `risk_True` endpoints were still running.

### Figure E. Physical bottleneck figure for `EXP05`
- X-axis: `max_trips_2` vs `max_trips_3`
- Y-axis: `failed_orders`, `service_rate`, `penalized_cost`
- Input paths:
  - `22.03thesis/data/results/EXP_EXP05/max_trips_2/`
  - `22.03thesis/data/results/EXP_EXP05/max_trips_3/`
- Best chapter: Ch. 7 sensitivity / physical bottleneck section
- Interpretation note: current 22.03 evidence shows only a very weak improvement from `max_trips=3`, with slightly higher raw and penalized cost. Do not write this as a strong positive result.

### Figure F. Threshold sensitivity figure for `EXP08`
- X-axis: threshold `0.6`, `0.7`, `0.826`, `0.9`
- Y-axis: `service_rate` or `penalized_cost`
- Input paths:
  - `22.03thesis/data/results/EXP_EXP08/delta_0.6/`
  - `22.03thesis/data/results/EXP_EXP08/delta_0.7/`
  - `22.03thesis/data/results/EXP_EXP08/delta_0.826/`
  - `22.03thesis/data/results/EXP_EXP08/delta_0.9/`
- Best chapter: Ch. 7 robustness section
- Status note: on 2026-03-06 only `config_dump.json` had landed.

### Figure G. Chapter 9 paired feature-ablation table/figure
- Input paths:
  - `22.01thesis/data/audits/ch9/_publication/paired_results.csv`
  - `22.01thesis/data/audits/ch9/_publication/final_decision.md`
  - `22.01thesis/data/audits/ch9/_publication/audit_index.json`
- Reuse for Ch. 9 until a 22.03 publication bundle exists.

## 7. Current Status Snapshot On 2026-03-06

| Experiment | Status | Exact evidence |
|---|---|---|
| `EXP00` | finished | full `Seed_1..10` outputs under `22.03thesis/data/results/EXP_EXP00/` |
| `EXP01` | finished | full `Seed_1..10` outputs under `22.03thesis/data/results/EXP_EXP01/` |
| `EXP03` | finished | full `Seed_1..10` outputs under `22.03thesis/data/results/EXP_EXP03/` |
| `EXP04` | finished | full `Seed_1..10` outputs under `22.03thesis/data/results/EXP_EXP04/` |
| `EXP05` | finished | full outputs under `22.03thesis/data/results/EXP_EXP05/max_trips_2/` and `22.03thesis/data/results/EXP_EXP05/max_trips_3/`; result is a weak-effect sensitivity point, not a headline win |
| `EXP06` | finished after corrected sweep rerun | full outputs under `22.03thesis/data/results/EXP_EXP06/ratio_0.58/` and `ratio_0.59/` |
| `EXP07` | partial | full outputs for `risk_False`; `risk_True` only `config_dump.json` at snapshot time |
| `EXP08` | running / partial | only `config_dump.json` under all `delta_*` endpoints |
| `EXP09` | finished | full `Seed_1..10` outputs under `22.03thesis/data/results/EXP_EXP09/` |
| Greedy comparison | finished for `EXP01` and `EXP04` | `22.03thesis/data/results/EXP_EXP01/mode_greedy/`, `22.03thesis/data/results/EXP_EXP04/mode_greedy/` |

## 8. Core Writing Conclusions Already Safe To Reuse

These are the conclusions that remain valid given the finished 22.03 evidence.

1. `EXP04 > EXP01` is still the main result.
2. `proactive > greedy` is clearly true on service rate, failures, and penalized cost.
3. `EXP03` is no longer best described as useless.
4. The correct wording is: `EXP03` gives only a small improvement; the main gain comes from `EXP04`.
5. `EXP06` confirms the old boundary direction still holds: `0.58` is better than `0.59`.
6. `EXP05` should be written as a weak-result sensitivity check: increasing daily trips from 2 to 3 does not materially improve the thesis-critical outcomes in 22.03.

## 9. Rebuild Workflow For The Next Writer/AI

1. Read `22.03thesis/paper/THESIS_EXPERIMENT_WRITING_MAP.md` first.
2. Recompute aggregates from `summary_final.json` instead of trusting any old manuscript number.
3. Use `22.01thesis/data/audits/` only for explicit historical comparison sections.
4. For `EXP05`, `EXP07`, `EXP08`, `EXP10`, `EXP11`, check run completion before writing final claims.
5. Rebuild LaTeX only after the Markdown tables and figure specs in this file are updated.

## 10. Code Entry Points

- Experiment definitions: `22.03thesis/scripts/experiment_definitions.py`
- CLI: `22.03thesis/scripts/cli.py`
- Main runner: `22.03thesis/scripts/runner/master_runner.py`
- HPC generator: `22.03thesis/scripts/runner/generate_hpc_jobs.py`
- Main simulator facade: `22.03thesis/src/src/__init__.py`
- Legacy greedy audit scripts: `22.03thesis/scripts/audit_greedy_completion.py`, `22.03thesis/scripts/audit_greedy_vs_proactive.py`
- Learning experiments: `22.03thesis/code/experiments/exp12_learned_allocator.py`, `22.03thesis/code/experiments/exp13_bandit_allocator.py`, `22.03thesis/code/experiments/exp14_sparse_failsafe.py`, `22.03thesis/code/experiments/exp15_ood_evaluation.py`

