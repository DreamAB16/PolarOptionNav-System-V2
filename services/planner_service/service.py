"""Build a one-day planning grid and optimize its three-objective route set."""

from datetime import datetime, timezone
import math
from threading import RLock
from uuid import uuid4

from core.models import Position, RoutePoint, RouteResult
from core.vessel.models import VesselProfile
from services.environment_service.service import EnvironmentService

from .dnsga3 import Individual, representative_routes, run_nsga3
from .environment_model import RISK_WEIGHTS, SingleDayEnvironmentModel
from .land_mask import GebcoLandMaskProvider
from .northern_grid import NorthernHemisphereGrid

EXPERIMENT_TIMESTAMP = datetime(2025, 2, 15, 12, tzinfo=timezone.utc)


class PlannerService:
    def __init__(self, environment_service: EnvironmentService | None = None, vessel_profile: VesselProfile | None = None):
        self.environment_service = environment_service or EnvironmentService()
        self.vessel_profile = vessel_profile or self._load_vessel_profile()
        self.land_mask = GebcoLandMaskProvider(self.environment_service)
        self.environment_model = SingleDayEnvironmentModel(self.environment_service, land_mask=self.land_mask)
        self.northern_grid = NorthernHemisphereGrid(self.environment_model, self.vessel_profile, self.land_mask)
        self._plan_snapshots: dict[str, dict[str, object]] = {}
        self._plan_lock = RLock()
        self._max_plan_snapshots = 8

    @staticmethod
    def _load_vessel_profile() -> VesselProfile:
        from services.vessel_service import VesselService

        return VesselService().get_current_profile()

    def plan(
        self,
        start: Position | None = None,
        goal: Position | None = None,
        timestamp: datetime | None = None,
        grid_size: int = 20,
        cell_size_m: int = 25_000,
        population_size: int = 36,
        generations: int = 20,
        seed: int = 42,
        vessel: VesselProfile | None = None,
    ) -> RouteResult:
        """Return a D* Lite seeded NSGA-III Pareto set.

        The no-argument call keeps the Phase-0 contract compatible for older
        clients; real calls require a start and goal.
        """

        if start is None and goal is None:
            return RouteResult(status="mock", risk={"status": "not_calculated"})
        if start is None or goal is None:
            return RouteResult(status="failed", risk={"status": "invalid_request", "message": "Both start and goal are required."})
        if population_size < 6 or population_size > 120 or generations < 1 or generations > 100:
            return RouteResult(status="failed", risk={"status": "invalid_request", "message": "population_size or generations is outside the supported range."})
        if cell_size_m != 25_000:
            return RouteResult(status="failed", risk={"status": "invalid_request", "message": "The experiment uses a fixed 25,000 m planning cell."})

        # The reproducible small experiment uses the day covered by the local
        # PolarData files when the caller does not provide an explicit time.
        departure = timestamp or EXPERIMENT_TIMESTAMP
        selected_vessel = vessel or self.vessel_profile
        try:
            # Global NEP planning reads the complete fixed 25 km matrix.  It is
            # intentionally independent of the browser's viewport grid API.
            grid = self.northern_grid.global_planning_grid(start, goal, departure)
            from types import SimpleNamespace
            built = SimpleNamespace(
                grid=grid, timestamp=departure, sample_count=int(grid.width * grid.height),
                occurrence_counts={}, data_sources={"GEBCO_2026_polar_3413_batch": "static"},
                unavailable=["real_environment_layers_use_deterministic_gap_fill"], historical_years=list(range(2017, 2026)),
                historical_frequency={"mode": "same_day_frequency_surrogate", "date": departure.date().isoformat()},
            )
            front = run_nsga3(built.grid, population_size, generations, seed)
            representatives = representative_routes(front)
        except (LookupError, ValueError, RuntimeError, OSError) as error:
            return RouteResult(status="failed", risk={"status": "planning_failed", "message": str(error)})

        routes = [self._route_payload(item, built.grid) for item in front]
        named = {name: self._route_payload(item, built.grid) for name, item in representatives.items()}
        recommended = representatives.get("lowest_risk")
        if recommended is None:
            return RouteResult(status="failed", risk={"status": "no_feasible_route"})
        route_points = [
            RoutePoint(position=Position(latitude=float(built.grid.coordinate((x, y))[0]), longitude=float(built.grid.coordinate((x, y))[1])))
            for x, y in recommended.path
        ]
        recommended_payload = named["lowest_risk"]
        plan_id = uuid4().hex
        full_grid = self._risk_layers_payload(built, include_cells=True)
        with self._plan_lock:
            self._plan_snapshots[plan_id] = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "risk_layers": full_grid,
            }
            while len(self._plan_snapshots) > self._max_plan_snapshots:
                self._plan_snapshots.pop(next(iter(self._plan_snapshots)))
        eta_hours = float(recommended.objectives[2])
        eta = built.timestamp.timestamp() + eta_hours * 3600
        eta_datetime = datetime.fromtimestamp(eta, timezone.utc)
        return RouteResult(
            status="ready",
            plan_id=plan_id,
            route_points=route_points,
            eta=eta_datetime,
            risk={"status": "calculated", "score": float(recommended.objectives[0]), "factor_weights": RISK_WEIGHTS},
            routes=routes,
            metadata={
                "algorithm": "D*-Lite + NSGA-III",
                "representative_routes": named,
                "timestamp": built.timestamp.isoformat(),
                "sample_count": built.sample_count,
                "grid_size": grid_size,
                "cell_size_m": built.grid.cell_size_m,
                "grid_crs": "EPSG:4326",
                "vessel_id": selected_vessel.identity.id,
                "speed_model": "environmental resistance + projected current + vessel limits",
                "occurrence_counts_2017_2025": built.occurrence_counts,
                "historical_sample_years": built.historical_years,
                "historical_frequency": built.historical_frequency,
                "data_sources": sorted(built.data_sources),
                "unavailable_layers": built.unavailable,
                "environment_scope": "single_day_2025-02-15_with_2017-2025_same_day_frequency",
                "recommended_route": recommended_payload,
                "plan_id": plan_id,
                "risk_layers": self._risk_layers_payload(built, include_cells=False),
            },
        )

    @staticmethod
    def _risk_layers_payload(built: object, *, include_cells: bool = True) -> dict[str, object]:
        """Serialize the six normalized planning-risk rasters for the UI."""

        grid = built.grid
        layer_names = {
            "rio": "ice",
            "fog": "fog",
            "wind": "wind",
            "wave": "wave",
            "depth": "depth",
        }
        layers = {
            output_name: grid.factors[input_name].astype(float).tolist()
            for output_name, input_name in layer_names.items()
        }
        layers["combined"] = grid.risk.astype(float).tolist()
        payload = {
            "width": grid.width,
            "height": grid.height,
            "cell_size_m": grid.cell_size_m,
            "latitudes": grid.latitudes.astype(float).tolist(),
            "longitudes": grid.longitudes.astype(float).tolist(),
            "layers": layers,
        }
        if include_cells:
            payload["cells"] = list((grid.cell_metadata or {}).values())
        return payload

    def get_plan_grid(self, plan_id: str) -> dict[str, object] | None:
        with self._plan_lock:
            snapshot = self._plan_snapshots.get(plan_id)
            return None if snapshot is None else dict(snapshot["risk_layers"])

    def get_plan_cell(self, plan_id: str, cell_id: str) -> dict[str, object] | None:
        grid = self.get_plan_grid(plan_id)
        if grid is None:
            return None
        for cell in grid.get("cells", []):
            if isinstance(cell, dict) and cell.get("cell_id") == cell_id:
                return cell
        return None

    def get_northern_grid(
        self,
        timestamp: datetime,
        south: float = 0.0,
        north: float = 90.0,
        west: float = -180.0,
        east: float = 180.0,
        max_cells: int = 2000,
    ) -> dict[str, object]:
        return self.northern_grid.build(timestamp, south, north, west, east, max_cells)

    def inspect_environment_cell(self, position: Position, timestamp: datetime) -> dict[str, object]:
        static_cell = self.northern_grid.cell_at(position.latitude, position.longitude, timestamp)
        if static_cell is not None:
            return static_cell
        return self.environment_model.inspect(position, timestamp, self.vessel_profile)

    @staticmethod
    def _is_global_corridor_request(start: Position, goal: Position) -> bool:
        return abs(start.longitude - goal.longitude) > 40.0 and max(start.latitude, goal.latitude) < 65.0

    @staticmethod
    def _great_circle_km(first: Position, second: Position) -> float:
        lat1, lat2 = math.radians(first.latitude), math.radians(second.latitude)
        dlat = lat2 - lat1
        dlon = math.radians(second.longitude - first.longitude)
        value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 6371.0088 * 2.0 * math.asin(min(1.0, math.sqrt(value)))

    def _global_corridor_result(
        self,
        start: Position,
        goal: Position,
        departure: datetime,
        vessel: VesselProfile,
        failure_reason: str,
    ) -> RouteResult:
        """Return a coarse marine corridor when a tiny grid misses a strait.

        This is deliberately a rescue path for global city-to-city demos. It
        does not replace the environmental D-NSGA3 planner used within the
        supported PolarData coverage; the response identifies the fallback so
        callers can distinguish it from an optimised Pareto route set.
        """

        raw_anchors = [
            start,
            Position(latitude=20.0, longitude=125.0),
            Position(latitude=8.0, longitude=105.0),
            Position(latitude=5.0, longitude=80.0),
            Position(latitude=-10.0, longitude=50.0),
            Position(latitude=-30.0, longitude=20.0),
            Position(latitude=-25.0, longitude=-25.0),
            Position(latitude=30.0, longitude=-25.0),
            Position(latitude=36.0, longitude=-5.0),
            goal,
        ]
        # Land is a hard obstacle: every corridor waypoint is snapped to the
        # nearest deep-enough water cell so the rescue route never crosses land.
        anchors = [self._nearest_water_anchor(point, vessel, departure) for point in raw_anchors]
        if self._corridor_crosses_land(anchors, vessel, departure):
            return RouteResult(
                status="failed",
                risk={
                    "status": "planning_failed",
                    "message": "No all-water route exists at this resolution; land is treated as a hard obstacle.",
                },
            )
        distance_km = sum(self._great_circle_km(a, b) for a, b in zip(anchors, anchors[1:]))
        speed_kn = max(4.0, min(vessel.safety_constraints.speed_limit, vessel.speed.service_speed_max_kn * 0.75))
        time_hours = distance_km / (1.852 * speed_kn)
        route = {
            "routeId": "global-corridor-fallback",
            "objectives": {"risk": 0.55, "distance_km": distance_km, "time_hours": time_hours},
            "path": [point.model_dump() for point in anchors],
        }
        eta = departure.astimezone(timezone.utc).timestamp() + time_hours * 3600.0
        return RouteResult(
            status="ready",
            route_points=[RoutePoint(position=point) for point in anchors],
            eta=datetime.fromtimestamp(eta, timezone.utc),
            risk={"status": "calculated", "score": 0.55, "mode": "global_corridor_fallback"},
            routes=[route],
            metadata={
                "algorithm": "global marine corridor fallback",
                "planning_status": "coarse_fallback",
                "fallback_reason": failure_reason,
                "representative_routes": {
                    "lowest_risk": route,
                    "shortest_distance": route,
                    "fastest_time": route,
                },
                "risk_layers": self._fallback_risk_layers(start, goal),
                "speed_model": "vessel service speed capped at 75% for coarse corridor",
                "environment_scope": "global coarse route; local PolarData D-NSGA3 unavailable at this resolution",
            },
        )

    def _corridor_crosses_land(self, anchors: list[Position], vessel: VesselProfile, timestamp: datetime) -> bool:
        """Return True when any corridor segment passes over a land cell.

        Land is a hard navigability constraint.  Sampling each great-circle
        segment catches peninsulas and islands that straight anchor-to-anchor
        corridors would otherwise paint across, so an unsafe corridor is never
        returned to the user.
        """

        required = vessel.safety_constraints.draft + 2.0
        for first, second in zip(anchors, anchors[1:]):
            samples = max(4, min(80, int(self._great_circle_km(first, second) / 40.0)))
            for index in range(samples + 1):
                fraction = index / samples
                latitude = first.latitude + (second.latitude - first.latitude) * fraction
                longitude = first.longitude + (second.longitude - first.longitude) * fraction
                try:
                    sample = self.environment_model.adapter.sample(Position(latitude=latitude, longitude=longitude), timestamp, vessel)
                    depth = sample.state.depth
                except (LookupError, OSError, RuntimeError, ValueError):
                    depth = None
                if depth is None or depth < required:
                    return True
        return False

    def _nearest_water_anchor(self, position: Position, vessel: VesselProfile, timestamp: datetime, search_radius_deg: float = 1.5) -> Position:
        """Snap a corridor anchor onto the nearest navigable water cell.

        The coarse global fallback must not paint a route across land.  Every
        anchor is nudged to the nearest water that clears the vessel draft
        safety margin; if none is found within the search radius the anchor
        is returned unchanged.
        """

        required = vessel.safety_constraints.draft + 2.0
        try:
            initial = self.environment_model.adapter.sample(position, timestamp, vessel)
            if initial.state.depth is not None and initial.state.depth >= required:
                return position
        except (LookupError, OSError, RuntimeError, ValueError):
            pass
        step_deg = 0.2
        for ring in range(1, int(search_radius_deg / step_deg) + 1):
            offsets = []
            for index in range(-ring, ring + 1):
                offsets.append((index * step_deg, -ring * step_deg))
                offsets.append((index * step_deg, ring * step_deg))
                offsets.append((-ring * step_deg, index * step_deg))
                offsets.append((ring * step_deg, index * step_deg))
            for d_lon, d_lat in offsets:
                latitude = position.latitude + d_lat
                longitude = position.longitude + d_lon
                if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
                    continue
                try:
                    sample = self.environment_model.adapter.sample(Position(latitude=latitude, longitude=longitude), timestamp, vessel)
                    depth = sample.state.depth
                except (LookupError, OSError, RuntimeError, ValueError):
                    continue
                if depth is not None and depth >= required:
                    return Position(latitude=latitude, longitude=longitude)
        return position

    @staticmethod
    def _fallback_risk_layers(start: Position, goal: Position) -> dict[str, object]:
        latitudes = [float(start.latitude), float(goal.latitude)]
        longitudes = [float(start.longitude), float(goal.longitude)]
        base = [[0.55, 0.55], [0.55, 0.55]]
        return {
            "width": 2,
            "height": 2,
            "latitudes": latitudes,
            "longitudes": longitudes,
            "layers": {name: [row[:] for row in base] for name in ("rio", "fog", "wind", "wave", "depth", "combined")},
        }

    @staticmethod
    def _route_payload(individual: Individual, grid: object) -> dict[str, object]:
        return {
            "objectives": {
                "risk": float(individual.objectives[0]),
                "distance_km": float(individual.objectives[1]),
                "time_hours": float(individual.objectives[2]),
            },
            "path": [
                {"latitude": float(grid.coordinate((x, y))[0]), "longitude": float(grid.coordinate((x, y))[1])}
                for x, y in individual.path
            ],
            "cell_ids": [
                (grid.cell_metadata or {}).get((x, y), {}).get("cell_id", f"r{y}c{x}")
                for x, y in individual.path
            ],
        }
