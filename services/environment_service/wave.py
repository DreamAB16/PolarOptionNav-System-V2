"""Copernicus Marine WAM Arctic hourly wave provider."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, timezone
from math import atan2, degrees, hypot
from pathlib import Path
from threading import RLock

import numpy as np
from netCDF4 import num2date

from core.models import Position, WaveState
from core.netcdf import open_netcdf
from .providers import EnvironmentProvider


class RealWaveProvider(EnvironmentProvider):
    """Query VHM0/VTPK/VMDR on the delivered regular latitude/longitude grid."""

    layer_id = "wave"
    layer_name = "Wave"
    source_name = "Copernicus Marine Arctic Wave"
    variable_names = ("VHM0", "VTPK", "VMDR")

    def __init__(self, data_directory: Path) -> None:
        self._lock = RLock()
        self._paths_by_date = {
            self._file_date(path): path
            for path in sorted(data_directory.glob("Copernicus_wave_*.nc"))
        } if data_directory.is_dir() else {}
        if not self._paths_by_date:
            raise FileNotFoundError("No Copernicus Arctic wave files found.")
        self._dataset = None
        self._active_path: Path | None = None
        self._latitude = np.array([], dtype=np.float64)
        self._longitude = np.array([], dtype=np.float64)
        self._times: list[datetime] = []
        self._slice_index: int | None = None
        self._slices: dict[str, np.ma.MaskedArray] = {}
        self._slice_cache: OrderedDict[tuple[Path, int], dict[str, np.ma.MaskedArray]] = OrderedDict()

    def get_metadata(self) -> dict[str, object]:
        return {
            "provider": self.layer_id,
            "status": "ready",
            "source": self.source_name,
            "files": len(self._paths_by_date),
            "variables": list(self.variable_names),
            "grid": "regular WGS84 latitude/longitude, 0.03 degree",
        }

    def get_available_layers(self) -> list[dict[str, str]]:
        return [{"id": self.layer_id, "name": self.layer_name, "status": "ready"}]

    def query(
        self,
        latitude: Position | float,
        longitude: datetime | float,
        timestamp: datetime | None = None,
    ) -> WaveState:
        """Accept the unified Position/time contract and scalar lat/lon/time callers."""

        if isinstance(latitude, Position):
            if not isinstance(longitude, datetime) or timestamp is not None:
                raise TypeError("Position queries require query(position, timestamp).")
            position = latitude
            requested = self._utc(longitude)
        else:
            if not isinstance(longitude, (int, float)) or timestamp is None:
                raise TypeError("Scalar queries require query(latitude, longitude, timestamp).")
            position = Position(latitude=float(latitude), longitude=float(longitude))
            requested = self._utc(timestamp)
        with self._lock:
            self._select_date(requested.date())
            time_index = self._nearest_time_index(requested)
            self._load_slice(time_index)
            return self._query_active(position, requested, self._times[time_index])

    def query_many(self, points: list[tuple[str, Position]], timestamp: datetime) -> dict[str, object]:
        """Query a viewport with one dataset and one cached hourly slice."""

        if not points:
            raise ValueError("Wave field requires at least one point.")
        if len(points) > 500:
            raise ValueError("A maximum of 500 wave sample points is supported.")
        requested = self._utc(timestamp)
        results: list[dict[str, object]] = []
        with self._lock:
            self._select_date(requested.date())
            time_index = self._nearest_time_index(requested)
            self._load_slice(time_index)
            matched = self._times[time_index]
            for point_id, position in points:
                try:
                    state = self._query_active(position, requested, matched)
                    results.append({"id": point_id, "available": True, **state.model_dump(mode="json")})
                except ValueError as error:
                    reason = "out_of_coverage" if "coverage" in str(error) else "no_data"
                    results.append({
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
            "waves": results,
        }

    def close(self) -> None:
        with self._lock:
            if self._dataset is not None:
                self._dataset.close()
                self._dataset = None
            self._active_path = None
            self._clear_slice(clear_cache=True)

    def _query_active(self, position: Position, requested: datetime, matched: datetime) -> WaveState:
        row0, row1, dy = self._bracket(self._latitude, position.latitude)
        column0, column1, dx = self._bracket(self._longitude, position.longitude)
        height = self._linear_sample("VHM0", row0, row1, column0, column1, dy, dx)
        period = self._linear_sample("VTPK", row0, row1, column0, column1, dy, dx)
        direction = self._circular_sample("VMDR", row0, row1, column0, column1, dy, dx)
        return WaveState(
            timestamp=matched,
            requested_time=requested,
            matched_time=matched,
            latitude=position.latitude,
            longitude=position.longitude,
            wave_height=height,
            wave_period=period,
            wave_direction_from=direction,
            source=self.source_name,
        )

    def _select_date(self, requested_date: date) -> None:
        path = self._paths_by_date.get(requested_date)
        if path is None:
            raise ValueError(f"No wave data for requested date {requested_date.isoformat()}.")
        if path == self._active_path and self._dataset is not None:
            return
        self._clear_slice()
        if self._dataset is not None:
            self._dataset.close()
        self._dataset = open_netcdf(path)
        self._active_path = path
        missing = {"time", "latitude", "longitude", *self.variable_names}.difference(self._dataset.variables)
        if missing:
            raise ValueError(f"Copernicus wave file is missing: {', '.join(sorted(missing))}")
        self._latitude = np.asarray(self._dataset.variables["latitude"][:], dtype=np.float64)
        self._longitude = np.asarray(self._dataset.variables["longitude"][:], dtype=np.float64)
        time_variable = self._dataset.variables["time"]
        values = num2date(
            time_variable[:],
            units=time_variable.units,
            calendar=getattr(time_variable, "calendar", "standard"),
            only_use_cftime_datetimes=False,
        )
        self._times = [self._utc(value) for value in values]
        if self._latitude.ndim != 1 or self._longitude.ndim != 1 or not self._times:
            raise ValueError("Copernicus wave coordinates must be one-dimensional latitude/longitude/time.")

    def _nearest_time_index(self, requested: datetime) -> int:
        # Stable ordering deliberately resolves an exact half-hour tie to the earlier hour.
        return min(
            range(len(self._times)),
            key=lambda index: (abs(self._times[index] - requested), self._times[index]),
        )

    def _load_slice(self, time_index: int) -> None:
        if self._slice_index == time_index:
            return
        assert self._dataset is not None
        assert self._active_path is not None
        key = (self._active_path, time_index)
        cached = self._slice_cache.pop(key, None)
        if cached is not None:
            self._slices = cached
            self._slice_cache[key] = cached
            self._slice_index = time_index
            return
        self._slices = {
            name: np.ma.masked_invalid(np.ma.asarray(self._dataset.variables[name][time_index, :, :]))
            for name in self.variable_names
        }
        self._slice_cache[key] = self._slices
        while len(self._slice_cache) > 3:
            self._slice_cache.popitem(last=False)
        self._slice_index = time_index

    def _clear_slice(self, *, clear_cache: bool = False) -> None:
        self._slice_index = None
        self._slices = {}
        if clear_cache:
            self._slice_cache.clear()

    def _linear_sample(
        self,
        name: str,
        row0: int,
        row1: int,
        column0: int,
        column1: int,
        dy: float,
        dx: float,
    ) -> float:
        values = self._valid_corners(name, row0, row1, column0, column1)
        return float(np.dot(values, self._weights(dy, dx)))

    def _circular_sample(
        self,
        name: str,
        row0: int,
        row1: int,
        column0: int,
        column1: int,
        dy: float,
        dx: float,
    ) -> float:
        angles = np.deg2rad(self._valid_corners(name, row0, row1, column0, column1))
        weights = self._weights(dy, dx)
        x = float(np.dot(np.cos(angles), weights))
        y = float(np.dot(np.sin(angles), weights))
        if hypot(x, y) < 1e-10:
            raise ValueError("Wave direction is undefined at requested location.")
        return (degrees(atan2(y, x)) + 360.0) % 360.0

    def _valid_corners(
        self,
        name: str,
        row0: int,
        row1: int,
        column0: int,
        column1: int,
    ) -> np.ndarray:
        values = self._slices[name]
        corners = np.ma.asarray(values[[row0, row0, row1, row1], [column0, column1, column0, column1]])
        raw = np.asarray(corners.filled(np.nan), dtype=np.float64)
        if np.any(np.ma.getmaskarray(corners)) or not np.all(np.isfinite(raw)):
            raise ValueError("No wave data at requested location.")
        return raw

    @staticmethod
    def _weights(dy: float, dx: float) -> np.ndarray:
        return np.array([(1-dy)*(1-dx), (1-dy)*dx, dy*(1-dx), dy*dx], dtype=np.float64)

    @staticmethod
    def _bracket(axis: np.ndarray, value: float) -> tuple[int, int, float]:
        minimum, maximum = float(np.min(axis)), float(np.max(axis))
        if value < minimum or value > maximum:
            raise ValueError(f"Point is outside wave coverage ({minimum}..{maximum}).")
        ascending = axis[0] < axis[-1]
        ordered = axis if ascending else axis[::-1]
        upper_ordered = min(max(int(np.searchsorted(ordered, value, side="right")), 1), len(axis) - 1)
        lower_ordered = upper_ordered - 1
        lower = lower_ordered if ascending else len(axis) - 1 - lower_ordered
        upper = upper_ordered if ascending else len(axis) - 1 - upper_ordered
        denominator = float(axis[upper] - axis[lower])
        fraction = 0.0 if denominator == 0 else (value - float(axis[lower])) / denominator
        return lower, upper, float(fraction)

    @staticmethod
    def _file_date(path: Path) -> date:
        try:
            return datetime.strptime(path.stem.rsplit("_", 1)[-1], "%Y%m%d").date()
        except ValueError as error:
            raise ValueError(f"Invalid Copernicus wave file name: {path.name}") from error

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")
