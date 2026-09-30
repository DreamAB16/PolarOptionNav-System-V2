"""Generic environmental field representation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from .enums import EnvironmentVariable
from .grid import GridSpec
from .metadata import FieldMetadata


class EnvironmentField(BaseModel):
    """Source-neutral values over a grid with provenance and quality metadata."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    variable: EnvironmentVariable
    data: object | None
    grid: GridSpec
    metadata: FieldMetadata


class WindFieldData(BaseModel):
    """Eastward/northward wind grids in metres per second; x=East, y=North."""

    model_config = ConfigDict(frozen=True)

    wind_east_mps: list[list[float | None]]
    wind_north_mps: list[list[float | None]]


class WindField(EnvironmentField):
    """Generic wind field; components use ENU East/North SI semantics."""

    variable: Literal[EnvironmentVariable.WIND] = EnvironmentVariable.WIND
    data: WindFieldData | None


class CurrentFieldData(BaseModel):
    """Eastward and northward current grids in metres per second."""

    model_config = ConfigDict(frozen=True)

    current_east_mps: list[list[float | None]]
    current_north_mps: list[list[float | None]]


class CurrentField(EnvironmentField):
    """Generic surface-current field using East/North SI components."""

    variable: Literal[EnvironmentVariable.CURRENT] = EnvironmentVariable.CURRENT
    data: CurrentFieldData | None


class IceFieldData(BaseModel):
    """Surface ice concentration, thickness and East/North drift components."""

    model_config = ConfigDict(frozen=True)

    ice_concentration: list[list[float | None]]
    ice_thickness_m: list[list[float | None]]
    ice_velocity_east_mps: list[list[float | None]]
    ice_velocity_north_mps: list[list[float | None]]


class IceField(EnvironmentField):
    """Generic surface sea-ice field; no risk or feasibility interpretation."""

    variable: Literal[EnvironmentVariable.ICE] = EnvironmentVariable.ICE
    data: IceFieldData | None


class WaveFieldData(BaseModel):
    """Wave height, period and TO direction grids in SI units/radians."""

    model_config = ConfigDict(frozen=True)

    wave_height_m: list[list[float | None]]
    wave_period_s: list[list[float | None]]
    wave_direction_rad: list[list[float | None]]


class WaveField(EnvironmentField):
    """Generic wave field with explicit TO-direction semantics."""

    variable: Literal[EnvironmentVariable.WAVE] = EnvironmentVariable.WAVE
    data: WaveFieldData | None
