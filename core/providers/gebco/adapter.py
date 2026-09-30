"""Translate GEBCO elevation samples into an Environment Contract field."""

from __future__ import annotations

from math import cos, pi, sqrt
from pathlib import Path
from typing import Literal

import numpy as np

from core.contracts import (
    EvidenceRecord,
    EvidenceStatus,
    LocalENUPosition,
    QualityMetadata,
    TimeMetadata,
)
from core.contracts.quality import AvailabilityStatus
from core.environment import EnvironmentField, EnvironmentVariable, FieldMetadata, GridSpec
from core.providers import BaseProviderAdapter
from core.providers.common import build_field_metadata, local_enu_to_wgs84

from .reader import GEBCONetCDFReader


class BathymetryField(EnvironmentField):
    """Generic environment field with explicit positive-down depth semantics."""

    variable: Literal[EnvironmentVariable.BATHYMETRY] = EnvironmentVariable.BATHYMETRY

    @property
    def depth_m(self) -> object | None:
        return self.data


class GEBCOProviderAdapter(BaseProviderAdapter):
    """Convert GEBCO elevation data to a depth field on a supplied ENU grid.

    The grid describes the representation of the supplied value array. This
    adapter does not resample a native geographic raster onto that grid.
    """

    def __init__(self, path: str | Path, grid: GridSpec) -> None:
        self.reader = GEBCONetCDFReader(path)
        self.grid = grid
        self._metadata: FieldMetadata | None = None
        self._field: BathymetryField | None = None
        self._depth_grid: list[list[float | None]] | None = None

    def load(self) -> None:
        self.reader.load()

    def read_metadata(self) -> FieldMetadata:
        if self._metadata is not None:
            return self._metadata

        source_attributes = self.reader.read_dataset_metadata()
        source_id = self._source_id(source_attributes)
        latitude, longitude = self.reader.read_coordinates()
        native_resolution = self._native_resolution(latitude, longitude)
        depth_grid = self._read_depth_grid(latitude, longitude)
        self._depth_grid = depth_grid
        availability = (
            AvailabilityStatus.AVAILABLE
            if any(value is not None for row in depth_grid for value in row)
            else AvailabilityStatus.MISSING
        )
        quality = QualityMetadata(availability=availability, source=source_id)
        evidence = EvidenceRecord(
            source=source_id,
            status=EvidenceStatus.UNKNOWN,
        )
        self._metadata = build_field_metadata(
            source_id=source_id,
            native_resolution_m=native_resolution,
            representation_resolution_m=self.grid.resolution_m,
            time=TimeMetadata(),
            quality=quality,
            evidence=evidence,
        )
        return self._metadata

    def convert_to_environment_field(self) -> BathymetryField:
        if self._field is not None:
            return self._field

        depth = self._get_depth_grid()
        depth_data = None if all(value is None for row in depth for value in row) else depth
        self._field = BathymetryField(
            data=depth_data,
            grid=self.grid,
            metadata=self.read_metadata(),
        )
        return self._field

    def _get_depth_grid(self) -> list[list[float | None]]:
        if self._depth_grid is None:
            latitude, longitude = self.reader.read_coordinates()
            self._depth_grid = self._read_depth_grid(latitude, longitude)
        return self._depth_grid

    def _read_depth_grid(
        self, latitude_axis: np.ndarray, longitude_axis: np.ndarray
    ) -> list[list[float | None]]:
        rows = self.grid.height_cells
        columns = self.grid.width_cells
        source_indices: list[list[tuple[int, int] | None]] = []
        for row in range(rows):
            y_north = self.grid.y_max_m - (row + 0.5) * self.grid.resolution_m
            row_indices: list[tuple[int, int] | None] = []
            for column in range(columns):
                x_east = self.grid.x_min_m + (column + 0.5) * self.grid.resolution_m
                position = LocalENUPosition(
                    frame=self.grid.frame,
                    x_east_m=x_east,
                    y_north_m=y_north,
                )
                geographic = local_enu_to_wgs84(position)
                latitude_index = self._nearest_axis_index(latitude_axis, geographic.latitude_deg)
                longitude_value = self._longitude_in_axis(
                    geographic.longitude_deg, longitude_axis
                )
                longitude_index = self._nearest_axis_index(longitude_axis, longitude_value)
                if (
                    latitude_index is None
                    or longitude_index is None
                    or geographic.latitude_deg < min(latitude_axis[0], latitude_axis[-1])
                    or geographic.latitude_deg > max(latitude_axis[0], latitude_axis[-1])
                ):
                    row_indices.append(None)
                else:
                    row_indices.append((latitude_index, longitude_index))
            source_indices.append(row_indices)

        valid_indices = [index for row in source_indices for index in row if index is not None]
        if not valid_indices:
            return [[None for _ in range(columns)] for _ in range(rows)]
        row_min = min(index[0] for index in valid_indices)
        row_max = max(index[0] for index in valid_indices)
        column_min = min(index[1] for index in valid_indices)
        column_max = max(index[1] for index in valid_indices)
        elevation = self.reader.read_elevation_window(
            row_min, row_max + 1, column_min, column_max + 1
        )
        values = np.asarray(elevation.filled(np.nan), dtype=np.float64)
        mask = np.ma.getmaskarray(elevation) | ~np.isfinite(values)
        output: list[list[float | None]] = []
        for row_indices in source_indices:
            depth_row: list[float | None] = []
            for index in row_indices:
                if index is None:
                    depth_row.append(None)
                    continue
                source_row, source_column = index[0] - row_min, index[1] - column_min
                depth_row.append(
                    None
                    if mask[source_row, source_column]
                    else max(0.0, -float(values[source_row, source_column]))
                )
            output.append(depth_row)
        return output

    @staticmethod
    def _source_id(attributes: dict[str, object]) -> str | None:
        for name in ("id", "source", "title"):
            value = attributes.get(name)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    @staticmethod
    def _native_resolution(latitude: np.ndarray, longitude: np.ndarray) -> float | None:
        if latitude.size < 2 or longitude.size < 2:
            return None
        latitude_step_m = float(np.median(np.abs(np.diff(latitude)))) * 111_132.0
        mean_latitude = float(np.mean(latitude)) * pi / 180.0
        longitude_step_m = (
            float(np.median(np.abs(np.diff(longitude))))
            * 111_320.0
            * abs(cos(mean_latitude))
        )
        if latitude_step_m <= 0 or longitude_step_m <= 0:
            return None
        return sqrt(latitude_step_m * longitude_step_m)

    @staticmethod
    def _nearest_axis_index(axis: np.ndarray, value: float) -> int | None:
        if axis.size == 0 or value < min(axis[0], axis[-1]) or value > max(axis[0], axis[-1]):
            return None
        ascending = axis if axis[0] < axis[-1] else axis[::-1]
        candidate = int(np.searchsorted(ascending, value))
        candidate = min(max(candidate, 0), ascending.size - 1)
        if candidate > 0 and abs(ascending[candidate - 1] - value) <= abs(ascending[candidate] - value):
            candidate -= 1
        return candidate if axis[0] < axis[-1] else axis.size - 1 - candidate

    @staticmethod
    def _longitude_in_axis(longitude: float, axis: np.ndarray) -> float:
        if axis.size == 0:
            return longitude
        axis_min, axis_max = min(axis[0], axis[-1]), max(axis[0], axis[-1])
        if axis_min >= 0 and axis_max > 180:
            return longitude % 360.0
        if axis_min < 0 and axis_max <= 180:
            return (longitude + 180.0) % 360.0 - 180.0
        return longitude


__all__ = ["BathymetryField", "GEBCOProviderAdapter"]
