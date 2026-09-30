# V5 Frontend UX Refinement v1

## 1. Scope

This refinement is limited to information organization in the existing Vue /
OpenLayers functional shell. It does not change the frozen product scope,
navigation contracts, map projection, tiles, environment providers, backend,
core, planner, or provider APIs.

## 2. Navigation Status

The right-side Selection Inspector now presents `Navigation Status` first, with
Current Position, Heading, COG, STW, SOG, ROT, Next Waypoint, Distance to WP,
XTE, and ETA. Missing live telemetry remains explicitly `NOT CONNECTED` or
`UNKNOWN`; values are not inferred from vessel capability data.

The same panel now separates `Environment Status`, `Route Status`, and
`System Status`. Route status keeps Recommended Route and Active Route as
`NONE` until real backend objects exist, while a frontend Captain Draft is
shown as `DRAFT · UNCHECKED`.

## 3. Planning Layout

Planning controls remain available but are grouped into collapsible sections:

- Route Planning
- Route Set
- Captain Draft
- Waypoint Constraints
- Route Validation
- Advanced Constraints

The Captain Draft editor keeps Add, Insert, Delete, Undo, Redo, Edit Mode,
Lock WP, and Must Pass. Backend-dependent Plan, Replan, Validate, Accept,
Activate, Lock Segment, Avoid Area, Preferred Corridor, and Manual STW remain
disabled with explanatory titles or state text.

## 4. Route Lifecycle Display

Planning now includes a display-only lifecycle strip:

`RecommendedRoute -> CaptainDraftRoute -> CHECKING -> VALID / CONDITIONAL /
INVALID -> ACCEPTED -> ACTIVE`

It does not advance lifecycle state or implement validation. The current
frontend draft is highlighted only when it exists; all unavailable backend
stages remain `NONE`.

## 5. Vessel Display

`Vessel Capability` and `Live Navigation State` remain separate. The live
section now leads with Heading, COG, STW, SOG, and ROT, followed by Position,
Timestamp, source, and quality. Maximum/reference speed is not reused as live
speed.

## 6. Environment Display

Existing environment controls and providers are unchanged. Each listed source
now exposes source metadata, matched/update-time context where available, and
an explicit `UNKNOWN` quality state. No synthetic quality value was added.
Future Ice Type, Ice Drift, unified inspection, data quality, and uncertainty
remain visibly unavailable/future capabilities.

## 7. Timeline

The existing environment time logic is unchanged. The footer now gives View
Time and Planning Time distinct visual rows and retains the explanation that
View Time is inspection context, not planner authorization for future data.
Forecast behavior was not added.

## 8. State Semantics and Limits

The refinement preserves the unified meanings of `NOT CONNECTED`,
`NOT CALCULATED`, `UNKNOWN`, and `UNAVAILABLE`. No fake ship telemetry, route,
risk, event, planner result, AIS, radar, or environment quality data was
introduced. Browser visual acceptance remains a separate environment-dependent
step documented in `V5_FRONTEND_VISUAL_ACCEPTANCE.md`.

## 9. Verification

- Frontend tests: 15 test files, 45 tests passed.
- Production build: passed; 356 modules transformed.
- Existing Vite advisory remains for the approximately 650 kB main chunk.

This worktree remains uncommitted and is ready for manual browser review.
