"""Translate TOPAZ5 surface current data into the generic CurrentField."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.contracts import EvidenceRecord, EvidenceStatus, LocalENUPosition, QualityMetadata, TimeMetadata
from core.contracts.quality import AvailabilityStatus
from core.environment import CurrentField, CurrentFieldData, FieldMetadata, GridSpec
from core.providers import BaseProviderAdapter
from core.providers.common import build_field_metadata, local_enu_to_wgs84

from .reader import TOPAZ5NetCDFReader


class TOPAZ5CurrentProviderAdapter(BaseProviderAdapter):
    """Build one TOPAZ5 surface-current time slice on a Local ENU grid."""

    def __init__(self, path: str | Path, grid: GridSpec, time_index: int = 0) -> None:
        self.reader = TOPAZ5NetCDFReader(path)
        self.grid = grid
        self.time_index = time_index
        self._metadata: FieldMetadata | None = None
        self._field: CurrentField | None = None
        self._components: tuple[list[list[float | None]], list[list[float | None]]] | None = None

    def load(self) -> None:
        self.reader.load()

    def read_metadata(self) -> FieldMetadata:
        if self._metadata is not None:
            return self._metadata
        times = self.reader.read_valid_times()
        if self.time_index < 0 or self.time_index >= len(times) or times[self.time_index] is None:
            raise ValueError("TOPAZ5 valid time is unavailable for the selected index.")
        east, north = self._read_components()
        available = any(value is not None for row in east for value in row) and any(value is not None for row in north for value in row)
        source = "TOPAZ5"
        attributes = self.reader.read_source_metadata()
        native = self._native_resolution(attributes)
        self._metadata = build_field_metadata(
            source_id=source,
            native_resolution_m=native,
            representation_resolution_m=self.grid.resolution_m,
            time=TimeMetadata(issue_time=self.reader.read_issue_time(), valid_time=times[self.time_index], ingest_time=self.reader.ingest_time),
            quality=QualityMetadata(availability=AvailabilityStatus.AVAILABLE if available else AvailabilityStatus.MISSING, source=source),
            evidence=EvidenceRecord(source=source, status=EvidenceStatus.UNKNOWN),
        )
        return self._metadata

    def convert_to_environment_field(self) -> CurrentField:
        if self._field is not None:
            return self._field
        east, north = self._read_components()
        data = None if not any(value is not None for row in east for value in row) else CurrentFieldData(current_east_mps=east, current_north_mps=north)
        self._field = CurrentField(data=data, grid=self.grid, metadata=self.read_metadata())
        return self._field

    def _read_components(self) -> tuple[list[list[float | None]], list[list[float | None]]]:
        if self._components is not None:
            return self._components
        latitude, longitude = self.reader.read_coordinates()
        u_data, v_data, units = self.reader.read_current_components(self.time_index)
        factor = 0.01 if units == "cm/s" else 1.0
        east: list[list[float | None]] = []
        north: list[list[float | None]] = []
        for row in range(self.grid.height_cells):
            y = self.grid.y_max_m - (row + 0.5) * self.grid.resolution_m
            east_row: list[float | None] = []
            north_row: list[float | None] = []
            for column in range(self.grid.width_cells):
                x = self.grid.x_min_m + (column + 0.5) * self.grid.resolution_m
                geographic = local_enu_to_wgs84(LocalENUPosition(frame=self.grid.frame, x_east_m=x, y_north_m=y))
                latitude_index = self._nearest_index(latitude, geographic.latitude_deg)
                longitude_index = self._nearest_index(longitude, geographic.longitude_deg)
                if latitude_index is None or longitude_index is None:
                    east_row.append(None)
                    north_row.append(None)
                else:
                    east_row.append(self._valid(u_data[latitude_index, longitude_index], factor))
                    north_row.append(self._valid(v_data[latitude_index, longitude_index], factor))
            east.append(east_row)
            north.append(north_row)
        self._components = east, north
        return self._components

    @staticmethod
    def _valid(value: object, factor: float) -> float | None:
        if np.ma.is_masked(value) or not np.isfinite(float(value)):
            return None
        return float(value) * factor

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


__all__ = ["TOPAZ5CurrentProviderAdapter"]
