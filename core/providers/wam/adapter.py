"""Translate WAM wave variables into the generic WaveField."""

from __future__ import annotations

from math import pi
from pathlib import Path

import numpy as np

from core.contracts import EvidenceRecord, EvidenceStatus, LocalENUPosition, QualityMetadata, TimeMetadata
from core.contracts.quality import AvailabilityStatus
from core.environment import FieldMetadata, GridSpec, WaveField, WaveFieldData
from core.providers import BaseProviderAdapter
from core.providers.common import build_field_metadata, local_enu_to_wgs84

from .reader import WAMNetCDFReader


class WAMWaveProviderAdapter(BaseProviderAdapter):
    """Build one WAM wave time slice on a Local ENU representation grid."""

    def __init__(self, path: str | Path, grid: GridSpec, time_index: int = 0) -> None:
        self.reader = WAMNetCDFReader(path)
        self.grid = grid
        self.time_index = time_index
        self._metadata: FieldMetadata | None = None
        self._field: WaveField | None = None
        self._components: tuple[list[list[float | None]], ...] | None = None

    def load(self) -> None:
        self.reader.load()

    def read_metadata(self) -> FieldMetadata:
        if self._metadata is not None:
            return self._metadata
        times = self.reader.read_valid_times()
        if self.time_index < 0 or self.time_index >= len(times) or times[self.time_index] is None:
            raise ValueError("WAM valid time is unavailable for the selected index.")
        height, period, direction = self._read_components()
        available = any(value is not None for row in height for value in row)
        source = "WAM"
        self._metadata = build_field_metadata(
            source_id=source,
            native_resolution_m=self._native_resolution(self.reader.read_source_metadata()),
            representation_resolution_m=self.grid.resolution_m,
            time=TimeMetadata(issue_time=self.reader.read_issue_time(), valid_time=times[self.time_index], ingest_time=self.reader.ingest_time),
            quality=QualityMetadata(availability=AvailabilityStatus.AVAILABLE if available else AvailabilityStatus.MISSING, source=source),
            evidence=EvidenceRecord(source=source, status=EvidenceStatus.UNKNOWN),
        ).model_copy(update={"direction_convention": "TO"})
        return self._metadata

    def convert_to_environment_field(self) -> WaveField:
        if self._field is not None:
            return self._field
        height, period, direction = self._read_components()
        data = None if not any(value is not None for row in height for value in row) else WaveFieldData(wave_height_m=height, wave_period_s=period, wave_direction_rad=direction)
        self._field = WaveField(data=data, grid=self.grid, metadata=self.read_metadata())
        return self._field

    def _read_components(self) -> tuple[list[list[float | None]], ...]:
        if self._components is not None:
            return self._components
        latitude, longitude = self.reader.read_coordinates()
        values = self.reader.read_wave_variables(self.time_index)
        units = self.reader.read_variable_units()
        grids = {key: [] for key in values}
        for row in range(self.grid.height_cells):
            y = self.grid.y_max_m - (row + 0.5) * self.grid.resolution_m
            for key in grids:
                grids[key].append([])
            for column in range(self.grid.width_cells):
                x = self.grid.x_min_m + (column + 0.5) * self.grid.resolution_m
                geographic = local_enu_to_wgs84(LocalENUPosition(frame=self.grid.frame, x_east_m=x, y_north_m=y))
                latitude_index = self._nearest_index(latitude, geographic.latitude_deg)
                longitude_index = self._nearest_index(longitude, geographic.longitude_deg)
                for key, grid in grids.items():
                    if latitude_index is None or longitude_index is None:
                        grid[row].append(None)
                    else:
                        grid[row].append(self._convert_value(values[key][latitude_index, longitude_index], key, units.get(key, "")))
        self._components = grids["height"], grids["period"], grids["direction"]
        return self._components

    @staticmethod
    def _convert_value(value: object, key: str, units: str) -> float | None:
        if np.ma.is_masked(value) or not np.isfinite(float(value)):
            return None
        numeric = float(value)
        unit = units.casefold().replace(" ", "")
        if key == "height" and unit in {"cm", "centimeter", "centimetre"}:
            numeric *= 0.01
        elif key == "period" and unit in {"ms", "millisecond", "milliseconds"}:
            numeric *= 0.001
        elif key == "direction" and unit not in {"rad", "radian", "radians"}:
            numeric = numeric * pi / 180.0
        return numeric if key != "direction" else numeric % (2.0 * pi)

    @staticmethod
    def _nearest_index(axis: np.ndarray, value: float) -> int | None:
        if axis.size == 0 or value < min(axis[0], axis[-1]) or value > max(axis[0], axis[-1]):
            return None
        ascending = axis if axis[0] < axis[-1] else axis[::-1]
        index = min(max(int(np.searchsorted(ascending, value)), 0), ascending.size - 1)
        if index and abs(ascending[index - 1] - value) <= abs(ascending[index] - value):
            index -= 1
        return index if axis[0] < axis[-1] else axis.size - 1 - index

    @staticmethod
    def _native_resolution(attributes: dict[str, object]) -> float | None:
        for key in ("native_resolution_m", "spatial_resolution_m", "resolution_m"):
            try:
                value = float(attributes[key])
            except (KeyError, TypeError, ValueError):
                continue
            if np.isfinite(value) and value > 0:
                return value
        return None


__all__ = ["WAMWaveProviderAdapter"]
