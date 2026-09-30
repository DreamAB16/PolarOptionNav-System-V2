# Environment service

环境服务 facade；调用方不绑定 NetCDF、GEBCO 或任何文件格式，具体格式由 provider 隔离。

`EnvironmentProvider` 统一定义 `get_metadata()` 和 `get_available_layers()`。当前注册：

- `RealBathymetryProvider`：持久打开 GEBCO NetCDF，提供单点查询和动态 XYZ PNG 瓦片
- `CopernicusIceProvider`：从真实 CF 元数据发现变量，按请求时间读取密集度、厚度、冰型、漂移和雪厚
- `CopernicusIceRasterProvider`：支持 Copernicus 一维规则经纬网（并兼容 CF 投影网格），生成并缓存海冰密集度/厚度 XYZ PNG 瓦片
- `CARRA2WindProvider`：在 CARRA2 二维环北极网格匹配最近3小时时次并读取 `si10/wdir10`
- `RealWindProvider`：保留 ERA5 规则经纬网兼容能力
- `RealCurrentProvider`：在 TOPAZ5 原始极射 x/y 网格双线性插值 `vxo/vyo`，再通过投影局部基向量转换为地理 East/North
- `RealWaveProvider`：在Copernicus WAM Arctic规则经纬网插值有效波高与峰值周期，并通过单位圆插值平均波浪来向
- `MockIceProvider`：仅用于独立测试或手动注入
- `WindProvider`、`CurrentProvider`、`WaveProvider`：相应真实文件缺失时的 pending 后备

`EnvironmentService` 聚合这些 provider，并通过 `GET /api/environment/layers` 发布图层目录。现有 `SyntheticEnvironmentProvider` 仅保留 Phase 0 的 `/api/environment` 状态 mock。

## Environment Query Service

`EnvironmentQueryService` 为一个 WGS84 位置和 UTC 时间聚合 GEBCO、neXtSIM-F、CARRA2、TOPAZ5 和 Arctic WAM 查询结果。它不读取 NetCDF、不转换坐标也不重新插值；各 Provider 继续独立选择最接近的真实时次，并在各分量的 `matched_time` 中返回实际数据时间。

单点接口：

```text
GET /api/environment/query?lat=80&lon=120&time=2025-08-15T13:00:00Z
```

批量接口：

```json
POST /api/environment/query/batch
{
  "time": "2025-08-15T13:00:00Z",
  "points": [{"id": "p1", "lat": 80, "lon": 120}]
}
```

批量接口要求 1–500 个点，按输入 `id` 返回 `environment`。统一 `EnvironmentState` 包含请求坐标和时间、正向下水深、带 `available` 标志的海冰/风/海流/海浪状态，以及五类数据源名称。单个 Provider 的覆盖外或 NoData 不会使整体请求失败。查询层使用最多 1000 条的线程安全 LRU，键由五位小数经纬度和规范化 UTC 请求时间组成；Provider 自身缓存保持不变。

## Environment Time Framework

`EnvironmentTimeManager` 是环境请求的统一 UTC 时钟，当前默认仿真时间为 `2025-02-15T12:00:00Z`，时间步长为一小时。它生成 `EnvironmentQuery(latitude, longitude, timestamp)`；海冰、风和海流 Provider 通过 `query(position, timestamp)` 接收该统一契约。Provider 决定如何将连续时间解析到自身的观测或预报目录，调用方不接触文件名或日期索引。

TOPAZ5 海流只允许选择请求当天的真实文件，并在文件内匹配最近小时（半小时时刻固定取较早小时），禁止跨日伪匹配。`GET /api/environment/current/query` 提供单点状态，`POST /api/environment/current/field` 一次查询最多 500 点；陆地、缺测和覆盖外点在批量结果中单独标记为 unavailable。当前产品为 detided surface current，不包含潮流。

WAM Arctic海浪同样只允许请求日期精确命中真实文件，并在当天匹配最近小时。`VHM0/VTPK`采用双线性插值，`VMDR`是波浪“来向”，采用圆角插值避免359°/1°跨界错误。单点和批量接口分别为`GET /api/environment/wave/query`、`POST /api/environment/wave/field`；NoData不会转换为0 m静浪。

`GET /api/environment/time` 返回当前 simulation/forecast time 和 step。海冰点查询的 `time=ISO-8601` 参数和瓦片的 `time=ISO-8601` 参数均使用这一套时间语义；Copernicus Provider 自动选择最近可用文件，并在文件内选择最近时次。`date=YYYYMMDD` 保留为调试兼容入口，不能与 `time` 同时使用。

`GET /api/environment/ice/query?lat=<latitude>&lon=<longitude>&time=<ISO-8601>` 返回 `SeaIceState`：坐标、观测时间、0–1 密集度、米级厚度、主导冰型、冰漂移 U/V、雪厚和数据来源。省略 `time` 时使用 `EnvironmentTimeManager` 的 simulation time；默认海冰实现固定为 `CopernicusIceProvider`。

`GET /api/environment/ice/tile/{z}/{x}/{y}.png?time=<ISO-8601>` 返回缓存的海冰密集度 PNG；`GET /api/environment/ice/thickness/tile/{z}/{x}/{y}.png?time=<ISO-8601>` 返回厚度 PNG。每个目标 Web Mercator 像素反投影到 Copernicus 坐标网格，物理值使用窗口化双线性采样，有效性、陆地/缺测和开水边界使用最近源单元掩膜，防止冰值越过边界扩散。颜色和 alpha 均由连续物理值插值，`NaN`、`_FillValue`、越界、陆地、缺测和零值保持透明；缓存键包含文件日期、小时索引和显示变量。

北极战术视图使用 `/api/environment/ice/polar/tile/{z}/{x}/{y}.png` 和对应 thickness 路径直接生成 EPSG:3413 瓦片，避免 EPSG:3857 在约 85.05°N 截止形成北极空洞。全球与极地缓存相互隔离。

水深 API 将 GEBCO 的正向上 `elevation` 转为正向下水深 `max(0, -elevation)`。Dataset 每个后端进程只打开一次，栅格数组保持磁盘惰性读取；点值与 PNG 瓦片分别使用有限 LRU 缓存。

其他未来 NC adapter 应实现 `EnvironmentProvider`，由 `EnvironmentService` 注入。规划器应调用 `EnvironmentService`，不得直接读取 `data/environment`。
