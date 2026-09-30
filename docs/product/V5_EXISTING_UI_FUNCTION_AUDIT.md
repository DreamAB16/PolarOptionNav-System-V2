# V5 Existing UI Function Audit

## 1. Executive Summary

The current WEB frontend is a single-page operational workbench with a real
OpenLayers environment-display shell and task/vessel setup flows, but it is not
yet a navigation planner or route-monitoring product. Environment map layers
and time controls are connected to backend endpoints; task creation is session
local; planning, live vessel data, route execution, and risk calculation are
explicitly unavailable or placeholder states.

This audit is source-code-derived. No browser or screenshot verification was
performed in this read-only pass.

## 2. Current Page Map

There is no frontend router and no separate URL-addressable page. `main.ts`
mounts `App.vue`, which renders one bridge shell:

```text
App.vue: PolarOptionNav workbench
├─ TopStatusBar: brand, task/vessel/time, service status popover
├─ MainNavigation: six panel selectors
├─ Left workbench (one active panel)
│  ├─ TaskPanel
│  ├─ VesselPanel
│  ├─ EnvironmentPanel
│  ├─ PlanningPanel
│  ├─ MonitoringPanel
│  └─ EventPanel
├─ Center map stage: OpenLayers map, toolbar, overlays, toast
├─ ContextPanel: right-side voyage/environment summary
└─ EnvironmentTimeline: bottom clock/scenario/playback controls
```

The six main panel views are the primary UI areas; map, context panel, top
status bar, and timeline remain visible around the active panel.

## 3. Current Layout

`App.vue` uses a top status bar, a three-column bridge workspace, and a bottom
environment timeline. The left rail selects the active workbench panel. The
center is the map. The right panel can collapse. The layout is CSS-driven in
`frontend/src/styles.css`; there is no route/page navigation layer.

## 4. Current UI Components

| Component | Actual responsibility |
|---|---|
| `TopStatusBar.vue` | Shows product name, current task, selected vessel, environment UTC time, planner/simulation state, API state, and a status popover. |
| `MainNavigation.vue` | Selects Task, Vessel, Environment, Planning, Monitoring, or Events panel. |
| `TaskPanel.vue` | Creates/edits a session-local task name, map-picked start/destination, local departure time, vessel selection, planning mode, and notes. |
| `VesselPanel.vue` | Displays the current vessel profile and public design parameters; offers selection, locate, and reset actions. |
| `EnvironmentPanel.vue` | Toggles chart, bathymetry, ice, wind, current, and wave layers; applies presets; controls ice variable/opacity; expands legends. |
| `PlanningPanel.vue` | Shows task/vessel prerequisites, objective selector, non-functional advanced constraints, and an unavailable planner action. |
| `MonitoringPanel.vue` | Displays empty monitoring fields and explicit “not calculated/not connected” states. |
| `EventPanel.vue` | Displays an empty event log and severity legend. |
| `MapToolbar.vue` | Switches standard/polar view and exposes locate, measure, coordinate, pick, layer-info, fullscreen, and reset tools. |
| `ContextPanel.vue` | Shows task/vessel/current coordinate summary and placeholder navigation/environment values. |
| `EnvironmentTimeline.vue` | Switches winter/summer scenario, seeks hourly time, steps, plays/pauses, and changes playback speed. |

## 5. Current Displayed Data

### Vessel

| Field | Display/source classification |
|---|---|
| Name, type, PC class | Backend `/api/vessel/current`, mapped to frontend summary; fallback sample profile exists in `App.vue`. |
| Length, beam, design draft | Backend vessel profile / static vessel data. |
| Maximum speed, propulsion, propulsion power | Backend vessel profile / static vessel data. |
| Continuous ice and snow thickness, ice speed, endurance | Backend vessel profile / static vessel data. |
| Current speed, heading, position | Fields exist, but no real vessel feed populates them; UI shows `--` or unavailable. |

### Environment

