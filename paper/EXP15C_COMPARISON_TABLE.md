# EXP15c Aggregate Table

Source data:
- `22.03thesis/data/results/EXP15/EXP15c/`
- `22.01thesis/data/results/EXP15/EXP15c/`

Notes:
- `22.03` currently contains `20` conditions x `10` seeds plus one earlier smoke run, so the canonical aggregate uses the named condition directories only.
- Comparison below is restricted to overlapping condition names present in both `22.03` and `22.01`.

## Key takeaways

- `shift_-2` high-ratio conditions are substantially better in `22.03` than in `22.01`.
- `shift_0` conditions around `ratio_0.59` are worse in `22.03` on service and penalized cost.
- The OOD line is therefore publishable as a conditional robustness result, not as universal dominance.
- This supports Chapter 9 if the headline is narrowed to `EXP13a` + selective `EXP15c` robustness wins.

## Representative `22.03 - 22.01` deltas

| Condition | Delta Service Rate | Delta Failed Orders | Delta Penalized Cost | Delta Raw Cost | Delta Plan Churn |
|---|---:|---:|---:|---:|---:|
| `full_ratio_0.65_shift_-2` | `+0.012165` | `-12.7` | `-2130.51` | `-225.51` | `-0.023808` |
| `no_calendar_aug_ratio_0.65_shift_-2` | `+0.012739` | `-13.3` | `-1884.35` | `+110.65` | `-0.014075` |
| `no_calendar_ratio_0.65_shift_-2` | `+0.011782` | `-12.3` | `-2168.79` | `-323.79` | `-0.035726` |
| `no_ratio_ratio_0.65_shift_-2` | `+0.012548` | `-13.1` | `-2290.41` | `-325.41` | `-0.032853` |
| `full_ratio_0.59_shift_0` | `-0.001628` | `+1.7` | `+279.91` | `+24.91` | `+0.036619` |
| `no_calendar_aug_ratio_0.59_shift_0` | `-0.002778` | `+2.9` | `+326.93` | `-108.07` | `-0.024234` |
| `no_calendar_ratio_0.59_shift_0` | `-0.002299` | `+2.4` | `+307.87` | `-52.13` | `+0.038706` |
| `no_ratio_ratio_0.59_shift_0` | `-0.003544` | `+3.7` | `+462.48` | `-92.52` | `+0.044248` |
