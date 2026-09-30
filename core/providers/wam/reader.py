"""NetCDF reader for WAM wave height, period and direction variables."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset, num2date

from core.providers.common import open_netcdf, resolve_lat_lon_names, resolve_variable


class WAMNetCDFReader:
    """Read WAM coordinates, time and wave variables without field logic."""

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
        lat_name, lon_name = resolve_lat_lon_names(dataset.variables)
        if lat_name is None or lon_name is None:
            raise ValueError("WAM requires latitude/lat and longitude/lon coordinates.")
        latitude = np.asarray(dataset.variables[lat_name][:], dtype=np.float64)
        longitude = np.asarray(dataset.variables[lon_name][:], dtype=np.float64)
        if latitude.ndim != 1 or longitude.ndim != 1:
            raise ValueError("WAM latitude and longitude axes must be one-dimensional.")
        self._validate_axis(latitude, "latitude")
        self._validate_axis(longitude, "longitude")
        return latitude, longitude

    def read_valid_times(self) -> tuple[datetime | None, ...]:
        dataset = self._require_dataset()
        variable = resolve_variable(dataset.variables, ("time",))
        if variable is None or not hasattr(variable, "units"):
            raise ValueError("WAM dataset requires a CF time variable with units.")
        values = num2date(variable[:], units=variable.units, calendar=getattr(variable, "calendar", "standard"), only_use_cftime_datetimes=False)
        return tuple(self._as_utc(value) for value in np.atleast_1d(values))

    def read_issue_time(self) -> datetime | None:
        dataset = self._require_dataset()
        variable = resolve_variable(dataset.variables, ("forecast_reference_time", "forecast_reference_date", "issue_time"))
        if variable is not None and hasattr(variable, "units"):
            values = np.atleast_1d(num2date(variable[:], units=variable.units, calendar=getattr(variable, "calendar", "standard"), only_use_cftime_datetimes=False)).reshape(-1)
            return self._as_utc(values[0]) if values.size else None
        for name in ("forecast_reference_time", "forecast_reference_date", "issue_time"):
            if name in dataset.ncattrs():
                return self._parse_datetime(dataset.getncattr(name))
        return None

    def read_wave_variables(self, time_index: int) -> dict[str, np.ma.MaskedArray]:
        dataset = self._require_dataset()
        aliases = {
            "height": ("Hs", "hs", "VHM0", "swh", "significant_wave_height"),
            "period": ("Tp", "tp", "VTPK", "peak_wave_period"),
            "direction": ("direction", "wave_direction", "VMDR", "mwd", "mean_wave_direction"),
        }
        variables = {key: resolve_variable(dataset.variables, names) for key, names in aliases.items()}
        missing = [key for key, variable in variables.items() if variable is None]
        if missing:
            raise ValueError(f"WAM dataset is missing required variables: {', '.join(missing)}")
        times = self.read_valid_times()
        if time_index < 0 or time_index >= len(times):
            raise IndexError("WAM time index is outside the time axis.")
        latitude, longitude = self.read_coordinates()
        result: dict[str, np.ma.MaskedArray] = {}
        for key, variable in variables.items():
            assert variable is not None
            result[key] = self._read_surface_slice(variable, time_index, latitude.size, longitude.size)
        return result

    def read_variable_units(self) -> dict[str, str]:
        dataset = self._require_dataset()
        aliases = {"height": ("Hs", "hs", "VHM0", "swh", "significant_wave_height"), "period": ("Tp", "tp", "VTPK", "peak_wave_period"), "direction": ("direction", "wave_direction", "VMDR", "mwd", "mean_wave_direction")}
        result: dict[str, str] = {}
        for key, names in aliases.items():
            variable = resolve_variable(dataset.variables, names)
            if variable is not None:
                result[key] = str(getattr(variable, "units", ""))
        return result

    def read_source_metadata(self) -> dict[str, Any]:
        dataset = self._require_dataset()
        return {name: dataset.getncattr(name) for name in dataset.ncattrs()}

    def _require_dataset(self) -> Dataset:
        if self._dataset is None:
            raise RuntimeError("Call load() before reading the WAM dataset.")
        return self._dataset

    @staticmethod
    def _read_surface_slice(variable, time_index: int, lat_size: int, lon_size: int) -> np.ma.MaskedArray:
        selection: list[int | slice] = [slice(None)] * variable.ndim
        time_axis = next((i for i, name in enumerate(variable.dimensions) if name.casefold() == "time"), None)
        if time_axis is None:
            raise ValueError("WAM variables must include a time dimension.")
        selection[time_axis] = time_index
        data = np.ma.asarray(variable[tuple(selection)], dtype=np.float64)
        if data.shape == (lat_size, lon_size):
            return data
        if data.shape == (lon_size, lat_size):
            return data.T
        raise ValueError("WAM variable dimensions must resolve to latitude/longitude.")

    @staticmethod
    def _validate_axis(values: np.ndarray, name: str) -> None:
        if values.size < 2 or not (np.all(np.diff(values) > 0) or np.all(np.diff(values) < 0)):
            raise ValueError(f"WAM {name} coordinates must be strictly monotonic.")

    @staticmethod
    def _as_utc(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            result = value
        elif all(hasattr(value, key) for key in ("year", "month", "day")):
            result = datetime(value.year, value.month, value.day, getattr(value, "hour", 0), getattr(value, "minute", 0), getattr(value, "second", 0))
        else:
            return None
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)

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
