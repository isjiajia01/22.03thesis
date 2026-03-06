# Chapter Rewrite Plan

This file is the rewrite order for the cleared LaTeX body.

## First pass: write only what is already locked

### Chapter 3: Problem Setting
Use:
- `22.02thesis/model.md`
- `22.03thesis/docs/decisions.md`
- `22.03thesis/docs/workflow.md`

Write:
- rolling-horizon setting
- flexible-day orders
- warehouse/gate constraints
- daily trip cap assumption (`2` trips by default)
- compute-budgeted decision process

### Chapter 4: Architecture and Implementation
Use:
- `22.03thesis/scripts/runner/master_runner.py`
- `22.03thesis/scripts/runner/generate_hpc_jobs.py`
- `22.03thesis/code/simulation/rolling_horizon_integrated.py`
- `22.03thesis/scripts/__init__.py`

Write:
- simulator pipeline
- policy layer vs solver layer
- HPC-only execution policy
- artifact dumping and auditability

### Chapter 5: Policies and Gates
Use:
- `22.03thesis/paper/THESIS_EXPERIMENT_WRITING_MAP.md`
- proactive vs greedy numbers already locked there

Write:
- greedy baseline
- proactive policy
- RiskGate
- dynamic compute logic
- end this chapter with the proactive-vs-greedy figure

### Chapter 6: Experimental Design and Auditing
Use:
- `22.03thesis/experiments.md`
- `22.03thesis/scripts/experiment_definitions.py`
- `22.03thesis/paper/FIGURE_BUILD_RECIPES.md`

Write:
- experiment numbering
- seeds and sweep dimensions
- HPC submission rules
- failed-run cleanup rule
- exact artifact schema

### Chapter 7: Results
Use these paper-facing tables first:
- `22.03thesis/paper/EXP11_ROI_TABLE.md`
- `22.03thesis/paper/EXP13_COMPARISON_TABLE.md`
- `22.03thesis/paper/EXP14_COMPARISON_TABLE.md`
- `22.03thesis/paper/EXP15C_COMPARISON_TABLE.md`
- `22.03thesis/paper/THESIS_EXPERIMENT_WRITING_MAP.md`

Write in this order:
1. core baseline table (`EXP00/01/03/04/09`)
2. proactive vs greedy
3. `EXP06` boundary
4. `EXP07` collapse
5. `EXP08` threshold robustness
6. `EXP10` phase curve
7. `EXP11` ROI curve
8. brief note that `EXP05` is a weak-effect sensitivity result

### Chapter 8: Discussion and Limitations
Write around three tensions:
- penalized cost vs raw cost
- compute budget vs outcome quality
- service quality vs plan churn

### Chapter 9: Learning-Augmented Allocation
Use in this order:
- `22.03thesis/paper/CLAIM_GUARDRAILS.md`
- `22.03thesis/paper/EXP13_COMPARISON_TABLE.md`
- `22.03thesis/paper/EXP14_COMPARISON_TABLE.md`
- `22.03thesis/paper/EXP15C_COMPARISON_TABLE.md`

Write in this order:
1. `EXP12` as a negative/weak baseline
2. `EXP13a` as main positive learning result
3. `EXP13b` as conditional gain
4. `EXP14b` as supportive mechanism result
5. `EXP15c` as selective OOD robustness result
6. explicitly say the learning line is not uniformly dominant

## Second pass: convert markdown locks into LaTeX tables and figures

Build first:
- main matrix table
- proactive vs greedy figure
- `EXP10` phase figure
- `EXP11` ROI figure
- one Chapter 9 comparison table (`EXP13` + `EXP14`)

## Third pass: only after the prose is stable

Then restore and tighten:
- introduction contribution bullets
- discussion wording
- conclusion claims

Do not start with Chapter 1. Start with Chapters 3-9, then return to the introduction.
