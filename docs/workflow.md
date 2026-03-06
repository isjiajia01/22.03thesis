# Workflow (living document)

## Defaults
- 优先小改动。
- 复用已有结构与脚本。
- 记录关键假设与决策。
- 实验必须可复现（输入、参数、矩阵版本、输出路径）。

## Commands
- Tests: `python3 -m pytest -q`

## Template Patch Log

## Template Patch (2026-03-05)
Change:
- [Add] Rule: 论文实验矩阵以 `paper/Chapters/06_experimental_design_and_auditing.tex` 为准。
- [Add] Rule: 路网距离统一使用 OSRM 矩阵，禁止欧氏距离近似。

Reason:
- 保证实验与论文一致，确保可复现与结果可信度。

Applies to:
- Optimization

Verification:
- 检查实验运行是否读取 `data/processed/vrp_matrix_latest/`。
- 检查 `experiments.md` 与论文矩阵一致。

Links:
- problem.md
- experiments.md
- docs/workflow/optimization.md

## Template Patch (2026-03-05)
Change:
- [Add] Rule: 正式实验必须通过 HPC (`bsub` / LSF) 提交，登录节点只允许 `--dry-run`、脚本生成与文档维护。
- [Add] Rule: 默认 `max_trips_per_vehicle = 2`，除非实验定义显式覆盖。
- [Add] Rule: 失败实验输出目录必须立即删除，不保留半成品。

Reason:
- 统一实验执行环境，固定车辆日内两趟约束，并避免残缺结果污染审计。

Applies to:
- Optimization

Verification:
- 非 LSF 环境执行 `python -m scripts.runner.master_runner --exp EXP00 --seed 1` 应被拒绝。
- 生成的 HPC 脚本应包含 `export VRP_MAX_TRIPS_PER_VEHICLE=2`。
- 失败运行后不应遗留对应结果目录。

Links:
- scripts/runner/master_runner.py
- scripts/runner/generate_hpc_jobs.py
- docs/workflow/optimization.md
