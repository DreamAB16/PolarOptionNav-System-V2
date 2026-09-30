"""Copernicus Marine TOPAZ5 detided surface-current provider."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, timezone
from math import atan2, degrees, hypot, radians, sin, cos
from pathlib import Path
from threading import RLock

import numpy as np
from netCDF4 import num2date
from pyproj import CRS, Geod, Transformer

from core.models import CurrentState, Position
from core.netcdf import open_netcdf
from .providers import EnvironmentProvider


TOPAZ_COORDINATE_UNIT_METRES = 100_000.0
TOPAZ_PROJ4 = "+proj=stere +lat_0=90 +lon_0=-45 +k=1 +R=6378273 +units=m +no_defs"
TOPAZ_CRS = CRS.from_proj4(TOPAZ_PROJ4)
WGS84_CRS = CRS.from_epsg(4326)


class RealCurrentProvider(EnvironmentProvider):
    """Query hourly TOPAZ5 current on its native regular polar grid."""

    layer_id = "current"
    layer_name = "Surface Current"
    source_name = "Copernicus Marine TOPAZ5 Arctic Ocean Physics"

    def __init__(self, data_directory: Path) -> None:
        self._lock = RLock()
        self._paths_by_date = {
            self._file_date(path): path
            for path in sorted(data_directory.glob("Copernicus_current_*.nc"))
        } if data_directory.is_dir() else {}
        if not self._paths_by_date:
            raise FileNotFoundError("No Copernicus TOPAZ5 current files found.")

        self._to_topaz = Transformer.from_crs(WGS84_CRS, TOPAZ_CRS, always_xy=True)
        self._to_wgs84 = Transformer.from_crs(TOPAZ_CRS, WGS84_CRS, always_xy=True)
        self._geod = Geod(ellps="WGS84")
        self._dataset = None
        self._active_path: Path | None = None
        self._x = np.array([], dtype=np.float64)
        self._y = np.array([], dtype=np.float64)
        self._times: list[datetime] = []
        self._slice_index: int | None = None
        self._vxo_slice: np.ma.MaskedArray | None = None
        self._vyo_slice: np.ma.MaskedArray | None = None
        self._slice_cache: OrderedDict[tuple[Path, int], tuple[np.ma.MaskedArray, np.ma.MaskedArray]] = OrderedDict()

    def get_metadata(self) -> dict[str, object]:
        return {
            "provider": self.layer_id,
            "status": "ready",
            "source": self.source_name,
            "files": len(self._paths_by_date),
            "variables": ["vxo", "vyo"],
            "grid": "TOPAZ polar stereographic, 6.25 km",
            "detided": True,
        }

    def get_available_layers(self) -> list[dict[str, str]]:
        return [{"id": self.layer_id, "name": self.layer_name, "status": "ready"}]

    def query(self, position: Position, timestamp: datetime) -> CurrentState:
        requested = self._utc(timestamp)
        with self._lock:
            self._select_date(requested.date())
            time_index = self._nearest_time_index(requested)
            self._load_slice(time_index)
            return self._query_active(position, self._times[time_index])

    def query_many(self, points: list[tuple[str, Position]], timestamp: datetime) -> dict[str, object]:
        """Query up to 500 points while reusing one dataset and one hourly slice."""

        if not points:
            raise ValueError("Current field requires at least one point.")
        if len(points) > 500:
            raise ValueError("A maximum of 500 current sample points is supported.")
        requested = self._utc(timestamp)
        results: list[dict[str, object]] = []
        with self._lock:
            self._select_date(requested.date())
            time_index = self._nearest_time_index(requested)
            self._load_slice(time_index)
            matched = self._times[time_index]
            for point_id, position in points:
                try:
                    state = self._query_active(position, matched)
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
            "units": "m/s",
            "detided": True,
            "currents": results,
        }

    def close(self) -> None:
        with self._lock:
            if self._dataset is not None:
                self._dataset.close()
                self._dataset = None
            self._active_path = None
            self._clear_slice(clear_cache=True)

    def geographic_components(
        self, longitude: float, latitude: float, vxo: float, vyo: float
    ) -> tuple[float, float]:
        """Rotate physical grid-axis components into geographic east/north."""

        x_m, y_m = self._to_topaz.transform(longitude, latitude)
        lon0, lat0 = self._to_wgs84.transform(x_m, y_m)
        lon_x, lat_x = self._to_wgs84.transform(x_m + 1000.0, y_m)
        lon_y, lat_y = self._to_wgs84.transform(x_m, y_m + 1000.0)
        azimuth_x = radians(self._geod.inv(lon0, lat0, lon_x, lat_x)[0])
        azimuth_y = radians(self._geod.inv(lon0, lat0, lon_y, lat_y)[0])
        east = vxo * sin(azimuth_x) + vyo * sin(azimuth_y)
        north = vxo * cos(azimuth_x) + vyo * cos(azimuth_y)
        return float(east), float(north)

    def topaz_to_wgs84(self, x_file: float, y_file: float) -> tuple[float, float]:
        """Expose an auditable native-coordinate conversion for validation."""

        return self._to_wgs84.transform(
            x_file * TOPAZ_COORDINATE_UNIT_METRES,
            y_file * TOPAZ_COORDINATE_UNIT_METRES,
        )

    def wgs84_to_topaz(self, longitude: float, latitude: float) -> tuple[float, float]:
        x_m, y_m = self._to_topaz.transform(longitude, latitude)
        return x_m / TOPAZ_COORDINATE_UNIT_METRES, y_m / TOPAZ_COORDINATE_UNIT_METRES

    def _query_active(self, position: Position, matched_time: datetime) -> CurrentState:
        x_file, y_file = self.wgs84_to_topaz(position.longitude, position.latitude)
        column0, column1, dx = self._bracket(self._x, x_file)
        row0, row1, dy = self._bracket(self._y, y_file)
        assert self._vxo_slice is not None and self._vyo_slice is not None
        vxo = self._bilinear(self._vxo_slice, row0, row1, column0, column1, dy, dx)
        vyo = self._bilinear(self._vyo_slice, row0, row1, column0, column1, dy, dx)
        east, north = self.geographic_components(position.longitude, position.latitude, vxo, vyo)
        speed = hypot(east, north)
        direction = (degrees(atan2(east, north)) + 360.0) % 360.0
        return CurrentState(
            timestamp=matched_time,
            latitude=position.latitude,
            longitude=position.longitude,
            vxo=vxo,
            vyo=vyo,
            current_east=east,
            current_north=north,
            current_speed=speed,
            current_direction_to=direction,
            source=self.source_name,
            detided=True,
        )

    def _select_date(self, requested_date: date) -> None:
        path = self._paths_by_date.get(requested_date)
        if path is None:
            raise ValueError(f"No current data for requested date {requested_date.isoformat()}.")
        if path == self._active_path and self._dataset is not None:
            return
        if self._dataset is not None:
            self._dataset.close()
        self._dataset = open_netcdf(path)
        self._active_path = path
        required = {"time", "x", "y", "vxo", "vyo"}
        missing = required.difference(self._dataset.variables)
        if missing:
            raise ValueError(f"TOPAZ5 current file is missing: {', '.join(sorted(missing))}")
        self._x = np.asarray(self._dataset.variables["x"][:], dtype=np.float64)
        self._y = np.asarray(self._dataset.variables["y"][:], dtype=np.float64)
        time_variable = self._dataset.variables["time"]
        values = num2date(
            time_variable[:],
            units=time_variable.units,
            calendar=getattr(time_variable, "calendar", "standard"),
            only_use_cftime_datetimes=False,
        )
        self._times = [self._utc(value) for value in values]
        if self._x.ndim != 1 or self._y.ndim != 1 or not self._times:
            raise ValueError("TOPAZ5 current coordinates must be one-dimensional x/y/time.")
        self._clear_slice()

    def _nearest_time_index(self, requested: datetime) -> int:
        # Stable min over time-ordered values makes exact half-hour ties choose earlier.
        return min(range(len(self._times)), key=lambda index: (abs(self._times[index] - requested), self._times[index]))

    def _load_slice(self, time_index: int) -> None:
        if self._slice_index == time_index:
            return
        assert self._dataset is not None
        assert self._active_path is not None
        key = (self._active_path, time_index)
        cached = self._slice_cache.pop(key, None)
        if cached is not None:
            self._vxo_slice, self._vyo_slice = cached
            self._slice_cache[key] = cached
            self._slice_index = time_index
            return
        self._vxo_slice = np.ma.masked_invalid(np.ma.asarray(self._dataset.variables["vxo"][time_index, :, :]))
        self._vyo_slice = np.ma.masked_invalid(np.ma.asarray(self._dataset.variables["vyo"][time_index, :, :]))
        self._slice_cache[key] = (self._vxo_slice, self._vyo_slice)
        while len(self._slice_cache) > 3:
            self._slice_cache.popitem(last=False)
        self._slice_index = time_index

    def _clear_slice(self, *, clear_cache: bool = False) -> None:
        self._slice_index = None
        self._vxo_slice = None
        self._vyo_slice = None
        if clear_cache:
            self._slice_cache.clear()

    @staticmethod
    def _bracket(axis: np.ndarray, value: float) -> tuple[int, int, float]:
        minimum, maximum = float(np.min(axis)), float(np.max(axis))
        if value < minimum or value > maximum:
            raise ValueError(f"Point is outside current coverage ({minimum}..{maximum}).")
        ascending = axis[0] < axis[-1]
        ordered = axis if ascending else axis[::-1]
        upper_ordered = int(np.searchsorted(ordered, value, side="right"))
        upper_ordered = min(max(upper_ordered, 1), len(axis) - 1)
        lower_ordered = upper_ordered - 1
        lower = lower_ordered if ascending else len(axis) - 1 - lower_ordered
        upper = upper_ordered if ascending else len(axis) - 1 - upper_ordered
        denominator = float(axis[upper] - axis[lower])
        fraction = 0.0 if denominator == 0 else (value - float(axis[lower])) / denominator
        return lower, upper, float(fraction)

    @staticmethod
    def _bilinear(
        values: np.ma.MaskedArray,
        row0: int,
        row1: int,
        column0: int,
        column1: int,
        dy: float,
        dx: float,
    ) -> float:
        corners = np.ma.asarray(values[[row0, row0, row1, row1], [column0, column1, column0, column1]])
        raw = np.asarray(corners.filled(np.nan), dtype=np.float64)
        if np.any(np.ma.getmaskarray(corners)) or not np.all(np.isfinite(raw)) or np.any(np.abs(raw) > 1e6):
            raise ValueError("No current data at requested location.")
        weights = np.array([(1-dy)*(1-dx), (1-dy)*dx, dy*(1-dx), dy*dx])
        return float(np.dot(raw, weights))

    @staticmethod
    def _file_date(path: Path) -> date:
        try:
            return datetime.strptime(path.stem.rsplit("_", 1)[-1], "%Y%m%d").date()
        except ValueError as error:
            raise ValueError(f"Invalid TOPAZ5 current file name: {path.name}") from error

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")
