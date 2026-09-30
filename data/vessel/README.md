# Vessel

`xuelong2.json` 是系统默认船舶档案，按 `core.vessel.VesselProfile` 校验加载。档案只包含公开资料中的设计参数，并记录每组数据的来源链接；运行时由 `VesselService` 读取，不在 Python 中硬编码。
