# Map layer architecture

`ManagedLayer` defines the frontend lifecycle shared by independently loaded map layers: `load`, `unload`, `refresh`, `updateTime`, visibility, state subscription and disposal.

Current adapters:

- `ChartLayer` owns the existing coastline GeoJSON workflow.
- `BathymetryLayer` owns the existing GEBCO XYZ raster workflow.
- `IceLayer` owns the processed Copernicus Marine XYZ raster workflow, concentration/thickness mode, time and opacity controls.
- `WindLayer` owns the CARRA2 viewport-sampled wind arrows.
- `CurrentLayer` owns TOPAZ5 viewport batch requests and geographic surface-current arrows; it discards stale requests during pan, projection and time changes.
- `WaveLayer` owns WAM Arctic viewport batch requests and renders sparse significant-wave-height symbols; direction remains a data attribute rather than a dense arrow field.

The ordinary bridge view remains EPSG:3857 and the Arctic strategic/detailed views use EPSG:3413. All modes share the same OSM cartographic source, which OpenLayers reprojects in polar mode. The polar View starts at the fixed 30°N–90°N strategic domain but is not constrained by a layer extent or `fit()` operation. `ChartLayer` reloads coastline GeoJSON in EPSG:3413 and sea ice uses native polar tiles.

`MapLayerManager` coordinates these layers and retains the original `register(key, olLayer)` / `setVisible` API through a legacy adapter. Future route layers should implement the same interface without adding data-loading branches to `App.vue`.
