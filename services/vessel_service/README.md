# Vessel service

船舶档案与状态 facade。当前档案默认从 `data/vessel/xuelong2.json` 加载，实时状态仍使用 mock provider；未来可在不改变 `VesselProfile` 契约的情况下接入多船选择、传感器或 AIS 适配器。

`VesselDraftConfig` 保存吃水和安全富余水深，单位均为米。`DepthSafetyService` 只执行 `required_depth = draft + ukc` 和余量判断，不依赖路径规划器，也不会改变航线。

`GET /api/vessel/current` 返回完整的 `VesselProfile`，包括 geometry、mass、propulsion、speed、ice_capability 与面向 EnvironmentGrid 的 safety_constraints。