| Field | Display/source classification |
|---|---|
| Chart/coastline | Backend chart layer GeoJSON and OpenLayers layer. |
| Bathymetry | Backend GEBCO tile endpoint when configured; readiness may be `not_found`. |
| Ice concentration/thickness | Backend sea-ice tile endpoint, with explicit legend and matched time. |
| Wind east/north vectors | Backend CARRA2 field endpoint and vector layer. |
| Current east/north vectors | Backend TOPAZ5 field endpoint and vector layer. |
| Wave height/period/from direction | Backend Arctic WAM field endpoint and clickable map popup. |
| Provider source/resolution/cadence | Frontend static metadata in `environment-layer-info.ts`. |
| Requested/matched time | Runtime layer state and matched-time labels. |

### Planning and monitoring

Route count, route ID, distance, ETA, risk score, fuel estimate, route status,
current position, SOG, heading, remaining distance, XTE, route version, and
risk rows exist as UI model/labels, but no route result currently populates
them. The visible monitoring risk values are explicitly `未计算`.

## 6. Current User Interactions

Implemented interactions are task form editing, map selection of task points,
layer toggles/presets, ice display mode and opacity, legends, standard/polar
map switching, locate/reset/fullscreen, coordinate picking, two-point distance
measurement, wave feature clicking, collapsible context/status panels, and
environment timeline playback/seek/step/scenario selection.

Task data is stored in Vue state for the current page session only. “Open task”,
“edit vessel parameters”, live vessel feed, and planner submission are disabled
or unavailable.

## 7. Current Map Capabilities

| Capability | Status | Evidence |
|---|---|---|
| Zoom / pan | IMPLEMENTED | OpenLayers default map interactions in `App.vue`. |
| Standard Mercator view | IMPLEMENTED | `polar-view.ts`, `MapToolbar.vue`. |
| Polar strategic view | IMPLEMENTED | EPSG:3413 mode and polar layer sources. |
| Current vessel marker | NOT IMPLEMENTED | Locate action requires a vessel position; no live position is supplied. |
| Chart/coastline | IMPLEMENTED | `ChartLayer` and chart client. |
| Bathymetry | IMPLEMENTED/PARTIAL | Tile layer exists; runtime source can be unavailable. |
| Ice raster | IMPLEMENTED/PARTIAL | Concentration/thickness tile sources and legends; data readiness depends on files. |
| Wind arrows | IMPLEMENTED/PARTIAL | Viewport sampling and vector rendering exist; provider/data availability applies. |
| Current arrows | IMPLEMENTED/PARTIAL | Viewport sampling and vector rendering exist; provider/data availability applies. |
| Wave cells | IMPLEMENTED/PARTIAL | Viewport sampling, color legend, and popup exist. |
| Tile layers / vector layers | IMPLEMENTED | Managed layer lifecycle and provider-backed sources. |
| Map click | IMPLEMENTED | Coordinate, pick, measure, and wave selection paths. |
| Hover | NOT IMPLEMENTED | No hover-specific data interaction found. |
| Coordinate display | IMPLEMENTED | Coordinate tool and right context summary. |
| Layer visibility | IMPLEMENTED | Toggles and presets. |
| Opacity | PARTIAL | Ice opacity only; no general opacity controls. |
| Legend | IMPLEMENTED/PARTIAL | Ice and wave legends; no unified all-layer legend. |
| Measurement | IMPLEMENTED | Two-point great-circle distance in nautical miles. |
| Waypoint marker | PARTIAL | Start/destination/point markers can be placed; no route waypoint model. |
| Route polyline | NOT IMPLEMENTED | Route layer is reserved but no route geometry is produced. |
| Route editing / drawing / drag | NOT IMPLEMENTED | No OpenLayers Draw or Modify route workflow. |
| Selectable objects | PARTIAL | Wave cells and map points have click paths; no selectable route objects. |
| Time-dependent refresh | IMPLEMENTED/PARTIAL | Timeline updates managed environment layers; it is not a ForecastWorld or planner clock. |

## 8. Environment UI

The environment panel presents six layers grouped into base and dynamic
environment, four presets, source/resolution/cadence labels, provider/layer
health, matched UTC time, ice mode/opacity controls, and ice/wave legends.
The backend maps these to chart, bathymetry, ice, wind, current, and wave
providers. Missing layers are surfaced as “数据缺失”/“无当前时间数据”.

The user can click the map to query coordinates and click wave cells to see
wave height, peak period, direction-from, and matched time. There is no generic
click-to-query popup for ice, wind, current, bathymetry, or a combined sample.

