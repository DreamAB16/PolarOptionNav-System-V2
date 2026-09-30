# WEB 项目只读技术审计报告

审计范围：仓库当前提交内容、README/配置、`core`、`services`、`backend`、`frontend`、离线数据工具、船舶资料和测试。审计期间未修改现有业务代码；本文件是本轮唯一新增文件。

结论先行：本项目当前是“环境感知与驾驶台显示平台”，不是已经实现的局部辅助导航规划器。环境数据适配、时间感知查询、地图图层、基础水深安全判断和静态船舶资料已有可运行实现；Planner 明确是 mock，RG-MPAO*、CF-JRS、RCOS、EdgeEvaluator、稀疏时变航路图、ETA/STW/SOG/COG 联合计算、实时船位闭环均未实现。

## 1. 项目总体结构

| 目录/模块 | 作用 |
|---|---|
| `frontend/` | Vue 3 + TypeScript + OpenLayers 驾驶台展示壳；地图、环境图层、时间轴、船舶/任务/规划面板。 |
| `backend/app/` | FastAPI 应用入口和 `/api` 路由组合。 |
| `services/environment_service/` | 水深、海冰、风、流、浪 provider；统一环境查询、网格单元、时间管理、切片输出。 |
| `services/chart_service/` | GeoPackage 海岸线读取并转 GeoJSON。 |
| `services/vessel_service/` | 静态船舶资料加载、mock 船位状态、Draft + UKC 判断。 |
| `services/planner_service/` | 规划服务边界；当前只返回 mock `RouteResult`。 |
| `core/` | Pydantic 数据契约、NetCDF 辅助和船舶 profile 模型。 |
| `config/` | 应用设置和外部环境数据根目录映射。 |
| `data/` | GeoPackage 海岸线、船舶 JSON；大体量环境数据在配置的外部 PolarData 根目录。 |
| `tools/data_tools/` | 独立下载、检查、预处理脚本，不被运行时导入。 |
| `backend/tests/`、`frontend/src/**/*.test.ts` | 后端 provider/API/服务测试和前端服务/地图 smoke tests。 |
| `docs/` | 项目结构、数据流和本审计。 |

依赖方向基本为 `frontend -> backend API -> services -> providers/data`。环境查询层与地图显示边界清楚；规划器没有算法实现，也没有与 UI 耦合。

## 2. 当前技术栈

- 前端：Vue 3、TypeScript、Vite、Vue TSC、Vitest、OpenLayers 10、Proj4。
- 后端：Python、FastAPI、Uvicorn、Pydantic v2、Pydantic Settings、HTTPX、pytest。
- 科学/空间计算：NumPy、xarray、netCDF4、rasterio、pyproj、Shapely、Pillow。
- 数据格式：NetCDF/NetCDF4、GeoTIFF、GeoPackage/SQLite、GeoJSON、JSON、PNG XYZ tiles。
- 地图：OpenLayers；全球显示使用 EPSG:3857，北极原生产品使用 EPSG:3413，服务契约位置为 WGS84/EPSG:4326。
- 数据源适配：GEBCO 水深、Copernicus Marine neXtSIM-F 海冰、CARRA2 风、TOPAZ5 表层流、Arctic WAM 海浪；ERA5 仅为兼容下载工具后备，不是默认 CARRA2 provider。
- 部署：本地 Python venv + `uvicorn ... --reload`，前端 `npm run dev`；没有 Docker、任务队列、数据库迁移或生产部署配置。运行时数据根目录由 `POLAR_ENVIRONMENT_DATA_ROOT`/`config/environment.yaml` 指向外部目录。

## 3. 当前环境数据能力

### 3.1 总体判断

`EnvironmentTimeManager` 只维护一个 UTC simulation time 和一个名为 `forecast_time` 的字段；provider 自己把请求时间匹配到文件/时间轴。仓库没有 Truth / Forecast / Belief 三层对象、观测融合、质量等级/不确定性传播或 scenario belief。统一响应保留 `requested_time`、各源 `matched_time` 和 `source`，但没有正式的 `source_time`、`valid_time`、quality、uncertainty 字段。

统一查询是“每源独立失败隔离 + 最近时间/源内插值”，不是可供规划器直接消费的未来世界模型。请求时间可以显式传入任意时刻；provider通常选最近可用时刻，没有统一最大时间偏差阈值，因此规划器若未来接入必须先补时间语义和数据泄露规则。

