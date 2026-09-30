# PolarOptionNav-System-V2 V5 Navigation Functional Specification

Status: Frozen Product Functional Baseline v1.0.
This document freezes product behavior and scope; it does not implement APIs,
planners, route editing, or UI changes.

Open Questions remain implementation/research gates and do not invalidate the
frozen product scope.

## 1. Product Purpose

PolarOptionNav-System-V2 is a polar vessel tactical intelligent navigation and
decision-support system for approximately the next 50 nautical miles. It
supports a captain's decision; it does not directly control a rudder, azimuth
thruster, propulsion system, or autopilot.

The system is advisory. It does not replace ECDIS and makes no ECDIS, BAM, or
autonomous-navigation certification claim.

## 2. Scope

The product accepts global-route context, a navigation task, `VesselCapability`,
`VesselState`, and time-valid environment/belief data including forecasts and
observations. It produces a recommended route set, route validation, speed and
track guidance, ETA/XTE, risk and data-quality explanations, and explicit
decision-support outcomes such as `WAIT`, `EXIT`, and `SAFE_HOLD`.

The tactical horizon targets about 50 nm. It is a planning scale, not a rule
that every task must be exactly 50 nm.

## 3. Existing System Baseline

The current product is one Vue/OpenLayers workbench, not multiple independent
pages. The existing shell is retained:

`TopStatusBar`, `MainNavigation`, `TaskPanel`, `VesselPanel`,
`EnvironmentPanel`, `PlanningPanel`, `MonitoringPanel`, `EventPanel`, the
central map, `ContextPanel`, and `EnvironmentTimeline`.

Existing real or partly real infrastructure includes chart and environment
layer display, provider readiness, UTC environment time, map selection and
measurement, public vessel profile retrieval, and regression-tested provider
boundaries. Task state is currently session-local. The planner endpoint is a
mock and is not currently called by the UI. Route editing, live vessel data,
monitoring, risk calculation, alerts, and route persistence are not yet
implemented.

## 4. UI Information Architecture

The workbench remains a three-column workspace with a top status bar and bottom
timeline:

```text
TopStatusBar
  MainNavigation -> one active left workbench panel
  Left: Task | Vessel | Environment | Planning | Monitoring | Events
  Center: OpenLayers map and navigation/environment/risk layers
  Right: ContextPanel as Selection Inspector
EnvironmentTimeline
```

Classification of current components:

| Component | Product decision |
|---|---|
| Map, projection/layer lifecycle, environment panel, timeline | KEEP, then EXTEND with V5 metadata and route layers |
| TaskPanel, VesselPanel | EXTEND with persisted/versioned task and capability/state separation |
| PlanningPanel | REWORK in place around route lifecycle and planner states |
| MonitoringPanel, ContextPanel | REWORK around ActiveRoute and Selection Inspector objects |
| EventPanel | EXTEND from empty log to project-severity event stream |
| TopStatusBar | EXTEND with explicit data/planner/route state; never equate online with quality |

## 5. Core Navigation Workflows

### A. Planning Loop

```text
Task -> Environment/Belief -> Planner -> RecommendedRoute(s)
      -> Route Validation -> Captain Review
```

The planner reads only time-valid Belief data through `EnvironmentQuery`.
Failure returns a named reason and an explicit outcome; it does not invent a
route merely to fill the UI.

### B. Captain Edit Loop

```text
RecommendedRoute -> CaptainDraftRoute -> Manual Edit -> Revalidation
                  -> Accept/Reject -> ActiveRoute
```

Every captain modification creates a new draft/version and revalidates it. A
draft edit never mutates `ActiveRoute` in place.

### C. Navigation Monitoring Loop

```text
ActiveRoute + VesselState -> Current Leg -> XTE
  -> STW/SOG -> Heading/COG -> ETA -> Route validity
```

Monitoring distinguishes measured state, planned values, recommended values,
and unavailable/unknown values.

### D. Environment/Replan Loop

