# V5.0 Engineering Contracts

Status: frozen design contract. This document defines future interfaces only; it does not implement them.

## 0. Mainline Boundary

```text
Raw / Synthetic Data -> Truth / Forecast / Observation / Belief
-> EnvironmentQuery -> Multi-scale Environment Map
-> Sparse Time-dependent Route Graph -> EdgeEvaluator
-> Time-dependent Baseline Planner -> RG-MPAO* -> CF-JRS -> RCOS
-> Navigation API -> WEB UI
```

The WEB repository is the only main project. Planners read only BeliefWorld through EnvironmentQuery. They may not read NetCDF, GeoTIFF, xarray, raster arrays, or provider internals. The 50 nmi dense motion-primitive lattice is baseline-only.

## A. Coordinate Contract

- Geographic coordinates: WGS84 latitude/longitude; degree only at geographic/API boundaries.
- Local planning coordinates: Local ENU metric frame, `x = East`, `y = North`, unit m.
- `navigation_bearing` / `navigation_heading`: 0 = True North; positive clockwise.
- `math_yaw`: 0 = East; positive counter-clockwise.
- Internal angle unit: rad.

The unique conversion is:

```text
math_yaw = wrap_2pi(pi/2 - navigation_bearing)
navigation_bearing = wrap_2pi(pi/2 - math_yaw)
```

Required boundary functions are `bearing_to_math_yaw(bearing_rad)` and `math_yaw_to_bearing(yaw_rad)`. Generic `heading_rad` is forbidden across boundaries. Use semantic names such as `navigation_bearing_rad` and `math_yaw_rad`. The old 3-DOF dynamics may use mathematical yaw (`xdot = cos(psi)*u - sin(psi)*v`, `ydot = sin(psi)*u + cos(psi)*v`, `psi_dot = r`); Navigation API uses navigation bearing.

## B. Unit Contract

Core algorithms use SI only: distance/position m, time/duration s, speed/STW/SOG/current m/s, angle rad, angular rate rad/s, power W, energy/work J, force N, acceleration m/s2, depth m, wave height m. API/UI may display nm, kn, degree, MW and kWh only through explicit boundary serializers. Every numeric field has named unit semantics. `1 kn = 0.514444... m/s`; `1 nm = 1852 m`.

## C. Direction Contract

- `wind_direction_from`: wind origin, true-north clockwise.
- `wave_direction_from`: wave origin, true-north clockwise.
- `current_direction_to`: current destination, true-north clockwise.

Core algorithms use east/north vectors first, for example `wind_east/north` and `current_east/north`. A generic `direction` field is forbidden in core contracts. From/to conversion occurs in a provider adapter and is tested.

## D. Time Contract

| Field | Meaning |
|---|---|
| `simulation_time` | Simulation clock, not a source timestamp. |
| `observation_time` | Time an observation occurred. |
| `source_time` | Source catalogue timestamp. |
| `issue_time` | Forecast publication/creation time. |
| `valid_time` | Time represented by forecast/analysis data. |
| `ingest_time` | Time the system received data. |

All internal times are timezone-aware UTC. `PlannerAt(t)` may use only observations with `observation_time <= t` and `ingest_time <= t`, and forecasts with `issue_time <= t` and applicable valid time. Truth is forbidden to planners. If availability cannot be proved, return stale/missing/unknown rather than a future value.

```text
LeadTime = valid_time - issue_time
DataAge = simulation_time - explicit_reference_time
Staleness = simulation_time - valid_time
```

A nearest-time provider may not cross an availability boundary.

## E. Truth / Forecast / Observation / Belief Contract

- **TruthWorld**: simulation ground truth for evaluator/metrics only.
- **ForecastWorld**: issued, versioned forecasts with uncertainty.
- **Observation**: radar, visual, satellite or vessel observation with observation time, ingest time, source, quality and uncertainty.
- **BeliefWorld**: time-valid fusion of ForecastWorld and Observation.

SparseGraph, EdgeEvaluator, baseline A*, RG-MPAO*, CF-JRS and RCOS access only BeliefWorld through EnvironmentQuery. Truth cannot be treated as forecast and future observations cannot be backfilled into historical belief.