### 3.2 各数据源

| 数据 | 来源/文件 | 空间/时间 | 变量与坐标 | 时间/空间处理 | 缓存与质量 |
|---|---|---|---|---|---|
| 水深 | `GEBCO_2026_sub_ice.nc`，NetCDF4；可选预处理 GeoTIFF | 全球规则经纬网，文档记录 15 arc-sec；无时间维度 | `lat/lon/elevation`，EPSG:4326，elevation 米、正向上 | 最近网格点；负高程转正向下 depth，陆地/NoData 变为 0；北极 GeoTIFF 为 EPSG:3413、1 km 默认 | Dataset 进程内懒加载；点和 tile 有 LRU；只有 `source`/timestamp，无观测质量/不确定性 |
| 海冰 | Copernicus Marine neXtSIM-F；`arctic_ice_YYYYMMDD.nc`，处理后 NetCDF4 | 原始规则经纬网；下载脚本按日文件、产品小时数据；UI 场景窗口按小时播放 | `siconc`、`sithick`、`siconc_my`、`siconc_young`、`vxsi/vysi`、`sisnthick`、`time/lat/lon`，CF standard_name 自动发现 | 文件按日期最近匹配；时间轴最近点；点查询最近空间网格；切片使用双线性/掩码最近有效单元，全球经度可周期处理 | 数据集/切片/tile LRU；返回 matched timestamp、source；没有 quality/uncertainty，不能证明 forecast cutoff |
| 风 | 默认 CARRA2 月度配对 NetCDF；后备 RealWind/待定 provider | CARRA2 curvilinear 约 2.5 km，3 小时 | `si10`、`wdir10`、二维 latitude/longitude、`valid_time`；后备使用 `u10/v10` | CARRA2 最近时间 + 最近曲线网格点；方向按 meteorological wind-from 真北顺时针转换为 u/v（向量 toward）；RealWind 对规则网格做双线性 | 月文件懒加载，最多 2 个时间 slice；保留 matched time/source；无质量/不确定性与统一最大时差 |
| 海流 | Copernicus Marine TOPAZ5 原始投影网格 NetCDF | 约 6.25 km，小时级/每日文件窗口 | `vxo/vyo` 原始网格分量，坐标/投影元数据 | 读取最近时间；空间双线性；依据网格经纬度局部旋转到 geographic east/north；输出 `current_direction_to`（真北顺时针，toward） | 数据集和 slice LRU；有 timestamp/source、`detided=True`；无质量/不确定性 |
| 海浪 | Copernicus Arctic WAM NetCDF | 规则经纬网，约 0.03°/约 3 km，小时级/每日文件 | `VHM0` 有效波高、`VTPK` 峰值周期、`VMDR` 平均波向 | 时间最近；规则网格标量双线性、方向圆周插值；明确输出 `wave_direction_from`（来向） | 每日文件、最多 3 个时间 slice；有 requested/matched time/source；无质量/不确定性 |

方向约定已经在模型中部分显式化：风同时提供数学向（toward）和气象来向（from）；流为 `direction_to`；浪为 `direction_from`。但统一 `EnvironmentWindState.direction`、`EnvironmentWaveState.direction` 是裸 float，规划契约没有强制携带方向语义，未来存在误用风险。海流网格旋转逻辑有实现，但必须用真实网格元数据做回归验证。

### 3.3 Forecast/Truth 泄露审计

代码没有 Truth/Forecast 类型，也没有 forecast issue time、lead time 或 cutoff 校验。`forecast_time` 是时间管理器字段，默认等于 simulation time，并没有约束 provider 只读取当时可获得的数据。因此无法证明“规划时未使用未来信息”；如果外部目录混入分析/预报文件，当前接口会按请求时间直接取最近值。海冰和风等 provider 的最近匹配还可能跨过请求时刻，形成未来信息泄露或回溯信息污染。该问题是 V4 规划接入前的高优先级阻断项。

## 4. 当前路径规划能力