```text
New observation/environment update/deviation -> Belief update
  -> ActiveRoute re-evaluation -> Continue | Updated Recommendation
  | Alternative | WAIT | EXIT | SAFE_HOLD -> Captain decision
```

The system must never silently replace `ActiveRoute`. Any proposed change shows
what changed, why it changed, the new validity/ETA/risk, and the captain action
required.

## 6. Route Lifecycle

The following are distinct product objects:

| Object | Meaning |
|---|---|
| `RecommendedRoute` | Algorithm proposal, immutable as an accepted record. |
| `AlternativeRoute` | Optional backup proposal with a distinct trade-off, bottleneck, topology, or risk source. |
| `CaptainDraftRoute` | Captain-editable route derived from a recommendation or created manually. |
| `ActiveRoute` | Captain-accepted route used for monitoring; only explicit captain activation changes it. |
| `ArchivedRouteVersion` | Historical immutable route/version retained for audit and replay. |

Route identity, validation result, and human workflow lifecycle are separate
dimensions. They must not be encoded as one overloaded status field.

### RouteRole

`RECOMMENDED`, `ALTERNATIVE`, `CAPTAIN_DRAFT`, `ACTIVE`, and `ARCHIVED` identify
what the route is in the product. An alternative remains a backup proposal; it
does not become active without explicit captain action.

### ValidationStatus

`UNCHECKED`, `CHECKING`, `VALID`, `CONDITIONAL`, and `INVALID` identify the
current result of required checks:

- `VALID`: all required checks pass for the applicable data, model, and evidence;
- `CONDITIONAL`: no hard failure is present, but a material `UNKNOWN`,
  applicability limit, data condition, or capability condition remains;
- `INVALID`: at least one hard safety check fails.

### LifecycleStatus

`DRAFT`, `PROPOSED`, `ACCEPTED`, `ACTIVE`, `SUPERSEDED`, and `ARCHIVED` identify
where the route is in the human workflow. Validation does not advance a route
through the human workflow.

For example, one route can be:

```text
RouteRole=ACTIVE, LifecycleStatus=ACTIVE, ValidationStatus=VALID
```

After an environment update, the same route can become:

```text
RouteRole=ACTIVE, LifecycleStatus=ACTIVE, ValidationStatus=CONDITIONAL
```

or even:

```text
RouteRole=ACTIVE, LifecycleStatus=ACTIVE, ValidationStatus=INVALID
```

In both cases the backend does not silently replace `ActiveRoute`. It triggers
safety/revalidation/replan processing and a captain decision. Algorithms must
never mistake `ValidationStatus` for `RouteRole`.

Algorithms may create recommendations and alternatives, but may not move a
route to `ACTIVE`.

## 7. Task Functions

`TaskPanel` is the entry point for a versioned navigation task. A task contains:

- `task_id`, name, vessel reference, departure/planning time;
- current start, local tactical goal, and global route context;
- tactical horizon target (default about 50 nm);
- planning intent/objective and captain constraints;
- notes, status, version, created/updated times.

The product supports Create, Edit, Save, Load, Duplicate, and Archive. The
current session-only task is a prototype state and is not the final contract.

## 8. Vessel Functions

The UI and backend must separate:

### VesselCapability

Identity, length, beam, actual operating draft, displacement when available, PC
class, propulsion, power, speed capability, ice capability, maneuver capability,
and evidence status. Each value carries unit, source, applicability, and
confidence/evidence. Unknown maneuver limits remain `UNKNOWN`.

### VesselState

Latitude, longitude, navigation heading, COG, STW, SOG, ROT when available,
timestamp, source, and sensor/data quality. Unknown fields display `UNKNOWN`,
never a fabricated zero or stale value presented as current.

## 9. Environment Functions

Existing chart, bathymetry, ice, wind, current, and wave layers are retained.
The future unified point inspector supports depth; ice concentration,
thickness, type/composition, partial concentration when available, and drift;
wind east/north and direction-from; current east/north and direction-to; and
wave Hs, period, and direction-from.

