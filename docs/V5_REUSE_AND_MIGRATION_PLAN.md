# V5.0 Reuse and Migration Plan

Status: architecture freeze. This plan changes no business code. The WEB repository is the only main engineering project. The former Motion Primitive / State Lattice repository is an asset and baseline source only.

## 1. V5.0 Target Architecture

```text
Raw / Synthetic Data
  -> Truth / Forecast / Observation / Belief
  -> EnvironmentQuery
  -> Multi-scale Environment Map
  -> Sparse Time-dependent Route Graph
  -> EdgeEvaluator
  -> Time-dependent Baseline Planner
  -> RG-MPAO* -> CF-JRS -> RCOS
  -> Navigation API -> WEB UI
```

The mainline must not restore a 50 nmi dense search over `position x heading x speed x time`. Motion primitives are permitted only for critical turns, edge junctions, speed transitions, narrow ice channels, local hull-collision validation, and maneuver-feasibility witnesses.

## 2. WEB Project Asset Classification

### KEEP

| Source module | Target role | Reason |
|---|---|---|
| `core/models.py` basic location/environment DTOs | Contract foundation | Pydantic validation and WGS84 boundary are useful. |
| `services/environment_service/providers.py` and source providers | Provider layer | Real-data adapters, interpolation and source isolation exist. |
| `EnvironmentQueryService` | EnvironmentQuery adapter | Fault-isolated point/batch querying is the right boundary. |
| `EnvironmentTimeManager` | Simulation clock | UTC normalization and scenario clock are reusable. |
| `EnvironmentGridBuilder` | Map-query cache | Useful cache/batch pattern, not a planner graph. |
| vessel profile JSON/models | Vessel-data source | Geometry, PC class and published static facts are reusable evidence inputs. |
| chart service, OpenLayers frontend, visualization | Navigation UI infrastructure | Map/projection/layer infrastructure is production-relevant. |
| existing WEB tests | Regression base | Provider, API and UI tests provide a starting safety net. |

### REFACTOR

| Source module | Target role | Required change |
|---|---|---|
| `core/models.py` environment fields | V5 data contract | Add explicit time metadata, quality, uncertainty, vector-first direction semantics. |
| `EnvironmentQueryService` | Belief-only query facade | Enforce availability/cutoff instead of nearest-time across a future boundary. |
| `EnvironmentTimeManager` | Time service | Separate simulation clock from forecast issue/valid semantics. |
| `EnvironmentGridBuilder` | Multi-scale map | Add scale/version/quality semantics; do not turn it into dense state space. |
| vessel service/profile | VesselCapability | Make actual draft one source of truth and attach parameter evidence. |
| depth safety | Safety Guard check | Convert to PASS/FAIL/UNKNOWN; use `actual_draft`, not a second constant. |
| FastAPI routes | Navigation API | Version contracts and separate synchronous UI reads from future planner work. |
| OpenLayers environment display | Navigation visualization | Show route alternatives, data quality, evidence and degraded state. |

### REWRITE

`PlannerService` is a mock and must be replaced later by a contract-compliant time-dependent baseline facade. TruthWorld, ForecastWorld, Observation, BeliefWorld, SparseGraph, Corridor, EdgeEvaluator facade, Navigation State Machine, Safety Guard orchestration, ETA/STW/SOG/COG/Heading semantics and experiment framework require new implementations. This is not authorization to implement them in this phase.

## 3. Former Primitive Project Asset Classification

### MIGRATE

- `environment/protocol.py`, `environment/state.py`: EnvironmentQuery and EnvironmentSample interface patterns.
- `environment/collision.py`: local capsule/object/tube collision checking as evidence-producing validation.
- `planning/physical_state.py`, `planning/goal.py`, `planning/continuity.py`: explicit state, goal and connector-continuity patterns.
- `lattice/primitive.py`: immutable local maneuver evidence schema, never a required high-level Edge type.
- `lattice/primitive_serialization.py`: JSON/NPZ integrity, hash and version pattern.

### REFACTOR