## F. Data Availability / Quality Contract

Allowed availability states are `AVAILABLE`, `AGING`, `STALE`, `MISSING`, `CONFLICT`, `INVALID`. Every environmental field carries quality, uncertainty, source and applicable time metadata. `UNKNOWN` never becomes SAFE by default.

## G. Feasibility Contract

Each check returns exactly `PASS`, `FAIL` or `UNKNOWN`. Required checks include geometry, depth, ice, operation, power, manoeuvre, dynamic object and data quality.

```text
any FAIL -> FAIL
no FAIL and any UNKNOWN -> UNKNOWN
all PASS -> PASS
```

PASS means only that the check passed within current data, model and evidence applicability; it is not an absolute safety guarantee. Each result carries reason codes, threshold/model version, time metadata and evidence.

## H. VesselCapability Contract

VesselCapability includes identity, geometry, classification/PC class, actual draft, propulsion, speed capability, ice capability, maneuver capability, energy/power model and evidence. Each parameter is `value`, `unit`, `source`, `status`, `applicability`, and `confidence`. Allowed statuses: `STANDARD`, `VESSEL_DATA`, `LITERATURE`, `PROJECT_ASSUMPTION`, `CALIBRATED`, `UNKNOWN`.

Legacy 3-DOF parameters and primitive artifacts are `SYNTHETIC_MODEL` or `PROJECT_ASSUMPTION` evidence, never validated Xuelong-2 dynamics. `SYNTHETIC_MODEL` is an additional allowed status for synthetic research assets. Actual draft comes from one VesselOperatingState; the WEB profile 7.85 m and legacy depth constants 10 m + 2 m UKC must not coexist in a planner. Rmin, yaw-rate envelope, acceleration, deceleration and stopping distance remain UNKNOWN until evidenced or calibrated.

## I. EnvironmentQuery Contract

```python
query(x_m, y_m, t, *, scale=None) -> EnvironmentSample
query_batch(points) -> list[EnvironmentSample]
```

Internal calls use local ENU x/y. A geographic adapter may accept WGS84, but exposes frame and origin. The sample contains depth; ice concentration/thickness/type/composition/drift; wind east/north and from metadata; wave Hs/period/from metadata; current east/north and to metadata; quality, uncertainty and full time metadata. Missing/expired/out-of-coverage values are explicit, not zero-filled. Searchers never access raw arrays.

## J. EdgeEvaluator Contract

```text
EvaluateEdge(edge, state_in, target_stw, mode, vessel_capability, belief)
```

`EdgeResult` includes feasibility and reasons, state_out, duration, arrival_time, distance, speed profile, STW profile, SOG profile, heading profile, COG/track profile, energy or explicitly labelled proxy, risk vector, risk sources, quality, evidence and environment dependencies. EdgeEvaluator is the one shared segment-evaluation entry point; algorithms must not implement separate ice/depth/current/speed formulas. It may invoke local maneuver evidence, but a high-level input cannot require a MotionPrimitive.

## K. Sparse Time-dependent Graph Contract

Node: `node_id`, local/geographic position, `node_type`, `corridor_id`, scale, time metadata, permitted modes/speed domain, environment/depth/ice summaries, quality and version.

Edge: `edge_id`, `from_node`, `to_node`, reference geometry/polyline, corridor, allowed modes/STW domain, time validity, static constraints, environment dependency IDs, cost hints, version and optional `local_maneuver_evidence_refs`.

Corridor: `corridor_id`, centerline/boundary or navigable area, scale, generation method, depth/ice/geometry thresholds, entry/exit nodes, topology labels, quality and version.

High-level edges do not require MotionPrimitive. The graph stays sparse and time-dependent; it must not expand the full 50 nmi position/heading/speed/time product.

## L. Planner State Contract

Planner labels include node, arrival time, STW/speed state, incoming course, mode, cost vector and parent. Under time dependence and WAIT, a node may retain finite nondominated labels; earliest-arrival-only is not a universal rule.

## M. Navigation Output Contract