Every displayed sample may expose source, `source_time`, `issue_time`,
`valid_time`, `observation_time` when applicable, `ingest_time`, matched time,
availability, quality, and uncertainty. Provider readiness is a service health
signal, not data quality.

Missing is not zero and `UNKNOWN` is not safe.

## 10. Timeline Functions

The product distinguishes:

- **Planning Time**: the time at which the vessel decision is evaluated;
- **View Time**: the time currently inspected by the captain.

Changing View Time must not grant the planner future information that was not
available at Planning Time. The timeline reserves Now, previous/next, play/
pause, speed, future-forecast view, and replay mode. Current winter/summer
scenarios remain scenario shells; they are not named or treated as a
`ForecastWorld`.

## 11. Planning Functions

The PlanningPanel supports Plan, Replan, Clear Draft, recommendation and
alternative display, route comparison, CaptainDraftRoute, Validate, Accept,
Reject, Activate, Save, Load, Clone, Undo, and Redo.

The visible product language is route and decision language, not algorithm names.
`RG-MPAO*` appears in engineering/research documentation only; the UI shows a
recommended route and zero or more alternatives. K may be 1, 2, or 3 (or another
bounded configured value); it is not always three.

## 12. Manual Route Editing

Manual editing is an MVP/P1 product capability. It supports Add, Delete, Drag,
Insert, and Reorder waypoint; drag route segment to create a waypoint and
replace the affected geometry; Lock waypoint; Lock segment; Must-pass point;
Avoid-area polygon; Preferred corridor; Manual STW; Release constraint; Undo;
and Redo.

All edits produce `CaptainDraftRoute` and trigger revalidation. They do not
write directly to `ActiveRoute`.

## 13. Route Validation

Any draft modification, environment/belief update, relevant vessel-state
change, or deviation can trigger validation. The future `EdgeEvaluator` and
named safety checks return exactly `PASS`, `FAIL`, or `UNKNOWN` per check.

The UI aggregates checks as:

- `VALID`: all required checks pass;
- `CONDITIONAL`: no failure, but at least one material unknown or applicability
  condition remains;
- `INVALID`: at least one hard check fails.

Validation stores failure reasons, unknown reasons, check/evidence versions,
and applicable time. It recalculates distance, STW profile, SOG profile,
heading, COG, ETA, risk vector, quality, and route/version metadata; changing
only a polyline is insufficient.

## 14. Route and Leg Data

### Waypoint

`waypoint_id`, latitude/longitude, local ENU planning position, name, sequence,
XTD/corridor settings, turning information when available, arrival estimate,
captain lock, must-pass flag, notes, and optional time window.

### Leg

`leg_id`, from/to waypoint, distance, geometry, planned COG, recommended heading,
target STW, expected SOG, entry/exit time, travel time, XTD/corridor, minimum
depth, environment summary, risk vector and sources, quality, unknown reasons,
validation status, and environment/belief/graph/plan versions.

## 15. Navigation Monitoring

MonitoringPanel displays ActiveRoute, current position, heading, COG, STW, SOG,
ROT when available, current leg, next waypoint, bearing and distance to it,
XTE, recommended STW, expected SOG, recommended heading, planned COG, ETA to
next waypoint and tactical goal, remaining distance/time, route validity,
checked prefix, plan age, planner state, and data state.

Near-field/safety evaluation and the 50 nm tactical planner are asynchronous.
While the tactical planner updates, a valid checked ActiveRoute prefix can
continue. The UI may show `ActiveRoute VALID`, `Checked Ahead 10.8 nm`, and
`Tactical Planner UPDATING`; it must not show STOP unless a safety guard actually
requires it.

## 16. Risk and Safety

Risk is multi-dimensional, not only a scalar. The UI exposes Depth, Ice,
Weather, Maneuver, Dynamic Object, and Uncertainty/Data dimensions, with where,
why, when, source, evidence, and quality where known.

Hard Safety Status is separate from optimization/risk indicators. A hard failure
cannot be compensated by a low economic risk score. `UNKNOWN != SAFE`.

## 17. Events and Alerts

