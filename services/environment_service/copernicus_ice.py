"""Copernicus Marine neXtSIM sea-ice point and raster adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
from io import BytesIO
from math import pi
from pathlib import Path
import re
from threading import RLock
from typing import Any, Iterable

import numpy as np
from PIL import Image
from pyproj import CRS, Transformer
import xarray as xr
from xarray.backends import NetCDF4DataStore
from xarray.backends.file_manager import DummyFileManager

from core.models import Position, SeaIceState
from core.netcdf import open_netcdf
from .providers import IceProvider, _ice_query_arguments


SOURCE_NAME = "Copernicus Marine neXtSIM-F"


@dataclass(frozen=True)
class CopernicusIceVariables:
    """Semantic variable names discovered from CF standard_name attributes."""

    concentration: str
    thickness: str | None
    multi_year_fraction: str | None
    young_ice_fraction: str | None
    drift_u: str | None
    drift_v: str | None
    snow_thickness: str | None
    time: str
    latitude: str | None
    longitude: str | None


def _variables_with_standard_name(dataset: xr.Dataset, names: Iterable[str]) -> list[str]:
    accepted = set(names)
    return [name for name, variable in dataset.variables.items() if variable.attrs.get("standard_name") in accepted]


def _coordinate_name(dataset: xr.Dataset, standard_name: str, aliases: tuple[str, ...]) -> str | None:
    matches = _variables_with_standard_name(dataset, (standard_name,))
    if matches:
        return matches[0]
    return next((name for name in aliases if name in dataset.variables), None)


def discover_copernicus_variables(dataset: xr.Dataset) -> CopernicusIceVariables:
    """Build the mapping from actual CF metadata instead of assuming NC names."""

    concentration = _variables_with_standard_name(dataset, ("sea_ice_area_fraction",))
    if not concentration:
        raise ValueError("Copernicus dataset has no CF sea_ice_area_fraction variable.")
    classifications = _variables_with_standard_name(dataset, ("sea_ice_classification",))

    def classification(kind: str) -> str | None:
        return next(
            (name for name in classifications if kind in str(dataset[name].attrs.get("long_name", "")).lower()),
            None,
        )

    time_name = _coordinate_name(dataset, "time", ("time", "valid_time", "forecast_time"))
    if time_name is None:
        raise ValueError("Copernicus dataset has no decodable time coordinate.")
    return CopernicusIceVariables(
        concentration=concentration[0],
        thickness=next(iter(_variables_with_standard_name(dataset, ("sea_ice_thickness",))), None),
        multi_year_fraction=classification("multi"),
        young_ice_fraction=classification("young"),
        drift_u=next(
            iter(_variables_with_standard_name(dataset, ("eastward_sea_ice_velocity", "sea_ice_x_velocity"))),
            None,
        ),
        drift_v=next(
            iter(_variables_with_standard_name(dataset, ("northward_sea_ice_velocity", "sea_ice_y_velocity"))),
            None,
        ),
        snow_thickness=next(iter(_variables_with_standard_name(dataset, ("surface_snow_thickness",))), None),
        time=time_name,
        latitude=_coordinate_name(dataset, "latitude", ("latitude", "lat", "nav_lat")),
        longitude=_coordinate_name(dataset, "longitude", ("longitude", "lon", "nav_lon")),
    )


class CopernicusIceDatasetIndex:
    """Resolve arctic_ice_YYYYMMDD.nc scenes to the nearest available day."""

    _pattern = re.compile(r"arctic_ice_(\d{8})\.nc$", re.IGNORECASE)

    def __init__(self, path: Path) -> None:
        root = path.resolve()
        candidates = [root] if root.is_file() else sorted(root.glob("arctic_ice_*.nc")) if root.is_dir() else []
        self._files: dict[str, Path] = {}
        for candidate in candidates:
            match = self._pattern.fullmatch(candidate.name)
            if match:
                datetime.strptime(match.group(1), "%Y%m%d")
                self._files[match.group(1)] = candidate
        if not self._files:
            raise FileNotFoundError("No Copernicus arctic_ice_YYYYMMDD.nc files were found.")

    @property
    def available_dates(self) -> list[str]:
        return sorted(self._files)

    @property
    def default_date(self) -> str:
        return self.available_dates[0]

    def path_for(self, key: str) -> Path:
        return self._files[key]

    def resolve(self, requested: str | date | datetime | None) -> str:
        if requested is None:
            return self.default_date
        if isinstance(requested, datetime):
            target = requested.date()
        elif isinstance(requested, date):
            target = requested
        else:
            try:
                target = datetime.strptime(requested, "%Y%m%d").date()
            except ValueError:
                target = datetime.fromisoformat(requested.replace("Z", "+00:00")).date()
        exact = target.strftime("%Y%m%d")
        if exact in self._files:
            return exact
        return min(
            self._files,
            key=lambda key: (abs((datetime.strptime(key, "%Y%m%d").date() - target).days), key),
        )


class CopernicusIceProvider(IceProvider):
    """Query multi-variable Copernicus sea ice at a WGS84 point and UTC time."""

    source_name = SOURCE_NAME

    def __init__(self, dataset_path: Path) -> None:
        self._lock = RLock()
        self._index = CopernicusIceDatasetIndex(dataset_path)
        self._active_date: str | None = None
        self._activate(self._index.default_date)

    def get_metadata(self) -> dict[str, object]:
        return {
            "provider": self.layer_id,
            "status": "ready",
            "source": self.source_name,
            "product": "ARCTIC_ANALYSISFORECAST_PHY_ICE_002_011",
            "dataset": "cmems_mod_arc_phy_anfc_nextsim_hm",
            "grid": self._grid_kind,
            "available_dates": self._index.available_dates,
            "active_date": self._active_date,
            "variables": self._mapping.__dict__,
        }

    def get_available_layers(self) -> list[dict[str, str]]:
        return [{"id": self.layer_id, "name": self.layer_name, "status": "ready"}]

    def query(
        self,
        position: Position | float,
        timestamp: datetime | float | None = None,
        legacy_timestamp: datetime | None = None,
    ) -> SeaIceState:
        latitude, longitude, requested_time = _ice_query_arguments(position, timestamp, legacy_timestamp)
        with self._lock:
            self._activate(self._index.resolve(requested_time))
            time_index = self._nearest_time_index(requested_time)
            spatial_indices = self._nearest_spatial_indices(latitude, longitude)
            concentration = self._read_fraction(self._mapping.concentration, time_index, spatial_indices)
            if concentration is None:
                raise LookupError("Sea-ice concentration is unavailable at this location.")
            thickness = self._read_nonnegative(self._mapping.thickness, time_index, spatial_indices)
            snow = self._read_nonnegative(self._mapping.snow_thickness, time_index, spatial_indices)
            drift_u = self._read_value(self._mapping.drift_u, time_index, spatial_indices)
            drift_v = self._read_value(self._mapping.drift_v, time_index, spatial_indices)
            young = self._read_fraction(self._mapping.young_ice_fraction, time_index, spatial_indices)
            multi = self._read_fraction(self._mapping.multi_year_fraction, time_index, spatial_indices)
            return SeaIceState(
                latitude=latitude,
                longitude=longitude,
                timestamp=self._time_values[time_index],
                concentration=concentration,
                thickness=thickness,
                ice_type=self._dominant_ice_type(concentration, young, multi),
                drift_u=drift_u,
                drift_v=drift_v,
                snow_thickness=snow,
                source=self.source_name,
            )

    def close(self) -> None:
        with self._lock:
            if hasattr(self, "_dataset"):
                self._dataset.close()
            self._active_date = None

    def _activate(self, dataset_date: str) -> None:
        if dataset_date == self._active_date:
            return
        if self._active_date is not None:
            self._dataset.close()
        netcdf_dataset = open_netcdf(self._index.path_for(dataset_date), mode="r")
        store = NetCDF4DataStore(DummyFileManager(netcdf_dataset))
        self._dataset = xr.open_dataset(store, decode_cf=True, mask_and_scale=True)
        self._mapping = discover_copernicus_variables(self._dataset)
        self._concentration = self._dataset[self._mapping.concentration]
        self._time_values = self._decode_times(self._dataset[self._mapping.time].values)
        self._configure_grid()
        self._active_date = dataset_date

    def _configure_grid(self) -> None:
        spatial_dims = self._concentration.dims[-2:]
        latitude = self._dataset[self._mapping.latitude] if self._mapping.latitude else None
        longitude = self._dataset[self._mapping.longitude] if self._mapping.longitude else None
        if latitude is not None and longitude is not None and latitude.ndim == longitude.ndim == 1:
            if latitude.dims[0] not in spatial_dims or longitude.dims[0] not in spatial_dims:
                raise ValueError("Copernicus geographic coordinates do not match the data grid.")
            self._grid_kind = "geographic"
            self._source_y = np.asarray(latitude.values, dtype=np.float64)
            self._source_x = np.asarray(longitude.values, dtype=np.float64)
            self._row_dimension = latitude.dims[0]
            self._column_dimension = longitude.dims[0]
            return

        row_dimension, column_dimension = spatial_dims
        if row_dimension in self._dataset.coords and column_dimension in self._dataset.coords:
            source_y = self._dataset[row_dimension]
            source_x = self._dataset[column_dimension]
            if source_y.ndim == source_x.ndim == 1:
                mapping_name = self._concentration.attrs.get("grid_mapping")
                if not isinstance(mapping_name, str) or mapping_name not in self._dataset.variables:
                    raise ValueError("Projected Copernicus grid has no CF grid_mapping variable.")
                self._grid_kind = "projected"
                self._row_dimension = row_dimension
                self._column_dimension = column_dimension
                self._source_y = np.asarray(source_y.values, dtype=np.float64)
                self._source_x = np.asarray(source_x.values, dtype=np.float64)
                self._source_y_scale = self._coordinate_scale(source_y.attrs.get("units"))
                self._source_x_scale = self._coordinate_scale(source_x.attrs.get("units"))
                source_crs = CRS.from_cf(dict(self._dataset[mapping_name].attrs))
                self._geographic_to_source = Transformer.from_crs("EPSG:4326", source_crs, always_xy=True)
                return
        if latitude is not None and longitude is not None and latitude.ndim == longitude.ndim == 2:
            self._grid_kind = "curvilinear"
            self._latitude_grid = np.asarray(latitude.values, dtype=np.float64)
            self._longitude_grid = np.asarray(longitude.values, dtype=np.float64)
            self._row_dimension, self._column_dimension = latitude.dims
            return
        raise ValueError("Unsupported Copernicus sea-ice coordinate grid.")

    def _nearest_spatial_indices(self, latitude: float, longitude: float) -> dict[str, int]:
        if self._grid_kind == "geographic":
            lon = self._normalize_longitude(longitude, self._source_x)
            if not self._inside(latitude, self._source_y) or not self._inside(lon, self._source_x):
                raise ValueError("Position is outside Copernicus sea-ice coverage.")
            return {
                self._row_dimension: int(np.argmin(np.abs(self._source_y - latitude))),
                self._column_dimension: int(np.argmin(np.abs(self._source_x - lon))),
            }
        if self._grid_kind == "projected":
            x_metres, y_metres = self._geographic_to_source.transform(longitude, latitude)
            x = x_metres / self._source_x_scale
            y = y_metres / self._source_y_scale
            if not self._inside(y, self._source_y) or not self._inside(x, self._source_x):
                raise ValueError("Position is outside Copernicus sea-ice coverage.")
            return {
                self._row_dimension: int(np.argmin(np.abs(self._source_y - y))),
                self._column_dimension: int(np.argmin(np.abs(self._source_x - x))),
            }
        longitude_delta = np.abs(((self._longitude_grid - longitude + 180.0) % 360.0) - 180.0)
        distance = (self._latitude_grid - latitude) ** 2 + (longitude_delta * np.cos(np.deg2rad(latitude))) ** 2
        valid = np.isfinite(distance)
        if not np.any(valid):
            raise LookupError("Copernicus grid contains no valid coordinates.")
        flat = int(np.nanargmin(np.where(valid, distance, np.nan)))
        row, column = np.unravel_index(flat, distance.shape)
        return {self._row_dimension: int(row), self._column_dimension: int(column)}

    def _nearest_time_index(self, requested: datetime | None) -> int:
        if requested is None:
            return 0
        target = requested.replace(tzinfo=timezone.utc) if requested.tzinfo is None else requested.astimezone(timezone.utc)
        return min(range(len(self._time_values)), key=lambda index: abs((self._time_values[index] - target).total_seconds()))

    def _read_value(self, name: str | None, time_index: int, spatial: dict[str, int]) -> float | None:
        if name is None:
            return None
        variable = self._dataset[name]
        selection = dict(spatial)
        if self._mapping.time in variable.dims:
            selection[self._mapping.time] = time_index
        value = np.ma.asarray(variable.isel(selection).values)
        if np.ma.is_masked(value):
            return None
        result = float(value)
        return result if np.isfinite(result) else None

    def _read_fraction(self, name: str | None, time_index: int, spatial: dict[str, int]) -> float | None:
        value = self._read_value(name, time_index, spatial)
        if value is None or name is None:
            return None
        units = str(self._dataset[name].attrs.get("units", "1")).strip().lower()
        if units in {"%", "percent", "percentage"}:
            value /= 100.0
        if not 0.0 <= value <= 1.0:
            return None
        return value

    def _read_nonnegative(self, name: str | None, time_index: int, spatial: dict[str, int]) -> float | None:
        value = self._read_value(name, time_index, spatial)
        return value if value is not None and value >= 0.0 else None

    @staticmethod
    def _dominant_ice_type(concentration: float, young: float | None, multi: float | None) -> int | None:
        if concentration <= 0.0:
            return 0
        if young is None and multi is None:
            return None
        if (multi or 0.0) > (young or 0.0):
            return 2
        if (young or 0.0) > (multi or 0.0):
            return 1
        return None

    @staticmethod
    def _decode_times(values: Any) -> list[datetime]:
        decoded: list[datetime] = []
        for value in np.asarray(values).reshape(-1):
            if isinstance(value, np.datetime64):
                decoded.append(datetime.fromisoformat(np.datetime_as_string(value, unit="us")).replace(tzinfo=timezone.utc))
            elif isinstance(value, datetime):
                decoded.append(value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc))
        if not decoded:
            raise ValueError("Copernicus dataset time coordinate is not decodable.")
        return decoded

    @staticmethod
    def _inside(value: float, coordinates: np.ndarray) -> bool:
        return float(np.nanmin(coordinates)) <= value <= float(np.nanmax(coordinates))

    @staticmethod
    def _normalize_longitude(longitude: float, coordinates: np.ndarray) -> float:
        if float(np.nanmin(coordinates)) >= 0 and longitude < 0:
            return longitude + 360.0
        if float(np.nanmax(coordinates)) <= 180 and longitude > 180:
            return longitude - 360.0
        return longitude

    @staticmethod
    def _coordinate_scale(units: object) -> float:
        normalized = str(units or "m").strip().lower()
        if normalized in {"m", "metre", "metres", "meter", "meters"}:
            return 1.0
        if normalized in {"km", "kilometre", "kilometres", "kilometer", "kilometers"}:
            return 1_000.0
        raise ValueError(f"Unsupported projected coordinate unit: {units}")


class CopernicusIceRasterProvider(CopernicusIceProvider):
    """Render cached XYZ concentration and thickness tiles from Copernicus CF grids."""

    tile_size = 256
    max_tile_zoom = 10
    _half_world = pi * 6_378_137.0
    _polar_half_extent = 3_314_693.0
    _mercator_to_geographic = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    _polar_to_geographic = Transformer.from_crs("EPSG:3413", "EPSG:4326", always_xy=True)

    def get_tile(
        self,
        zoom: int,
        x: int,
        y: int,
        requested_time: str | date | datetime | None = None,
        time_index: int = 0,
        *,
        render_mode: str = "concentration",
    ) -> bytes:
        if render_mode not in {"concentration", "thickness"}:
            raise ValueError("Sea-ice render mode must be concentration or thickness.")
        dataset_date = self._index.resolve(requested_time)
        with self._lock:
            self._activate(dataset_date)
            selected_index = self._nearest_time_index(requested_time if isinstance(requested_time, datetime) else None)
            if requested_time is None and time_index:
                selected_index = time_index
            if not 0 <= selected_index < len(self._time_values):
                raise ValueError("Sea-ice time index is outside the dataset.")
        return self._render_tile(dataset_date, selected_index, zoom, x, y, render_mode)

    def get_polar_tile(
        self,
        zoom: int,
        x: int,
        y: int,
        requested_time: str | date | datetime | None = None,
        time_index: int = 0,
        *,
        render_mode: str = "concentration",
    ) -> bytes:
        """Render one native EPSG:3413 XYZ tile for the Arctic tactical view."""

        if render_mode not in {"concentration", "thickness"}:
            raise ValueError("Sea-ice render mode must be concentration or thickness.")
        dataset_date = self._index.resolve(requested_time)
        with self._lock:
            self._activate(dataset_date)
            selected_index = self._nearest_time_index(
                requested_time if isinstance(requested_time, datetime) else None
            )
            if requested_time is None and time_index:
                selected_index = time_index
            if not 0 <= selected_index < len(self._time_values):
                raise ValueError("Sea-ice time index is outside the dataset.")
        return self._render_polar_tile(
            dataset_date,
            selected_index,
            zoom,
            x,
            y,
            render_mode,
        )

    @lru_cache(maxsize=256)
    def _render_tile(
        self,
        dataset_date: str,
        time_index: int,
        zoom: int,
        x: int,
        y: int,
        render_mode: str,
    ) -> bytes:
        return self._render_projected_tile(
            dataset_date,
            time_index,
            zoom,
            x,
            y,
            render_mode,
            target_projection="EPSG:3857",
        )

    @lru_cache(maxsize=256)
    def _render_polar_tile(
        self,
        dataset_date: str,
        time_index: int,
        zoom: int,
        x: int,
        y: int,
        render_mode: str,
    ) -> bytes:
        return self._render_projected_tile(
            dataset_date,
            time_index,
            zoom,
            x,
            y,
            render_mode,
            target_projection="EPSG:3413",
        )

    def _render_projected_tile(
        self,
        dataset_date: str,
        time_index: int,
        zoom: int,
        x: int,
        y: int,
        render_mode: str,
        *,
        target_projection: str,
    ) -> bytes:
        with self._lock:
            self._activate(dataset_date)
            self._validate_tile(zoom, x, y)
            if render_mode == "concentration":
                values = self._resample_field(
                    self._mapping.concentration,
                    time_index,
                    zoom,
                    x,
                    y,
                    fraction=True,
                    target_projection=target_projection,
                )
                rgba = self.colorize_concentration(values)
            else:
                if self._mapping.thickness is None:
                    raise ValueError("Copernicus dataset has no sea-ice thickness variable.")
                values = self._resample_field(
                    self._mapping.thickness,
                    time_index,
                    zoom,
                    x,
                    y,
                    fraction=False,
                    target_projection=target_projection,
                )
                rgba = self.colorize_thickness(values)
            output = BytesIO()
            Image.fromarray(rgba, mode="RGBA").save(output, format="PNG", optimize=True)
            return output.getvalue()

    def _resample_field(
        self,
        name: str,
        time_index: int,
        zoom: int,
        x: int,
        y: int,
        *,
        fraction: bool,
        target_projection: str,
    ) -> np.ndarray:
        target_x, target_y = self._target_grid(
            zoom,
            x,
            y,
            half_extent=(
                self._half_world
                if target_projection == "EPSG:3857"
                else self._polar_half_extent
            ),
        )
        target_to_geographic = (
            self._mercator_to_geographic
            if target_projection == "EPSG:3857"
            else self._polar_to_geographic
        )
        if self._grid_kind == "geographic":
            sample_x, sample_y = target_to_geographic.transform(target_x, target_y)
            sample_x = np.asarray(sample_x, dtype=np.float64)
            sample_y = np.asarray(sample_y, dtype=np.float64)
        elif self._grid_kind == "projected":
            geographic_x, geographic_y = target_to_geographic.transform(target_x, target_y)
            source_x, source_y = self._geographic_to_source.transform(geographic_x, geographic_y)
            sample_x = np.asarray(source_x, dtype=np.float64) / self._source_x_scale
            sample_y = np.asarray(source_y, dtype=np.float64) / self._source_y_scale
        else:
            raise ValueError("Curvilinear Copernicus grids require projected x/y coordinates for raster tiles.")

        rows = self._fractional_indices(sample_y, self._source_y)
        periodic_longitude = (
            self._grid_kind == "geographic"
            and target_projection == "EPSG:3413"
            and self._is_global_longitude_grid(self._source_x)
        )
        columns = (
            self._periodic_longitude_indices(sample_x, self._source_x)
            if periodic_longitude
            else self._fractional_indices(sample_x, self._source_x)
        )
        valid_target = np.isfinite(rows) & np.isfinite(columns)
        output = np.full(rows.shape, np.nan, dtype=np.float32)
        if not np.any(valid_target):
            return output
        row_slice = self._window(rows[valid_target], len(self._source_y))
        column_slice = (
            slice(0, len(self._source_x))
            if periodic_longitude
            else self._window(columns[valid_target], len(self._source_x))
        )
        variable = self._dataset[name]
        selection: dict[str, object] = {
            self._row_dimension: row_slice,
            self._column_dimension: column_slice,
        }
        if self._mapping.time in variable.dims:
            selection[self._mapping.time] = time_index
        selected = variable.isel(selection).transpose(self._row_dimension, self._column_dimension)
        values = np.asarray(np.ma.asarray(selected.values).filled(np.nan), dtype=np.float32)
        if fraction and str(variable.attrs.get("units", "1")).strip().lower() in {"%", "percent", "percentage"}:
            values /= 100.0
        valid_values = np.isfinite(values) & (values >= 0.0) & ((values <= 1.0) if fraction else True)
        values = np.where(valid_values, values, np.nan)
        sampler = (
            self._bilinear_with_nearest_mask_periodic_columns
            if periodic_longitude
            else self._bilinear_with_nearest_mask
        )
        return sampler(
            values,
            rows - row_slice.start,
            columns - column_slice.start,
            valid_target,
        )

    @classmethod
    def _target_grid(
        cls,
        zoom: int,
        x: int,
        y: int,
        *,
        half_extent: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        count = 1 << zoom
        width = 2 * half_extent / count
        west = -half_extent + x * width
        north = half_extent - y * width
        offsets = (np.arange(cls.tile_size, dtype=np.float64) + 0.5) / cls.tile_size
        return np.meshgrid(west + width * offsets, north - width * offsets)

    def _validate_tile(self, zoom: int, x: int, y: int) -> None:
        count = 1 << zoom
        if not 0 <= zoom <= self.max_tile_zoom:
            raise ValueError(f"Tile zoom must be between 0 and {self.max_tile_zoom}.")
        if not 0 <= x < count or not 0 <= y < count:
            raise ValueError("Tile coordinate is outside the requested zoom level.")

    @staticmethod
    def _fractional_indices(values: np.ndarray, coordinates: np.ndarray) -> np.ndarray:
        increasing = coordinates[-1] > coordinates[0]
        ordered = coordinates if increasing else coordinates[::-1]
        ordered_indices = np.arange(coordinates.size) if increasing else np.arange(coordinates.size)[::-1]
        result = np.full(values.shape, np.nan, dtype=np.float64)
        inside = np.isfinite(values) & (values >= ordered[0]) & (values <= ordered[-1])
        result[inside] = np.interp(values[inside], ordered, ordered_indices)
        return result

    @staticmethod
    def _is_global_longitude_grid(coordinates: np.ndarray) -> bool:
        if coordinates.ndim != 1 or coordinates.size < 2:
            return False
        spacing = float(np.median(np.abs(np.diff(coordinates))))
        coverage = float(np.nanmax(coordinates) - np.nanmin(coordinates)) + spacing
        return np.isclose(coverage, 360.0, atol=max(spacing, 1e-6))

    @staticmethod
    def _periodic_longitude_indices(
        values: np.ndarray,
        coordinates: np.ndarray,
    ) -> np.ndarray:
        """Return cyclic indices so EPSG:3413 has no antimeridian spoke."""

        if coordinates.ndim != 1 or coordinates.size < 2:
            return CopernicusIceRasterProvider._fractional_indices(values, coordinates)
        if coordinates[-1] < coordinates[0]:
            raise ValueError("Periodic longitude coordinates must be increasing.")
        spacing = float(np.median(np.diff(coordinates)))
        period = spacing * coordinates.size
        result = np.full(values.shape, np.nan, dtype=np.float64)
        finite = np.isfinite(values)
        result[finite] = (
            ((values[finite] - coordinates[0] + period / 2.0) % period)
            - period / 2.0
        ) / spacing
        return result

    @staticmethod
    def _window(positions: np.ndarray, size: int) -> slice:
        start = max(0, int(np.floor(np.nanmin(positions))) - 1)
        stop = min(size, int(np.ceil(np.nanmax(positions))) + 2)
        if stop - start < 2:
            start = max(0, min(start, size - 2))
            stop = start + 2
        return slice(start, stop)

    @classmethod
    def _bilinear_with_nearest_mask(
        cls,
        values: np.ndarray,
        rows: np.ndarray,
        columns: np.ndarray,
        valid_target: np.ndarray,
    ) -> np.ndarray:
        return cls._bilinear_core(
            values, rows, columns, valid_target, periodic_columns=False
        )

    @classmethod
    def _bilinear_with_nearest_mask_periodic_columns(
        cls,
        values: np.ndarray,
        rows: np.ndarray,
        columns: np.ndarray,
        valid_target: np.ndarray,
    ) -> np.ndarray:
        return cls._bilinear_core(
            values, rows, columns, valid_target, periodic_columns=True
        )

    @staticmethod
    def _bilinear_core(
        values: np.ndarray,
        rows: np.ndarray,
        columns: np.ndarray,
        valid_target: np.ndarray,
        *,
        periodic_columns: bool,
    ) -> np.ndarray:
        """Interpolate values while taking validity/open-water from the nearest source cell.

        This prevents valid ice neighbours from bleeding into land, missing cells or
        source cells that explicitly contain zero ice.
        """

        output = np.full(rows.shape, np.nan, dtype=np.float32)
        if min(values.shape) < 2:
            return output
        rows_safe = np.where(valid_target, rows, 0.0)
        columns_safe = np.where(valid_target, columns, 0.0)
        row0 = np.clip(np.floor(rows_safe).astype(int), 0, values.shape[0] - 2)
        raw_column0 = np.floor(columns_safe).astype(int)
        column0 = (
            np.mod(raw_column0, values.shape[1])
            if periodic_columns
            else np.clip(raw_column0, 0, values.shape[1] - 2)
        )
        column1 = (
            np.mod(column0 + 1, values.shape[1])
            if periodic_columns
            else column0 + 1
        )
        row_fraction = np.clip(rows_safe - row0, 0, 1)
        column_fraction = np.clip(columns_safe - raw_column0, 0, 1)
        neighbours = (
            (values[row0, column0], (1 - row_fraction) * (1 - column_fraction)),
            (values[row0, column1], (1 - row_fraction) * column_fraction),
            (values[row0 + 1, column0], row_fraction * (1 - column_fraction)),
            (values[row0 + 1, column1], row_fraction * column_fraction),
        )
        weighted = np.zeros(rows.shape, dtype=np.float64)
        weights = np.zeros(rows.shape, dtype=np.float64)
        for neighbour, weight in neighbours:
            available = np.isfinite(neighbour)
            weighted += np.where(available, neighbour, 0.0) * weight
            weights += available * weight
        nearest_rows = np.clip(np.rint(rows_safe).astype(int), 0, values.shape[0] - 1)
        rounded_columns = np.rint(columns_safe).astype(int)
        nearest_columns = (
            np.mod(rounded_columns, values.shape[1])
            if periodic_columns
            else np.clip(rounded_columns, 0, values.shape[1] - 1)
        )
        nearest = values[nearest_rows, nearest_columns]
        valid = valid_target & np.isfinite(nearest) & (weights > 0.0)
        output[valid] = (weighted[valid] / weights[valid]).astype(np.float32)
        output[valid & (nearest == 0.0)] = 0.0
        return output

    @classmethod
    def colorize_concentration(cls, concentration: np.ndarray) -> np.ndarray:
        """Continuously map the physical 0–1 concentration field to RGBA."""

        return cls._continuous_rgba(
            concentration,
            stops=np.array([0.0, 0.15, 0.40, 0.60, 0.80, 1.0]),
            colors=np.array(
                [
                    [218, 246, 249, 0],
                    [190, 235, 242, 120],
                    [92, 190, 180, 180],
                    [58, 144, 139, 210],
                    [215, 225, 225, 238],
                    [255, 255, 255, 255],
                ],
                dtype=np.float64,
            ),
            maximum=1.0,
        )

    @classmethod
    def colorize_thickness(cls, thickness: np.ndarray) -> np.ndarray:
        """Continuously map thickness in metres; zero and missing cells stay clear."""

        return cls._continuous_rgba(
            thickness,
            stops=np.array([0.0, 0.50, 1.50, 3.0, 5.0]),
            colors=np.array(
                [
                    [255, 246, 214, 0],
                    [255, 229, 153, 145],
                    [239, 155, 70, 210],
                    [132, 82, 125, 240],
                    [255, 255, 255, 255],
                ],
                dtype=np.float64,
            ),
            maximum=5.0,
        )

    @staticmethod
    def _continuous_rgba(
        field: np.ndarray,
        *,
        stops: np.ndarray,
        colors: np.ndarray,
        maximum: float,
    ) -> np.ndarray:
        values = np.asarray(field, dtype=np.float32)
        rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
        visible = np.isfinite(values) & (values > 0.0)
        if not np.any(visible):
            return rgba
        clipped = np.clip(values[visible], 0.0, maximum)
        for channel in range(4):
            rgba[..., channel][visible] = np.rint(
                np.interp(clipped, stops, colors[:, channel])
            ).astype(np.uint8)
        return rgba

    # Backward-compatible name retained for callers that only render concentration.
    colorize = colorize_concentration
