# 实验清单与复现计划

本文件定义 22.03 需要重跑的实验矩阵，并记录实验清理与复现状态。

## 必跑实验矩阵（来自论文实验设计）

核心实验（主结论）：
- `EXP00` BAU 基线（无压力）
- `EXP01` Crunch 基线（单波压力，无风险门）
- `EXP02` 静态高算力上界
- `EXP03` 仅风险门（不切换算力）
- `EXP04` 动态算力 + 风险门（核心贡献）

消融实验：
- `EXP09` 风险模型消融

敏感性分析：
- `EXP05` 容量比 sweep
- `EXP06` 多趟 sweep
- `EXP07` 车队并行度 sweep
- `EXP08` 风险阈值敏感性
- `EXP10` 细粒度容量比 sweep
- `EXP11` 计算时限 sweep

## 运行方式（迁移完成后）
- 配置检查：`python -m scripts.cli run-exp --exp EXP01 --seed 1 --dry-run`
- 正式运行：先生成 HPC 脚本，再用 `bsub` 提交，不在登录节点直接跑。

## 数据要求
- 订单数据：`data/processed/multiday_benchmark_herlev.json`
- 路网矩阵：`data/processed/vrp_matrix_latest/`

## 清理规则
- 仅保留以上实验及其审计输出。
- 非论文实验、历史临时脚本、旧结果目录不迁移到 22.03。

## 学习增强链路（已恢复并按论文编号对齐）
- `EXP12` 离线 learned allocator
- `EXP13` 在线 bandit-augmented allocator（含 `EXP13a` / `EXP13b`）
- `EXP14` sparse fail-safe bandit（含 `EXP14a` / `EXP14b` / `EXP14c`）
- `EXP15a` 时序 shift 鲁棒性
- `EXP15b` 需求量与空间扰动鲁棒性
- `EXP15c` calendar leakage 诊断与修复
- 该链路不通过 `master_runner`，请使用 `code/experiments/`、`scripts/run_exp12*.sh` 与 `scripts.cli audit/publish` 等入口。
- 旧的 Greedy vs Proactive 对照不再占用 `EXP13` 编号；如需回看历史脚本，请视为 legacy analysis，而不是 22.03 主复现实验矩阵。

## 复现状态
- [ ] EXP00
- [ ] EXP01
- [ ] EXP02
- [ ] EXP03
- [ ] EXP04
- [ ] EXP05
- [ ] EXP06
- [ ] EXP07
- [ ] EXP08
- [ ] EXP09
- [ ] EXP10
- [ ] EXP11
- [ ] EXP12
- [ ] EXP13
- [ ] EXP14
- [ ] EXP15a
- [ ] EXP15b
- [ ] EXP15c
