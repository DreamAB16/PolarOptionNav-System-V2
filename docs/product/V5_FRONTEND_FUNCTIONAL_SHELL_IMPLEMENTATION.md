# V5 Frontend Functional Shell Implementation

## 1. Scope

This worktree implements the V5 frontend functional shell and a frontend-only
CaptainDraftRoute editor. It does not implement a planner, EdgeEvaluator,
SparseGraph, RouteValidation backend, RouteLifecycle backend, ETA/risk formula,
live vessel feed, AIS, radar, or any control function.

## 2. Source Baseline

Branch: `feat/v5-frontend-functional-shell`.

Base: product functional baseline commit `c0a8edb5f5c7972c9ef0a6febd4ae6f8a84aa6f3`.

The Phase 1 foundation-contract changes in the original worktree were kept
isolated and were not modified, staged, or committed here.

## 3. Existing UI Preserved

The existing Vue/OpenLayers workbench, visual language, map projections,
environment providers, tiles, vectors, and environment timeline were retained.
The implementation adds functional shell sections without changing backend
provider behavior.

## 4. Components Added/Modified

Added:

- `frontend/src/components/StateBadge.vue`
- `frontend/src/services/ui-status.ts`
- `frontend/src/services/route-draft.ts`
- `frontend/src/types/navigation.ts`

Modified:

- `App.vue` for draft state, map layer, selection, edit mode, undo/redo, and
  planning/view-time wiring;
- `TaskPanel.vue`, `VesselPanel.vue`, `PlanningPanel.vue`,
  `MonitoringPanel.vue`, `EnvironmentPanel.vue`, `ContextPanel.vue`,
  `EnvironmentTimeline.vue`, `TopStatusBar.vue`, `EventPanel.vue`;
- `styles.css` for state badges, route cards, waypoint editor, navigation-layer
  menu, and inspector layout.

## 5. Navigation Data Fields Added

The shell visibly reserves planning time and view time, task tactical horizon,
global route context, captain constraints, route role/validation/lifecycle,
waypoint identity/sequence/coordinates/lock/must-pass, geometry distance,
current leg and waypoint monitoring fields, risk dimensions, data quality, and
future navigation-layer entries.

## 6. UI Data State Semantics

`NOT_CONNECTED`, `NOT_CALCULATED`, `UNKNOWN`, and `UNAVAILABLE` are distinct
display states in `ui-status.ts` and `StateBadge.vue`. `UNKNOWN` is never
rendered as zero, safe, or no risk.

## 7. Vessel Capability / State Separation

`VesselPanel` now separates static/evidence-backed `Vessel Capability` from
`Live Navigation State`. Public profile fields remain real backend/static data.
Latitude, longitude, heading, COG, STW, SOG, navigation timestamp, data source,
and data quality are explicitly `NOT CONNECTED` or `UNKNOWN`; maximum speed is
not reused as STW/SOG.

## 8. Task Functions

Existing task creation, map start/destination selection, planning intent, and
notes remain functional. Tactical horizon (default 50 nm), global route context,
and captain constraints are visible. Save, Load, Duplicate, and Archive are
visible but disabled with persistence explanations; no localStorage fake
persistence was added.

## 9. Environment Functions

Existing chart, bathymetry, ice concentration/thickness, wind, current, wave,
presets, legends, opacity, matched time, and provider states are unchanged.
Future Ice Type/Composition, Ice Drift, Unified Point Inspect, Data Quality, and
Uncertainty are visible with honest unavailable states. Existing wave click
inspection remains the only real point-level dynamic popup.

## 10. Planning Functions

PlanningPanel is now a route planning and captain editing center with Plan,
Replan, Clear Draft, route-set cards, Captain Draft, Validate Route, Accept,
Activate, advanced constraints, and lifecycle sections. Planner, validation, and
lifecycle actions are disabled or explicit unavailable states; no mock planner
route is displayed.

## 11. Captain Draft Route Editor

`route-draft.ts` is explicitly a UI-only prototype model. It creates a
Start-to-Goal `CaptainDraftRoute`, supports add, insert, delete, select, move
(OpenLayers Modify), lock, must-pass, and geometric distance recalculation.
Every edit resets `validation` to `UNCHECKED`; the model cannot become
`RecommendedRoute`, `ValidatedRoute`, or `ActiveRoute`.