The eventual Navigation API exposes recommended and alternative routes, recommended STW, expected SOG, planned COG/track, recommended heading, ETA, XTE, next waypoint, remaining distance/time, risk sources, data quality, confidence/evidence, route-switch conditions and plan validity. The system is advisory only and never directly controls the vessel.

## N. Research / Engineering Separation

Engineering foundation includes providers, NetCDF, cache, API, database, tiles, frontend, deployment and observability. Research-method modules are EdgeEvaluator, SparseGraph, RG-MPAO*, CF-JRS and RCOS. Each research module must link mathematical definitions, pseudocode, implementation, unit/property tests, a baseline, ablations, experiments and limitations. Full state-lattice, D* Lite and risk A* stay baselines, not renamed V5 algorithms.

## O. Experiment Evidence Contract

Every run records `run_id`, `scenario_id`, `seed`, `git_commit`, `config_hash`, `environment_version`, `vessel_version`, `algorithm_version`, `timestamp`, `runtime`, `raw_metrics` and `result_path`, plus contract version, cutoff, baseline, Truth-evaluator flag and artifact hashes. SyntheticEnvironment remains a permanent reproducible fixture.

## P. Parameter Evidence Contract

Every important parameter carries value, unit, source, status and applicability. Standard, literature, vessel data, project assumption, calibrated and unknown must remain distinguishable. Unknown-source weights or safety factors cannot silently become physical truth.

## Q. Safety Principle

Hard safety constraints are separate from economic optimization. Large penalties do not replace explicit infeasibility. `UNKNOWN != SAFE`. A planner may return `NO_ROUTE`, `WAIT`, `EXIT`, `SAFE_HOLD` or `HUMAN_INTERVENTION`; it must not invent a route merely to produce output.

## P0 Closure Matrix

Contract definitions do not mean existing source code is fixed. Every row remains unresolved until the listed code and tests exist.

| P0 issue | Audit finding | Contract section | Resolution | Still unresolved? | Required code change later |
|---|---|---|---|---|---|
| P0-01 bearing/math yaw | Navigation and dynamics angles can be mixed | A | Unique conversion pair and semantic fields | YES | Typed conversion adapter and tests |
| P0-02 ENU frame | x/y and angle frame are not enforced | A | Local ENU and explicit frame IDs | YES | Frame-aware state contracts |
| P0-03 future leakage | Nearest-time forecast can use future data | D/E | PlannerAt cutoff and availability gate | YES | Cutoff-aware providers and belief |
| P0-04 time metadata | Source/issue/valid/observation fields are absent | D/F/I | Required metadata and age metrics | YES | Extend EnvironmentQuery models |
| P0-05 world layers | No Truth/Forecast/Observation/Belief separation | E | Four explicit worlds and planner boundary | YES | World adapters and fusion |
| P0-06 draft conflict | 7.85 m profile versus 10 m + 2 m legacy | H | Single operating draft source | YES | Remove duplicate constants and audit |
| P0-07 synthetic 3DOF evidence | Synthetic parameters can be read as vessel data | H/P | Explicit synthetic/project status | YES | Tag models/artifacts and gate claims |
| P0-08 maneuver unknowns | Rmin/yaw/accel/stop data are unvalidated | H | Unknown until evidence/calibration | YES | Capability evidence and fail-closed checks |
| P0-09 direction semantics | Cross-layer bare direction fields exist | C/I | From/to names and vectors | YES | Rename/adapt models and reject generic fields |
| P0-10 mock planner | WEB PlannerService returns mock | J/L/M | Contract baseline is a later phase | YES | Replace mock after graph/evaluator gates |
| P0-11 old tests not run | Primitive audit did not execute complete pytest | O/N | Run evidence is mandatory | YES | Execute/archive complete primitive test run |
| P0-12 quality/uncertainty | No unified propagation contract | F/E/I | Availability, quality and uncertainty required | YES | Add propagation and UNKNOWN tests |

The first future source module should be the contract foundation for coordinate/unit/direction/time and typed environment/vessel DTOs. Do not modify it as part of this documentation freeze.
