"""NetCDF reader for GEBCO-style elevation datasets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset, Variable

from core.providers.common import open_netcdf, resolve_lat_lon_names, resolve_variable


class GEBCONetCDFReader:
    """Read elevation and coordinate variables without applying domain policy."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._dataset: Dataset | None = None

    def load(self) -> None:
        if self._dataset is None:
            self._dataset = open_netcdf(self.path, mode="r")

    def close(self) -> None:
        if self._dataset is not None:
            self._dataset.close()
            self._dataset = None

    def read_coordinates(self) -> tuple[np.ndarray, np.ndarray]:
        dataset = self._require_dataset()
        latitude_name, longitude_name = resolve_lat_lon_names(dataset.variables)
        if latitude_name is None or longitude_name is None:
            raise ValueError("GEBCO dataset requires latitude/lat and longitude/lon coordinates.")
        latitude = dataset.variables[latitude_name]
        longitude = dataset.variables[longitude_name]
        if latitude.ndim != 1 or longitude.ndim != 1:
            raise ValueError("GEBCO latitude and longitude coordinates must be one-dimensional.")
        latitude_values = np.asarray(latitude[:], dtype=np.float64)
        longitude_values = np.asarray(longitude[:], dtype=np.float64)
        self._validate_axis(latitude_values, "latitude")
        self._validate_axis(longitude_values, "longitude")
        return latitude_values, longitude_values

    def read_elevation(self) -> np.ma.MaskedArray:
        variable = self._validated_elevation_variable()
        return np.ma.asarray(variable[:], dtype=np.float64)

    def read_elevation_window(
        self, row_start: int, row_stop: int, column_start: int, column_stop: int
    ) -> np.ma.MaskedArray:
        """Read a half-open latitude/longitude window without loading the full grid."""

        variable = self._validated_elevation_variable()
        return np.ma.asarray(
            variable[row_start:row_stop, column_start:column_stop], dtype=np.float64
        )

    def read_dataset_metadata(self) -> dict[str, Any]:
        """Return raw source attributes for translation by the adapter."""

        dataset = self._require_dataset()
        return {name: dataset.getncattr(name) for name in dataset.ncattrs()}

    def _require_dataset(self) -> Dataset:
        if self._dataset is None:
            raise RuntimeError("Call load() before reading the GEBCO dataset.")
        return self._dataset

    def _validated_elevation_variable(self) -> Variable:
        dataset = self._require_dataset()
        variable = self._find_elevation(dataset)
        latitude_name, longitude_name = resolve_lat_lon_names(dataset.variables)
        if latitude_name is None or longitude_name is None:
            raise ValueError("GEBCO dataset requires latitude and longitude coordinates.")
        latitude_dimension = dataset.variables[latitude_name].dimensions[0]
        longitude_dimension = dataset.variables[longitude_name].dimensions[0]
        if variable.dimensions != (latitude_dimension, longitude_dimension):
            raise ValueError("GEBCO elevation dimensions must be ordered latitude, longitude.")
        units = str(getattr(variable, "units", "")).strip().casefold()
        if units not in {"m", "meter", "meters", "metre", "metres"}:
            raise ValueError("GEBCO elevation must use metres.")
        return variable

    @staticmethod
    def _validate_axis(values: np.ndarray, axis_name: str) -> None:
        if values.size < 2:
            raise ValueError(f"GEBCO {axis_name} axis requires at least two coordinates.")
        differences = np.diff(values)
        if not (np.all(differences > 0) or np.all(differences < 0)):
            raise ValueError(f"GEBCO {axis_name} coordinates must be strictly monotonic.")

    @staticmethod
    def _find_elevation(dataset: Dataset) -> Variable:
        for variable in dataset.variables.values():
            if getattr(variable, "standard_name", None) == "height_above_mean_sea_level":
                return variable
        variable = resolve_variable(dataset.variables, ("elevation",))
        if variable is None:
            raise ValueError("GEBCO dataset has no elevation variable.")
        return variable
