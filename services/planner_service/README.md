# Planner service

当前服务是一个可复现实验切片：目标日默认使用本地 PolarData 覆盖的
`2025-02-15 12:00 UTC`，在单日栅格上运行 D* Lite 初始路径和 NSGA-III
三目标优化（风险、距离、航时）。

规划栅格固定为 `25,000 m x 25,000 m`。网格沿确定性海上走廊生成，单元
中心使用 WGS84，边界按测地线计算。每个单元同时保留原始环境值、五个风险
因子、综合风险、有效航速、可通行状态、数据质量和来源。

风、浪、雾不依赖本地 2 月/8 月文件来伪造其它月份，而是从 Open-Meteo
Archive/Marine 下载并缓存同一日的 `2017-2025` 年逐小时数据。某一年只要该日
任一小时超过阈值，就计为一次发生：风 `11.7 m/s`、有效波高 `5 m`、雾能见度
`<1000 m`（无能见度时使用 WMO 雾码 45/48）。每个因子按自身有效年份计算
`count / available_years`，缺测不会被算成零风险。

缓存目录为配置的 `PolarData/environment/planner/historical_frequency`，规划
返回值的 `metadata.historical_frequency` 包含阈值、次数、分母、来源和缺测信息。

由于当前本地风、浪、海流和海冰数据主要覆盖北极，规划器通过
`PlannerEnvironmentAdapter` 先使用真实 provider；对 provider 覆盖外的单元，
使用版本化的确定性 gap-fill 模型，并将每个字段标为 `quality=synthetic`、
来源标为 `planner-deterministic-gap-fill-v1`。未来接入全球 provider 时只需替换
该适配器，不需要修改 D* Lite、NSGA-III、API 或前端。

环境栅格接口：

- `GET /api/planner/grid/spec`：固定分辨率、字段、风险层和缺失数据策略。
- `POST /api/planner/grid/cell`：查询单个 25km 单元的环境数据、质量和来源。
- `POST /api/planner`：返回路线、轻量风险矩阵和 `plan_id`。
- `GET /api/planner/{plan_id}/grid`：返回该规划快照的完整栅格单元。
- `GET /api/planner/{plan_id}/grid/{cell_id}`：返回单个栅格的环境、风险、质量和来源。
