# AGENTS.md

## Project Type
Hybrid project combining:

- software engineering
- optimization models
- data experiments

## Work Modes
Choose mode by task intent:

- If task mentions API/feature/bug/test/refactor, use **Software mode**.
- If task mentions model/formulation/solver/heuristic/experiment, use **Optimization mode**.
- If ambiguous, ask whether the primary goal is software delivery or model/experiment research.

## Workflows

### 1) Software development
Follow: `docs/workflow/software.md`

### 2) Optimization research
Follow: `docs/workflow/optimization.md`

## Folder Responsibilities

- `src/app`: software logic
- `src/optimization`: optimization models/solvers/heuristics
- `src/algorithms`: general algorithm implementations
- `model`: mathematical formulations and solver design notes
- `data/raw`: source datasets (read-only)
- `data/processed`: generated data artifacts
- `tests`: automated tests
- `docs`: architecture, workflow, decisions, literature

## Coding Rules
Prefer languages:

- Python
- TypeScript

Preferred libraries (as needed):

- numpy
- pandas
- scipy
- OR-Tools
- pyomo

## Safety Rules

- Never modify `data/raw`.
- Never remove tests to make failures disappear.
- Never break public API without updating docs and tests.
- Official experiment runs must go through HPC (`bsub` / LSF), not direct execution on the login node.
- Default fleet policy is `max_trips_per_vehicle = 2` unless an experiment explicitly overrides it.
- Failed experiment outputs must be deleted instead of being left in `results/` or `data/results/`.

## Template Evolution Rules

- `docs/workflow.md` and `docs/decisions.md` are append-first by default.
- Per task, add at most **1-3** template patch items.
- After each task, if a reusable pattern emerges, append a **Template Patch** to `docs/workflow.md`.

## Template Patch Format

```md
## Template Patch (YYYY-MM-DD)
Change:
- [Add/Modify/Remove] Rule/Step/Convention: ...

Reason:
- ...

Applies to:
- Software | Optimization | Both

Verification:
- How to validate this rule works

Links:
- Files/paths that motivated this patch
```
