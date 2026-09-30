# Core

共享领域模型。环境时间框架使用 `EnvironmentQuery`（latitude、longitude、timestamp）将连续位置/时间请求传递给 Environment Service，`EnvironmentTimeState` 描述当前 simulation time、forecast time 和固定 time step。它们不绑定 NetCDF、API 或地图实现。

跨模块共享的数据契约。这里不放 OpenLayers、FastAPI 或具体数据源逻辑，保证领域模型可被未来服务和规划器复用。