EventPanel remains the event stream and adds categories: Navigation,
Environment, Data Quality, Safety, Planner, Route Lifecycle, Captain Action,
and Sensor. Examples include new ice data, validation changed, route
invalidated, alternative available, captain route accepted, XTE exceeded, data
stale, and sensor lost.

The initial UI severity vocabulary is `INFO`, `CAUTION`, `WARNING`, and
`CRITICAL`. It is a project UI severity, not a claim of BAM certification.

## 18. Data Quality

The common states are `AVAILABLE`, `AGING`, `STALE`, `MISSING`, `CONFLICT`, and
`INVALID`. A quality display includes source, relevant time(s), availability,
uncertainty, and quality/evidence. The system never converts missing to zero,
future data to historical data, or unknown to safe.

## 19. Map Layers

### Base

Chart/coast and bathymetry.

### Environment

Ice concentration, ice thickness, ice type/composition, ice drift, wind,
current, and wave.

### Navigation

Own ship, historical track, global route context, RecommendedRoute,
CaptainDraftRoute, ActiveRoute, AlternativeRoute, waypoints, XTD/corridor, and
checked prefix.

### Risk

Hard exclusion, unknown areas, critical risk zones, and bottlenecks.

### Dynamic

AIS, radar objects, and dynamic ice objects. These are reserved contracts even
when their initial implementations are later priority.

ContextPanel becomes a Selection Inspector for own ship, waypoint, route leg,
each route object, environment point, dynamic target, and risk zone. Selecting a
leg shows complete leg data; selecting an environment point shows physical
values plus metadata.

## 20. Alternative Routes

Alternatives are compared by distance, ETA, average/planned STW, ice exposure,
depth, weather, uncertainty, critical bottleneck, risk sources, data quality,
and common/shared risk sources when available. A single fast status may be
shown, but it cannot replace the vector comparison.

An alternative should represent a meaningfully different risk source,
bottleneck, topology, or decision strategy; it is not merely the same search
run repeated with a different label.

## 21. Decision Support / CF Behavior

The user-facing concepts are Decision Point, Commitment Point, Information
Pending, conditional route branch, and recommended speed while waiting. The
system can show a common segment leading to an observation and then a choice of
branches. `WAIT` may mean slow, hold, loiter, or use a safe waiting area; it is
not automatically speed zero.

### MVP result boundary

When no acceptable route is available, the MVP planner/safety boundary may
return `NO_ROUTE`, `WAIT`, `EXIT`, `SAFE_HOLD`, or `HUMAN_INTERVENTION`. The
result includes a reason, applicable time, and basic data-quality/unknown
information. The MVP must not invent a route just to populate the UI.

MVP does not solve where to wait, how long to wait, which speed is optimal,
which observation is expected, or when a conditional branch should be entered.

### P1 CF-JRS boundary

CF-JRS later adds safe waiting areas, recommended STW while waiting, expected
observation/reveal time, Decision Point, Commitment Point, conditional A/B
branches, and the distinction between `WAIT`, slow, hold, and loiter. Thus MVP
supports the result type; CF-JRS supports the information-driven WAIT decision
strategy.

A captain decides whether to accept or activate a corresponding route/action.

## 22. Closed-loop / RCOS Behavior

User-facing outcomes are Continue, ETA Update, Repair, Alternative Suggested,
Switch Ready, Route Invalid, Safe Hold, and Human Intervention. The system
shows why a route changed, what changed, new ETA/risk, and the switch condition.
There is no silent ActiveRoute switch.

## 23. Route Versioning

Each route record reserves `route_id`, `route_version`, `environment_version`,
`belief_version`, `graph_version`, `plan_version`, and `validation_version`.
Captain edits create a new draft version. Replanning creates a new
RecommendedRoute version. Historical versions are not overwritten.

## 24. Save / Load / Replay

MVP saves navigation task, CaptainDraftRoute, and ActiveRoute and loads prior
tasks/routes. The first route format may be an internal format; S-421 exchange
is not required for MVP.

