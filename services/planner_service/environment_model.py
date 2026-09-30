"""Minimum single-day planning-grid model backed by PolarData."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import numpy as np

from core.models import EnvironmentState, Position
from core.vessel.models import VesselProfile
from services.environment_service.service import EnvironmentService

from .dnsga3 import PlanningGrid
from .historical_frequency import (
    HistoricalFrequencyResult,
    WAVE_THRESHOLD_M,
    WIND_THRESHOLD_MS,
    compute_historical_frequency,
)
from .speed_model import effective_speed_knots
from .environment_adapter import PlannerEnvironmentAdapter
from .land_mask import GebcoLandMaskProvider, LandMaskProvider

RISK_WEIGHTS = {
    "ice": 0.4,
    "depth": 0.2,
    "fog": 0.2,
    "wind": 0.1,
    "wave": 0.1,
}

# Fixed planning-cell resolution: every search cell is CELL_SIZE_KM square.
CELL_SIZE_KM = 25.0
LAT_KM_PER_DEG = 111.32
# Only cells inside this band around the sea-route corridor are sampled and
# searched; the rest of the corridor rectangle is a hard obstacle.
CORRIDOR_BAND_KM = 50.0
# Sentinel for cells that are outside the corridor band (no data).
NO_DATA = -1.0
# Frontend risk-raster display cap (cells are aggregated for the browser).
MAX_DISPLAY_DIM = 100

@dataclass(slots=True)
class PlanningGridResult:
    grid: PlanningGrid
    timestamp: datetime
    sample_count: int
    occurrence_counts: dict[str, int]
    data_sources: dict[str, str]
    unavailable: list[str]
    historical_years: list[int]
    historical_frequency: dict[str, object]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _ice_risk(state: EnvironmentState, vessel: VesselProfile) -> tuple[float, bool]:
    if not state.ice.available:
        return 0.5, False
    concentration = float(state.ice.concentration or 0.0)
    thickness = float(state.ice.thickness or 0.0)
    capability = max(vessel.ice_capability.continuous_ice_thickness_m, 0.1)
    # POLARIS-inspired RIO surrogate for the minimum data product: coverage,
    # thickness and multi-year ice are converted to one conservative load.
    multi_year_factor = 1.35 if thickness > 1.0 else 1.0
    load = concentration * (0.35 + 0.65 * min(thickness / capability, 1.5)) * multi_year_factor
    risk = float(np.clip((load - 0.12) / 1.15, 0.0, 1.0))
    # RIO < -10 is represented by the far end of the surrogate load scale.
    return risk, bool(load >= 1.35)


def _threshold_risk(value: float, threshold: float, margin: float, frequency: float) -> float:
    instantaneous = np.clip((value - (threshold - margin)) / max(margin, 1e-9), 0.0, 1.0)
    # A historical event frequency is already a [0, 1] risk score.  Taking the
    # maximum keeps a severe observation from being diluted by a calm prior.
    return float(np.clip(max(float(instantaneous), float(frequency)), 0.0, 1.0))


def _depth_risk(depth: float | None, vessel: VesselProfile) -> tuple[float, bool]:
    required = vessel.safety_constraints.draft + 2.0
    if depth is None:
        return 1.0, True
    value = float(depth)
    if value < required:
        return 1.0, True
    return float(np.clip((required + 40.0 - value) / 40.0, 0.0, 1.0)), False


def _corridor_waypoints(start: Position, goal: Position) -> list[tuple[float, float]]:
    """Return deterministic global-marine waypoints for the experiment."""

    if min(start.latitude, goal.latitude) < 60.0 and max(start.latitude, goal.latitude) < 65.0 and abs(start.longitude - goal.longitude) > 40.0:
        return [
            (start.latitude, start.longitude), (31.0, 125.0), (20.0, 120.0),
            (10.0, 110.0), (5.0, 105.0), (5.0, 80.0), (0.0, 60.0),
            (-10.0, 50.0), (-20.0, 40.0), (-30.0, 30.0), (-35.0, 20.0),
            (-35.0, 0.0), (-20.0, -10.0), (0.0, -10.0), (-20.0, -25.0),
            (10.0, -25.0), (30.0, -25.0), (51.0, -25.0), (20.0, -10.0),
            (36.0, -5.0), (goal.latitude, goal.longitude),
        ]
    return [(start.latitude, start.longitude), (goal.latitude, goal.longitude)]


def _great_circle_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1 = np.radians(first)
    lat2, lon2 = np.radians(second)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    hav = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return float(6371.0088 * 2.0 * np.arcsin(min(1.0, np.sqrt(hav))))


def _initial_bearing(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math_bearing(first[0], first[1], second[0], second[1])


def _destination(point: tuple[float, float], bearing_deg: float, distance_km: float) -> tuple[float, float]:
    lat1, lon1 = np.radians(point)
    bearing = np.radians(bearing_deg)
    angular = distance_km / 6371.0088
    lat2 = np.arcsin(np.sin(lat1) * np.cos(angular) + np.cos(lat1) * np.sin(angular) * np.cos(bearing))
    lon2 = lon1 + np.arctan2(np.sin(bearing) * np.sin(angular) * np.cos(lat1), np.cos(angular) - np.sin(lat1) * np.sin(lat2))
    return float(np.degrees(lat2)), float(((np.degrees(lon2) + 540.0) % 360.0) - 180.0)


def _interpolate(first: tuple[float, float], second: tuple[float, float], fraction: float) -> tuple[float, float]:
    """Spherical interpolation between two WGS84 points."""

    lat1, lon1 = np.radians(first)
    lat2, lon2 = np.radians(second)
    d = _great_circle_km(first, second) / 6371.0088
    if d < 1e-12:
        return first
    a = np.sin((1.0 - fraction) * d) / np.sin(d)
    b = np.sin(fraction * d) / np.sin(d)
    x = a * np.cos(lat1) * np.cos(lon1) + b * np.cos(lat2) * np.cos(lon2)
    y = a * np.cos(lat1) * np.sin(lon1) + b * np.cos(lat2) * np.sin(lon2)
    z = a * np.sin(lat1) + b * np.sin(lat2)
    return float(np.degrees(np.arctan2(z, np.hypot(x, y)))), float(np.degrees(np.arctan2(y, x)))


def _planning_axes(start: Position, goal: Position, grid_size: int) -> tuple[np.ndarray, np.ndarray]:
    """Build a two-dimensional 25km x 25km corridor grid.

    ``grid_size`` is retained for API compatibility. The physical resolution
    is fixed by ``CELL_SIZE_KM`` and the second dimension is the cross-track
    corridor index. The returned arrays are [row, column] cell-centre WGS84
    coordinates, so a single longitude step is never mistaken for a fixed
    distance at all latitudes.
    """

    waypoints = _corridor_waypoints(start, goal)
    centres: list[tuple[float, float, float]] = []
    carry = 0.0
    for segment_index, (first, second) in enumerate(zip(waypoints, waypoints[1:])):
        segment_km = _great_circle_km(first, second)
        bearing = _initial_bearing(first, second)
        distance = 0.0 if segment_index == 0 else CELL_SIZE_KM - carry
        while distance < segment_km:
            centre = _destination(first, bearing, distance)
            centres.append((centre[0], centre[1], bearing))
            distance += CELL_SIZE_KM
        carry = (carry + segment_km) % CELL_SIZE_KM
    centres.append((waypoints[-1][0], waypoints[-1][1], _initial_bearing(waypoints[-2], waypoints[-1])))
    offsets = np.arange(-CORRIDOR_BAND_KM, CORRIDOR_BAND_KM + CELL_SIZE_KM, CELL_SIZE_KM)
    latitudes = np.zeros((len(offsets), len(centres)), dtype=float)
    longitudes = np.zeros_like(latitudes)
    for column, (latitude, longitude, bearing) in enumerate(centres):
        for row, offset in enumerate(offsets):
            latitudes[row, column], longitudes[row, column] = _destination((latitude, longitude), bearing + 90.0, float(offset))
    return latitudes, longitudes


def _sample_points(latitudes: np.ndarray, longitudes: np.ndarray) -> Iterable[tuple[str, Position]]:
    for y in range(latitudes.shape[0]):
        for x in range(latitudes.shape[1]):
            yield f"{x}:{y}", Position(latitude=float(latitudes[y, x]), longitude=float(longitudes[y, x]))


def _largest_water_mask(obstacle: np.ndarray) -> np.ndarray:
    """Label the largest connected navigable water component.

    Coarse planning grids often leave tiny isolated water puddles around
    ports.  Snapping a city onto such a pixel traps the route inside it, so
    the anchor point is biased toward the dominant ocean body instead.
    """

    height, width = obstacle.shape
    visited = np.zeros((height, width), dtype=bool)
    largest_id = 0
    sizes: dict[int, int] = {}
    for start_y in range(height):
        for start_x in range(width):
            if obstacle[start_y, start_x] or visited[start_y, start_x]:
                continue
            next_id = len(sizes) + 1
            stack = [(start_x, start_y)]
            visited[start_y, start_x] = True
            size = 0
            while stack:
                x, y = stack.pop()
                size += 1
                for dx, dy in (
                    (1, 0), (-1, 0), (0, 1), (0, -1),
                    (1, 1), (1, -1), (-1, 1), (-1, -1),
                ):
                    nx, ny = x + dx, y + dy
                    if not (0 <= ny < height and 0 <= nx < width):
                        continue
                    if obstacle[ny, nx] or visited[ny, nx]:
                        continue
                    if dx != 0 and dy != 0:
                        # Never cut diagonally through a blocked corner.
                        if obstacle[y, nx] or obstacle[ny, x]:
                            continue
                    visited[ny, nx] = True
                    stack.append((nx, ny))
            sizes[next_id] = size
            if largest_id == 0 or size > sizes[largest_id]:
                largest_id = next_id
    if largest_id == 0:
        return np.zeros((height, width), dtype=bool)
    label = np.zeros((height, width), dtype=int)
    current_id = 0
    for start_y in range(height):
        for start_x in range(width):
            if obstacle[start_y, start_x] or label[start_y, start_x]:
                continue
            current_id += 1
            stack = [(start_x, start_y)]
            label[start_y, start_x] = current_id
            while stack:
                x, y = stack.pop()
                for dx, dy in (
                    (1, 0), (-1, 0), (0, 1), (0, -1),
                    (1, 1), (1, -1), (-1, 1), (-1, -1),
                ):
                    nx, ny = x + dx, y + dy
                    if not (0 <= ny < height and 0 <= nx < width):
                        continue
                    if obstacle[ny, nx] or label[ny, nx]:
                        continue
                    if dx != 0 and dy != 0:
                        if obstacle[y, nx] or obstacle[ny, x]:
                            continue
                    label[ny, nx] = current_id
                    stack.append((nx, ny))
    return label == largest_id


def _nearest_traversable(
    obstacle: np.ndarray,
    latitudes: np.ndarray,
    longitudes: np.ndarray,
    target: tuple[int, int],
) -> tuple[int, int] | None:
    """Find the nearest free cell when a city coordinate is on land."""

    candidates = np.argwhere(~obstacle)
    if not len(candidates):
        return None
    water_component = _largest_water_mask(obstacle)
    target_x, target_y = target
    target_lat = float(latitudes[target_y, target_x] if latitudes.ndim == 2 else latitudes[target_y])
    target_lon = float(longitudes[target_y, target_x] if longitudes.ndim == 2 else longitudes[target_x])
    distances = []
    for y, x in candidates:
        candidate_lat = float(latitudes[int(y), int(x)] if latitudes.ndim == 2 else latitudes[int(y)])
        candidate_lon = float(longitudes[int(y), int(x)] if longitudes.ndim == 2 else longitudes[int(x)])
        lat_delta = candidate_lat - target_lat
        lon_delta = (candidate_lon - target_lon) * np.cos(np.radians(target_lat))
        # A single isolated water pixel is usually a coarse-grid shoreline
        # artefact. Prefer cells with nearby water, then minimise distance.
        neighbour_count = 0
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = int(x) + dx, int(y) + dy
            if 0 <= ny < obstacle.shape[0] and 0 <= nx < obstacle.shape[1] and not obstacle[ny, nx]:
                neighbour_count += 1
        isolation_penalty = 1000.0 if neighbour_count == 0 else 0.0
        # Ports sitting in tiny coastal puddles must still reach the main
        # ocean body.  Cells outside the largest water component pay a hard
        # penalty so both snapped anchors join the same connected water.
        component_penalty = 1e6 if not water_component[int(y), int(x)] else 0.0
        distances.append(lat_delta * lat_delta + lon_delta * lon_delta + isolation_penalty + component_penalty)
    y, x = candidates[int(np.argmin(distances))]
    return int(x), int(y)


class SingleDayEnvironmentModel:
    """Build one static planning grid from a single UTC day.

    Historical hazard frequency is calculated from records on the same month
    and day in the explicit 2017-2025 experiment window. The target day itself
    remains a single PolarData observation; history contributes only priors.
    """

    def __init__(
        self,
        environment_service: EnvironmentService,
        frequency_provider=compute_historical_frequency,
        land_mask: LandMaskProvider | None = None,
    ):
        self.environment_service = environment_service
        self.frequency_provider = frequency_provider
        self.adapter = PlannerEnvironmentAdapter(environment_service)
        self.land_mask = land_mask or GebcoLandMaskProvider(environment_service)

    def build(
        self,
        start: Position,
        goal: Position,
        timestamp: datetime,
        vessel: VesselProfile,
        grid_size: int,
    ) -> PlanningGridResult:
        if grid_size < 12 or grid_size > 32:
            raise ValueError("grid_size must be between 12 and 32")
        timestamp = _utc(timestamp)
        latitudes, longitudes = _planning_axes(start, goal, grid_size)
        grid_height, grid_width = latitudes.shape
        points = list(_sample_points(latitudes, longitudes))
        sampled: dict[str, object] = {}
        for point_id, position in points:
            # The adapter decides whether the real providers cover this point;
            # outside the Arctic it queries only bathymetry and fills the other
            # layers deterministically. This avoids five full NetCDF lookups
            # for every global corridor cell.
            sampled[point_id] = self.adapter.sample(position, timestamp, vessel)

        # History is reduced at the midpoint of the route.  It is a regional
        # prior for this minimum experiment, while the target-day grid remains
        # spatially sampled from the configured PolarData providers.
        historical: HistoricalFrequencyResult = self.frequency_provider(
            timestamp,
            float((start.latitude + goal.latitude) / 2.0),
            float((start.longitude + goal.longitude) / 2.0),
        )
        wind_frequency = historical.hazards["strong_wind"].frequency
        wave_frequency = historical.hazards["high_wave"].frequency
        fog_frequency = historical.hazards["fog"].frequency
        occurrence_summary = {
            "wind": historical.hazards["strong_wind"].count,
            "wave": historical.hazards["high_wave"].count,
            "fog": historical.hazards["fog"].count,
        }
        # Ice is still reported as a target-day factor; no remote ice history
        # is inferred from the weather-frequency service.
        occurrence_summary["ice"] = 0
        shape = (grid_height, grid_width)
        factor_arrays = {name: np.zeros(shape, dtype=float) for name in RISK_WEIGHTS}
        combined_risk = np.full(shape, -1.0, dtype=float)
        speed = np.zeros(shape, dtype=float)
        obstacle = np.zeros(shape, dtype=bool)
        unavailable: set[str] = set()
        sources: dict[str, str] = {}
        sources["historical_frequency"] = historical.source
        if wind_frequency is None:
            unavailable.add("historical_wind_frequency")
        if wave_frequency is None:
            unavailable.add("historical_wave_frequency")
        cell_metadata: dict[tuple[int, int], dict[str, object]] = {}
        for y in range(grid_height):
            for x in range(grid_width):
                adapted = sampled[f"{x}:{y}"]
                raw_state = adapted.state
                state = adapted.state
                land = self.land_mask.check_cell(float(latitudes[y, x]), float(longitudes[y, x]), CELL_SIZE_KM)
                if land.is_land:
                    obstacle[y, x] = True
                    cell_metadata[(x, y)] = {
                        "cell_id": f"r{y}c{x}",
                        "center": {"latitude": float(latitudes[y, x]), "longitude": float(longitudes[y, x])},
                        "cell_size_m": CELL_SIZE_KM * 1000.0,
                        "bounds": {
                            "north": _destination((float(latitudes[y, x]), float(longitudes[y, x])), 0.0, CELL_SIZE_KM / 2.0)[0],
                            "east": _destination((float(latitudes[y, x]), float(longitudes[y, x])), 90.0, CELL_SIZE_KM / 2.0)[1],
                            "south": _destination((float(latitudes[y, x]), float(longitudes[y, x])), 180.0, CELL_SIZE_KM / 2.0)[0],
                            "west": _destination((float(latitudes[y, x]), float(longitudes[y, x])), 270.0, CELL_SIZE_KM / 2.0)[1],
                        },
                        "environment": {}, "quality": {"land_mask": "real"}, "sources": {"land_mask": land.source},
                        "risk": {"rio": -1.0, "fog": -1.0, "wind": -1.0, "wave": -1.0, "depth": -1.0, "combined": -1.0},
                        "is_land": True, "land_ratio": land.land_ratio, "effective_speed_kn": None,
                        "traversable": False, "obstacle_type": "land", "obstacle_reason": "land",
                    }
                    continue
                ice, ice_blocked = _ice_risk(state, vessel)
                depth, depth_blocked = _depth_risk(state.depth, vessel)
                wind_value = float(state.wind.speed or 0.0) if state.wind.available else 0.0
                wave_value = float(state.wave.height or 0.0) if state.wave.available else 0.0
                # For this experiment wind and wave risk are the historical
                # exceedance frequencies.  Instantaneous target-day thresholds
                # are only a fallback when the frequency source is unavailable.
                local_frequency = self.adapter.frequency(
                    Position(latitude=float(latitudes[y, x]), longitude=float(longitudes[y, x])), timestamp,
                    {"wind": wind_frequency if wind_frequency is not None else 0.28, "wave": wave_frequency if wave_frequency is not None else 0.24, "fog": fog_frequency if fog_frequency is not None else 0.12},
                )
                wind = max(local_frequency["wind"], _threshold_risk(wind_value, WIND_THRESHOLD_MS, 5.0, 0.0))
                wave = max(local_frequency["wave"], _threshold_risk(wave_value, WAVE_THRESHOLD_M, 1.2, 0.0))
                # PolarData has no visibility layer.  The eight-year visibility
                # / fog-code frequency is therefore the complete fog factor.
                fog = local_frequency["fog"]
                if not state.ice.available:
                    unavailable.add("ice")
                if not state.wind.available:
                    unavailable.add("wind")
                if not state.current.available:
                    unavailable.add("current")
                if not state.wave.available:
                    unavailable.add("wave")
                if state.depth is None:
                    unavailable.add("bathymetry")
                if fog_frequency is None:
                    unavailable.add("historical_fog_frequency")
                factor_arrays["ice"][y, x] = ice
                factor_arrays["depth"][y, x] = depth
                factor_arrays["fog"][y, x] = fog
                factor_arrays["wind"][y, x] = wind
                factor_arrays["wave"][y, x] = wave
                risk = sum(RISK_WEIGHTS[name] * factor_arrays[name][y, x] for name in RISK_WEIGHTS)
                combined_risk[y, x] = risk
                course = math_bearing(float(latitudes[y, x]), float(longitudes[y, x]), goal.latitude, goal.longitude)
                speed[y, x] = effective_speed_knots(state, vessel, course, risk)
                obstacle[y, x] = ice_blocked or depth_blocked or speed[y, x] <= 0.1
                cell_metadata[(x, y)] = {
                    "cell_id": f"r{y}c{x}",
                    "center": {"latitude": float(latitudes[y, x]), "longitude": float(longitudes[y, x])},
                    "cell_size_m": CELL_SIZE_KM * 1000.0,
                    "bounds": {
                        "north": _destination((float(latitudes[y, x]), float(longitudes[y, x])), 0.0, CELL_SIZE_KM / 2.0)[0],
                        "east": _destination((float(latitudes[y, x]), float(longitudes[y, x])), 90.0, CELL_SIZE_KM / 2.0)[1],
                        "south": _destination((float(latitudes[y, x]), float(longitudes[y, x])), 180.0, CELL_SIZE_KM / 2.0)[0],
                        "west": _destination((float(latitudes[y, x]), float(longitudes[y, x])), 270.0, CELL_SIZE_KM / 2.0)[1],
                    },
                    "environment": {
                        "depth_m": state.depth,
                        "ice_concentration": state.ice.concentration,
                        "ice_thickness_m": state.ice.thickness,
                        "wind_speed_ms": state.wind.speed,
                        "wind_direction_deg": state.wind.direction,
                        "wave_height_m": state.wave.height,
                        "wave_period_s": state.wave.period,
                        "wave_direction_deg": state.wave.direction,
                        "current_u_ms": state.current.u,
                        "current_v_ms": state.current.v,
                        "current_speed_ms": state.current.speed,
                    },
                    "quality": adapted.quality,
                    "sources": adapted.sources,
                    "risk": {"rio": float(ice), "fog": float(fog), "wind": float(wind), "wave": float(wave), "depth": float(depth), "combined": float(risk)},
                    "is_land": False,
                    "land_ratio": float(land.land_ratio),
                    "effective_speed_kn": float(speed[y, x]),
                    "traversable": not bool(obstacle[y, x]),
                    "obstacle_type": "shallow_water_or_ice" if obstacle[y, x] else None,
                    "obstacle_reason": "insufficient_depth_or_ice" if obstacle[y, x] else None,
                }
                for source in (state.sources.bathymetry, state.sources.ice, state.sources.wind, state.sources.current, state.sources.wave):
                    if source:
                        sources[source] = source

        # A cell centre is not enough to establish navigability at a 25 km
        # resolution.  A narrow island or a peninsula can sit between two
        # otherwise wet centres.  Treat every sampled neighbour edge as a
        # hard constraint and block both cells when its midpoint is too
        # shallow.  This also prevents diagonal shortcuts around coastlines.
        required_depth = vessel.safety_constraints.draft + 2.0
        checked_edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
        for y in range(grid_height):
            for x in range(grid_width):
                if obstacle[y, x]:
                    continue
                for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < grid_width and 0 <= ny < grid_height):
                        continue
                    edge = ((x, y), (nx, ny))
                    reverse = ((nx, ny), (x, y))
                    if edge in checked_edges or reverse in checked_edges:
                        continue
                    checked_edges.add(edge)
                    midpoint = Position(
                        latitude=float((latitudes[y, x] + latitudes[ny, nx]) / 2.0),
                        longitude=float((longitudes[y, x] + longitudes[ny, nx]) / 2.0),
                    )
                    try:
                        midpoint_sample = self.adapter.sample(midpoint, timestamp, vessel)
                        midpoint_depth = midpoint_sample.state.depth
                    except (LookupError, OSError, RuntimeError, ValueError):
                        midpoint_depth = None
                    if midpoint_depth is None or float(midpoint_depth) < required_depth:
                        obstacle[y, x] = True
                        obstacle[ny, nx] = True
                        cell_metadata[(x, y)]["traversable"] = False
                        cell_metadata[(x, y)]["obstacle_reason"] = "land_or_shallow_edge"
                        cell_metadata[(nx, ny)]["traversable"] = False
                        cell_metadata[(nx, ny)]["obstacle_reason"] = "land_or_shallow_edge"

        requested_start = tuple(int(value) for value in np.unravel_index(np.argmin((latitudes - start.latitude) ** 2 + (longitudes - start.longitude) ** 2), latitudes.shape)[::-1])
        requested_goal = tuple(int(value) for value in np.unravel_index(np.argmin((latitudes - goal.latitude) ** 2 + (longitudes - goal.longitude) ** 2), latitudes.shape)[::-1])
        planning_start = _nearest_traversable(obstacle, latitudes, longitudes, requested_start)
        planning_goal = _nearest_traversable(obstacle, latitudes, longitudes, requested_goal)
        if planning_start is None or planning_goal is None:
            raise RuntimeError("The environment grid contains no navigable water cells")
        grid = PlanningGrid(
            latitudes,
            longitudes,
            combined_risk,
            speed,
            obstacle,
            factor_arrays,
            planning_start,
            planning_goal,
            CELL_SIZE_KM * 1000.0,
            cell_metadata,
        )
        return PlanningGridResult(
            grid,
            timestamp,
            len(sampled),
            occurrence_summary,
            sources,
            sorted(unavailable),
            historical.available_years,
            historical.as_dict(),
        )

    def inspect(self, position: Position, timestamp: datetime, vessel: VesselProfile) -> dict[str, object]:
        """Return one complete 25 km environment/risk cell.

        This is the point-inspection contract used by the independent
        environment raster.  It intentionally shares the adapter and the
        one-day historical frequency source with the route planner so a cell
        inspected before creating a task has the same semantics as a planned
        cell.
        """
        timestamp = _utc(timestamp)
        adapted = self.adapter.sample(position, timestamp, vessel)
        state = adapted.state
        historical = self.frequency_provider(timestamp, position.latitude, position.longitude)
        base = {
            "wind": historical.hazards["strong_wind"].frequency or 0.28,
            "wave": historical.hazards["high_wave"].frequency or 0.24,
            "fog": historical.hazards["fog"].frequency or 0.12,
        }
        local = self.adapter.frequency(position, timestamp, base)
        ice, ice_blocked = _ice_risk(state, vessel)
        depth, depth_blocked = _depth_risk(state.depth, vessel)
        wind = max(local["wind"], _threshold_risk(float(state.wind.speed or 0.0), WIND_THRESHOLD_MS, 5.0, 0.0))
        wave = max(local["wave"], _threshold_risk(float(state.wave.height or 0.0), WAVE_THRESHOLD_M, 1.2, 0.0))
        fog = local["fog"]
        risk = sum(RISK_WEIGHTS[name] * value for name, value in {
            "ice": ice, "depth": depth, "fog": fog, "wind": wind, "wave": wave,
        }.items())
        speed = effective_speed_knots(state, vessel, 0.0, risk)
        obstacle = ice_blocked or depth_blocked or speed <= 0.1
        half = CELL_SIZE_KM / 2.0
        return {
            "cell_id": f"env-{round(position.latitude, 5)}-{round(position.longitude, 5)}",
            "center": {"latitude": position.latitude, "longitude": position.longitude},
            "cell_size_m": CELL_SIZE_KM * 1000.0,
            "bounds": {
                "north": _destination((position.latitude, position.longitude), 0.0, half)[0],
                "east": _destination((position.latitude, position.longitude), 90.0, half)[1],
                "south": _destination((position.latitude, position.longitude), 180.0, half)[0],
                "west": _destination((position.latitude, position.longitude), 270.0, half)[1],
            },
            "environment": {
                "depth_m": state.depth,
                "ice_concentration": state.ice.concentration,
                "ice_thickness_m": state.ice.thickness,
                "wind_speed_ms": state.wind.speed,
                "wind_direction_deg": state.wind.direction,
                "wave_height_m": state.wave.height,
                "wave_period_s": state.wave.period,
                "wave_direction_deg": state.wave.direction,
                "current_u_ms": state.current.u,
                "current_v_ms": state.current.v,
                "current_speed_ms": state.current.speed,
            },
            "risk": {"rio": ice, "fog": fog, "wind": wind, "wave": wave, "depth": depth, "combined": risk},
            "quality": adapted.quality,
            "sources": adapted.sources,
            "effective_speed_kn": speed,
            "traversable": not obstacle,
            "obstacle_reason": "insufficient_depth_or_ice" if obstacle else None,
        }


def math_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing in degrees clockwise from true north."""

    a1, a2 = np.radians([lat1, lat2])
    delta = np.radians(lon2 - lon1)
    value = np.degrees(np.arctan2(np.sin(delta) * np.cos(a2), np.cos(a1) * np.sin(a2) - np.sin(a1) * np.cos(a2) * np.cos(delta)))
    return float((value + 360.0) % 360.0)
