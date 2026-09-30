# V5 Function Gap Matrix

This is a gap analysis, not the final functional specification. It compares
the current WEB workbench with the frozen V5 architecture and product target.

| Function | Current UI | Current Backend | Current Status | Target Function | Action | Priority | Research Relevance | Engineering Relevance |
|---|---|---|---|---|---|---|---|---|
| Navigation State | Context/monitoring placeholders | No live state feed | Placeholder | Position, STW/SOG, heading/COG, phase, data quality | REWORK | MVP | Medium | High |
| Environment Layers | Chart, bathymetry, ice, wind, current, wave toggles | Provider/tile/field endpoints | Partial real | Belief-backed layers with explicit quality/time | EXTEND | MVP | High | High |
| Timeline | Winter/summer hourly playback | Environment clock endpoint | Partial real | Simulation, issue, valid, observation and ingest semantics | EXTEND | MVP | High | High |
| Task Setup | Session-local name, start, destination, departure, vessel, preference | No task persistence endpoint | Partial | Versioned navigation task and constraints | EXTEND | MVP | Medium | High |
| Manual Route Editing | Start/destination map picks only | No route editor API | Not implemented | Captain waypoint/segment editing | NEW | MVP | Medium | High |
| Captain Modified Route | None | None | Not implemented | CaptainDraftRoute with edit history and validation | NEW | MVP | High | High |
| Active Route | None | None | Not implemented | ActiveRoute lifecycle and activation rules | NEW | MVP | High | High |
| Recommended Route | Candidate route placeholder | `/api/planner` returns mock | Mock/placeholder | RecommendedRoute from sparse time-dependent planner | REWORK | MVP | High | High |
| Alternative Routes | Candidate count always zero | No alternatives | Not implemented | K=1/2/3 route set with comparison | NEW | P1 | High | Medium |
| Waypoint Editing | Start/destination picks | None | Partial | Add/delete/drag/reorder/lock waypoints | EXTEND | MVP | Medium | High |
| XTD / corridor | None | None | Not implemented | Corridor geometry, XTD, route validity | NEW | P1 | High | High |
| Manual STW | No control | None | Not implemented | Per-route/leg manual STW constraints | NEW | P1 | Medium | High |
| STW / SOG | Empty `--` fields | No live vessel/current fusion | Not implemented | Recommended STW and expected SOG with current | NEW | MVP | High | High |
| Heading / COG | Empty/static heading field | No live feed | Not implemented | Semantic heading and COG/track display | NEW | MVP | High | High |
| ETA | Placeholder label | Planner mock only | Not implemented | Arrival time with validity/uncertainty | NEW | MVP | Medium | High |
| XTE | Placeholder “偏航距离” | None | Not implemented | Cross-track error and alerting | NEW | MVP | Medium | High |
| Route Validation | No route | No EdgeEvaluator | Not implemented | PASS/FAIL/UNKNOWN checks and reasons | NEW | MVP | High | High |
| Risk Explanation | `未计算` rows | No risk engine | Placeholder | Named risk sources and evidence | NEW | MVP | High | High |
| Data Quality | Layer ready/error and matched time only | Provider metadata | Partial | Availability, uncertainty, source and time metadata | EXTEND | MVP | High | High |
| Truth / Forecast / Observation / Belief | None | Current providers/query facade only | Not implemented | Explicit world separation and belief boundary | NEW | MVP | High | High |
| 50 nm Tactical Planning | No route domain control | No planner | Not implemented | Local tactical planning horizon and map context | NEW | MVP | High | High |
| SparseGraph | None | None | Not implemented | Sparse time-dependent route graph | NEW | P1 | High | Medium |
| EdgeEvaluator | None | None | Not implemented | Shared edge feasibility/cost/evidence evaluator | NEW | P1 | High | High |
| RG-MPAO* | None | None | Not implemented | Multi-route option search | NEW | P2 | High | Medium |
| CF-JRS | None | None | Not implemented | Reveal/Commitment/WAIT route switching | NEW | P2 | High | High |
| RCOS | None | None | Not implemented | Closed-loop route optimization/supervision | NEW | P2 | High | High |
| WAIT / EXIT / SAFE_HOLD | None | None | Not implemented | Explicit no-route and degraded-operation outcomes | NEW | P1 | High | High |
| AIS | “未接入” status | No AIS endpoint | Not implemented | Dynamic vessel awareness and quality | NEW | P1 | Medium | High |
| Radar | None | None | Not implemented | Optional near-field observation source | NEW | LATER | Medium | Medium |
| Dynamic ice objects | Raster only | Ice provider fields, no object layer | Not implemented | Dynamic obstacle/object representation | NEW | P2 | High | High |
| Near-field safety | No UI | Depth API only; no route guard | Partial backend | Explicit safety guard and UNKNOWN behavior | EXTEND | MVP | High | High |
| Replay | Timeline only | No replay run contract | Not implemented | Reproducible data/route replay | NEW | P2 | High | Medium |
| Experiment mode | None | No experiment UI | Not implemented | Run metadata, seed, baseline and artifacts | NEW | LATER | High | Medium |
| Route versioning | No route | None | Not implemented | Environment/belief/graph/plan version references | NEW | P1 | High | High |
| Save/load route | Task session only | None | Not implemented | Persisted route drafts and active route | NEW | MVP | Medium | High |
| Undo/redo | None | None | Not implemented | Captain edit history | NEW | P1 | Medium | High |
| Must-pass | None | None | Not implemented | Hard route waypoint constraint | NEW | P1 | Medium | High |
| Avoid-area | None | None | Not implemented | Polygon hard/soft exclusion | NEW | P1 | High | High |
| Locked waypoint/segment | None | None | Not implemented | Captain locks respected by replanning | NEW | P1 | High | High |
| Preferred corridor | None | None | Not implemented | Captain corridor preference | NEW | P1 | High | High |
| Route acceptance | No action | None | Not implemented | Accept/reject recommendation with reason | NEW | MVP | Medium | High |
| Alternative switching | None | None | Not implemented | Captain-controlled route switch and revalidation | NEW | P1 | High | High |
| Alerts/events | Empty event panel | No event stream | Placeholder | Data, safety, deviation and replan alerts | NEW | MVP | Medium | High |
| Captain-in-the-loop boundary | Advisory text only | No route lifecycle | Partial concept | RecommendedRoute → CaptainDraftRoute → ActiveRoute | REWORK | MVP | High | High |