Replay is P2 and records VesselState, Environment, Belief, route versions,
planner decisions, captain actions, and events. Replay does not imply an
autonomous control or certification function.

## 25. Dynamic Targets

`DynamicObject` is the shared future contract for AIS, radar, and dynamic ice
objects. The product may detect, display, evaluate, warn, and trigger a
replanning proposal. It may not directly steer to avoid a target and does not
implement complete COLREG autonomous collision avoidance.

AIS is P1. Radar hardware integration is later. Dynamic ice objects are P2.

## 26. Functional Priorities

The counts below are feature groups, not individual UI fields.

### MVP: 20 feature groups

1. Existing workbench/map/environment shell.
2. Versioned task create/edit/save/load.
3. VesselCapability display with evidence.
4. VesselState contract/display with explicit unknowns.
5. Unified environment layers and point inspection.
6. Planning Time/View Time separation.
7. Plan/Replan request state.
8. RecommendedRoute display.
9. Basic CaptainDraftRoute editing.
10. Route validation and PASS/FAIL/UNKNOWN aggregation.
11. Accept/Reject/Activate route lifecycle.
12. ActiveRoute and current-leg monitoring.
13. STW/SOG display.
14. Heading/COG display.
15. ETA and XTE display.
16. Multi-dimensional risk/safety explanation.
17. Data quality and evidence display.
18. Basic route save/load and version references.
19. Basic event/alert stream.
20. Near-field checked-prefix and asynchronous planner state.

### P1: 10 feature groups

1. Sparse corridor and XTD UI.
2. Advanced captain constraints: lock, must-pass, avoid-area, preferred corridor,
   and manual STW policies.
3. Alternative route set and comparison.
4. Full WAIT/EXIT/SAFE_HOLD decision presentation and CF-JRS strategy.
5. AIS dynamic-object display and quality.
6. Route-version history UI.
7. Route switching with captain confirmation.
8. Belief/update-driven revalidation triggers and decision conditions.
9. Global-route context and tactical-horizon linkage.
10. Expanded Selection Inspector for route/risk/dynamic objects.

### P2: 7 feature groups

1. Full RG-MPAO* option set.
2. CF-JRS decision-point/commitment behavior.
3. RCOS closed-loop supervision.
4. Dynamic ice objects.
5. Replay mode.
6. Monte Carlo and research experiment mode.
7. Research artifact/result comparison.

### LATER: 4 feature groups

1. Radar hardware integration.
2. S-100/S-421 route/data exchange.
3. Shipboard system integration and deployment hardening.
4. Production certification work and external operational assurance.

Algorithm research priority and product release priority are separate. An
algorithm may be P2 research while the product still delivers a simpler MVP
recommendation path.

## 27. Backend Capability Mapping

| UI function | Required backend capability |
|---|---|
| Task save/load/version | NavigationTask service and persistence |
| VesselCapability | VesselCapability repository, evidence, version adapter |
| VesselState/monitoring | NavigationState service and quality-aware source adapter |
| Environment point inspector | `EnvironmentQuery` and unified sample metadata |
| Planning Time/View Time | Simulation/planning clock and cutoff-aware query facade |
| Plan/Replan | Baseline planner facade and asynchronous job state |
| Recommended/Alternative routes | SparseGraph, planner, route-set serializer |
| Route drag/edit | CaptainDraftRoute service and route geometry editor contract |
| Route validation | EdgeEvaluator, named safety checks, validation record |
| Monitoring | ActiveRoute service, XTE/ETA/STW/SOG/heading/COG computation |
| Risk explanation | Risk vector/source model and hard-safety result model |
| Data quality | Availability/quality/uncertainty/evidence propagation |
| Route accept/activate/switch | Route lifecycle service with explicit captain action |
| Events/alerts | Event stream, severity, acknowledgement/action model |
| Alternatives | RG-MPAO* route-set facade (P1 product boundary, P2 full research) |
| Decision Point/WAIT | CF-JRS decision-state facade |
| Closed-loop outcomes | RCOS supervisory facade |
| AIS/radar/dynamic ice | `DynamicObject` adapters and observation quality |
| Replay | Experiment/replay recorder and immutable artifact store |

