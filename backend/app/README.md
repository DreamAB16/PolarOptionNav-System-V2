# API application

`main.py` 创建 FastAPI 应用，`routes.py` 暴露系统状态、图表、环境、船舶和规划接口。

Chart APIs:

- `GET /api/chart/layers` — allowed layer catalogue only
- `GET /api/chart/layers/coastline` — coastline GeoJSON feature collection

Environment API:

- `GET /api/environment/layers` — registered environment layer catalogue
- `GET /api/environment/query?lat=<lat>&lon=<lon>&time=<ISO-8601>` — fault-isolated unified point environment state
- `POST /api/environment/query/batch` — up to 500 unified WGS84 point queries
- `GET /api/environment/ice/query?lat=<lat>&lon=<lon>&time=<ISO-8601>` — time-aware multi-variable sea-ice state query
- `GET /api/environment/ice/tile/{z}/{x}/{y}.png?time=<ISO-8601>` — cached sea-ice raster tile (`date=YYYYMMDD` remains a debug-compatible alias)
- `GET /api/environment/ice/thickness/tile/{z}/{x}/{y}.png?time=<ISO-8601>` — cached sea-ice thickness raster tile
- `GET /api/environment/ice/polar/tile/{z}/{x}/{y}.png?time=<ISO-8601>` — native EPSG:3413 concentration tile
- `GET /api/environment/ice/thickness/polar/tile/{z}/{x}/{y}.png?time=<ISO-8601>` — native EPSG:3413 thickness tile
- `GET /api/environment/bathymetry/query?lat=<lat>&lon=<lon>` — GEBCO point query
- `GET /api/environment/bathymetry/safety?lat=<lat>&lon=<lon>` — Draft + UKC check
- `GET /api/environment/bathymetry/tiles/{z}/{x}/{y}.png` — dynamic bathymetry raster tile
- `GET /api/environment/bathymetry/polar/tile/{z}/{x}/{y}.png` — native EPSG:3413 bathymetry tile (requires the offline polar product)