- 搜索算法：无 A*、Dijkstra、lattice、motion primitive、采样规划或任何路线搜索实现。`PlannerService.plan()` 固定返回 `RouteResult(status="mock", risk={"status":"not_calculated"})`。
- 图/栅格：`EnvironmentGridBuilder` 是按需点采样缓存，不是导航图；无稀疏时变图、corridor、航段/节点结构。
- 搜索状态：仅有位置、时间、环境 cell 等数据契约；没有搜索状态、航向、速度、模式、风险签名或 option set。
- 边代价：不存在。没有 ETA、能耗、风险、可行性或多目标代价。
- 时间/速度维度：环境查询有请求时间；规划没有时间维度状态，也没有速度维度、等待动作或速度模式。
- 海流/船首向：环境查询可提供流，`VesselState` 有 heading，但二者没有进入任何航迹/速度计算。
- 动态重规划：无。前端规划面板明确显示“规划器未接入”，监控面板显示未连接/未计算。

## 5. 当前风险模型

唯一正式计算是水深安全：`required_depth = draft + ukc`，`margin = depth - required_depth`，`safe = margin >= 0`，位置在 `services/vessel_service/depth_safety.py`。默认 legacy 配置为 `draft=10, ukc=2`，而雪龙2 profile 的 design draft 是 7.85 m，存在配置不一致。

除此之外没有海冰、冰厚、冰型、风、流、浪、能耗、转弯、偏航或综合风险公式；`RouteResult.risk` 只是未计算状态。不存在可标注“正式来源”的风险公式。Draft/UKC 为工程参数，profile 中的 PC3、功率、速度上限来自 JSON source URL，但没有对应的风险映射/标准实现。需要补充参数来源、单位、阈值有效范围、UNKNOWN 语义和不确定性传播后，才可用于论文或规划。

## 6. 当前船舶模型

已实现：`data/vessel/xuelong2.json` + Pydantic profile，包含船长 122.5 m、船宽 22.32 m、设计吃水 7.85 m、排水量、双吊舱各 7.5 MW/总 15 MW、服务/最大航速、续航、PC3、连续冰厚/雪厚和连续破冰速度范围；`VesselService` 可加载 profile 并提供 `/api/vessel/current`。

仅为常量或 mock：`MockVesselProvider` 固定位置 69.65N/18.96E、heading 45°、speed 8 kn；`VesselState.speed` 没有 STW/SOG 语义；没有 COG、航迹方向、加减速、转弯半径、推进/阻力/功率曲线、能耗、POLARIS、航速受冰/风浪/流影响模型。Draft + UKC 使用独立默认 10+2 m，未自动使用 profile 的 7.85 m。船舶能力证据只有 JSON sources，没有运行时能力等级或证据结构。

## 7. 当前前后端接口

主要 API（`backend/app/routes.py`）：

| API | 输入 | 输出/用途 | V4 对应 |
|---|---|---|---|
| `GET /api/status`, `/api/` | 无 | 服务状态 | 系统健康 |
| `GET /api/chart`, `/api/chart/layers`, `/api/chart/layers/{id}` | 图层 id | 图层元数据/海岸线 GeoJSON | 前端底图 |
| `GET /api/environment/layers` | 无 | provider readiness | EnvironmentQuery 元数据 |
| `GET /api/environment/time` | 无 | simulation/forecast 字段、步长、场景范围 | 时间轴基础 |
| `GET /api/environment/query` | lat/lon/time | 五源 fault-isolated `EnvironmentState` | 可演化为 EnvironmentQuery |
| `POST /api/environment/query/batch` | 最多 500 点 + time | 批量环境状态 | EnvironmentQuery 批量 |
| `GET /api/environment/grid/query`、`POST .../batch` | WGS84 点 + time | `EnvironmentCell` | 多尺度地图输入的原型 |
| `GET/POST /api/environment/{ice,wind,current,wave}/query|field` | 点/批量点、可选 time | 源特定状态/矢量场 | provider 适配器 |
| `GET /api/environment/*/tile` | XYZ、date/time/index | PNG tile | 前端显示，不是规划数据接口 |
| `GET /api/environment/bathymetry/safety` | lat/lon | Draft + UKC 结果 | 初级 Safety Guard 素材 |
| `GET /api/vessel` | 无 | mock `VesselState` | 不能直接作为 VesselCapability |
| `GET /api/vessel/current` | 无 | static `VesselProfile` | VesselCapability 的静态起点 |
| `POST /api/planner` | 无 | mock `RouteResult` | Planner 占位，不能作为 V4 Planner |

