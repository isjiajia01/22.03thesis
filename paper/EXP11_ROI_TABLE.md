# EXP11 ROI Table

Source data:
- `22.03thesis/data/results/EXP_EXP11/`
- `22.01thesis/data/results/EXP_EXP11/`

## Table A. EXP11 ROI summary (`22.03`, mean ± sd)

| Endpoint | Service Rate | Failed Orders | Penalized Cost | Raw Cost | Cost/Order | Plan Churn |
|---|---:|---:|---:|---:|---:|---:|
| `risk_False_tl_30` | `0.975096 ± 0.000000` | `26.0 ± 0.0` | `10513.07 ± 0.00` | `6613.07 ± 0.00` | `6.496136 ± 0.000000` | `0.569444 ± 0.000000` |
| `risk_False_tl_60` | `0.975192 ± 0.000953` | `25.9 ± 0.99` | `10200.23 ± 167.40` | `6315.23 ± 66.78` | `6.202966 ± 0.066281` | `0.578125 ± 0.005490` |
| `risk_False_tl_120` | `0.976054 ± 0.000000` | `25.0 ± 0.0` | `9818.53 ± 148.83` | `6068.53 ± 148.83` | `5.955376 ± 0.146058` | `0.516429 ± 0.026453` |
| `risk_False_tl_300` | `0.975862 ± 0.000606` | `25.2 ± 0.63` | `9814.90 ± 25.81` | `6034.90 ± 110.90` | `5.923481 ± 0.105411` | `0.561989 ± 0.004661` |
| `risk_True_tl_30` | `0.974521 ± 0.000925` | `26.6 ± 0.97` | `10543.02 ± 48.54` | `6553.02 ± 96.84` | `6.440870 ± 0.089149` | `0.567361 ± 0.003354` |
| `risk_True_tl_60` | `0.975287 ± 0.000989` | `25.8 ± 1.03` | `10209.38 ± 163.17` | `6339.38 ± 11.08` | `6.226075 ± 0.016082` | `0.579167 ± 0.005379` |
| `risk_True_tl_120` | `0.975766 ± 0.001281` | `25.3 ± 1.34` | `9807.55 ± 175.80` | `6012.55 ± 132.51` | `5.902106 ± 0.126265` | `0.533800 ± 0.029687` |
| `risk_True_tl_300` | `0.975862 ± 0.000606` | `25.2 ± 0.63` | `9831.86 ± 56.91` | `6051.86 ± 135.19` | `5.940117 ± 0.129421` | `0.561593 ± 0.004115` |

## Table B. `22.03 - 22.01`

| Endpoint | Delta Service Rate | Delta Failed Orders | Delta Penalized Cost | Delta Raw Cost | Delta Plan Churn |
|---|---:|---:|---:|---:|---:|
| `risk_False_tl_30` | `-0.001916` | `+2.0` | `+360.04` | `+60.04` | `+0.027671` |
| `risk_False_tl_60` | `+0.002107` | `-2.2` | `-225.17` | `+104.83` | `+0.032977` |
| `risk_False_tl_120` | `-0.000287` | `+0.3` | `-116.87` | `-161.87` | `+0.011298` |
| `risk_False_tl_300` | `+0.001245` | `-1.3` | `-176.52` | `+18.48` | `+0.020119` |
| `risk_True_tl_30` | `-0.002490` | `+2.6` | `+390.70` | `+0.70` | `+0.025588` |
| `risk_True_tl_60` | `+0.002203` | `-2.3` | `-217.36` | `+127.64` | `+0.034725` |
| `risk_True_tl_120` | `-0.000287` | `+0.3` | `-181.90` | `-226.90` | `+0.016763` |
| `risk_True_tl_300` | `+0.001533` | `-1.6` | `-153.72` | `+86.28` | `+0.018516` |

## Writing notes

- The ROI curve improves substantially from `30s` to `60s` and reaches a broad plateau by `120s`-`300s`.
- Relative to `22.01`, the `22.03` pipeline is not uniformly better at ultra-low budget: both `30s` endpoints are worse.
- For `60s` and `300s`, `22.03` is better on service and penalized cost.
- Around `120s`, the result is mixed: penalized cost improves, but service rate is roughly flat/slightly worse.
- `PlanChurn` is consistently higher in `22.03`, which supports the Week 4 churn trade-off storyline rather than contradicting it.