The top status popover currently labels all five environment sources as
“可用” when the API is online, while the environment panel has more granular
runtime layer status. This is a UI consistency gap, not proof that every source
file is present.

## 9. Timeline

The timeline supports winter/summer scenario selection, hourly slider seek,
previous/next hour, play/pause, and 1x/2x/5x playback. `App.vue` first reads
`/api/environment/time`, then updates the managed layers for the selected UTC
time. It changes environment display requests and matched-time labels; it does
not implement a forecast/observation/belief model and does not drive planning.
The frontend owns a playback clock after the initial backend state read.

## 10. Vessel UI

The vessel panel displays Snow Dragon 2 public profile fields: name, type,
PC3, dimensions, draft, maximum speed, propulsion, propulsion power, continuous
ice/snow capability, ice speed, current speed, and current heading. Public
profile data is fetched from `/api/vessel/current`; a static sample summary is
also defined in `App.vue` for task selection fallback.

Real position, heading, SOG/STW distinction, COG, ROT, XTE, ETA, next waypoint,
AIS, and live vessel status are NOT IMPLEMENTED. The panel explicitly labels
the shown profile as public/non-real-time data.

## 11. Planner UI

The planning panel requires a task and vessel, offers fastest/lowest-risk/
balanced objective selection, and expands five advanced constraint inputs:
maximum ice concentration, maximum wave height, minimum safe depth, maximum
speed, and safety margin. These inputs are explicitly interface-only and do not
participate in calculations. The “开始规划” button only emits an unavailable
toast; it does not call `/api/planner`. Backend `/api/planner` exists but
returns `RouteResult(status="mock", risk={"status": "not_calculated"})` and is
not wired into the frontend.

## 12. Route Editing

| Capability | Status | Current evidence |
|---|---|---|
| Create waypoint | PARTIAL | Start/destination map picks only. |
| Delete waypoint | NOT IMPLEMENTED | No waypoint collection or delete action. |
| Drag waypoint/segment | NOT IMPLEMENTED | No Draw/Modify interaction. |
| Insert/reorder waypoint | NOT IMPLEMENTED | No route editor. |
| Lock waypoint/segment | NOT IMPLEMENTED | No model or control. |
| Must-pass / avoid-area / preferred corridor | NOT IMPLEMENTED | No geometry or API contract. |
| Manual speed | NOT IMPLEMENTED | No route segment speed editor. |
| Undo/redo | NOT IMPLEMENTED | No route history. |
| Save/load/clone/compare route | NOT IMPLEMENTED | Task is session-local; no route persistence API. |
| Accept/activate route | NOT IMPLEMENTED | No route lifecycle. |

## 13. Navigation Monitoring

There is a monitoring panel and right-side context summary, but no active route
state. Current leg, next waypoint, bearing/distance to waypoint, XTE, ETA,
remaining distance/time, deviation detection, route validity, replanning,
alternatives, route switching, and navigation alerts are NOT IMPLEMENTED.
The panel deliberately displays empty values and says real-time data, risk
calculation, and simulation are not connected.

## 14. Risk / Alerts

The event panel provides an empty info/warning/critical legend and event count.
The monitoring panel lists ice, shallow-water, wind/wave, deviation, and overall
risk, but every value is `未计算`. There is no combined risk formula, maneuver
risk, uncertainty propagation, quality-based risk, or alert engine in the UI.
Depth-safety backend functionality exists as an API, but it is not presented as
a live route guard in the frontend.

## 15. Data / System Status

Visible status includes API online/unavailable, environment UTC time, provider
layer status/matched time, planner not connected, simulation not connected,
and vessel/AIS not connected. The UI does not display source time, issue time,
valid time, ingest time, uncertainty, conflict, or a unified V5 availability
state. Static source/cadence labels are informational metadata.

## 16. Frontend-to-Backend Mapping

