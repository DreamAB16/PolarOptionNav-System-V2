# Project structure

| Module | Responsibility |
| --- | --- |
| `frontend` | Vue3/OpenLayers bridge display shell; communicates through HTTP API |
| `backend` | FastAPI application and route composition |
| `services` | Chart, environment, vessel and reserved planner service facades/providers |
| `core` | Shared Pydantic contracts (`EnvironmentState`, legacy environment state, `VesselState`, `RouteResult`) |
| `config` | Environment-aware application settings |
| `data` | External data mount points; never imported by frontend |
| `tests` | Backend/API and frontend smoke tests |

The dependency direction is `frontend -> backend API -> services -> providers/data`. `EnvironmentQueryService` aggregates the five provider outputs, and `EnvironmentGrid` exposes a source-faithful `EnvironmentCell` without risk, cost or route semantics. The planner service is a reserved interface with no algorithm implementation or UI dependency.
