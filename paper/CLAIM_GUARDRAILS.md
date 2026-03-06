# Claim Guardrails

This file defines what the paper can safely claim based on the completed `22.03` reruns and the verified `22.01` comparisons.

## Claims that are safe

1. `EXP04` is the strongest main-matrix stressed configuration.
- Supported by `EXP01`, `EXP03`, `EXP04`, `EXP09`.
- Safe wording: dynamic compute plus RiskGate outperforms the stressed baseline on service and penalized cost.

2. Proactive control dominates greedy on paper-critical metrics.
- Supported by proactive vs greedy comparisons for `EXP01` and `EXP04`.
- Safe wording: greedy reduces raw cost only by failing substantially more orders.

3. The main-matrix sweep conclusions from `22.01` broadly survive in `22.03`.
- Supported by `EXP06`, `EXP07`, `EXP08`, `EXP10`, `EXP11`.
- Safe wording: the frontier shape and boundary direction remain stable after the rebuild.

4. `EXP11` supports a real ROI curve rather than monotone "more compute is always better".
- Safe wording: `60s+` is where the rebuilt pipeline starts to outperform `22.01`; `30s` is not a win.

5. Churn is the main cost of the stronger `22.03` policies.
- Safe wording: better service and penalized cost often come with higher `plan_churn`.

6. The learning-augmented line has selective, not universal, benefits.
- Supported by `EXP13a`, `EXP13b`, `EXP14`, `EXP15c`.
- Safe wording: the strongest evidence comes from `EXP13a`, `EXP14b`, and selected `EXP15c` conditions.

## Claims that must be softened

1. `EXP03` is not a null result.
- Do not write: RiskGate-only is ineffective.
- Write instead: RiskGate-only has a positive but smaller effect than the full coupled `EXP04` design.

2. `EXP05` is not a headline positive result.
- Do not write: allowing three trips clearly breaks the bottleneck.
- Write instead: the additional trip allowance has only weak marginal effect in the current setting.

3. `EXP11` is not uniformly stronger than `22.01`.
- Do not write: the rebuilt system dominates at every time limit.
- Write instead: the rebuilt system improves medium and high budgets, but not the tightest `30s` setting.

4. `EXP12` is not a positive headline.
- Do not write: the learned allocator line clearly improves on `22.01`.
- Write instead: `EXP12` lowers raw operating cost but underperforms on service, failures, penalized cost, and churn.

5. `EXP13b` is not universally stronger.
- Write it as a conditional gain, especially at higher ratios.

6. `EXP15c` is not universal robustness dominance.
- Write it as selective robustness: stronger in several hard `shift_-2` / high-ratio conditions, weaker around `shift_0` / `ratio_0.59`.

## Claims to avoid entirely

1. Avoid any statement that all learning-augmented variants dominate `22.01`.
2. Avoid any statement that more compute always improves outcomes.
3. Avoid any statement that lower raw cost alone means a better policy.
4. Avoid any statement that churn is an implementation artifact; the experiments now show it is a real trade-off axis.

## Recommended chapter-level headline

- Chapters 5-8: a stronger proactive control policy improves service and penalized cost under stress, but with higher churn.
- Chapter 9: learning augmentation helps in specific allocation/control regimes, with `EXP13a` and `EXP14b` as the clearest positive results.
