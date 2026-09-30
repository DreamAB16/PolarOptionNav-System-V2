"""NetCDF reader for CARRA2 10 m forecast wind components."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset, num2date

from core.providers.common import open_netcdf, resolve_lat_lon_names, resolve_variable


class CARRA2NetCDFReader:
    """Read coordinate, time and u10/v10 data without creating environment fields."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._dataset: Dataset | None = None
        self.ingest_time: datetime | None = None

    def load(self) -> None:
        if self._dataset is None:
            self._dataset = open_netcdf(self.path, mode="r")
            self.ingest_time = datetime.now(timezone.utc)

    def close(self) -> None:
        if self._dataset is not None:
            self._dataset.close()
            self._dataset = None
            self.ingest_time = None

    def read_coordinates(self) -> tuple[np.ndarray, np.ndarray]:
        dataset = self._require_dataset()
        latitude_name, longitude_name = resolve_lat_lon_names(dataset.variables)
        if latitude_name is None or longitude_name is None:
            raise ValueError("CARRA2 requires latitude/lat and longitude/lon coordinates.")
        latitude = np.asarray(dataset.variables[latitude_name][:], dtype=np.float64)
        longitude = np.asarray(dataset.variables[longitude_name][:], dtype=np.float64)
        if latitude.ndim != 1 or longitude.ndim != 1:
            raise ValueError("CARRA2 latitude and longitude axes must be one-dimensional.")
        self._validate_axis(latitude, "latitude")
        self._validate_axis(longitude, "longitude")
        return latitude, longitude

    def read_valid_times(self) -> tuple[datetime | None, ...]:
        dataset = self._require_dataset()
        time_variable = resolve_variable(dataset.variables, ("time",))
        if time_variable is None:
            raise ValueError("CARRA2 forecast dataset has no time variable.")
        if not hasattr(time_variable, "units"):
            raise ValueError("CARRA2 time variable has no CF units attribute.")
        values = num2date(
            time_variable[:],
            units=time_variable.units,
            calendar=getattr(time_variable, "calendar", "standard"),
            only_use_cftime_datetimes=False,
        )
        return tuple(self._as_utc(value) for value in np.atleast_1d(values))

    def read_issue_time(self) -> datetime | None:
        dataset = self._require_dataset()
        issue_variable = resolve_variable(
            dataset.variables,
            ("forecast_reference_time", "forecast_reference_date", "issue_time"),
        )
        if issue_variable is not None:
            if not hasattr(issue_variable, "units"):
                return None
            values = num2date(
                issue_variable[:],
                units=issue_variable.units,
                calendar=getattr(issue_variable, "calendar", "standard"),
                only_use_cftime_datetimes=False,
            )
            flattened = np.atleast_1d(values).reshape(-1)
            return self._as_utc(flattened[0]) if flattened.size else None

        for name in ("forecast_reference_time", "issue_time", "forecast_reference_date"):
            value = dataset.getncattr(name) if name in dataset.ncattrs() else None
            if value is not None:
                return self._parse_datetime(value)
        return None

    def read_wind_components(self, time_index: int) -> tuple[np.ma.MaskedArray, np.ma.MaskedArray]:
        dataset = self._require_dataset()
        u_variable = resolve_variable(dataset.variables, ("u10",))
        v_variable = resolve_variable(dataset.variables, ("v10",))
        missing = [name for name, variable in (("u10", u_variable), ("v10", v_variable)) if variable is None]
        if missing:
            raise ValueError(f"CARRA2 forecast dataset is missing required variables: {', '.join(missing)}")
        assert u_variable is not None and v_variable is not None
        if u_variable.shape != v_variable.shape:
            raise ValueError("CARRA2 u10 and v10 arrays must have matching shapes.")
        valid_times = self.read_valid_times()
        if time_index < 0 or time_index >= len(valid_times):
            raise IndexError("CARRA2 time index is outside the forecast time axis.")
        latitude, longitude = self.read_coordinates()
        u_data = self._read_spatial_slice(u_variable, time_index, latitude.size, longitude.size)
        v_data = self._read_spatial_slice(v_variable, time_index, latitude.size, longitude.size)
        if u_data.shape != (latitude.size, longitude.size) or v_data.shape != (latitude.size, longitude.size):
            raise ValueError("CARRA2 u10/v10 spatial dimensions must match latitude/longitude axes.")
        return u_data, v_data

    def read_source_metadata(self) -> dict[str, Any]:
        dataset = self._require_dataset()
        return {name: dataset.getncattr(name) for name in dataset.ncattrs()}

    def _require_dataset(self) -> Dataset:
        if self._dataset is None:
            raise RuntimeError("Call load() before reading the CARRA2 dataset.")
        return self._dataset

    @staticmethod
    def _read_spatial_slice(variable, time_index: int, latitude_size: int, longitude_size: int):
        dimensions = variable.dimensions
        time_axis = next((index for index, name in enumerate(dimensions) if name.casefold() == "time"), None)
        latitude_axis = next(
            (index for index, name in enumerate(dimensions) if name.casefold() in {"latitude", "lat"}),
            None,
        )
        longitude_axis = next(
            (index for index, name in enumerate(dimensions) if name.casefold() in {"longitude", "lon"}),
            None,
        )
        if time_axis is None or latitude_axis is None or longitude_axis is None:
            if variable.ndim == 3 and variable.shape[-2:] == (latitude_size, longitude_size):
                return np.ma.asarray(variable[time_index, :, :], dtype=np.float64)
            raise ValueError("CARRA2 u10/v10 dimensions must identify time, latitude and longitude.")
        selection: list[int | slice] = [slice(None)] * variable.ndim
        selection[time_axis] = time_index
        data = np.ma.asarray(variable[tuple(selection)], dtype=np.float64)
        remaining_dimensions = [index for index in range(variable.ndim) if index != time_axis]
        lat_position = remaining_dimensions.index(latitude_axis)
        lon_position = remaining_dimensions.index(longitude_axis)
        if (lat_position, lon_position) != (0, 1):
            data = np.moveaxis(data, (lat_position, lon_position), (0, 1))
        return data

    @staticmethod
    def _validate_axis(values: np.ndarray, name: str) -> None:
        if values.size < 2:
            raise ValueError(f"CARRA2 {name} axis requires at least two coordinates.")
        differences = np.diff(values)
        if not (np.all(differences > 0) or np.all(differences < 0)):
            raise ValueError(f"CARRA2 {name} coordinates must be strictly monotonic.")

    @staticmethod
    def _as_utc(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            result = value
        elif all(hasattr(value, name) for name in ("year", "month", "day")):
            result = datetime(
                value.year,
                value.month,
                value.day,
                getattr(value, "hour", 0),
                getattr(value, "minute", 0),
                getattr(value, "second", 0),
                getattr(value, "microsecond", 0),
            )
        else:
            return None
        if result.tzinfo is None:
            return result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)

    @classmethod
    def _parse_datetime(cls, value: Any) -> datetime | None:
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        if isinstance(value, str):
            try:
                return cls._as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
            except ValueError:
                return None
        return cls._as_utc(value)
