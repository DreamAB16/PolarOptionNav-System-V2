"""Translate neXtSIM-F surface variables into the generic IceField."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.contracts import EvidenceRecord, EvidenceStatus, LocalENUPosition, QualityMetadata, TimeMetadata
from core.contracts.quality import AvailabilityStatus
from core.environment import FieldMetadata, GridSpec, IceField, IceFieldData
from core.providers import BaseProviderAdapter
from core.providers.common import build_field_metadata, local_enu_to_wgs84

from .reader import NextSIMNetCDFReader


class NextSIMIceProviderAdapter(BaseProviderAdapter):
    """Build one neXtSIM-F surface ice time slice on a Local ENU grid."""

    def __init__(self, path: str | Path, grid: GridSpec, time_index: int = 0) -> None:
        self.reader = NextSIMNetCDFReader(path)
        self.grid = grid
        self.time_index = time_index
        self._metadata: FieldMetadata | None = None
        self._field: IceField | None = None
        self._components: tuple[list[list[float | None]], ...] | None = None

    def load(self) -> None:
        self.reader.load()

    def read_metadata(self) -> FieldMetadata:
        if self._metadata is not None:
            return self._metadata
        times = self.reader.read_valid_times()
        if self.time_index < 0 or self.time_index >= len(times) or times[self.time_index] is None:
            raise ValueError("neXtSIM-F valid time is unavailable for the selected index.")
        concentration, thickness, velocity_u, velocity_v = self._read_components()
        available = any(value is not None for row in concentration for value in row)
        source = "neXtSIM-F"
        self._metadata = build_field_metadata(
            source_id=source,
            native_resolution_m=self._native_resolution(self.reader.read_source_metadata()),
            representation_resolution_m=self.grid.resolution_m,
            time=TimeMetadata(issue_time=self.reader.read_issue_time(), valid_time=times[self.time_index], ingest_time=self.reader.ingest_time),
            quality=QualityMetadata(availability=AvailabilityStatus.AVAILABLE if available else AvailabilityStatus.MISSING, source=source),
            evidence=EvidenceRecord(source=source, status=EvidenceStatus.UNKNOWN),
        )
        return self._metadata

    def convert_to_environment_field(self) -> IceField:
        if self._field is not None:
            return self._field
        concentration, thickness, east, north = self._read_components()
        data = None if not any(value is not None for row in concentration for value in row) else IceFieldData(
            ice_concentration=concentration,
            ice_thickness_m=thickness,
            ice_velocity_east_mps=east,
            ice_velocity_north_mps=north,
        )
        self._field = IceField(data=data, grid=self.grid, metadata=self.read_metadata())
        return self._field

    def _read_components(self) -> tuple[list[list[float | None]], ...]:
        if self._components is not None:
            return self._components
        latitude, longitude = self.reader.read_coordinates()
        values = self.reader.read_surface_variables(self.time_index)
        units = self.reader.read_variable_units()
        grids = {key: [] for key in values}
        for row in range(self.grid.height_cells):
            y = self.grid.y_max_m - (row + 0.5) * self.grid.resolution_m
            for key in grids:
                grids[key].append([])
            for column in range(self.grid.width_cells):
                x = self.grid.x_min_m + (column + 0.5) * self.grid.resolution_m
                position = local_enu_to_wgs84(LocalENUPosition(frame=self.grid.frame, x_east_m=x, y_north_m=y))
                latitude_index = self._nearest_index(latitude, position.latitude_deg)
                longitude_index = self._nearest_index(longitude, position.longitude_deg)
                for key, grid in grids.items():
                    if latitude_index is None or longitude_index is None:
                        grid[row].append(None)
                    else:
                        grid[row].append(self._convert_value(values[key][latitude_index, longitude_index], key, units.get(key, self._unit_for(key))))
        self._components = (grids["concentration"], grids["thickness"], grids["velocity_u"], grids["velocity_v"])
        return self._components

    def _unit_for(self, key: str) -> str:
        return "1" if key == "concentration" else ("m" if key == "thickness" else "m/s")

    @staticmethod
    def _convert_value(value: object, key: str, units: str) -> float | None:
        if np.ma.is_masked(value) or not np.isfinite(float(value)):
            return None
        numeric = float(value)
        if key == "concentration":
            return min(1.0, max(0.0, numeric / 100.0 if numeric > 1 else numeric))
        if key == "thickness" and units in {"cm", "cm/s"}:
            return numeric * 0.01
        if key.startswith("velocity") and units in {"cm/s", "cms-1"}:
            return numeric * 0.01
        return numeric

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


__all__ = ["NextSIMIceProviderAdapter"]
