"""Planner-facing environment adapter with deterministic gap filling.

The operational providers remain the source of truth.  Planning, however,
needs a complete value for every 25 km cell so that a missing Arctic-only
layer cannot silently turn into a zero-risk cell.  This adapter fills only
missing fields with a deterministic, documented experiment model and records
the quality of every field.  A future global provider can replace this class
without changing the planner or API contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math

import numpy as np

from core.models import (
    EnvironmentCurrentState,
    EnvironmentIceState,
    EnvironmentSources,
    EnvironmentState,
    EnvironmentVector,
    EnvironmentWaveState,
    EnvironmentWindState,
    Position,
)
from core.vessel.models import VesselProfile
from services.environment_service.service import EnvironmentService


@dataclass(slots=True)
class PlannerEnvironmentSample:
    state: EnvironmentState
    quality: dict[str, str]
    sources: dict[str, str]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _phase(latitude: float, longitude: float, day_of_year: int) -> float:
    return math.radians(latitude * 2.7 + longitude * 0.83 + day_of_year * 3.1)


def _synthetic_depth(latitude: float, longitude: float) -> float:
    """Return a repeatable fallback bathymetry value in metres.

    The low-frequency pseudo-continents are intentionally only a fallback. In
    normal operation GEBCO supplies the depth and land mask. The pattern is
    stable across runs, spatially smooth, and conservative around shorelines.
    """

    p = math.radians(latitude * 1.9 + longitude * 0.55)
    q = math.radians(latitude * 0.43 - longitude * 1.15)
    continental = math.sin(p) + 0.55 * math.sin(q) + 0.2 * math.cos(p * 0.43)
    if continental > 1.0:
        return 0.0
    return float(1800.0 + 1800.0 * (0.5 + 0.5 * math.sin(p + q)))


def _synthetic_ice(latitude: float, longitude: float, day_of_year: int) -> tuple[float, float, EnvironmentVector]:
    seasonal = 0.5 + 0.5 * math.cos(math.radians(day_of_year - 35.0))
    polar = np.clip((abs(latitude) - 52.0) / 35.0, 0.0, 1.0)
    wave = 0.5 + 0.5 * math.sin(math.radians(longitude * 2.0 + latitude * 3.0))
    concentration = float(np.clip(polar * (0.18 + 0.65 * seasonal) * (0.65 + 0.35 * wave), 0.0, 1.0))
    thickness = float(np.clip(concentration * (0.25 + 1.25 * seasonal), 0.0, 2.2))
    velocity = EnvironmentVector(
        u=float(0.08 * math.sin(math.radians(longitude))),
        v=float(0.08 * math.cos(math.radians(latitude))),
        speed=0.08,
    )
    return concentration, thickness, velocity


def _synthetic_wind(latitude: float, longitude: float, day_of_year: int) -> tuple[float, float, float, float]:
    phase = _phase(latitude, longitude, day_of_year)
    speed = float(np.clip(6.0 + 5.0 * math.sin(phase) + 2.5 * math.cos(phase * 0.61), 0.5, 22.0))
    direction = float((180.0 + math.degrees(phase * 1.7)) % 360.0)
    direction_rad = math.radians(direction)
    return speed, direction, -speed * math.sin(direction_rad), -speed * math.cos(direction_rad)


def _synthetic_wave(latitude: float, longitude: float, day_of_year: int) -> tuple[float, float, float]:
    phase = _phase(latitude, longitude, day_of_year)
    height = float(np.clip(1.4 + 1.8 * (0.5 + 0.5 * math.sin(phase * 1.31)) + 0.7 * abs(math.sin(phase * 0.47)), 0.1, 7.5))
    period = float(np.clip(6.0 + 2.5 * math.cos(phase), 3.0, 14.0))
    direction = float((math.degrees(phase * 2.0) + 180.0) % 360.0)
    return height, period, direction


class PlannerEnvironmentAdapter:
    """Complete planner cells while preserving real/synthetic provenance."""

    source_name = "planner-deterministic-gap-fill-v1"
    arctic_provider_latitude = 45.0

    def __init__(self, environment_service: EnvironmentService):
        self.environment_service = environment_service

    def sample(
        self,
        position: Position,
        timestamp: datetime,
        vessel: VesselProfile | None = None,
        state: EnvironmentState | None = None,
    ) -> PlannerEnvironmentSample:
        requested = _utc(timestamp)
        if state is None and abs(position.latitude) < self.arctic_provider_latitude:
            try:
                depth = self.environment_service.query_bathymetry(position.latitude, position.longitude).depth
            except Exception:
                depth = None
            state = EnvironmentState(
                timestamp=requested,
                requested_time=requested,
                latitude=position.latitude,
                longitude=position.longitude,
                depth=depth,
                ice=EnvironmentIceState(available=False, reason="outside_arctic_provider_band"),
                wind=EnvironmentWindState(available=False, reason="outside_arctic_provider_band"),
                current=EnvironmentCurrentState(available=False, reason="outside_arctic_provider_band"),
                wave=EnvironmentWaveState(available=False, reason="outside_arctic_provider_band"),
                sources=EnvironmentSources(bathymetry="GEBCO_2026_sub_ice" if depth is not None else None),
            )
        elif state is None:
            try:
                state = self.environment_service.query_complete_environment(position.latitude, position.longitude, requested)
            except Exception:
                state = None
        day_of_year = requested.timetuple().tm_yday
        quality: dict[str, str] = {}
        sources: dict[str, str] = {}

        depth = None if state is None else state.depth
        if depth is None:
            depth = _synthetic_depth(position.latitude, position.longitude)
            quality["depth"] = "synthetic"
            sources["bathymetry"] = self.source_name
        else:
            quality["depth"] = "real"
            sources["bathymetry"] = state.sources.bathymetry or "bathymetry"

        ice = None if state is None else state.ice
        if ice is None or not ice.available or ice.concentration is None:
            concentration, thickness, velocity = _synthetic_ice(position.latitude, position.longitude, day_of_year)
            ice = EnvironmentIceState(available=True, matched_time=requested, concentration=concentration, thickness=thickness, velocity=velocity, reason="deterministic_gap_fill")
            quality["ice"] = "synthetic"
            sources["ice"] = self.source_name
        else:
            quality["ice"] = "real"
            sources["ice"] = ice_source = (state.sources.ice if state is not None else None) or "ice"

        wind = None if state is None else state.wind
        if wind is None or not wind.available or wind.speed is None:
            speed, direction, u10, v10 = _synthetic_wind(position.latitude, position.longitude, day_of_year)
            wind = EnvironmentWindState(available=True, matched_time=requested, speed=speed, direction=direction, u10=u10, v10=v10, reason="deterministic_gap_fill")
            quality["wind"] = "synthetic"
            sources["wind"] = self.source_name
        else:
            quality["wind"] = "real"
            sources["wind"] = (state.sources.wind if state is not None else None) or "wind"

        current = None if state is None else state.current
        if current is None or not current.available or current.u is None or current.v is None:
            phase = _phase(position.latitude, position.longitude, day_of_year)
            u, v = 0.35 * math.sin(phase), 0.35 * math.cos(phase)
            current = EnvironmentCurrentState(available=True, matched_time=requested, u=u, v=v, speed=math.hypot(u, v), reason="deterministic_gap_fill")
            quality["current"] = "synthetic"
            sources["current"] = self.source_name
        else:
            quality["current"] = "real"
            sources["current"] = (state.sources.current if state is not None else None) or "current"

        wave = None if state is None else state.wave
        if wave is None or not wave.available or wave.height is None:
            height, period, direction = _synthetic_wave(position.latitude, position.longitude, day_of_year)
            wave = EnvironmentWaveState(available=True, matched_time=requested, height=height, period=period, direction=direction, reason="deterministic_gap_fill")
            quality["wave"] = "synthetic"
            sources["wave"] = self.source_name
        else:
            quality["wave"] = "real"
            sources["wave"] = (state.sources.wave if state is not None else None) or "wave"

        if state is not None:
            state = state.model_copy(deep=True)
            state.depth = depth
            state.ice = ice
            state.wind = wind
            state.current = current
            state.wave = wave
            state.sources = EnvironmentSources(
                bathymetry=sources.get("bathymetry", state.sources.bathymetry),
                ice=sources.get("ice", state.sources.ice),
                wind=sources.get("wind", state.sources.wind),
                current=sources.get("current", state.sources.current),
                wave=sources.get("wave", state.sources.wave),
            )
        else:
            state = EnvironmentState(
                timestamp=requested,
                requested_time=requested,
                latitude=position.latitude,
                longitude=position.longitude,
                depth=depth,
                ice=ice,
                wind=wind,
                current=current,
                wave=wave,
                sources=EnvironmentSources(**sources),
            )
        return PlannerEnvironmentSample(state=state, quality=quality, sources=sources)

    def frequency(self, position: Position, timestamp: datetime, base: dict[str, float] | None = None) -> dict[str, float]:
        """Return spatially varying same-day hazard priors for a cell."""

        day_of_year = _utc(timestamp).timetuple().tm_yday
        phase = _phase(position.latitude, position.longitude, day_of_year)
        base = base or {"wind": 0.28, "wave": 0.24, "fog": 0.12}
        modulation = lambda offset: float(np.clip(0.65 + 0.5 * math.sin(phase + offset), 0.35, 1.2))
        return {
            "wind": float(np.clip((base.get("wind") if base.get("wind") is not None else 0.28) * modulation(0.0), 0.0, 1.0)),
            "wave": float(np.clip((base.get("wave") if base.get("wave") is not None else 0.24) * modulation(1.7), 0.0, 1.0)),
            "fog": float(np.clip((base.get("fog") if base.get("fog") is not None else 0.12) * modulation(3.1), 0.0, 1.0)),
        }


__all__ = ["PlannerEnvironmentAdapter", "PlannerEnvironmentSample"]
