# V5 Multi-source Provider Architecture

## 1. Purpose

`core/providers/` supplies a small adapter boundary between external datasets
and the source-neutral Environment Contract. It defines common utilities and
one base interface; it is not a plugin registry or a data-source
implementation.

## 2. Data Flow

```text
External Dataset
    -> Provider Adapter
    -> EnvironmentField
    -> Environment Contract
```

An adapter loads its source, reads source facts into shared `FieldMetadata`,
and converts values and coordinates into an `EnvironmentField`. It reuses the
environment grid and Foundation coordinate, time, quality, availability, and
evidence contracts. The adapter owns source-format interpretation; consumers
receive the generic field model.

## 3. Base Adapter Interface

`BaseProviderAdapter` deliberately has only three operations:

- `load()` prepares or opens a source dataset.
- `read_metadata()` returns shared `FieldMetadata`.
- `convert_to_environment_field()` returns an `EnvironmentField`.

There is no lifecycle manager, registration mechanism, source catalogue,
provider-specific metadata DTO, or query policy in this phase.

## 4. Common Utilities

- `common/netcdf.py` exposes the existing generic NetCDF opener from
  `core/netcdf.py`; it contains no dataset-specific behavior.
- `common/variables.py` resolves conventional variable aliases and
  latitude/longitude names without assuming a particular product.
- `common/coordinates.py` converts Foundation `WGS84Position` into
  `LocalENUPosition` using the `LocalENUFrameRef` origin and WGS84 ellipsoid.
  Height is assumed zero because the Foundation frame reference has no origin
  altitude field.
- `common/metadata.py` builds the Environment Contract `FieldMetadata` from
  Foundation `TimeMetadata`, `QualityMetadata`, and `EvidenceRecord`. It does
  not introduce a ProviderMetadata type.

## 5. Future Source-to-Field Mappings

These are intended mappings. Phase 2.1 implements only the GEBCO adapter;
the other four remain future mappings.

| Future source | Generic environment variable | Future conversion responsibility |
|---|---|---|
| GEBCO | Bathymetry | Read elevation and normalize positive-up metres to positive-down `depth_m`. |
| CARRA2 | Wind | Resolve wind variables/coordinates and normalize vector components. |
| TOPAZ5 | Current | Resolve current variables and transform grid vectors to East/North. |
| neXtSIM-F | Ice | Map ice concentration, thickness, type, and drift into generic field data. |
| WAM | Wave | Map wave height, period, and directional/vector quantities. |

The common layer contains none of these product mappings or source names.

### GEBCO Phase 2.1 Flow

```text
GEBCO NetCDF
    -> GEBCONetCDFReader
       - resolves latitude/lat and longitude/lon
       - reads elevation and source attributes
    -> GEBCOProviderAdapter
       - samples ENU cell centers against the native WGS84 axes
       - converts valid elevation_m to max(0, -elevation_m)
       - preserves masked/NaN cells as None
       - builds shared FieldMetadata
    -> BathymetryField (EnvironmentField)
       - data / depth_m, GridSpec, FieldMetadata
```

The adapter requires a caller-supplied Local ENU `GridSpec`. It samples cell
centers with nearest-neighbour selection and reads only the bounding source
window, leaving outside-coverage and NoData cells as `None`. This phase does
not add a configurable resampling policy. Static GEBCO time metadata is
represented with `TimeMetadata` fields unset, not with a synthetic timestamp.

### CARRA2 Phase 2.2 Flow

```text
CARRA2 Forecast NetCDF
    -> CARRA2NetCDFReader
       - resolves latitude/lat, longitude/lon and time
       - reads u10/v10 at an explicit forecast time index
       - reads forecast reference time when present
    -> CARRA2WindProviderAdapter
       - maps u10 to wind_east_mps and v10 to wind_north_mps
       - samples target Local ENU cell centers via shared coordinate helpers
       - maps NaN, masked and outside-coverage values to None
       - builds shared FieldMetadata
    -> WindField (EnvironmentField)
       - data.wind_east_mps, data.wind_north_mps
       - GridSpec, FieldMetadata
```

Each adapter instance represents one valid forecast time selected by
`time_index`; it performs no temporal interpolation. CF `time` supplies
`valid_time`; `forecast_reference_time` (or an equivalent issue-time source)
supplies `issue_time`; the reader's actual dataset load instant supplies
`ingest_time`. Unavailable issue time remains `None`, and no synthetic
`timestamp` is introduced. Wind is stored only as East/North components in
m/s; no FROM/TO bearing or angle is carried in `WindField`.

### TOPAZ5 Phase 2.3 Flow

```text
TOPAZ5 NetCDF
    -> TOPAZ5NetCDFReader
       - resolves latitude/lat, longitude/lon, time and uo/vo or current_u/current_v
       - selects surface (index 0) when an optional depth axis is present
    -> TOPAZ5CurrentProviderAdapter
       - converts cm/s to m/s when required
       - samples Local ENU cell centers against WGS84 source axes
       - maps NaN, masked and outside-coverage values to None
       - builds shared FieldMetadata
    -> CurrentField (EnvironmentField)
       - data.current_east_mps, data.current_north_mps
       - GridSpec, FieldMetadata
```

TOPAZ5 Phase 2.3 supports only surface current. It preserves `issue_time`,
`valid_time`, and `ingest_time` through Foundation `TimeMetadata`, and does
not create direction angles, depth-layer fields, risk, planning, route, ETA,
or speed logic.

### neXtSIM-F Phase 2.4 Flow

```text
neXtSIM-F NetCDF
    -> NextSIMNetCDFReader
       - resolves latitude/lat, longitude/lon and time
       - reads concentration, thickness and ice u/v aliases
       - selects surface (index 0) for optional depth axes
    -> NextSIMIceProviderAdapter
       - normalizes concentration to 0-1
       - converts thickness to metres and velocity to m/s
       - samples Local ENU cell centers against WGS84 source axes
       - maps NaN, masked and outside-coverage values to None
       - builds shared FieldMetadata
    -> IceField (EnvironmentField)
       - concentration, thickness_m and East/North velocity components
       - GridSpec, FieldMetadata
```

This phase is a data adapter only. It does not implement POLARIS, RIV, ice
risk, feasibility, route, ETA, speed, or other safety/planning logic.

### WAM Phase 2.5 Flow

```text
WAM NetCDF
    -> WAMNetCDFReader
       - resolves latitude/lat, longitude/lon and time
       - reads Hs, Tp and direction aliases
    -> WAMWaveProviderAdapter
       - converts wave height to metres and period to seconds
       - converts direction to radians with explicit TO semantics
       - samples Local ENU cell centers against WGS84 source axes
       - maps NaN, masked and outside-coverage values to None
       - builds shared FieldMetadata with direction_convention="TO"
    -> WaveField (EnvironmentField)
       - wave_height_m, wave_period_s, wave_direction_rad
       - GridSpec, FieldMetadata
```

WAM carries no FROM direction, risk, planner, route, ETA, speed, ship-motion,
or wave-resistance logic in this adapter phase.

## 6. Risk and Planning Boundary

Providers are responsible for loading, interpreting, and converting data plus
its metadata. They do not calculate risk, feasibility, routes, ETA, or speed
recommendations. Future Risk and Planner layers consume Environment Contract
fields and apply their own explicit domain policies; source adapters remain
independent of those policies. Missing values remain unknown and are not
silently converted into safe defaults.