## 28. Research Algorithm Mapping

- Time-dependent baseline planner: supplies the first real
  `RecommendedRoute` implementation.
- `SparseGraph`: supplies sparse corridor/node/edge topology; it is not a dense
  position-heading-speed-time lattice.
- `EdgeEvaluator`: the shared segment feasibility, duration, risk, quality, and
  evidence entry point used by planning and revalidation.
- `RG-MPAO*`: generates a bounded, meaningfully diverse route set; the UI calls
  these Recommended/Alternative Routes.
- `CF-JRS`: exposes decision and commitment points, information-pending
  branches, and WAIT/EXIT/SAFE_HOLD recommendations.
- `RCOS`: supervises closed-loop re-evaluation and presents Continue, Repair,
  Switch Ready, or Human Intervention; it never silently activates a route.

## 29. Backend Implementation Dependency Order

Product priority and backend implementation order are different concepts. MVP,
P1, P2, and LATER describe product maturity and release scope; they do not mean
that source code is written in feature-list order.

The implementation dependency order is:

```text
V5 Foundation Contracts
        -> Environment Data Contract
        -> Truth / Forecast / Observation / Belief
        -> VesselCapability / VesselOperatingState
        -> EnvironmentQuery
        -> EdgeEvaluator
        -> Sparse Time-dependent Route Graph
        -> Time-dependent Single-route Baseline Planner
        -> RecommendedRoute
        -> CaptainDraftRoute + RouteValidation
        -> ActiveRoute + Navigation Monitoring
        -> Alternative Route Set / RG-MPAO*
        -> CF-JRS
        -> RCOS
```

Graph and `EdgeEvaluator` may be implemented iteratively together, but the
architecture remains a sparse search graph plus one shared edge evaluator.
`RecommendedRoute` is an MVP product capability but cannot bypass Environment,
VesselCapability, `EdgeEvaluator`, or the sparse graph with a fake planner.

## 30. Out of Scope

Autopilot, direct rudder control, direct propulsion control, complete COLREG
autonomous collision avoidance, automatic berthing, full stability management,
full ECDIS replacement, ECDIS certification, BAM certification, GMDSS,
ship-control integration, and claims of autonomous navigation certification are
outside this product scope.

## 31. MVP Acceptance Criteria

Each row is testable at the product boundary.

