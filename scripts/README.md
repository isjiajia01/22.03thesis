## `scripts/` 目录说明

`scripts/` 是本仓库的 **实验与工具入口层**，负责：

- 启动/配置实验（runner）
- 对结果进行审计、聚合和可视化（analysis / audit / publish）
- 运行预检查与烟雾测试（preflight / smoke）
- 驱动 HPC 提交脚本的生成（runner + hpc）

为兼顾历史脚本和新人可读性，本目录采用“**分层子包 + 顶层兼容 wrapper**” 模式。

---

## 子目录与角色

- `analysis/`：**分析与聚合**
  - 典型命名：`aggregate_*.py`、`analysis_pack.py`、`generate_demo_pack.py`
  - 示例：
    - `analysis/aggregate_exp15b.py`：EXP15b 指标聚合
    - `analysis/analysis_pack.py`：全 EXP 指标、交通灯、配对统计
    - `analysis/generate_demo_pack.py`：生成 demo 图与 one‑pager

- `audit/`：**审计与验证**
  - 典型命名：`audit_*.py`、`*_audit.py`
  - 示例：
    - `audit/audit_exp21.py`：EXP21 审计入口
    - `audit/audit_exp15c.py`：EXP15c 审计入口

- `runner/`：**实验定义与运行器 / HPC 工具**
  - 典型命名：`*_runner.py`、`generate_*jobs.py`
  - 示例：
    - `runner/master_runner.py`：主运行器（EXP00–EXP11）
    - `runner/generate_hpc_jobs.py`：生成 LSF 提交脚本

- `preflight/`：**预检查 / 烟雾测试**
  - 当前仅包含 `__init__.py`，以下脚本仍在顶层，但逻辑上归属于此类：
    - `hpc_acceptance_test.py`
    - `local_smoke_test.py`
    - `regression_test.py`
    - `smoke_test_phase_a.py`
    - `preflight_check.py` / `pre_hpc_validation.py` / `pre_hpc_check.sh`

- `publish/`：**发表与论文辅助**
  - 典型命名：`publish_*.py`、`generate_*summary.py`
  - 示例：
    - `publish/publish_exp13b_final_decision.py`：EXP13b 最终决策与 publication bundle
    - `generate_publication_summary.py`：EXP15c publication summary JSON（仍在顶层）

- `legacy/`：**旧入口与兼容脚本**
  - 典型内容：
    - `master_runner_old.py`
    - `master_runner.py.backup`
    - 计划迁入：`run_exp12*.sh` 及类似一次性脚本

---

## 顶层 Python 文件的分类规则

在 `scripts/` 根目录下，Python 脚本分为两类：

1. **兼容 wrapper（推荐使用新的包路径或 CLI）**
2. **仍在演进中的一等入口（后续可按需下沉到子包）**

### 1. 兼容 wrapper（已迁移实现到子包）

以下文件的主要逻辑已经迁入对应子包，原位置只保留一个小 wrapper，用于兼容历史调用：

| 旧路径                            | 新推荐入口                                      |
|-----------------------------------|------------------------------------------------|
| `scripts/audit_exp21.py`         | `python -m scripts.audit.audit_exp21`         |
| `scripts/audit_exp15c.py`        | `python -m scripts.audit.audit_exp15c`        |
| `scripts/publish_exp13b_final_decision.py` | `python -m scripts.publish.publish_exp13b_final_decision` |
| `scripts/master_runner.py`       | `python -m scripts.runner.master_runner`      |
| `scripts/generate_hpc_jobs.py`   | `python -m scripts.runner.generate_hpc_jobs`  |

所有这些 wrapper 在调用时会：

- 打印 `FutureWarning`，提示新路径或 CLI 用法
- 使用 `runpy.run_module(...)` 转发到对应的包内实现

### 2. 顶层仍在使用的脚本

这些脚本还未完全下沉到子包，但可以通过 CLI 或直接调用使用：

- 分析 / 审计相关：
  - `analysis_pack.py`（实现已复制到 `analysis/analysis_pack.py`，顶层可视为兼容入口）
  - `generate_demo_pack.py`（`analysis/generate_demo_pack.py` 提供新的模块入口）
  - `completion_audit.py`、`full_audit.py`、`supplementary_audit.py`、`audit_greedy_vs_proactive.py`、`exp02_audit.py`
  - `audit_greedy_vs_proactive.py` 与 `audit_greedy_completion.py` 属于 legacy Greedy 对照分析，不代表论文中的 `EXP13`
- 预检查 / 烟雾测试：
  - `hpc_acceptance_test.py`
  - `local_smoke_test.py`
  - `regression_test.py`
  - `smoke_test_phase_a.py`
  - `pre_hpc_check.sh`
  - `pre_hpc_validation.py`
  - `preflight_check.py`
- 发表辅助：
  - `generate_publication_summary.py`

后续如果要进一步“完全分层”，可以将上述脚本移动到对应子目录（`analysis/`、`audit/`、`preflight/`、`publish/`），并在原路径保留兼容 wrapper（模式同上）。

---

## 推荐命名风格

- **analysis 层**
  - `aggregate_<exp>.py`：对特定实验（或一组实验）进行聚合输出
  - `<topic>_pack.py`：批量生成多种审计/统计/图表的“打包脚本”
  - `generate_*_pack.py`：生成 demo / publication 等特定用途打包输出

- **audit 层**
  - `audit_<exp>.py`：对应某个 EXP 的主审计入口
  - `<scope>_audit.py`：面向更大范围的审计（例如全仓、单实验族）

- **runner 层**
  - `<role>_runner.py`：实验运行器（如 `master_runner.py`）
  - `generate_*jobs.py`：统一负责生成 HPC 作业脚本

- **preflight 层**
  - `<context>_acceptance_test.py`：某一路径的验收测试
  - `preflight_check.py` / `pre_hpc_*`：在 HPC 作业开始前运行的依赖/模型检查

- **publish 层**
  - `publish_<exp>_*.py`：生成某个实验的最终发表/论文包
  - `generate_*summary.py`：生成 JSON/CSV 风格的摘要，供论文引用

- **legacy 层**
  - 原路径尽量通过 **小 wrapper** 提示用户迁移，例如：
    - `run_exp12_*.sh` → 调用 `scripts/legacy/...` 中的真实实现，并打印“LEGACY ONLY” 提示

---

## 快速使用备忘

- **首选入口：统一 CLI**
  - `python -m scripts.cli run-exp --exp EXP01 --seed 1 --dry-run`
  - `python -m scripts.cli audit exp21`
  - `python -m scripts.cli publish exp13b`
  - `python -m scripts.cli smoke phase-a`
  - `python -m scripts.cli hpc-generate --all`

- **编号约定：**
  - `run-exp` 只用于主实验矩阵 `EXP00`–`EXP11` 的配置检查与 HPC 作业负载
  - 论文中的 `EXP12`–`EXP15c` 属于学习增强链路，入口在 `code/experiments/` 与相关 shell / audit / publish 脚本

- **需要直接调用具体脚本时，优先使用包路径：**
  - `python -m scripts.runner.master_runner ...` 仅在 LSF 作业环境中执行正式实验
  - `python -m scripts.audit.audit_exp15c`
  - `python -m scripts.analysis.analysis_pack`
  - `python -m scripts.publish.publish_exp13b_final_decision`

- **历史命令仍然可用（wrapper 会打印弃用警告），例如：**
  - `python scripts/master_runner.py --exp EXP04 --seed 1`
  - `python scripts/audit_exp21.py`