- `polar/edge_evaluator.py`, `polar/constraint_field.py`: primary EdgeEvaluator reference; remove lattice primitive, static map and synthetic-vessel coupling.
- `environment/rollout.py`, `interpolation.py`, `views.py`: retain time sampling only through V5 Belief/EnvironmentQuery.
- `geodesy/local_frame.py`, `geodesy/types.py`, `vessel/state.py`: enforce ENU and bearing/math-yaw types.
- `vessel/model_3dof.py`, `vessel/simulator.py`, control/trim code: optional synthetic local maneuver oracle only, with explicit evidence status.
- `lattice/endpoint_solver.py`: keypoint/junction connector only, bounded and cached.
- `option_search` dominance/archive concepts: preserve concepts/tests for future RG-MPAO*, but rebuild identity around sparse-graph labels.

### BASELINE_ONLY

- `paper/baselines.py`: grid A*, risk-weighted A*, state-lattice A*, D* Lite and sequential alternatives remain research comparators.
- `search/astar.py`, `time_search/astar.py`, `time_search/graph.py`, `time_search/heuristic.py`: controlled full-lattice or local benchmark implementations only.
- frozen primitive-library artifacts: synthetic fixtures and reproducible benchmark inputs only.
- existing primitive-project tests: regression/reference assets, not proof of real-vessel calibration.

### REMOVE_FROM_MAINLINE

- Any global `500 m x 8 heading x 3 speed x time-bin` lattice expansion.
- Any mainline successor loop that evaluates long primitive sample arrays across the whole 50 nmi domain.
- Bare `heading_rad` crossing navigation/dynamics boundaries.
- Claims that synthetic 3-DOF or primitive artifacts are validated Xuelong-2 maneuver performance.
- Direct planner access to NetCDF, GeoTIFF or raw provider arrays.

## 4. Final Motion Primitive Use

Allowed: critical turn, route-segment connection, speed transition, narrow ice channel, local hull-collision validation, maneuver-feasibility witness.

Forbidden: 50 nmi dense high-level search or a requirement that every SparseGraph edge be a `MotionPrimitive`. A high-level edge may carry an optional `LocalManeuverEvidence` reference only.

## 5. Migration Matrix

| Source Project | Source File / Module | Current Responsibility | Target Module | Action | Migration Method | Dependencies | Required Tests | Research Value | Engineering Value | Risk | Priority |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WEB | `core/models.py` | DTOs | V5 contracts | REFACTOR | Versioned adapters; explicit semantics | time/units | schema and units | High | High | P0 | 0 |
| WEB | environment providers | data access | provider layer | KEEP | Preserve behind query facade | PolarData | source/time/vector tests | Medium | High | High | 1 |
| WEB | `environment_query.py` | aggregate query | EnvironmentQuery | REFACTOR | Belief-only availability gate | BeliefWorld | future-leakage/batch tests | High | High | P0 | 1 |
| WEB | `time_manager.py` | clock | time service | REFACTOR | split simulation/issue/valid time | contracts | UTC/cutoff tests | High | High | P0 | 1 |
| WEB | `grid.py` | sampled cache | multi-scale map | REFACTOR | scale-aware adapter | EnvironmentQuery | cache/scale tests | Medium | High | Medium | 3 |
| WEB | vessel profile/service | static vessel data | VesselCapability | REFACTOR | evidence-valued parameters | evidence | draft consistency tests | High | High | P0 | 2 |
| WEB | `depth_safety.py` | depth check | Safety Guard | REFACTOR | three-valued check | capability/belief | PASS/FAIL/UNKNOWN | Medium | High | P0 | 2 |
| WEB | PlannerService | mock response | baseline facade | REWRITE | new sparse-graph contract | graph/evaluator | route/ETA failure tests | High | High | P0 | 6 |
| WEB | FastAPI/UI/tests | host/display/tests | Navigation API/UI | REFACTOR | contract consumers | API contracts | API/UI regression | Medium | High | Medium | 8 |
| Primitive | `environment/protocol.py`, `state.py` | environment DTO/protocol | EnvironmentQuery | MIGRATE | map fields to V5 schema | contracts | batch/metadata tests | High | High | High | 1 |
| Primitive | `polar/edge_evaluator.py` | primitive edge evaluation | EdgeEvaluator | REFACTOR | geometry edge + optional witness | query/capability | feasibility/time/risk tests | High | High | P0 | 5 |
| Primitive | `polar/constraint_field.py` | constraints | evaluator checks | REFACTOR | split named checks | belief/capability | per-check tests | High | High | P0 | 5 |
| Primitive | `environment/collision.py` | capsule collisions | local validation | MIGRATE | evidence-producing local service | geometry | sampling convergence | High | Medium | High | 5 |
| Primitive | `vessel/state.py`, geodesy | state/frame | geometry/state contracts | REFACTOR | typed bearing/yaw boundary | contracts | cardinal/round-trip | High | High | P0 | 1 |
| Primitive | 3DOF/simulator | synthetic dynamics | local oracle | REFACTOR | label synthetic, scope local | evidence | stability/label tests | Medium | Low | P0 | 5 |
| Primitive | primitive/endpoint/serialization | connectors/assets | local evidence | MIGRATE/REFACTOR | immutable local assets only | local oracle | hash/continuity tests | High | Medium | High | 5 |
| Primitive | time search | timed lattice | benchmarks | BASELINE_ONLY | isolate configuration | fixtures | reproducibility/limit tests | High | Low | High | 7 |
| Primitive | option search | labels/archive | future RG-MPAO* | REFACTOR | reuse concepts, not keys | SparseGraph | dominance tests | High | Medium | High | 8 |
| Primitive | `paper/baselines.py` | baselines | experiments | BASELINE_ONLY | freeze and record config | evidence | parity/run evidence | High | Low | Medium | 7 |

