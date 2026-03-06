# EXP13 Aggregate Table

Source data:
- `22.03thesis/data/results/EXP13/EXP13a/`
- `22.03thesis/data/results/EXP13/EXP13b/`
- `22.01thesis/data/results/EXP13/EXP13a/`
- `22.01thesis/data/results/EXP13/EXP13b/`

Canonical `EXP_EXPxx` entry points:
- `22.03thesis/data/results/EXP_EXP13/EXP13a/`
- `22.03thesis/data/results/EXP_EXP13/EXP13b/`

Note: `22.01` contains duplicate reruns for some `crunch_d5_d10` seeds. For the comparison below, the newest result per seed was retained.

## Table A. Overall aggregate (`22.03`, mean)

| Variant | n | Service Rate | Failed Orders | Penalized Cost | Raw Cost | Cost/Order | Plan Churn |
|---|---:|---:|---:|---:|---:|---:|---:|
| `EXP13a` | `70` | `0.979639` | `21.257143` | `9223.10` | `6034.53` | `5.900410` | `0.495388` |
| `EXP13b` | `70` | `0.978175` | `22.785714` | `9678.22` | `6260.36` | `6.130712` | `0.474604` |

## Table B. `22.03 - 22.01` overall

| Variant | Delta Service Rate | Delta Failed Orders | Delta Penalized Cost | Delta Raw Cost | Delta Cost/Order | Delta Plan Churn |
|---|---:|---:|---:|---:|---:|---:|
| `EXP13a` | `+0.002627` | `-2.742857` | `-451.31` | `-39.88` | `-0.055086` | `+0.007705` |
| `EXP13b` | `+0.000055` | `-0.057143` | `-112.69` | `-104.12` | `-0.101775` | `+0.029835` |

## Table C. Scenario-level `22.03 - 22.01`

### `EXP13a`

| Scenario | Delta Service Rate | Delta Failed Orders | Delta Penalized Cost | Delta Raw Cost | Delta Plan Churn |
|---|---:|---:|---:|---:|---:|
| `crunch_d3_d6` | `+0.000096` | `-0.1` | `+16.33` | `+31.33` | `+0.011478` |
| `crunch_d5_d10` | `+0.004310` | `-4.5` | `-763.28` | `-88.28` | `-0.000262` |
| `crunch_d6_d9` | `-0.002682` | `+2.8` | `+281.80` | `-138.20` | `+0.041037` |
| `ratio_0.55` | `+0.004023` | `-4.2` | `-688.32` | `-58.32` | `-0.009127` |
| `ratio_0.59` | `+0.004885` | `-5.1` | `-806.02` | `-41.02` | `+0.009593` |
| `ratio_0.6` | `+0.003257` | `-3.4` | `-512.05` | `-2.05` | `+0.007287` |
| `ratio_0.65` | `+0.004502` | `-4.7` | `-687.61` | `+17.39` | `-0.006070` |

### `EXP13b`

| Scenario | Delta Service Rate | Delta Failed Orders | Delta Penalized Cost | Delta Raw Cost | Delta Plan Churn |
|---|---:|---:|---:|---:|---:|
| `crunch_d3_d6` | `-0.000192` | `+0.2` | `+39.07` | `+9.07` | `+0.083755` |
| `crunch_d5_d10` | `-0.002969` | `+3.1` | `+388.68` | `-76.32` | `+0.046980` |
| `crunch_d6_d9` | `+0.000575` | `-0.6` | `-257.27` | `-167.27` | `+0.012462` |
| `ratio_0.55` | `-0.002682` | `+2.8` | `+333.10` | `-86.90` | `+0.026806` |
| `ratio_0.59` | `-0.002299` | `+2.4` | `+255.38` | `-104.62` | `+0.022426` |
| `ratio_0.6` | `+0.004023` | `-4.2` | `-774.07` | `-144.07` | `+0.016323` |
| `ratio_0.65` | `+0.003927` | `-4.1` | `-773.69` | `-158.69` | `+0.000095` |

## Writing notes

- `EXP13a` is clearly stronger than `22.01` overall. The gains are broad-based and largest on `crunch_d5_d10` and the ratio scenarios.
- `EXP13b` is weaker as a headline claim. It improves the high-ratio scenarios (`0.6`, `0.65`) but regresses on several lower-ratio and crunch settings.
- Chapter 9 still stands if the main claim is phrased around `EXP13a` and around conditional gains rather than universal dominance.
- The current evidence does **not** support writing `EXP13b` as uniformly better than `22.01`.
