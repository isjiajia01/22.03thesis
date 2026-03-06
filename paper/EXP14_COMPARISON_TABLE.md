# EXP14 Aggregate Table

Source data:
- `22.03thesis/data/results/EXP14/`
- `22.01thesis/data/results/EXP14/`

Scenario:
- `crunch_d5_d10`

## Table A. `22.03` aggregate (`mean ± sd` omitted here; see raw summaries if needed)

| Variant | Service Rate | Failed Orders | Penalized Cost | Raw Cost | Cost/Order | Plan Churn |
|---|---:|---:|---:|---:|---:|---:|
| `EXP14a` | `0.976149` | `24.9` | `10057.95` | `6322.95` | `6.204432` | `0.577706` |
| `EXP14b` | `0.977203` | `23.8` | `9859.24` | `6289.24` | `6.164731` | `0.562054` |
| `EXP14c` | `0.976533` | `24.5` | `9978.82` | `6303.82` | `6.183306` | `0.564285` |

## Table B. `22.03 - 22.01`

| Variant | Delta Service Rate | Delta Failed Orders | Delta Penalized Cost | Delta Raw Cost | Delta Cost/Order | Delta Plan Churn |
|---|---:|---:|---:|---:|---:|---:|
| `EXP14a` | `+0.001533` | `-1.6` | `-229.66` | `+10.34` | `+0.000397` | `+0.039375` |
| `EXP14b` | `+0.002299` | `-2.4` | `-359.55` | `+0.45` | `-0.014085` | `+0.026862` |
| `EXP14c` | `+0.001724` | `-1.8` | `-235.15` | `+34.85` | `+0.023346` | `+0.022964` |

## Writing notes

- `EXP14` is a positive line overall relative to `22.01`.
- `EXP14b` is the strongest of the three variants on the main metrics.
- The gains are moderate rather than dramatic, so `EXP14` should be written as a supportive mechanism result, not as the main headline.
- `PlanChurn` is higher for all three variants in `22.03`, consistent with the broader Week 4 trade-off picture.
