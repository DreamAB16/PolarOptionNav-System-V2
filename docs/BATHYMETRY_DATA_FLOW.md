# Bathymetry data flow

```text
GEBCO_2026_sub_ice.nc (lat/lon/elevation, EPSG:4326)
        ├── lazy NetCDF reads → RealBathymetryProvider
        │                         ├── point query → BathymetryState
        │                         └── /bathymetry/tiles → EPSG:3857 XYZ PNG
        │
        └── offline preprocess_bathymetry_polar.py
                                  ↓ EPSG:3413, 30°N–90°N, masked GeoTIFF
                    bathymetry_polar_3413.tif
                                  ↓
                    PolarBathymetryProvider
                                  └── /bathymetry/polar/tile
                                      → native EPSG:3413 XYZ PNG

EnvironmentService keeps both providers independent.
Global navigation consumes EPSG:3857; Arctic strategic and tactical views
consume native EPSG:3413 tiles. No polar view reprojects the global bathymetry
source, so the Web Mercator 85.0511°N cutoff cannot form a polar hole.

Both renderers apply the same mask policy: only negative, finite elevation
(water) receives colour and alpha; land and `_FillValue`/NoData are fully
transparent and are never used in depth colour mapping.

        ↓ FastAPI
        ├── point depth query
        └── depth → VesselService → DepthSafetyService
                              ↓
                     Draft + UKC result
```

## Dataset inspection

- Format: NETCDF4, CF-1.6 / ACDD-1.3
- Coordinates: `lat` (43,200), `lon` (86,400)
- Raster: `elevation(lat, lon)`, `int16`, metres, positive upward
- CRS: EPSG:4326
- Cell-centre ranges: latitude -89.9979167…89.9979167; longitude -179.9979167…179.9979167
- Resolution: 0.0041666667° (15 arc-seconds)

The API converts negative elevation to positive-down water depth. Land elevation maps to zero water depth and therefore fails any positive Draft + UKC requirement.
