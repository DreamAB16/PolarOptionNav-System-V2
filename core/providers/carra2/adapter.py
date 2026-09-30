"""Translate CARRA2 forecast components into a generic Environment WindField."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.contracts import (
    EvidenceRecord,
    EvidenceStatus,
    LocalENUPosition,
    QualityMetadata,
    TimeMetadata,
)
from core.contracts.quality import AvailabilityStatus
from core.environment import FieldMetadata, GridSpec, WindField, WindFieldData
from core.providers import BaseProviderAdapter
from core.providers.common import build_field_metadata, local_enu_to_wgs84

from .reader import CARRA2NetCDFReader


class CARRA2WindProviderAdapter(BaseProviderAdapter):
    """Build one time slice of CARRA2 East/North wind on an ENU GridSpec."""

    def __init__(self, path: str | Path, grid: GridSpec, time_index: int = 0) -> None:
        self.reader = CARRA2NetCDFReader(path)
        self.grid = grid
        self.time_index = time_index
        self._metadata: FieldMetadata | None = None
        self._field: WindField | None = None
        self._component_grids: tuple[list[list[float | None]], list[list[float | None]]] | None = None

    def load(self) -> None:
        self.reader.load()

    def read_metadata(self) -> FieldMetadata:
        if self._metadata is not None:
            return self._metadata
        valid_times = self.reader.read_valid_times()
        if self.time_index < 0 or self.time_index >= len(valid_times):
            raise IndexError("CARRA2 time index is outside the forecast time axis.")
        valid_time = valid_times[self.time_index]
        if valid_time is None:
            raise ValueError("CARRA2 valid time could not be decoded.")
        issue_time = self.reader.read_issue_time()
        ingest_time = self.reader.ingest_time
        time = TimeMetadata(
            issue_time=issue_time,
            valid_time=valid_time,
            ingest_time=ingest_time,
        )
        east, north = self._read_component_grids()
        available = any(
            value is not None for row in east for value in row
        ) and any(value is not None for row in north for value in row)
        source_attributes = self.reader.read_source_metadata()
        quality = QualityMetadata(
            availability=AvailabilityStatus.AVAILABLE if available else AvailabilityStatus.MISSING,
            source="CARRA2",
        )
        evidence = EvidenceRecord(source="CARRA2", status=EvidenceStatus.UNKNOWN)
        self._metadata = build_field_metadata(
            source_id="CARRA2",
            native_resolution_m=self._native_resolution(source_attributes),
            representation_resolution_m=self.grid.resolution_m,
            time=time,
            quality=quality,
            evidence=evidence,
        )
        return self._metadata

    def convert_to_environment_field(self) -> WindField:
        if self._field is not None:
            return self._field
        east, north = self._read_component_grids()
        data = None if not any(value is not None for row in east for value in row) else WindFieldData(
            wind_east_mps=east,
            wind_north_mps=north,
        )
        self._field = WindField(data=data, grid=self.grid, metadata=self.read_metadata())
        return self._field

    def _read_component_grids(self) -> tuple[list[list[float | None]], list[list[float | None]]]:
        if self._component_grids is not None:
            return self._component_grids
        latitude, longitude = self.reader.read_coordinates()
        u10, v10 = self.reader.read_wind_components(self.time_index)
        if u10.shape != v10.shape:
            raise ValueError("CARRA2 u10 and v10 spatial grids must match.")
        east_grid: list[list[float | None]] = []
        north_grid: list[list[float | None]] = []
        for row in range(self.grid.height_cells):
            y_north = self.grid.y_max_m - (row + 0.5) * self.grid.resolution_m
            east_row: list[float | None] = []
            north_row: list[float | None] = []
            for column in range(self.grid.width_cells):
                x_east = self.grid.x_min_m + (column + 0.5) * self.grid.resolution_m
                position = LocalENUPosition(
                    frame=self.grid.frame,
                    x_east_m=x_east,
                    y_north_m=y_north,
                )
                geographic = local_enu_to_wgs84(position)
                latitude_index = self._nearest_index(latitude, geographic.latitude_deg)
                longitude_index = self._nearest_index(longitude, geographic.longitude_deg)
                if latitude_index is None or longitude_index is None:
                    east_row.append(None)
                    north_row.append(None)
                    continue
                u_value = self._valid_value(u10[latitude_index, longitude_index])
                v_value = self._valid_value(v10[latitude_index, longitude_index])
                east_row.append(u_value)
                north_row.append(v_value)
            east_grid.append(east_row)
            north_grid.append(north_row)
        self._component_grids = east_grid, north_grid
        return self._component_grids

    @staticmethod
    def _valid_value(value: object) -> float | None:
        if np.ma.is_masked(value):
            return None
        numeric = float(value)
        return numeric if np.isfinite(numeric) else None

    @staticmethod
    def _nearest_index(axis: np.ndarray, value: float) -> int | None:
        if axis.size == 0 or value < min(axis[0], axis[-1]) or value > max(axis[0], axis[-1]):
            return None
        ascending = axis if axis[0] < axis[-1] else axis[::-1]
        index = int(np.searchsorted(ascending, value))
        index = min(max(index, 0), ascending.size - 1)
        if index and abs(ascending[index - 1] - value) <= abs(ascending[index] - value):
            index -= 1
        return index if axis[0] < axis[-1] else axis.size - 1 - index

    @staticmethod
    def _native_resolution(attributes: dict[str, object]) -> float | None:
        for key in ("native_resolution_m", "spatial_resolution_m", "resolution_m"):
            value = attributes.get(key)
            if value is not None:
                try:
                    result = float(value)
                except (TypeError, ValueError):
                    continue
                if np.isfinite(result) and result > 0:
                    return result
        return None


__all__ = ["CARRA2WindProviderAdapter"]
