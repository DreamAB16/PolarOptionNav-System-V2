# Chart service

海图服务 facade。`ChartProvider` 是数据源边界，当前 `GeoPackageChartProvider` 从服务端 `data/charts/base_map.gpkg` 读取 `coastline`，转换为 GeoJSON。

API 仅暴露图层标识和 GeoJSON，不返回文件系统路径。未来可注入 S-57、S-101、GeoTIFF 或其他 provider。
