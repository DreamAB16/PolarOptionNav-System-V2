# V5 Phase 1 Implementation

## 1. Scope

This phase implements only the V5 foundation contracts: coordinate, unit,
direction, time, availability/quality, and evidence. No planner, graph,
environment-provider migration, or frontend behavior was changed.

## 2. Source Files

Added:

- `core/contracts/__init__.py`
- `core/contracts/coordinates.py`
- `core/contracts/units.py`
- `core/contracts/directions.py`
- `core/contracts/time.py`
- `core/contracts/quality.py`
- `core/contracts/evidence.py`

The existing `core/models.py`, services, API routes, frontend, and provider
implementations were not modified.

## 3. Coordinate Convention

Local planning coordinates use ENU: `x` is East and `y` is North. Geographic
frame references are WGS84 latitude/longitude in degrees. Navigation bearing
is true-north zero and clockwise positive; mathematical yaw is East zero and
counter-clockwise positive. Internal angles are radians.

The conversion pair is:

```text
math_yaw = wrap_2pi(pi/2 - navigation_bearing)
navigation_bearing = wrap_2pi(pi/2 - math_yaw)
```

`WGS84Position` is restricted to the geographic boundary. `LocalENUFrameRef`
records a frame identifier, WGS84 origin, and CRS/projection identifier;
`LocalENUPosition` then carries `x_east_m`, `y_north_m`, and `z_up_m` in that
frame. Neither type implements projection algorithms, and WGS84 coordinates
must not be used as an algorithm-space Euclidean distance.

## 4. Unit Convention

Core contracts use SI units. Explicit pure functions cover nautical miles and
metres, knots and metres/second, and degrees and radians. The formal constants
are `1 nm = 1852 m` and `1 kn = 1852/3600 m/s`; no unit dependency was added.

## 5. Direction Convention

Wind and wave directions are explicitly `FROM`; current direction is explicitly
`TO`. `to_bearing_speed_to_en` maps a TO bearing to `(east, north)` components
using `east = speed*sin(bearing)` and `north = speed*cos(bearing)`.
FROM conversion is explicit through `from_bearing_to_to_bearing` before vector
conversion.

## 6. Time Convention

`TimeMetadata` carries optional source, issue, valid, observation, and ingest
timestamps. All present values are normalized to UTC. `ensure_utc` rejects naive
datetimes rather than guessing a local timezone. `lead_time`, `data_age`, and
`staleness` only calculate timedeltas and contain no source-specific thresholds.

## 7. Availability / Evidence

`AvailabilityStatus` contains `AVAILABLE`, `AGING`, `STALE`, `MISSING`,
`CONFLICT`, and `INVALID`. `EvidenceStatus` contains `STANDARD`, `VESSEL_DATA`,
`LITERATURE`, `PROJECT_ASSUMPTION`, `CALIBRATED`, `SYNTHETIC_MODEL`, and
`UNKNOWN`. `EvidenceRecord`/`ParameterEvidence` preserve source, status,
applicability, confidence, and notes. Confidence is structurally bounded when
provided but is not interpreted as a probability.

`available_at_decision_time` is the foundation-level availability gate for a
future query facade: a record whose issue time or ingest time is after the
decision time is unavailable, even if its valid time is suitable. It returns
`None` when publication/ingest availability cannot be established. It does not
implement ForecastWorld, Observation, BeliefWorld, source selection, or a
staleness policy.

## 8. Feasibility Tri-state

`FeasibilityStatus` contains only `PASS`, `FAIL`, and `UNKNOWN`. It deliberately
raises when coerced to `bool`, preventing `UNKNOWN` from becoming a truthy safe
result. This contract evaluates no depth, ice, wave, vessel, or route condition.

## 9. Public API

Future consumers import shared contracts from `core.contracts`, including
`WGS84Position`, `LocalENUFrameRef`, `LocalENUPosition`, unit conversion
helpers, explicit direction wrappers/vector helpers, `TimeMetadata`,
`AvailabilityStatus`, `FeasibilityStatus`, and evidence types. Environment must
reuse these types rather than define parallel time, availability, direction,
unit, or evidence contracts.

## 10. Tests

Added five focused test files with 37 tests:

- `backend/tests/test_v5_coordinates.py`
- `backend/tests/test_v5_units.py`
- `backend/tests/test_v5_directions.py`
- `backend/tests/test_v5_time.py`
- `backend/tests/test_v5_quality_evidence.py`

Focused tests cover cardinal bearing/yaw conversion, wrapping, WGS84/ENU type
separation, SI boundary conversions, Wind/Wave FROM and Current TO vectors,
UTC normalization, naive-time rejection, future issue/ingest leakage, six
availability states, feasibility tri-state protection, and evidence states.

Full backend result: **95 passed, 4 warnings**. Warnings are existing third-
party deprecation/pending-deprecation warnings from `dateutil` and `rasterio`.

## 11. P0 Status

- P0-01 bearing/math yaw: **MAIN-PROJECT FOUNDATION RESOLVED** by implementation
  and cardinal/round-trip tests.
- P0-02 ENU frame: **PARTIALLY RESOLVED**; the new frame reference and tests
  exist, but legacy models have not been migrated.
- P0-03 future leakage: **PARTIALLY RESOLVED**; the foundation availability gate
  is tested, but Forecast/Observation/Belief providers are not implemented.
- P0-04 time metadata: **PARTIALLY RESOLVED**; the foundation contract exists,
  but providers have not been migrated.
- P0-05 Truth/Forecast/Belief: **UNRESOLVED**.
- P0-06 draft conflict: **UNRESOLVED**.
- P0-07 synthetic 3DOF evidence: **UNRESOLVED**; no legacy algorithm code was
  migrated in this phase.
- P0-08 manoeuvre unknowns: **UNRESOLVED**.
- P0-09 direction semantics: **PARTIALLY RESOLVED**; new explicit FROM/TO
  contracts exist, but existing providers have not been migrated.
- P0-10 mock Planner: **UNRESOLVED**.
- P0-11 old project tests: **UNRESOLVED in this repository**. The separately
  recorded legacy baseline is `138 passed, 4 failed, 1 error`; the five failures
  are attributed to missing external real sea-ice data.
- P0-12 quality/uncertainty: **PARTIALLY RESOLVED**; availability/evidence
  structures exist, but propagation is not implemented.

## 12. Out of Scope and Next Phase

The next phase should address the Environment Data Contract only. It must reuse
these Foundation contracts and must not define parallel time, availability,
direction, units, or evidence models. This phase does not authorize environment
providers, risk, vessel capability, planner, graph, provider interpolation, or
frontend work.
