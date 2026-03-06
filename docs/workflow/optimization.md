# Optimization Workflow

1. 阅读 `problem.md`，确认问题定义与数据路径。
2. 以 `paper/Chapters/06_experimental_design_and_auditing.tex` 为实验矩阵依据。
3. 使用 `scripts/cli.py` 运行实验与审计。
4. 所有实验必须使用 `data/processed/vrp_matrix_latest/` 路网矩阵。
5. 记录结果并更新 `experiments.md` 和 `docs/decisions.md`。
6. 清理失败或非论文实验的结果目录，只保留必要实验。
7. `run-exp` 仅覆盖 `EXP00`–`EXP11`；`EXP12`–`EXP15c` 走学习增强链路专用脚本。
8. 正式实验必须通过 HPC (`bsub`) 提交，登录节点只允许 `--dry-run`、脚本生成与文档维护。
9. 默认 `max_trips_per_vehicle = 2`，除非实验定义显式覆盖。

## 核心实验提交
- `python -m scripts.cli hpc-generate --all`
- `bsub < jobs/submit_exp00.sh`
- `bsub < jobs/submit_exp01.sh`
- `bsub < jobs/submit_exp02.sh`
- `bsub < jobs/submit_exp03.sh`
- `bsub < jobs/submit_exp04.sh`

## 汇总
- `python -m scripts.cli analyze`
- `python -m scripts.cli audit exp15c`
- `python -m scripts.cli audit exp21`
- `python -m scripts.cli publish exp13b`

## 学习增强实验运行
- `bash scripts/run_exp12.sh`
- `python code/experiments/exp13_bandit_allocator.py --seeds 10`
- `python code/experiments/exp14_sparse_failsafe.py --variant all --seeds 10`
- `python code/experiments/exp15_ood_evaluation.py --mode exp15a --ratio 0.59 --shift 0 --seeds 10`

## 结果命名与清理规则
- 结果目录必须使用实验 ID + 语义名称，不使用纯时间戳。
- 只保留论文矩阵实验与其审计产物。
- 失败实验必须立即删除对应输出目录，不保留半成品。
