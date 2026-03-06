# Raw Data Intake (2026-03-05)

## 说明
本次 22.03 不迁移 22.01 的历史数据结果。
我们只迁移了用于真实路网计算的处理后矩阵。

## 已迁移的数据
- 路网矩阵：`data/processed/vrp_matrix_latest/`
- 基准订单集：`data/processed/multiday_benchmark_herlev.json`

## 原始数据
- 原始 Excel：`data/raw/RangeOfDaysSimulationDataTemplate - Test Data 001.xlsx`

## 数据质量备注
- 旧版实验使用欧氏距离近似，已弃用。
- 22.03 统一使用 OSRM 路网矩阵作为距离与时间基准。