| MVP feature | User sees | User can do | System returns | Failure/UNKNOWN behavior |
|---|---|---|---|---|
| Workbench/map/environment shell | Existing panels, map, timeline, status | Switch panels, pan/zoom, toggle layers | Stable workbench state | Layer error is visible; shell remains usable |
| Versioned task | Task identity, vessel, time, start/goal, horizon | Create, edit, save, load | Task ID/version and persisted draft | Validation error names missing/invalid fields |
| VesselCapability | Static capability plus source/evidence | Select vessel | Capability version | Unknown parameter shows `UNKNOWN`, never a guessed value |
| VesselState | Position, heading/COG, STW/SOG, timestamp, quality | Inspect current state | Quality-tagged state | Missing/stale source is shown as unavailable/unknown |
| Environment inspection | Physical values and all available metadata | Click a map point | Unified sample with availability/quality | Missing/conflict/invalid is explicit; no zero fill |
| Planning/View time | Separate planning and view times | Move view time, set planning time | Cutoff-aware query context | Future data is rejected or marked unavailable |
| Plan/Replan | Job state and request context | Start plan/replan, cancel draft | Async result or named no-route outcome | No fake route; show WAIT/EXIT/SAFE_HOLD/HUMAN_INTERVENTION where applicable |
| RecommendedRoute | Geometry, legs, metrics, validity, evidence | Inspect and compare | Immutable recommendation/version | Invalid or conditional result explains reasons |
| CaptainDraftRoute editing | Editable waypoints/segments and draft status | Add/delete/drag/insert/reorder | New draft version and validation job | Active route remains unchanged; edit conflict is visible |
| Route validation | VALID/CONDITIONAL/INVALID and reasons | Validate/revalidate | PASS/FAIL/UNKNOWN check results | UNKNOWN remains conditional, not safe |
| Accept/Reject/Activate | Route role, validation status, lifecycle status, and confirmation | Accept/reject/activate | Explicit lifecycle transition | `INVALID` cannot enter normal activation; `CONDITIONAL` never auto-activates and awaits a separately approved Conditional Activation Policy; `VALID` still requires captain acceptance; algorithms cannot activate `ActiveRoute` |
| ActiveRoute monitoring | Current leg, next WP, XTE, ETA, state | Inspect and acknowledge events | Derived navigation metrics | Stale state marks monitoring degraded; no fabricated metric |
| STW/SOG | Planned/recommended STW and expected/measured SOG | Inspect per leg | Unit-labelled values and source | Unknown current/vessel data propagates to UNKNOWN |
| Heading/COG | Recommended heading, planned COG, measured heading/COG | Inspect per leg/state | Explicit semantic angle values | Missing sensor or applicability is shown as unknown |
| ETA/XTE | ETA to WP/goal and XTE | Inspect trends/alerts | Versioned calculation result | No valid route/state produces unavailable ETA/XTE |
| Risk/safety explanation | Depth, ice, weather, maneuver, object, data dimensions | Open source/reason details | Hard status plus vector indicators | Hard FAIL cannot be offset by score; UNKNOWN is distinct |
| Data quality/evidence | Availability, source, times, uncertainty, evidence | Inspect metadata | Quality/evidence record | Stale/missing/conflict/invalid visible without “online=good” shortcut |
| Route save/load/version | Route IDs and version history | Save/load/clone/archive | Immutable route versions | Persistence failure preserves local draft and reports error |
| Events/alerts | Categorized severity stream | Inspect/acknowledge captain actions | Event with time, source, route/version context | Severity is project UI severity, not BAM certification |
| Checked-prefix/asynchronous state | Checked distance, ActiveRoute state, planner state | Continue monitoring while planner updates | Independent near-field and tactical states | Stop only when safety guard requires it |

## 32. Open Questions

These are intentionally not invented or silently frozen:

1. What production source and message contract will provide real `VesselState`,
   including COG, STW/SOG, ROT, timestamp, and sensor quality?
2. Which AIS source, update cadence, retention, and coverage are approved?
3. Is radar an onboard adapter, a shore/bridge feed, or a later hardware
   integration, and what is its observation contract?
4. What persistence technology and deployment boundary will store tasks/routes?
5. What exact XTD/corridor policy applies by route mode and maneuver context?
6. Which staleness/aging thresholds are approved for each data source?
7. Which maneuver limits, stopping-distance evidence, and capability envelopes
   are available for the target vessel(s)?
8. Which exact hard-safety thresholds and reason-code taxonomy are approved?
9. How should conditional route activation be governed when a material result is
   `UNKNOWN`?
10. What route comparison normalization is approved for distance, ETA, exposure,
    uncertainty, and common risk sources?
11. Which route exchange format is required after the internal MVP format?
12. What event acknowledgement, escalation, and operator workflow is required?
13. What are the approved safe waiting areas and policies for `WAIT`?
14. Which version/hash fields must be displayed to a captain versus retained for
    audit only?
15. What exact acceptance test scenarios and external-data fixtures will be used
    for the 50 nm tactical horizon?

## 33. Conflicts and Freeze Recommendation

No direct conflict with the frozen V5 technical architecture was introduced.
The specification makes several current gaps explicit: the UI timeline is not
ForecastWorld/BeliefWorld, provider readiness is not data quality, static vessel
capability is not live VesselState, `/api/planner` is a mock boundary, and the
three route identities do not yet exist in code.

This document is suitable to freeze as the product functional baseline, with
the Open Questions retained as implementation and human-review gates. It does
not authorize Phase 2 backend implementation or any algorithm work.
