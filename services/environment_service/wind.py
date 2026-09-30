"""CARRA2 and legacy ERA5 10 m wind providers."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, timezone
from math import atan2, cos, degrees, hypot, radians, sin
from pathlib import Path
from threading import RLock

import numpy as np
from netCDF4 import num2date

from core.models import Position, WindState
from core.netcdf import open_netcdf
from .providers import EnvironmentProvider


class CARRA2WindProvider(EnvironmentProvider):
    """Query paired CARRA2 speed/direction files on their 2-D Arctic grid."""

    layer_id = "wind"
    layer_name = "Wind"
    source_name = "CARRA2 Pan-Arctic"
    _coarse_stride = 24
    _maximum_distance_degrees = 0.2

    def __init__(self, data_directory: Path) -> None:
        self._lock = RLock()
        speed_paths = {
            self._file_month(path): path
            for path in data_directory.glob("10m_wind_speed_*.nc")
        } if data_directory.is_dir() else {}
        direction_paths = {
            self._file_month(path): path
            for path in data_directory.glob("10m_wind_direction_*.nc")
        } if data_directory.is_dir() else {}
        self._paths_by_month = {
            month: (speed_paths[month], direction_paths[month])
            for month in sorted(speed_paths.keys() & direction_paths.keys())
        }
        if not self._paths_by_month:
            raise FileNotFoundError("No paired CARRA2 si10/wdir10 files found.")

        self._speed_dataset = None
        self._direction_dataset = None
        self._active_month: date | None = None
        self._times: list[datetime] = []
        self._latitude = np.array([], dtype=np.float32)
        self._longitude = np.array([], dtype=np.float32)
        self._coarse_latitude = np.array([], dtype=np.float32)
        self._coarse_longitude = np.array([], dtype=np.float32)
        self._slice_index: int | None = None
        self._speed_slice: np.ma.MaskedArray | None = None
        self._direction_slice: np.ma.MaskedArray | None = None
        self._slice_cache: OrderedDict[int, tuple[np.ma.MaskedArray, np.ma.MaskedArray]] = OrderedDict()

    def get_metadata(self) -> dict[str, object]:
        return {
            "provider": self.layer_id,
            "status": "ready",
            "source": self.source_name,
            "files": len(self._paths_by_month) * 2,
            "variables": ["si10", "wdir10"],
            "grid": "CARRA2 curvilinear Pan-Arctic grid, about 2.5 km",
            "time_step": "3 hours",
        }

    def get_available_layers(self) -> list[dict[str, str]]:
        return [{"id": self.layer_id, "name": self.layer_name, "status": "ready"}]

    def query(self, position: Position, timestamp: datetime) -> WindState:
        requested = self._utc(timestamp)
        with self._lock:
            self._select_month(requested)
            time_index = self._nearest_time_index(requested)
            self._load_slice(time_index)
            return self._query_active(position, self._times[time_index])

    def query_many(self, points: list[tuple[str, Position]], timestamp: datetime) -> dict[str, object]:
        if not points:
            raise ValueError("Wind field requires at least one point.")
        if len(points) > 500:
            raise ValueError("A maximum of 500 wind sample points is supported.")
        requested = self._utc(timestamp)
        vectors: list[dict[str, object]] = []
        with self._lock:
            self._select_month(requested)
            time_index = self._nearest_time_index(requested)
            self._load_slice(time_index)
            matched = self._times[time_index]
            for point_id, position in points:
                try:
                    state = self._query_active(position, matched)
                    vectors.append({"id": point_id, "available": True, **state.model_dump(mode="json")})
                except ValueError as error:
                    reason = "out_of_coverage" if "coverage" in str(error) else "no_data"
                    vectors.append({
                        "id": point_id,
                        "available": False,
                        "latitude": position.latitude,
                        "longitude": position.longitude,
                        "reason": reason,
                    })
        return {
            "requested_time": self._iso(requested),
            "matched_time": self._iso(matched),
            "source": self.source_name,
            "units": "m/s",
            "vectors": vectors,
        }

    def close(self) -> None:
        with self._lock:
            if self._speed_dataset is not None:
                self._speed_dataset.close()
            if self._direction_dataset is not None:
                self._direction_dataset.close()
            self._speed_dataset = None
            self._direction_dataset = None
            self._active_month = None
            self._clear_slice(clear_cache=True)

    def _select_month(self, requested: datetime) -> None:
        requested_month = requested.date().replace(day=1)
        month = min(
            self._paths_by_month,
            key=lambda candidate: abs((candidate - requested_month).days),
        )
        if month == self._active_month and self._speed_dataset is not None:
            return
        self.close()
        speed_path, direction_path = self._paths_by_month[month]
        self._speed_dataset = open_netcdf(speed_path)
        try:
            self._direction_dataset = open_netcdf(direction_path)
            self._validate_active_datasets()
        except Exception:
            self.close()
            raise
        self._active_month = month

    def _validate_active_datasets(self) -> None:
        assert self._speed_dataset is not None and self._direction_dataset is not None
        for dataset, variable_name in (
            (self._speed_dataset, "si10"),
            (self._direction_dataset, "wdir10"),
        ):
            required = {"latitude", "longitude", "valid_time", variable_name}
            missing = required.difference(dataset.variables)
            if missing:
                raise ValueError(f"CARRA2 file is missing variables: {', '.join(sorted(missing))}")
        speed_shape = self._speed_dataset.variables["si10"].shape
        direction_shape = self._direction_dataset.variables["wdir10"].shape
        if speed_shape != direction_shape:
            raise ValueError("CARRA2 speed, direction and coordinate grids do not align.")
        if self._latitude.size == 0:
            self._latitude = np.asarray(self._speed_dataset.variables["latitude"][:], dtype=np.float32)
            self._longitude = np.asarray(self._speed_dataset.variables["longitude"][:], dtype=np.float32)
            if self._latitude.ndim != 2 or self._longitude.shape != self._latitude.shape:
                raise ValueError("CARRA2 latitude/longitude must be matching two-dimensional grids.")
            self._coarse_latitude = self._latitude[::self._coarse_stride, ::self._coarse_stride]
            self._coarse_longitude = self._longitude[::self._coarse_stride, ::self._coarse_stride]
        if speed_shape[-2:] != self._latitude.shape:
            raise ValueError("CARRA2 monthly files do not share one coordinate grid.")
        speed_times = self._read_times(self._speed_dataset)
        direction_times = self._read_times(self._direction_dataset)
        if speed_times != direction_times or not speed_times:
            raise ValueError("CARRA2 speed and direction time axes do not align.")
        self._times = speed_times

    def _read_times(self, dataset: object) -> list[datetime]:
        variable = dataset.variables["valid_time"]
        values = num2date(
            variable[:],
            units=variable.units,
            calendar=getattr(variable, "calendar", "standard"),
            only_use_cftime_datetimes=False,
        )
        return [self._utc(value) for value in values]

    def _nearest_time_index(self, requested: datetime) -> int:
        return min(range(len(self._times)), key=lambda index: abs(self._times[index] - requested))

    def _load_slice(self, time_index: int) -> None:
        if self._slice_index == time_index:
            return
        cached = self._slice_cache.pop(time_index, None)
        if cached is not None:
            self._speed_slice, self._direction_slice = cached
            self._slice_cache[time_index] = cached
            self._slice_index = time_index
            return
        assert self._speed_dataset is not None and self._direction_dataset is not None
        self._speed_slice = np.ma.asarray(self._speed_dataset.variables["si10"][time_index, :, :])
        self._direction_slice = np.ma.asarray(self._direction_dataset.variables["wdir10"][time_index, :, :])
        self._slice_cache[time_index] = (self._speed_slice, self._direction_slice)
        while len(self._slice_cache) > 2:
            self._slice_cache.popitem(last=False)
        self._slice_index = time_index

    def _query_active(self, position: Position, matched_time: datetime) -> WindState:
        row, column, distance = self._nearest_grid_point(position.latitude, position.longitude)
        if distance > self._maximum_distance_degrees:
            raise ValueError(
                f"Position {position.latitude},{position.longitude} is outside CARRA2 coverage."
            )
        assert self._speed_slice is not None and self._direction_slice is not None
        speed = self._scalar(self._speed_slice[row, column])
        direction = self._scalar(self._direction_slice[row, column]) % 360.0
        direction_rad = radians(direction)
        # wdir10 is meteorological wind-from direction clockwise from true north.
        u10 = -speed * sin(direction_rad)
        v10 = -speed * cos(direction_rad)
        math_direction = (degrees(atan2(v10, u10)) + 360.0) % 360.0
        return WindState(
            latitude=position.latitude,
            longitude=position.longitude,
            timestamp=matched_time,
            matched_time=matched_time,
            u10=u10,
            v10=v10,
            wind_speed=speed,
            wind_direction_math=math_direction,
            wind_direction_meteorological=direction,
            wind_direction=direction,
            source=self.source_name,
        )

    def _nearest_grid_point(self, latitude: float, longitude: float) -> tuple[int, int, float]:
        coarse_distance = self._distance_squared(
            self._coarse_latitude,
            self._coarse_longitude,
            latitude,
            longitude,
        )
        if not np.isfinite(coarse_distance).any():
            raise ValueError("CARRA2 coordinate grid contains no usable points.")
        coarse_row, coarse_column = np.unravel_index(np.nanargmin(coarse_distance), coarse_distance.shape)
        centre_row = coarse_row * self._coarse_stride
        centre_column = coarse_column * self._coarse_stride
        radius = self._coarse_stride * 2
        row_start = max(0, centre_row - radius)
        row_stop = min(self._latitude.shape[0], centre_row + radius + 1)
        column_start = max(0, centre_column - radius)
        column_stop = min(self._latitude.shape[1], centre_column + radius + 1)
        local_distance = self._distance_squared(
            self._latitude[row_start:row_stop, column_start:column_stop],
            self._longitude[row_start:row_stop, column_start:column_stop],
            latitude,
            longitude,
        )
        local_row, local_column = np.unravel_index(np.nanargmin(local_distance), local_distance.shape)
        return (
            row_start + local_row,
            column_start + local_column,
            float(np.sqrt(local_distance[local_row, local_column])),
        )

    @staticmethod
    def _distance_squared(
        grid_latitude: np.ndarray,
        grid_longitude: np.ndarray,
        latitude: float,
        longitude: float,
    ) -> np.ndarray:
        longitude_delta = (grid_longitude - longitude + 180.0) % 360.0 - 180.0
        return (
            (grid_latitude - latitude) ** 2
            + (longitude_delta * cos(radians(latitude))) ** 2
        )

    @staticmethod
    def _scalar(value: object) -> float:
        if np.ma.is_masked(value):
            raise ValueError("CARRA2 wind sample is missing at the requested location.")
        result = float(value)
        if not np.isfinite(result):
            raise ValueError("CARRA2 wind sample is missing at the requested location.")
        return result

    def _clear_slice(self, *, clear_cache: bool = False) -> None:
        self._slice_index = None
        self._speed_slice = None
        self._direction_slice = None
        if clear_cache:
            self._slice_cache.clear()

    @staticmethod
    def _file_month(path: Path) -> date:
        suffix = path.stem.rsplit("_", 1)[-1]
        try:
            return datetime.strptime(suffix, "%Y%m").date().replace(day=1)
        except ValueError as error:
            raise ValueError(f"CARRA2 file name has no YYYYMM date: {path.name}") from error

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")


class RealWindProvider(EnvironmentProvider):
    """Read ERA5 ``u10``/``v10`` files without loading the full archive."""

    layer_id = "wind"
    layer_name = "Wind"
    source_name = "ERA5 hourly data on single levels"

    def __init__(self, data_directory: Path) -> None:
        self._lock = RLock()
        self._paths = sorted(data_directory.glob("ERA5_wind_*.nc")) if data_directory.is_dir() else []
        if not self._paths:
            raise FileNotFoundError("No ERA5 wind files found in the configured directory.")
        self._dataset = None
        self._active_path: Path | None = None
        self._time_values: list[datetime] = []
        self._latitude = np.array([], dtype=np.float64)
        self._longitude = np.array([], dtype=np.float64)
        self._u_name = "u10"
        self._v_name = "v10"
        self._latitude_name = "latitude"
        self._longitude_name = "longitude"
        self._time_name = "time"
        self._activate(self._paths[0])

    def get_metadata(self) -> dict[str, object]:
        return {"provider": self.layer_id, "status": "ready", "source": self.source_name, "files": len(self._paths), "variables": [self._u_name, self._v_name]}

    def get_available_layers(self) -> list[dict[str, str]]:
        return [{"id": self.layer_id, "name": self.layer_name, "status": "ready"}]

    def query(self, position: Position, timestamp: datetime) -> WindState:
        requested = self._utc(timestamp)
        path = min(self._paths, key=lambda candidate: abs(self._file_date(candidate) - requested.date()))
        with self._lock:
            self._activate(path)
            index = min(range(len(self._time_values)), key=lambda item: abs(self._time_values[item] - requested))
            u10, v10 = self._bilinear(index, position.latitude, position.longitude)
            sampled_time = self._time_values[index]
        speed = hypot(u10, v10)
        math_direction = (degrees(atan2(v10, u10)) + 360.0) % 360.0
        meteorological_direction = (degrees(atan2(-u10, -v10)) + 360.0) % 360.0
        return WindState(
            latitude=position.latitude,
            longitude=position.longitude,
            timestamp=sampled_time,
            u10=u10,
            v10=v10,
            wind_speed=speed,
            wind_direction_math=math_direction,
            wind_direction_meteorological=meteorological_direction,
            source=self.source_name,
        )

    def query_many(self, points: list[tuple[str, Position]], timestamp: datetime) -> dict[str, object]:
        """Sample many locations against one active ERA5 slice and dataset handle."""
        if len(points) > 500:
            raise ValueError("A maximum of 500 wind sample points is supported.")
        results = []
        requested = self._utc(timestamp)
        for point_id, position in points:
            state = self.query(position, requested)
            results.append({"id": point_id, **state.model_dump(mode="json")})
        matched = results[0]["timestamp"] if results else requested.isoformat().replace("+00:00", "Z")
        return {"requested_time": requested.isoformat().replace("+00:00", "Z"), "matched_time": matched, "source": self.source_name, "units": "m/s", "vectors": results}

    def close(self) -> None:
        with self._lock:
            if self._dataset is not None:
                self._dataset.close()
                self._dataset = None

    def _activate(self, path: Path) -> None:
        if path == self._active_path and self._dataset is not None:
            return
        if self._dataset is not None:
            self._dataset.close()
        self._dataset = open_netcdf(path)
        self._active_path = path
        self._u_name = self._find_name(("u10", "10m_u_component_of_wind"))
        self._v_name = self._find_name(("v10", "10m_v_component_of_wind"))
        self._latitude_name = self._find_name(("latitude", "lat"))
        self._longitude_name = self._find_name(("longitude", "lon"))
        self._time_name = self._find_name(("valid_time", "time"))
        self._latitude = np.asarray(self._dataset.variables[self._latitude_name][:], dtype=np.float64)
        self._longitude = np.asarray(self._dataset.variables[self._longitude_name][:], dtype=np.float64)
        self._time_values = self._read_times()
        if self._latitude.ndim != 1 or self._longitude.ndim != 1 or not self._time_values:
            raise ValueError("ERA5 wind file must contain one-dimensional latitude/longitude and time.")

    def _find_name(self, candidates: tuple[str, ...]) -> str:
        for candidate in candidates:
            if candidate in self._dataset.variables:
                return candidate
        raise ValueError(f"ERA5 wind file is missing one of: {', '.join(candidates)}")

    def _read_times(self) -> list[datetime]:
        variable = self._dataset.variables[self._time_name]
        values = num2date(variable[:], units=variable.units, calendar=getattr(variable, "calendar", "standard"), only_use_cftime_datetimes=False)
        return [self._utc(value) for value in values]

    def _bilinear(self, time_index: int, latitude: float, longitude: float) -> tuple[float, float]:
        latitude_min = float(np.nanmin(self._latitude))
        latitude_max = float(np.nanmax(self._latitude))
        if not latitude_min <= latitude <= latitude_max:
            raise ValueError(
                f"Latitude {latitude} is outside ERA5 coverage {latitude_min}..{latitude_max}."
            )
        lat = float(latitude)
        lat_order = self._latitude if self._latitude[0] < self._latitude[-1] else self._latitude[::-1]
        lat_indices = np.arange(len(self._latitude)) if self._latitude[0] < self._latitude[-1] else np.arange(len(self._latitude))[::-1]
        row_position = float(np.interp(lat, lat_order, lat_indices))
        lon_order = self._longitude.astype(np.float64)
        if lon_order[-1] < lon_order[0]:
            lon_order = lon_order[::-1]
            lon_indices = np.arange(len(self._longitude))[::-1]
        else:
            lon_indices = np.arange(len(self._longitude))
        if float(np.nanmin(lon_order)) < 0:
            lon = ((longitude + 180.0) % 360.0) - 180.0
        else:
            lon = longitude % 360.0
        # ERA5 is global. Extend the first column across the date line so
        # interpolation near +/-180 degrees does not clamp to a map edge.
        extended_longitudes = np.append(lon_order, lon_order[0] + 360.0)
        extended_indices = np.append(lon_indices, lon_indices[0] + len(self._longitude))
        if lon < extended_longitudes[0]:
            lon += 360.0
        column_position = float(np.interp(lon, extended_longitudes, extended_indices))
        return self._sample(self._u_name, time_index, row_position, column_position), self._sample(self._v_name, time_index, row_position, column_position)

    def _sample(self, name: str, time_index: int, row: float, column: float) -> float:
        row0 = int(np.clip(np.floor(row), 0, len(self._latitude) - 2))
        row1 = row0 + 1
        column_floor = int(np.floor(column))
        col0 = column_floor % len(self._longitude)
        col1 = (column_floor + 1) % len(self._longitude)
        dr, dc = row - row0, column - column_floor
        values = np.array(
            [
                [self._read_value(name, time_index, row0, col0), self._read_value(name, time_index, row0, col1)],
                [self._read_value(name, time_index, row1, col0), self._read_value(name, time_index, row1, col1)],
            ],
            dtype=np.float64,
        )
        result = ((1 - dr) * (1 - dc) * values[0, 0] + (1 - dr) * dc * values[0, 1] + dr * (1 - dc) * values[1, 0] + dr * dc * values[1, 1])
        if not np.isfinite(result):
            raise ValueError("ERA5 wind sample is missing at the requested location.")
        return float(result)

    def _read_value(self, name: str, time_index: int, row: int, column: int) -> float:
        variable = self._dataset.variables[name]
        indices: list[int] = []
        for dimension in variable.dimensions:
            if dimension == self._time_name:
                indices.append(time_index)
            elif dimension == self._latitude_name:
                indices.append(row)
            elif dimension == self._longitude_name:
                indices.append(column)
            elif len(self._dataset.dimensions[dimension]) == 1:
                indices.append(0)
            else:
                raise ValueError(f"Unsupported ERA5 dimension {dimension!r} in {name!r}.")
        value = variable[tuple(indices)]
        if np.ma.is_masked(value):
            return float("nan")
        return float(value)

    @staticmethod
    def _file_date(path: Path) -> date:
        suffix = path.stem.rsplit("_", 1)[-1]
        for pattern in ("%Y%m%d", "%Y%m"):
            try:
                parsed = datetime.strptime(suffix, pattern).date()
                return parsed if pattern == "%Y%m%d" else parsed.replace(day=15)
            except ValueError:
                continue
        raise ValueError(f"ERA5 file name has no YYYYMM or YYYYMMDD date: {path.name}")

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