最接近未来边界的是：`EnvironmentQuery` 可演化为 EnvironmentQuery/EnvironmentCell；`VesselProfile` 可演化为 ShipCapability；`/api/planner` 需要完全替换为带任务、起终点、时间、能力和规划选项的接口。当前没有 EdgeEvaluator、NavigationUpdate、Observation、BeliefWorld 或航线切换接口。

## 8. 实时导航能力

- 船位更新：没有真实 AIS/传感器输入；只有固定 mock vessel state。
- 偏航与 ETA：无计算、无事件输入、无路线版本。
- 环境刷新：前端可通过时间轴按钮/服务请求刷新图层；地图风/流/浪使用 viewport 采样与 fetch，海冰/水深使用 tile。它是显示刷新，不是导航闭环。
- 重规划：不存在。
- WebSocket/SSE/polling：未发现。HTTP fetch 为请求触发；没有后台订阅或推送。
- 异步：FastAPI 路由为同步 `def`；NetCDF/raster 读取和 tile 渲染在请求线程执行。批量点有 500/1000 限制，但无任务队列、超时、取消或优先级机制。远场大批量查询/切片可能阻塞同一进程中的近场请求。

## 9. 测试体系

实际运行结果：后端 `pytest -q` 为 **66 passed, 4 warnings**；前端 `npm test -- --run` 为 **13 files / 38 tests passed**；`npm run build` 成功，但 Vite 警告主 JS chunk 约 604 kB。

- Unit tests：有。覆盖 provider 算法（海冰/风/流/浪）、时间管理、网格、深度安全、profile、前端服务和地图层。
- Integration/API tests：有。`backend/tests/test_api.py` 及 environment service/query tests 覆盖 FastAPI/服务拼装。
- Scenario tests：基本没有。没有东北航道多情景、冰情揭示、等待/退出、安全保持、偏航和路线切换情景。
- Performance tests：没有正式性能/并发/端到端基准；仅有缓存和限制的单元测试。
- 真实数据依赖测试：部分 Copernicus 测试在数据可用时验证，整体未形成 Truth/Forecast 防泄露测试。

## 10. 可复用资产清单

### A：直接保留

- `core` 的 WGS84 位置、时间和环境状态基础契约：边界清楚、Pydantic 校验完整。
- provider 抽象、独立数据适配和 fault-isolated `EnvironmentQueryService`：适合作为 Environment Data Access 层。
- `EnvironmentTimeManager` 的 UTC 规范化、场景范围和可控时间步进：可保留为仿真时钟，但需重命名/补 forecast 语义。
- OpenLayers 图层管理、EPSG:4326/3857/3413 处理、GeoPackage 只读发布。
- 数据下载/检查/压缩工具的凭据隔离和原子输出策略。
- 船舶 profile JSON 的静态身份/几何/功率/冰级数据结构。

### B：小改后复用

- `EnvironmentGridBuilder`：可作为地图采样或规划输入适配层，但需支持多尺度、源时间、质量、不确定性和批量数组。
- 各源空间插值/方向转换/切片缓存：可复用底层数值逻辑，需统一方向、时间和质量契约。
- `DepthSafetyService`：可成为 Safety Guard 的一个子检查，但不能代表完整风险模型。
- `/api/environment/*field` 批量接口：可演化为 EdgeEvaluator 的环境采样输入，不应直接承担边可行性判断。
- 前端任务/规划/监控面板：可保留布局和状态展示框架，当前大量内容是预览占位。

### C：只能参考思想/局部代码

- `forecast_time`、winter/summer 场景：只有时钟壳，不是 ForecastWorld/BeliefWorld。
- `RouteResult`、`PlannerService`：仅可作为接口雏形。
- `VesselState`：heading/speed 字段可参考，语义不足以支撑 STW/SOG/COG。
- 统一 `EnvironmentCell`：是 source-faithful cell，不含风险/航行语义，可作为底层输入。

### D：应该废弃或重写

- `PlannerService.plan()` mock 及前端“规划偏好”假实现：接入 V4 前应重写为真实任务/规划契约。
- 固定 `MockVesselProvider` 作为运行时船位：生产导航必须替换为 Observation/NavigationState 输入。
- legacy `/api/environment` 和裸 `dict` 风险字段：可暂时兼容，但长期应收敛到版本化契约。
- Draft/UKC 默认 10+2 与 profile 7.85 不一致的双轨配置：应统一能力来源。

