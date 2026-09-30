# Charts

当前 `base_map.gpkg` 由 `chart_service` 的 `GeoPackageChartProvider` 读取，并仅向 API 发布允许的 `coastline` 图层。前端不得直接读取此目录。

后续可在保持 `ChartProvider` 接口不变的前提下接入 ENC S-57、S-101、GeoTIFF 等来源。
