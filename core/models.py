"""Stable API/domain models shared by service implementations and adapters."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class Position(BaseModel):
    """WGS84 geographic position in decimal degrees."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class EnvironmentQuery(BaseModel):
    """A location and UTC instant for all time-aware environment providers."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    timestamp: datetime

    @property
    def position(self) -> Position:
        """Expose a shared WGS84 position without duplicating validation rules."""

        return Position(latitude=self.latitude, longitude=self.longitude)


class EnvironmentTimeState(BaseModel):
    """Current clock configuration for time-aware environmental queries."""

    simulation_time: datetime
    forecast_time: datetime | None = None
    time_step_seconds: int = Field(..., gt=0)
    scenario: Literal["winter", "summer"]
    range_start: datetime
    range_end: datetime
    is_playing: bool = False


class EnvironmentVector(BaseModel):
    """Two-dimensional geographic vector and its magnitude."""

    u: float
    v: float
    speed: float = Field(..., ge=0)


class EnvironmentIceState(BaseModel):
    """Planner-ready sea-ice subset with explicit availability semantics."""

    available: bool
    matched_time: datetime | None = None
    concentration: float | None = Field(default=None, ge=0, le=1)
    thickness: float | None = Field(default=None, ge=0)
    velocity: EnvironmentVector | None = None
    reason: str | None = None


class EnvironmentWindState(BaseModel):
    """Planner-ready 10 m wind subset."""

    available: bool
    matched_time: datetime | None = None
    speed: float | None = Field(default=None, ge=0)
    direction: float | None = Field(default=None, ge=0, lt=360)
    u10: float | None = None
    v10: float | None = None
    reason: str | None = None


class EnvironmentCurrentState(BaseModel):
    """Planner-ready geographic surface-current subset."""

    available: bool
    matched_time: datetime | None = None
    u: float | None = None
    v: float | None = None
    speed: float | None = Field(default=None, ge=0)
    reason: str | None = None


class EnvironmentWaveState(BaseModel):
    """Planner-ready Arctic wave subset."""

    available: bool
    matched_time: datetime | None = None
    height: float | None = Field(default=None, ge=0)
    period: float | None = Field(default=None, ge=0)
    direction: float | None = Field(default=None, ge=0, lt=360)
    reason: str | None = None


class EnvironmentSources(BaseModel):
    """Source attribution for every component in one unified response."""

    bathymetry: str | None = None
    ice: str | None = None
    wind: str | None = None
    current: str | None = None
    wave: str | None = None


class LegacyEnvironmentState(BaseModel):
    """Phase 0 snapshot retained unchanged by the legacy ``/api/environment`` API."""

    position: Position
    time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ice: dict[str, object] | None = None
    wind: dict[str, object] | None = None
    current: dict[str, object] | None = None
    wave: dict[str, object] | None = None
    depth: float | None = Field(default=None, ge=0)


class EnvironmentState(BaseModel):
    """One typed, fault-isolated WGS84/time environment snapshot."""

    timestamp: datetime
    requested_time: datetime
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    depth: float | None = Field(default=None, ge=0)
    ice: EnvironmentIceState
    wind: EnvironmentWindState
    current: EnvironmentCurrentState
    wave: EnvironmentWaveState
    sources: EnvironmentSources


class EnvironmentCell(BaseModel):
    """One unified, source-faithful environmental grid cell.

    The cell is an intermediate representation only: it carries sampled
    physical values and per-source match times, but deliberately contains no
    risk, routing, or navigability interpretation.
    """

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    timestamp: datetime
    requested_time: datetime
    depth: float | None = Field(default=None, ge=0)
    ice: EnvironmentIceState
    wind: EnvironmentWindState
    current: EnvironmentCurrentState
    wave: EnvironmentWaveState
    sources: EnvironmentSources


class SeaIceState(BaseModel):
    """Sea-ice observation at a WGS84 location and timestamp.

    Concentration is a fractional coverage in the inclusive range 0.0–1.0;
    thickness is expressed in metres. This contract is source-format agnostic.
    """

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    timestamp: datetime
    concentration: float = Field(..., ge=0, le=1)
    thickness: float | None = Field(default=None, ge=0, description="Sea-ice thickness in metres")
    ice_type: int | None = Field(
        default=None,
        ge=0,
        le=2,
        description="Dominant type: 0 open water, 1 young ice, 2 multi-year ice",
    )
    drift_u: float | None = Field(default=None, description="Sea-ice drift U component in m/s")
    drift_v: float | None = Field(default=None, description="Sea-ice drift V component in m/s")
    snow_thickness: float | None = Field(default=None, ge=0, description="Snow thickness in metres")
    source: str


class BathymetryState(BaseModel):
    """Positive-down water depth sampled at a WGS84 location."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    depth: float = Field(..., ge=0, description="Water depth in metres, positive downward")
    timestamp: datetime
    source: str