## 11. 与目标 V4 架构的缺口矩阵

| 目标模块 | 当前实现 | 文件位置 | 完成度 | 可复用 | 主要问题 | 优先级 |
|---|---|---|---:|---|---|---|
| Environment Data Contract | EnvironmentState/Cell/provider 状态 | `core/models.py` | 40% | B | 缺 source_time/valid_time、质量、不确定性、方向语义统一 | P0 |
| SyntheticEnvironment | 只有 `SyntheticEnvironmentProvider` 基础状态 | `services/environment_service/service.py` | 15% | C | 非可配置合成世界/真值生成器 | P1 |
| ForecastWorld | 无 | 全仓库 | 0% | C | 无 issue/cutoff/lead time | P0 |
| BeliefWorld | 无 | 全仓库 | 0% | C | 无融合、不确定性、信念更新 | P0 |
| Observation | 无 | 全仓库 | 0% | C | 无观测模型/揭示机制 | P0 |
| VesselCapability | 静态 VesselProfile | `core/vessel/models.py`, `data/vessel/xuelong2.json` | 30% | B | 无动态能力、证据等级、STW/SOG/功率曲线 | P0 |
| POLARIS | PC3 常量 | profile JSON | 5% | C | 没有 POLARIS 风险索引/规则 | P1 |
| Risk Model | Draft + UKC | `services/vessel_service/depth_safety.py` | 10% | B | 无冰/风浪/流/能耗/不确定性风险 | P0 |
| SparseGraph | 无，仅规则点网格采样 | `services/environment_service/grid.py` | 5% | C | 无节点/边/corridor/拓扑多样性 | P0 |
| Corridor | 无 | 全仓库 | 0% | D | 未建模 | P0 |
| EdgeEvaluator | 无 | 全仓库 | 0% | D | 无 PASS/FAIL/UNKNOWN、边状态和终点状态 | P0 |
| Time-dependent A* | 无 | `services/planner_service/service.py` | 0% | D | 无时间状态/启发式/动态边代价 | P0 |
| RG-MPAO* | 无 | 全仓库 | 0% | D | 无 Option Set、Risk Signature、Common Failure、adaptive K | P0 |
| CF-JRS | 无 | 全仓库 | 0% | D | 无 scenario belief、Reveal Set、WAIT/EXIT/SAFE-HOLD | P0 |
| RCOS | 无 | 全仓库 | 0% | D | 无闭环 belief/偏航/修复/滞回/degraded mode | P0 |
| Safety Guard | 仅深度安全 | depth safety/API | 10% | B | 无独立运行时安全门和切换约束 | P0 |
| Navigation State Machine | 无 | 前端仅 UI 状态 | 0% | C | 无任务/路线/执行/降级状态 | P0 |
| ETA | `RouteResult.eta` 可空字段 | `core/models.py` | 5% | C | 无航段时间、速度/流影响 | P0 |
| STW/SOG | VesselState 一个 speed 常量 | `core/models.py` | 5% | C | 无区分、无流合成 | P0 |
| COG/Heading | VesselState heading | `core/models.py` | 5% | C | 无航迹/船首关系、操纵约束 | P0 |
| Near-field | 无 | 全仓库 | 0% | D | 无局部操纵/转弯/变速可行性 | P0 |
| Far-field | 无 | 全仓库 | 0% | D | 无稀疏时变航路图 | P0 |
| Frontend visualization | 地图/环境层/任务面板 | `frontend/src` | 60%（显示） | A/B | 规划/监控值均为占位，缺路线与可信度可视化 | P1 |
| Experiment framework | provider/unit tests | `backend/tests`, `tools/data_tools/tests` | 25% | B | 无可复现实验、指标、场景矩阵、性能基准 | P0 |

## 12. 论文价值审计

工程能力：多源 NetCDF/GeoTIFF/GeoPackage 适配、WGS84/极地投影、最近时间/空间采样、方向转换、切片服务、环境缓存、FastAPI/Vue 展示、Draft + UKC 基础判断。这些适合支撑系统实现章节和数据工程章节，但本身不是 RG-MPAO*/CF-JRS/RCOS 方法创新。

