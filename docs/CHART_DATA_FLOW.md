# Chart data flow

```text
data/charts/base_map.gpkg
        ↓ (server-side read only)
GeoPackageChartProvider : ChartProvider
        ↓ GeoJSON FeatureCollection
ChartService
        ↓
GET /api/chart/layers             (catalogue)
GET /api/chart/layers/coastline   (feature data)
        ↓ HTTP
frontend chart-client
        ↓ EPSG:4326 → EPSG:3857 conversion
OpenLayers VectorLayer
        ↓
MapLayerManager (charts visibility)
```

The browser only receives authorised layer metadata and GeoJSON. The GeoPackage's physical location is an implementation detail of the backend provider.

