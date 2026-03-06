# Architecture

## 层次结构
- 入口与编排：`scripts/`（实验、审计、预检查、发布）
- 核心算法：`code/`（simulation, solvers, allocator, experiments）
- 兼容包名：`src/`（通过 `src/__init__.py` 将 `src.*` 映射到 `code/`）
- 论文与公式：`paper/`
- 数据：`data/raw`（只读）, `data/processed`（可复现产物）
- 结果与审计：`data/results`, `data/audits`

## 数据流
1. 原始数据进入 `data/raw`（不覆盖历史）
2. 处理后产物进入 `data/processed`
3. 实验运行读取 `data/processed` 并输出到 `data/results`
4. 审计与汇总写入 `data/audits`

## 计算矩阵
- 路网矩阵采用 OSRM 生成并存于 `data/processed/vrp_matrix_latest/`。
- 所有实验应使用该矩阵，禁止回退到欧氏距离近似。