潜在方法基础：provider 隔离、fault-isolated 环境 cell、可控时间轴、海冰场/风流浪方向处理、可缓存批量采样，可作为实验基础设施。要形成方法论文，必须补齐明确的数学定义：状态空间、环境/船舶动力学、风险函数、可行性和 UNKNOWN 规则、Option-set dominance、scenario belief/observation model、commitment/viability、重规划滞回与安全证明。

直接宣称创新会缺乏依据的部分：当前不存在任何 RG-MPAO*、CF-JRS、RCOS 算法代码、复杂度分析、最优性/可行性证明或对照实验；`RouteResult.risk` 和 UI 文案不能作为论文结果。还需要 SyntheticEnvironment/ForecastWorld/TruthWorld 可复现实验、基线 A*/单路线规划、消融实验、不同 K/揭示时机/偏航和数据缺失场景，以及 ETA、风险、成功率、计算时间等指标。

## 13. 技术债与风险

1. 时间语义：最近时间匹配无统一容差；`forecast_time` 未参与数据选择；没有 source/valid/issue/cutoff 结构，存在未来信息泄露。
2. 数据质量：质量和不确定性没有字段，provider 异常被压成 `available=false/reason`，无法区分缺测、过期、低质量和模型不确定性。
3. 方向单位：裸 `direction` 字段可能丢失 from/to 语义；风/浪/流的方向虽在专用模型中写明，跨层传递仍不安全。
4. 吃水配置冲突：profile 7.85 m 与 legacy 10 m + UKC 2 m 并存，导致同一船舶安全结果不可追溯。
5. 坐标/分辨率：WGS84、EPSG:3857、EPSG:3413 分层合理，但水深 nearest、CARRA2 nearest、其他双线性采样精度与误差没有统一记录；经度周期和极区边界需持续验证。
6. 风险缺失：无完整风险模型、阈值来源、UNKNOWN 传播、综合风险或能力证据。
7. 算法缺失：没有图、边、搜索、速度/航向/等待、备用路线、路线切换条件。
8. 实时性：同步 FastAPI + NetCDF/raster I/O；没有近场优先级、异步任务、超时、取消或并发隔离，远场查询可能阻塞更新。
9. 前后端契约：legacy dict、mock planner、UI 状态与真实后端脱节；没有 API 版本化和 NavigationUpdate 事件模型。
10. 测试缺口：缺真实运行时 forecast/quality 防泄露测试、端到端导航场景、性能/并发、数据漂移和故障注入。
11. 可维护性：运行时依赖外部机器路径；README 中部分“真实 PolarData”能力取决于本机文件是否存在，部署可复现性不足。
12. 前端构建：生产主 JS chunk 约 604 kB，虽不影响功能，但应作为后续性能债记录。

## 14. 最终结论

1. **是否适合作为后续主项目：适合，但定位应是“环境与驾驶台基础平台”，不能误认为已有 V4 规划器。** 服务边界、测试、真实数据适配和地图壳具备继续演进价值。
2. **应保留：** provider 抽象与五源环境读取、统一查询/时间轴、坐标与切片处理、GeoPackage 图表服务、船舶 profile 数据结构、前端地图/环境显示、现有测试基础。
3. **应先重构：** Environment Data Contract（Truth/Forecast/quality/uncertainty/方向/时间）、船舶能力与吃水单一来源、Synthetic/Forecast/Belief 分层、规划输入输出版本化、异步/批量计算边界。之后再实现 EdgeEvaluator。
4. **暂时不要碰：** 已通过测试的底层 NetCDF 空间插值、投影/切片渲染、GeoPackage 读取和前端地图层管理；除非有明确数据错误或性能证据，不要先做大规模 UI/架构重写。
5. **最小下一阶段：** 建立可复现实验纵切片：`SyntheticEnvironment + Truth/Forecast/Belief/Observation`、统一 `EnvironmentDataContract`、`VesselCapability`、单航段 `EdgeEvaluator`（PASS/FAIL/UNKNOWN + STW/SOG/Heading/ETA/risk/quality/终点状态），配套一个最小时间相关单路线搜索和 3 个 scenario tests。先不实现 RG-MPAO*、CF-JRS、RCOS 全部复杂逻辑；用该纵切片验证数据语义、单位、时间防泄露和可行性输出，再扩展到稀疏图与多方案规划。