## Current-vs-target interpretation

The strongest existing assets are the OpenLayers map/projection/layer lifecycle,
provider-backed environment display, source readiness metadata, UTC environment
timeline, public vessel profile endpoint, and regression tests. These should be
kept and extended.

The largest product gaps are route lifecycle, manual captain editing,
validation/evidence, live state, monitoring, risk explanation, and the
Truth/Forecast/Observation/Belief boundary. The planner panel is a useful UI
location but is currently a placeholder and should be reworked only after the
foundation contracts, environment data contract, graph, and evaluator gates.

## Captain-in-the-loop distance assessment

The current system already provides a map, coordinate picking, a task form, and
an advisory statement. It lacks the data and interaction model for:

1. RecommendedRoute generated by an algorithm.
2. Captain drag of waypoints or segments.
3. Insert/delete/reorder and lock semantics.
4. Must-pass, avoid-area, and preferred-corridor constraints.
5. Manual STW and route validation.
6. CaptainDraftRoute persistence and version history.
7. ActiveRoute acceptance, activation, deviation detection, and revalidation.
8. Alternative route comparison and switching.

The three route identities must be explicit in a future contract:
`RecommendedRoute`, `CaptainDraftRoute`, and `ActiveRoute`. They do not exist in
the current code and should not be conflated with the current empty
`RouteSummary` list.

## V5 conflicts to resolve before functional freeze

- The current timeline is a UI/environment display clock, not a ForecastWorld or
  BeliefWorld. Its semantics must not be promoted by naming alone.
- Existing provider DTOs still use legacy direction/time fields in places;
  V5 `FROM`/`TO`, UTC metadata, and availability semantics need adapters before
  planner consumption.
- The UI shows static source/readiness labels and some top-bar “可用” values;
  these must be separated from evidence-backed data quality.
- The current vessel panel combines static capability and empty current-state
  fields; V5 should separate VesselCapability from live VesselState.
- `/api/planner` is a mock boundary, not a route-planning implementation.

## Scope boundary

This matrix does not authorize implementation, final functional-spec freezing,
autopilot, steering/propulsion control, complete COLREG autopilot, berthing,
stability software, or ECDIS certification functions. Those remain outside the
current advisory decision-support boundary.