| Frontend feature | Frontend service/component | Endpoint/backend | Reality |
|---|---|---|---|
| API status | `system-client.ts` | `GET /api/status` | REAL backend health response |
| Vessel profile | `system-client.ts`, `VesselPanel.vue` | `GET /api/vessel/current` → `VesselService` | REAL static profile data |
| Environment clock | `environment-time.ts` | `GET /api/environment/time` → `EnvironmentTimeManager` | REAL clock metadata; UI playback thereafter |
| Provider readiness | `environment-layer-info.ts` | `GET /api/environment/layers` → `EnvironmentService` | REAL readiness metadata |
| Chart | `chart-client.ts`, `ChartLayer` | `/api/chart/layers*` → `ChartService` | REAL/static chart service |
| Bathymetry | `bathymetry-layer.ts` | bathymetry tile endpoints → provider | REAL when dataset configured; otherwise unavailable |
| Sea ice | `ice-layer.ts` | ice tile endpoints → Copernicus/placeholder provider | REAL when processed data configured; otherwise unavailable |
| Wind/current/wave vectors | `wind-field.ts`, `current-field.ts`, `wave-field.ts` | field POST endpoints → providers | REAL provider boundary; dependent on data |
| Coordinate/measure/pick | `App.vue` and OpenLayers | No backend call | CALCULATED FRONTEND |
| Task creation | `TaskPanel.vue`, `App.vue` | No endpoint | FRONTEND SESSION STATE |
| Planning | `PlanningPanel.vue` | No call; `/api/planner` is unused by UI | PLACEHOLDER / backend MOCK |
| Monitoring/events | panels only | No live route/event endpoint | PLACEHOLDER |

## 17. REAL / MOCK / PLACEHOLDER Matrix

| Capability | Classification |
|---|---|
| API status | REAL BACKEND DATA |
| Public vessel profile | REAL BACKEND DATA / STATIC VESSEL DATA |
| Chart and environment tile/field boundaries | REAL BACKEND DATA when configured |
| Environment source labels, layer resolution, cadence | STATIC CONFIG |
| Coordinate display and great-circle measurement | CALCULATED FRONTEND |
| Task form and start/destination selection | FRONTEND HARDCODED/SESSION STATE |
| Planner result | MOCK backend, currently not called |
| Route lines and route metrics | PLACEHOLDER |
| Monitoring values and risk | PLACEHOLDER (`--`/`未计算`) |
| Events and alerts | PLACEHOLDER empty state |
| AIS/live vessel data | NOT IMPLEMENTED |

## 18. KEEP / EXTEND / REWORK / PLACEHOLDER / REMOVE

| Asset/function | Classification | Reason |
|---|---|---|
| OpenLayers map and projection/layer lifecycle | KEEP | Useful engineering infrastructure already connected to providers. |
| Environment source panels and timeline | EXTEND | Preserve interaction; add V5 time/quality semantics and unified sampling. |
| Public vessel profile panel | EXTEND | Add evidence/version semantics and separate static capability from live state. |
| Task setup panel | EXTEND | Keep workflow; add persisted/versioned task and explicit route roles. |
| Planner panel layout | REWORK | Keep location, but bind to real graph/evaluator/planner contracts later. |
| Monitoring panel | REWORK | Replace empty metrics with ActiveRoute and live navigation state. |
| Context summary | REWORK | Separate current state, recommended route, captain draft, and active route. |
| Empty event/risk states | PLACEHOLDER | No event, alert, quality, or risk engine is connected. |
| `/api/planner` mock | PLACEHOLDER | Contract boundary only; do not treat as planning capability. |
| Existing OpenLayers measurement | KEEP | Valid supporting tool, not route editing. |
| Automatic driving/control features | REMOVE from scope | Conflicts with advisory captain-in-the-loop boundary. |

## 19. Test / Build Status

- Frontend `npm test -- --run`: **38 passed** across 13 test files.
- Frontend `npm run build`: **success**; `vue-tsc` and Vite build completed
  successfully (350 modules).
- Frontend build warning: the main JavaScript chunk is larger than 500 kB
  (604.04 kB, 189.86 kB gzip); this did not fail the build.
- Backend `pytest`: **103 passed, 4 warnings**.
- Warnings are third-party `dateutil` and `rasterio` deprecation/pending-
  deprecation warnings.

## 20. Limitations of Audit

This was a source-code and test/build audit. No browser session, screenshot,
network-backed runtime, or visual interaction validation was performed. Data
availability is reported from provider readiness code and endpoint contracts;
actual external datasets may be absent in a local environment. Existing
untracked Phase 1 files on `feat/v5-foundation-contracts` were preserved and
not modified.
