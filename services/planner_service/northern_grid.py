"""Viewport DTOs from the persistent Northeast Passage planning grid."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter

import numpy as np

from core.models import EnvironmentCurrentState, EnvironmentIceState, EnvironmentSources, EnvironmentState, EnvironmentWaveState, EnvironmentWindState
from core.vessel.models import VesselProfile
from .environment_adapter import _phase, _synthetic_ice, _synthetic_wave, _synthetic_wind
from .environment_model import RISK_WEIGHTS, _depth_risk, _ice_risk, _threshold_risk
from .historical_frequency import WAVE_THRESHOLD_M, WIND_THRESHOLD_MS
from .speed_model import effective_speed_knots
from .static_grid import StaticGridRepository
from .dnsga3 import PlanningGrid


class NorthernHemisphereGrid:
    """Compatibility name; it now exposes only the configured NEP grid."""

    def __init__(self, model: object, vessel: VesselProfile, land_mask: object | None = None):
        self.vessel = vessel
        self.static_grid = StaticGridRepository.load()
        self._risk_cache: dict[tuple[str, str, int, int], dict[str, object]] = {}

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    def _dynamic_cell(self, row: int, col: int, timestamp: datetime) -> dict[str, object]:
        key = (timestamp.date().isoformat(), self.vessel.identity.id, row, col)
        if key in self._risk_cache:
            return self._risk_cache[key]
        grid = self.static_grid
        latitude, longitude = float(grid.center_lat[row, col]), float(grid.center_lon[row, col])
        bounds = {"north": float(grid.corners_lat[row, col].max()), "south": float(grid.corners_lat[row, col].min()), "east": float(grid.corners_lon[row, col].max()), "west": float(grid.corners_lon[row, col].min())}
        geometry = [[float(grid.corners_lon[row, col, index]), float(grid.corners_lat[row, col, index])] for index in range(4)]
        cell_id = f"r{row}c{col}"
        if not grid.static_traversable[row, col]:
            reason = "land" if grid.is_land[row, col] else "shallow_water"
            result = {"cell_id": cell_id, "row": row, "col": col, "inside_planning_region": True, "center": {"latitude": latitude, "longitude": longitude}, "bounds": bounds, "geometry": geometry, "cell_size_m": 25_000.0, "environment": {"depth_m": float(grid.depth_m[row, col])}, "risk": {"rio": -1.0, "fog": -1.0, "wind": -1.0, "wave": -1.0, "depth": -1.0, "combined": -1.0}, "quality": {"static_grid": "real"}, "sources": {"static_grid": "GEBCO_2026_polar_3413_batch"}, "is_land": bool(grid.is_land[row, col]), "land_ratio": float(grid.land_ratio[row, col]), "effective_speed_kn": None, "traversable": False, "obstacle_type": reason, "obstacle_reason": reason}
            self._risk_cache[key] = result
            return result
        day = timestamp.timetuple().tm_yday
        concentration, thickness, velocity = _synthetic_ice(latitude, longitude, day)
        wind_speed, wind_direction, wind_u, wind_v = _synthetic_wind(latitude, longitude, day)
        wave_height, wave_period, wave_direction = _synthetic_wave(latitude, longitude, day)
        phase = _phase(latitude, longitude, day)
        current_u, current_v = .35 * np.sin(phase), .35 * np.cos(phase)
        state = EnvironmentState(timestamp=timestamp, requested_time=timestamp, latitude=latitude, longitude=longitude, depth=float(grid.depth_m[row, col]), ice=EnvironmentIceState(available=True, concentration=concentration, thickness=thickness, velocity=velocity), wind=EnvironmentWindState(available=True, speed=wind_speed, direction=wind_direction, u10=wind_u, v10=wind_v), current=EnvironmentCurrentState(available=True, u=float(current_u), v=float(current_v), speed=float(np.hypot(current_u, current_v))), wave=EnvironmentWaveState(available=True, height=wave_height, period=wave_period, direction=wave_direction), sources=EnvironmentSources(bathymetry="GEBCO_2026_polar_3413_batch", ice="planner-deterministic-gap-fill-v1", wind="planner-deterministic-gap-fill-v1", current="planner-deterministic-gap-fill-v1", wave="planner-deterministic-gap-fill-v1"))
        ice, ice_blocked = _ice_risk(state, self.vessel); depth, depth_blocked = _depth_risk(state.depth, self.vessel)
        frequency = {"wind": float(np.clip(.35 + .25 * np.sin(phase * .77), 0, 1)), "wave": float(np.clip(.12 + .2 * np.cos(phase * .51), 0, 1)), "fog": float(np.clip(.18 + .18 * np.sin(phase + 1.4), 0, 1))}
        wind = _threshold_risk(wind_speed, WIND_THRESHOLD_MS, 5.0, frequency["wind"]); wave = _threshold_risk(wave_height, WAVE_THRESHOLD_M, 1.2, frequency["wave"]); fog = frequency["fog"]
        combined = sum(RISK_WEIGHTS[name] * value for name, value in {"ice": ice, "depth": depth, "fog": fog, "wind": wind, "wave": wave}.items())
        speed = effective_speed_knots(state, self.vessel, 0.0, combined); blocked = ice_blocked or depth_blocked or speed <= .1
        result = {"cell_id": cell_id, "row": row, "col": col, "inside_planning_region": True, "center": {"latitude": latitude, "longitude": longitude}, "bounds": bounds, "geometry": geometry, "cell_size_m": 25_000.0, "environment": {"depth_m": state.depth, "ice_concentration": concentration, "ice_thickness_m": thickness, "wind_speed_ms": wind_speed, "wind_direction_deg": wind_direction, "wave_height_m": wave_height, "wave_period_s": wave_period, "wave_direction_deg": wave_direction, "current_u_ms": float(current_u), "current_v_ms": float(current_v), "current_speed_ms": float(np.hypot(current_u, current_v))}, "risk": {"rio": float(ice), "fog": fog, "wind": wind, "wave": wave, "depth": float(depth), "combined": float(combined)}, "quality": {"depth": "real", "ice": "synthetic", "wind": "synthetic", "wave": "synthetic", "current": "synthetic"}, "sources": {"static_grid": "GEBCO_2026_polar_3413_batch"}, "is_land": False, "land_ratio": float(grid.land_ratio[row, col]), "effective_speed_kn": float(speed), "traversable": not blocked, "obstacle_type": "shallow_water_or_ice" if blocked else None, "obstacle_reason": "insufficient_depth_or_ice" if blocked else None}
        self._risk_cache[key] = result
        return result

    def build(self, timestamp: datetime, south: float = 60., north: float = 80., west: float = 30., east: float = 180., max_cells: int = 2000) -> dict[str, object]:
        started = perf_counter(); timestamp = self._utc(timestamp); max_cells = max(100, min(max_cells, 3000))
        indices, intersection = self.static_grid.viewport_indices(south, north, west, east)
        if intersection is None:
            return {"cell_size_m": 25_000.0, "coordinate_reference": "EPSG:3413 fixed 25 km grid", "planning_region": self.static_grid.metadata["region"], "bounds": {"south": south, "north": north, "west": west, "east": east}, "cells": [], "cell_count": 0, "timestamp": timestamp.isoformat(), "metrics": {"intersection": None, "total_ms": round((perf_counter()-started)*1000,2), "cache_hit": True}}
        if len(indices) > max_cells:
            raise ValueError(f"GRID_LIMIT_EXCEEDED: 当前视口包含 {len(indices)} 个 25 km 栅格，超过 {max_cells} 个显示上限。请放大后查看。")
        before_dynamic = perf_counter(); cells = [self._dynamic_cell(int(row), int(col), timestamp) for row, col in indices]
        return {"cell_size_m": 25_000.0, "coordinate_reference": "EPSG:3413 fixed 25 km grid", "planning_region": self.static_grid.metadata["region"], "bounds": intersection, "cells": cells, "cell_count": len(cells), "timestamp": timestamp.isoformat(), "metrics": {"intersection": intersection, "row_range": [int(indices[:,0].min()), int(indices[:,0].max())] if len(indices) else [], "col_range": [int(indices[:,1].min()), int(indices[:,1].max())] if len(indices) else [], "static_query_ms": 0., "environment_query_ms": round((perf_counter() - before_dynamic)*1000, 2), "risk_ms": 0., "serialize_ms": 0., "total_ms": round((perf_counter()-started)*1000,2), "cache_hit": False}}

    def cell_at(self, latitude: float, longitude: float, timestamp: datetime) -> dict[str, object] | None:
        point = self.static_grid.nearest_cell(latitude, longitude)
        return None if point is None else self._dynamic_cell(point[1], point[0], self._utc(timestamp))

    def global_planning_grid(self, start: object, goal: object, timestamp: datetime) -> PlanningGrid:
        """Return the entire fixed NEP matrix for D* Lite and NSGA-III.

        This deliberately bypasses the viewport cap and never serializes via
        the HTTP DTO path.  D* Lite receives the same fixed row/column index
        that the environment panel renders.
        """
        from core.models import Position

        if not isinstance(start, Position) or not isinstance(goal, Position):
            raise ValueError("起点和终点必须是有效坐标。")
        start_cell = self.static_grid.nearest_cell(start.latitude, start.longitude)
        goal_cell = self.static_grid.nearest_cell(goal.latitude, goal.longitude)
        if start_cell is None or goal_cell is None:
            region = self.static_grid.metadata["region"]
            raise ValueError(f"本实验仅支持东北航道研究区：{region['south']}–{region['north']}°N、{region['west']}–{region['east']}°E。")
        timestamp = self._utc(timestamp)
        height, width = self.static_grid.shape
        risk = np.ones((height, width), dtype=float)
        speed = np.zeros((height, width), dtype=float)
        obstacle = ~self.static_grid.static_traversable.copy()
        factors = {name: np.ones((height, width), dtype=float) for name in ("ice", "depth", "fog", "wind", "wave")}
        metadata: dict[tuple[int, int], dict[str, object]] = {}
        for row, col in np.argwhere(self.static_grid.inside_region):
            cell = self._dynamic_cell(int(row), int(col), timestamp)
            cell_risk = cell["risk"]
            risk[row, col] = float(cell_risk["combined"])
            obstacle[row, col] = not bool(cell["traversable"])
            if not obstacle[row, col]:
                speed[row, col] = float(cell["effective_speed_kn"] or 0.0)
                factors["ice"][row, col] = float(cell_risk["rio"])
                factors["depth"][row, col] = float(cell_risk["depth"])
                factors["fog"][row, col] = float(cell_risk["fog"])
                factors["wind"][row, col] = float(cell_risk["wind"])
                factors["wave"][row, col] = float(cell_risk["wave"])
            metadata[(int(col), int(row))] = cell
        # Search out from a requested cell if a coast cell was selected.
        def nearest_open(point: tuple[int, int]) -> tuple[int, int] | None:
            x, y = point
            for radius in range(max(width, height)):
                for yy in range(max(0, y - radius), min(height, y + radius + 1)):
                    for xx in range(max(0, x - radius), min(width, x + radius + 1)):
                        if max(abs(xx - x), abs(yy - y)) == radius and not obstacle[yy, xx]:
                            return xx, yy
            return None
        resolved_start, resolved_goal = nearest_open(start_cell), nearest_open(goal_cell)
        if resolved_start is None or resolved_goal is None:
            raise RuntimeError("东北航道标准网格中不存在可通航的起点或终点。")
        return PlanningGrid(self.static_grid.center_lat, self.static_grid.center_lon, risk, speed, obstacle, factors, resolved_start, resolved_goal, 25_000.0, metadata)