Undo/redo is session-local and covers model edits. Edit Mode is visible and the
map has an independent Captain Draft/Waypoint layer with visible handles.

## 12. Monitoring Fields

MonitoringPanel visibly reserves Active Route, current position/leg, next
waypoint, heading, COG, STW, SOG, ROT, bearing/distance to waypoint, XTE,
recommended STW, expected SOG, recommended heading, planned COG, ETA fields,
remaining distance/time, checked prefix, plan age, planner state, and data
state. Values remain `NOT CALCULATED`/`NOT CONNECTED` until real capabilities
exist.

## 13. Risk/Safety Display

The shell displays Hard Safety Status, Depth, Ice, Weather, Maneuver, Dynamic
Object, Data/Uncertainty, Main Risk Source, Critical Segment, and Unknown
Reasons as `NOT CALCULATED`. No scalar risk score or safety formula was added.

## 14. Event Display

EventPanel retains the empty event state and now exposes project UI severities
INFO, CAUTION, WARNING, and CRITICAL plus disabled filter/search/acknowledge
entry points. No fake events or alerts are generated.

## 15. Map Navigation Layers

The map exposes a navigation-layer menu for Own Ship, Historical Track, Global
Route, Recommended Route, Captain Draft Route, Active Route, Alternatives,
Waypoints, XTD/Corridor, Checked Prefix, Risk Zones, AIS, Radar, and Dynamic Ice
Objects. Only Captain Draft Route and Waypoints have real frontend geometry;
other entries are empty, unavailable, or not connected.

## 16. Selection Inspector

ContextPanel now presents a Selection Inspector for a selected waypoint,
CaptainDraftRoute, or unavailable future environment/route-leg selection. It
shows waypoint coordinates, lock/must-pass, draft role/lifecycle/validation,
and geometric distance without pretending to provide ETA/STW or route validity.

## 17. Implemented vs Placeholder

| Feature | Visible | Frontend functional | Backend connected | Current state |
|---|---:|---:|---:|---|
| Environment layers | YES | YES | YES/partial | Real provider-backed behavior retained |
| Planning/View Time | YES | YES | Environment clock only | View Time does not imply future planner access |
| Vessel Capability | YES | YES | YES | Static/profile data |
| Live VesselState | YES | NO | NO | `NOT CONNECTED` |
| Captain Draft creation | YES | YES | No backend needed | `CAPTAIN_DRAFT / DRAFT / UNCHECKED` |
| Add/move/delete/insert waypoint | YES | YES | No backend needed | UI-only geometry |
| Undo/redo | YES | YES | No backend needed | Session-local |
| Validate Route | YES | NO | NO | Disabled; EdgeEvaluator required |
| Recommended/Alternative Route | YES | NO | NO | `NONE` / `UNAVAILABLE` |
| Active Route | YES | NO | NO | `NONE` |
| ETA/XTE/STW/SOG/risk | YES | NO | NO | `NOT CALCULATED` |
| AIS/Radar/Dynamic Ice | YES | NO | NO | `NOT CONNECTED` |
| Events | YES | NO | NO | No active events |

## 18. Tests

Added focused tests:

- `frontend/src/services/route-draft.test.ts`: 3 tests;
- `frontend/src/services/ui-status.test.ts`: 4 tests.

Frontend result: **15 test files, 45 tests passed**.

Build result: **successful**, `vue-tsc` and Vite completed with 356 modules.
The existing main chunk warning remains (about 647 kB minified, above the 500
kB advisory threshold); no runtime dependency was added.

## 19. Known Limitations

The full OpenLayers pointer-drag path is type/build checked and uses the
existing `Modify` interaction, but this pass does not add browser E2E tests.
Segment insertion is exposed through the editor action and uses the selected
waypoint segment midpoint. Start/Goal remain task anchors and are not silently
rewritten by draft editing. No route geometry is treated as navigationally
valid.

## 20. Backend Capabilities Still Required

Task persistence, VesselState adapters, unified EnvironmentQuery metadata,
EdgeEvaluator, RouteValidation, SparseGraph and baseline planner,
Recommended/Alternative route contracts, RouteLifecycle, ActiveRoute
monitoring/XTE/ETA, risk/evidence propagation, events, AIS, radar, and dynamic
ice objects remain backend or later research work.