class WindState(BaseModel):
    """10 m wind sampled at a WGS84 position and UTC time."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    timestamp: datetime
    matched_time: datetime | None = Field(
        default=None,
        description="Nearest source timestamp used for the sample",
    )
    u10: float = Field(..., description="Eastward wind component in m/s")
    v10: float = Field(..., description="Northward wind component in m/s")
    wind_speed: float = Field(..., ge=0, description="Wind speed in m/s")
    wind_direction_math: float = Field(..., ge=0, lt=360, description="Direction toward, degrees CCW from east")
    wind_direction_meteorological: float = Field(..., ge=0, lt=360, description="Direction from, degrees clockwise from north")
    wind_direction: float | None = Field(
        default=None,
        ge=0,
        lt=360,
        description="Original meteorological wind-from direction in degrees true",
    )
    source: str


class CurrentState(BaseModel):
    """TOPAZ5 surface current converted from grid axes to geographic axes."""

    timestamp: datetime
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    vxo: float = Field(..., description="Original TOPAZ grid-x velocity in m/s")
    vyo: float = Field(..., description="Original TOPAZ grid-y velocity in m/s")
    current_east: float = Field(..., description="Geographic eastward velocity in m/s")
    current_north: float = Field(..., description="Geographic northward velocity in m/s")
    current_speed: float = Field(..., ge=0, description="Surface-current speed in m/s")
    current_direction_to: float = Field(
        ...,
        ge=0,
        lt=360,
        description="Direction toward, degrees clockwise from geographic north",
    )
    source: str
    detided: bool = True


class WaveState(BaseModel):
    """Copernicus Arctic wave conditions at one WGS84 position."""

    timestamp: datetime = Field(..., description="Actual matched data time")
    requested_time: datetime
    matched_time: datetime
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    wave_height: float = Field(..., ge=0, description="Significant wave height VHM0 in metres")
    wave_period: float = Field(..., ge=0, description="Peak wave period VTPK in seconds")
    wave_direction_from: float = Field(
        ...,
        ge=0,
        lt=360,
        description="Mean wave direction VMDR, degrees from which waves arrive",
    )
    source: str


class VesselDraftConfig(BaseModel):
    """Vessel draft and under-keel-clearance requirement in metres."""

    draft: float = Field(..., ge=0)
    ukc: float = Field(..., ge=0)


class DepthSafetyResult(BaseModel):
    """Result of comparing available depth with draft plus UKC."""

    depth: float = Field(..., ge=0)
    required_depth: float = Field(..., ge=0)
    safe: bool
    margin: float


class VesselState(BaseModel):
    """Current vessel state exposed to the bridge UI."""

    position: Position
    heading: float = Field(..., ge=0, lt=360)
    speed: float = Field(..., ge=0, description="Speed in knots")


class RoutePoint(BaseModel):
    """One point in a future planner-produced route."""

    position: Position
    timestamp: datetime | None = None


class RouteResult(BaseModel):
    """Planner output contract with optional multi-objective route metadata."""

    plan_id: str | None = None
    route_points: list[RoutePoint] = Field(default_factory=list)
    eta: datetime | None = None
    risk: dict[str, object] | None = None
    status: Literal["mock", "ready", "failed"] = "mock"
    routes: list[dict[str, object]] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