## 6. P0 Issues

| ID | Required resolution before affected phase |
|---|---|
| P0-01 | Define and test navigation bearing versus mathematical yaw conversion. |
| P0-02 | Enforce ENU x=East/y=North and angle-frame contracts. |
| P0-03 | Block future nearest-time forecast/observation leakage. |
| P0-04 | Carry source, issue, valid and observation time metadata. |
| P0-05 | Implement Truth/Forecast/Observation/Belief separation. |
| P0-06 | Resolve 7.85 m profile versus legacy 10 m + 2 m UKC draft split. |
| P0-07 | Mark legacy 3-DOF parameters synthetic, never validated Xuelong-2. |
| P0-08 | Treat Rmin, yaw-rate, acceleration/deceleration and stopping distance as UNKNOWN until evidenced. |
| P0-09 | Remove bare cross-layer `direction` fields from core contracts. |
| P0-10 | Replace mock PlannerService only after contracts/graph/evaluator exist. |
| P0-11 | Run and record complete primitive-project pytest before migration claims. |
| P0-12 | Define quality/uncertainty propagation and UNKNOWN behavior. |

## 7. Small-Step Migration Order

Phase 0 Contracts; Phase 1 Coordinate/Unit/Direction/Time; Phase 2 Environment Data Contract; Phase 3 Truth/Forecast/Observation/Belief; Phase 4 VesselCapability; Phase 5 EdgeEvaluator migration; Phase 6 SparseGraph; Phase 7 time-dependent A* baseline; Phase 8 RG-MPAO*; Phase 9 CF-JRS; Phase 10 RCOS; Phase 11 real-data replay, Monte Carlo and experiments.

No phase authorizes an all-at-once refactor.

## 8. Paper Asset Retention

The old grid A*, risk-weighted A*, state-lattice A*, D* Lite and sequential alternatives must not be deleted. They remain auditable research baselines. State-lattice A* is explicitly a synthetic full-lattice comparator, not the V5 planner and not Hybrid A*.

## 9. Migration Gates

- Gate 0: V5 contracts frozen and contract tests specified.
- Gate A: Environment, VesselCapability, EdgeEvaluator, SparseGraph and time-dependent A* baseline pass foundation tests.
- Gate B: RG-MPAO* stably returns reasonable K=1/2/3 route sets.
- Gate C: CF-JRS supports Reveal, Commitment and WAIT.
- Gate D: RCOS runs closed loop stably.

All P0 items above are planned but unresolved until code and tests exist.
