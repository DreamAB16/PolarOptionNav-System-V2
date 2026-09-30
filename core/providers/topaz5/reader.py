"""NetCDF reader for TOPAZ5 surface-current components."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset, num2date

from core.providers.common import open_netcdf, resolve_lat_lon_names, resolve_variable


class TOPAZ5NetCDFReader:
    """Read TOPAZ5 coordinates, times and current components only."""

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
            raise ValueError("TOPAZ5 requires latitude/lat and longitude/lon coordinates.")
        latitude = np.asarray(dataset.variables[lat_name][:], dtype=np.float64)
        longitude = np.asarray(dataset.variables[lon_name][:], dtype=np.float64)
        if latitude.ndim != 1 or longitude.ndim != 1:
            raise ValueError("TOPAZ5 latitude and longitude axes must be one-dimensional.")
        self._validate_axis(latitude, "latitude")
        self._validate_axis(longitude, "longitude")
        return latitude, longitude

    def read_valid_times(self) -> tuple[datetime | None, ...]:
        dataset = self._require_dataset()
        variable = resolve_variable(dataset.variables, ("time",))
        if variable is None or not hasattr(variable, "units"):
            raise ValueError("TOPAZ5 dataset requires a CF time variable with units.")
        values = num2date(
            variable[:], units=variable.units,
            calendar=getattr(variable, "calendar", "standard"),
            only_use_cftime_datetimes=False,
        )
        return tuple(self._as_utc(value) for value in np.atleast_1d(values))

    def read_issue_time(self) -> datetime | None:
        dataset = self._require_dataset()
        variable = resolve_variable(
            dataset.variables, ("forecast_reference_time", "forecast_reference_date", "issue_time")
        )
        if variable is not None and hasattr(variable, "units"):
            values = np.atleast_1d(num2date(
                variable[:], units=variable.units,
                calendar=getattr(variable, "calendar", "standard"),
                only_use_cftime_datetimes=False,
            )).reshape(-1)
            return self._as_utc(values[0]) if values.size else None
        for name in ("forecast_reference_time", "forecast_reference_date", "issue_time"):
            if name in dataset.ncattrs():
                return self._parse_datetime(dataset.getncattr(name))
        return None

    def read_current_components(self, time_index: int) -> tuple[np.ma.MaskedArray, np.ma.MaskedArray, str]:
        dataset = self._require_dataset()
        u_variable = resolve_variable(dataset.variables, ("uo", "current_u"))
        v_variable = resolve_variable(dataset.variables, ("vo", "current_v"))
        missing = [name for name, value in (("uo/current_u", u_variable), ("vo/current_v", v_variable)) if value is None]
        if missing:
            raise ValueError(f"TOPAZ5 dataset is missing required variables: {', '.join(missing)}")
        assert u_variable is not None and v_variable is not None
        times = self.read_valid_times()
        if time_index < 0 or time_index >= len(times):
            raise IndexError("TOPAZ5 time index is outside the time axis.")
        latitude, longitude = self.read_coordinates()
        u_data = self._read_surface_slice(u_variable, time_index, latitude.size, longitude.size)
        v_data = self._read_surface_slice(v_variable, time_index, latitude.size, longitude.size)
        if u_data.shape != v_data.shape or u_data.shape != (latitude.size, longitude.size):
            raise ValueError("TOPAZ5 current components must match latitude/longitude dimensions.")
        units = self._normalise_units(getattr(u_variable, "units", None))
        v_units = self._normalise_units(getattr(v_variable, "units", None))
        if units != v_units:
            raise ValueError("TOPAZ5 current component units must match.")
        return u_data, v_data, units

    def read_source_metadata(self) -> dict[str, Any]:
        dataset = self._require_dataset()
        return {name: dataset.getncattr(name) for name in dataset.ncattrs()}

    def _require_dataset(self) -> Dataset:
        if self._dataset is None:
            raise RuntimeError("Call load() before reading the TOPAZ5 dataset.")
        return self._dataset

    @staticmethod
    def _read_surface_slice(variable, time_index: int, lat_size: int, lon_size: int):
        dimensions = variable.dimensions
        selection: list[int | slice] = [slice(None)] * variable.ndim
        time_axis = next((i for i, name in enumerate(dimensions) if name.casefold() == "time"), None)
        if time_axis is None:
            raise ValueError("TOPAZ5 current variables must include a time dimension.")
        selection[time_axis] = time_index
        depth_axis = next((i for i, name in enumerate(dimensions) if name.casefold() in {"depth", "lev", "level"}), None)
        if depth_axis is not None:
            if variable.shape[depth_axis] < 1:
                raise ValueError("TOPAZ5 depth dimension is empty.")
            selection[depth_axis] = 0
        data = np.ma.asarray(variable[tuple(selection)], dtype=np.float64)
        if data.shape != (lat_size, lon_size):
            if data.ndim == 2 and data.shape == (lon_size, lat_size):
                data = data.T
            else:
                raise ValueError("TOPAZ5 current dimensions must resolve to latitude/longitude.")
        return data

    @staticmethod
    def _normalise_units(units: object) -> str:
        value = str(units or "m/s").strip().casefold().replace(" ", "")
        if value in {"m/s", "ms-1", "m.s-1", "mps"}:
            return "m/s"
        if value in {"cm/s", "cms-1", "cm.s-1", "cmps"}:
            return "cm/s"
        raise ValueError(f"Unsupported TOPAZ5 current units: {units!r}")

    @staticmethod
    def _validate_axis(values: np.ndarray, name: str) -> None:
        if values.size < 2 or not (np.all(np.diff(values) > 0) or np.all(np.diff(values) < 0)):
            raise ValueError(f"TOPAZ5 {name} coordinates must be strictly monotonic.")

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
        return (result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc))

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
