# V5 Environment Model Design

## 1. Design Goal

`core/environment/` defines source-neutral contracts between external data
adapters and future consumers. The flow is:

```text
External Environment Data -> EnvironmentField -> EnvironmentScaleSnapshot
-> MultiScaleEnvironmentState
```

This package defines data shape and provenance only. It does not read datasets,
select sources, interpolate, calculate risk, or plan routes. Legacy
`services/environment_service/` remains outside this contract.

## 2. Multi-scale Representation

| Scale | Range | Representation resolution | Refresh target |
|---|---:|---:|---:|
| Near | 0-3 nm | 75 m | 1-5 s |
| Middle | 2-15 nm | 250 m | 300-600 s |
| Remote | 12-50 nm | 1000 m | 1800-3600 s |

These are independent representations, not nested replacements. Near and
Middle overlap from 2-3 nm; Middle and Remote overlap from 12-15 nm. Consumers
can retain both local detail and broader context in overlap zones.

## 3. Scale Rationale

Near covers immediate maneuvering context, so it uses the finest grid and the
fastest refresh target. A 0-3 nm extent keeps that high-cost representation
focused around the vessel while allowing enough local look-ahead for tactical
decisions. The exact operational horizon remains a product/configuration
decision, not a risk threshold encoded by this model.

Middle bridges local maneuvering and regional context at 2-15 nm. Its overlap
with Near avoids a discontinuity at the scale boundary; 250 m and a 5-10 minute
refresh target represent a lower update cost than the near field.

Remote provides regional context to 50 nm. The 12-15 nm overlap with Middle
avoids a hard handoff, while 1000 m representation and a 30-60 minute refresh
target suit broad-scale inputs. The model preserves these ranges as metadata;
it does not decide which scale a future query must use.

## 4. Grid and Coordinate Frame

`GridSpec` uses `LocalENUFrameRef` from `core/contracts`. Its bounds are
`x_min_m`, `x_max_m`, `y_min_m`, and `y_max_m`; x is East, y is North, and all
distances/resolution are metres. Cell counts and resolution must agree with the
outer grid extent. Geographic WGS84 positions remain boundary types and are
not redefined here.

## 5. Field Model

`EnvironmentField` is generic across bathymetry, wind, current, ice, and wave
variables. It carries a variable kind, data (or `None` when unknown), a grid,
and `FieldMetadata`. There are intentionally no source-specific field classes
or provider implementations in this phase. Vector values follow East/North
component semantics; direction-bearing values are not represented by a bare
`direction` contract here.

## 6. Metadata Model

`FieldMetadata` carries `source_id`, `native_resolution_m`,
`representation_resolution_m`, `TimeMetadata`, `QualityMetadata`, and
`EvidenceRecord`, all imported from `core/contracts`. Availability is exposed
through `QualityMetadata.availability`, avoiding a second availability field
with potentially conflicting state. Unknown source/resolution values are
`None`.

## 7. Time Model

Field time information reuses Foundation `TimeMetadata` with its fixed
`source_time`, `issue_time`, `valid_time`, `observation_time`, and `ingest_time`
meanings. Snapshot `time_context` uses the same model. The environment package
does not create alternate time structures or make availability decisions.

## 8. Snapshot and Sample

`EnvironmentScaleSnapshot` groups one scale, its grid, generic fields,
snapshot metadata, and time context. `MultiScaleEnvironmentState` contains
exactly one Near, Middle, and Remote snapshot and validates that each snapshot
is assigned to the matching scale. `EnvironmentSample` represents one
variable at a typed local ENU position and timezone-aware time; its value may
be `None` when unavailable or unknown.

## 9. Future Provider Boundary

Future provider adapters may translate source formats into generic
`EnvironmentField` objects and populate the shared metadata. They should not
add source-specific field models to this package. Provider APIs and adapter
behavior are deliberately not implemented by this contract phase.

## 10. Future Risk and Planner Consumers

Future risk and planner layers may consume `MultiScaleEnvironmentState` or
samples selected from its snapshots. They must interpret missing values and
quality explicitly: unknown is not safe, and `None` must not be silently
replaced by zero or false. Those consumers, their policies, and route/ETA/speed
logic are outside this package and are not implemented here.
