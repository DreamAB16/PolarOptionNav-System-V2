from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from core.models import Position, SeaIceState
from core.config.environment_config import get_dataset_path
from services.environment_service import (
    CopernicusIceDatasetIndex,
    CopernicusIceProvider,
    CopernicusIceRasterProvider,
    EnvironmentService,
    EnvironmentTimeManager,
)
from tools.data_tools.inspect.inspect_nc import open_netcdf


REAL_PROCESSED_DIRECTORY = get_dataset_path("ice") / "processed" / "copernicus"


def _require_real_copernicus_dataset() -> None:
    if not REAL_PROCESSED_DIRECTORY.is_dir() or not any(REAL_PROCESSED_DIRECTORY.glob("arctic_ice_*.nc")):
        pytest.skip("Copernicus sea-ice dataset not available")


def create_copernicus_file(path: Path, day: date = date(2025, 2, 15)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open_netcdf(path, "w", format="NETCDF4") as dataset:
        dataset.createDimension("time", 3)
        dataset.createDimension("latitude", 5)
        dataset.createDimension("longitude", 5)

        time = dataset.createVariable("time", "f8", ("time",))
        time.standard_name = "time"
        time.units = f"hours since {day:%Y-%m-%d} 00:00:00"
        time.calendar = "standard"
        time[:] = [12, 13, 14]

        latitude = dataset.createVariable("latitude", "f8", ("latitude",))
        latitude.standard_name = "latitude"
        latitude.units = "degrees_north"
        latitude[:] = [50, 60, 70, 80, 90]
        longitude = dataset.createVariable("longitude", "f8", ("longitude",))
        longitude.standard_name = "longitude"
        longitude.units = "degrees_east"
        longitude[:] = [-180, -90, 0, 90, 180]

        dimensions = ("time", "latitude", "longitude")
        fields = {
            "siconc": ("sea_ice_area_fraction", "Sea Ice Concentration", "1", 0.9),
            "sithick": ("sea_ice_thickness", "Sea Ice Thickness", "m", 2.5),
            "siconc_my": ("sea_ice_classification", "Sea Ice Area Fraction of Multi-year Ice", "1", 0.8),
            "siconc_young": ("sea_ice_classification", "Sea Ice Area Fraction of Young Ice", "1", 0.1),
            "vxsi": ("eastward_sea_ice_velocity", "Eastward sea ice velocity", "m s-1", 0.12),
            "vysi": ("northward_sea_ice_velocity", "Northward sea ice velocity", "m s-1", -0.04),
            "sisnthick": ("surface_snow_thickness", "Surface Snow Thickness", "m", 0.3),
        }
        for name, (standard_name, long_name, units, value) in fields.items():
            variable = dataset.createVariable(name, "f4", dimensions, fill_value=-9999.0)
            variable.standard_name = standard_name
            variable.long_name = long_name
            variable.units = units
            variable[:] = value

        concentration = dataset.variables["siconc"]
        concentration[:, 0, :] = 0.0
        concentration[:, 1, :] = 0.1
        concentration[:, 2, :] = 0.5
        concentration[:, 3:, :] = 0.9
        concentration[:, 2, 1] = -9999.0


def test_copernicus_index_and_multivariable_point_query(tmp_path: Path) -> None:
    path = tmp_path / "arctic_ice_20250215.nc"
    create_copernicus_file(path)
    index = CopernicusIceDatasetIndex(tmp_path)
    provider = CopernicusIceProvider(tmp_path)
    try:
        state = provider.query(
            Position(latitude=80, longitude=0),
            datetime(2025, 2, 15, 13, 20, tzinfo=timezone.utc),
        )

        assert index.available_dates == ["20250215"]
        assert index.resolve("2025-02-16T00:00:00Z") == "20250215"
        assert isinstance(state, SeaIceState)
        assert state.timestamp == datetime(2025, 2, 15, 13, tzinfo=timezone.utc)
        assert state.concentration == pytest.approx(0.9)
        assert state.thickness == pytest.approx(2.5)
        assert state.ice_type == 2
        assert state.drift_u == pytest.approx(0.12)
        assert state.drift_v == pytest.approx(-0.04)
        assert state.snow_thickness == pytest.approx(0.3)
        assert state.source == "Copernicus Marine neXtSIM-F"
    finally:
        provider.close()


def test_copernicus_raster_masks_open_water_fill_and_outside_coverage(tmp_path: Path) -> None:
    create_copernicus_file(tmp_path / "arctic_ice_20250215.nc")
    provider = CopernicusIceRasterProvider(tmp_path)
    try:
        png = provider.get_tile(1, 1, 0, datetime(2025, 2, 15, 13, tzinfo=timezone.utc))
        rgba = np.asarray(Image.open(BytesIO(png)).convert("RGBA"))

        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert rgba.shape == (256, 256, 4)
        assert (rgba[..., 3] == 0).any()
        assert (rgba[..., 3] > 0).any()
        assert np.all(rgba[rgba[..., 3] == 0, :3] == 0)
        assert (rgba[..., 3] >= 240).sum() > 100
    finally:
        provider.close()


def test_copernicus_palette_is_continuous_and_transparent_for_zero_and_missing() -> None:
    values = np.array([[np.nan, 0.0, 0.10, 0.11, 0.4, 0.7, 0.9]])
    rgba = CopernicusIceRasterProvider.colorize_concentration(values)

    assert tuple(rgba[0, 0]) == (0, 0, 0, 0)
    assert tuple(rgba[0, 1]) == (0, 0, 0, 0)
    assert rgba[0, 2, 3] > 0
    assert not np.array_equal(rgba[0, 2], rgba[0, 3])
    assert tuple(rgba[0, 4]) == (92, 190, 180, 180)
    assert rgba[0, 6, 3] > rgba[0, 4, 3]


def test_copernicus_thickness_palette_preserves_zero_and_changes_continuously() -> None:
    rgba = CopernicusIceRasterProvider.colorize_thickness(
        np.array([[np.nan, 0.0, 0.25, 0.5, 1.0, 1.5, 3.0, 5.0]])
    )

    assert tuple(rgba[0, 0]) == (0, 0, 0, 0)
    assert tuple(rgba[0, 1]) == (0, 0, 0, 0)
    assert rgba[0, 2, 3] > 0
    assert not np.array_equal(rgba[0, 2], rgba[0, 3])
    assert tuple(rgba[0, -1]) == (255, 255, 255, 255)


def test_bilinear_values_use_nearest_source_cell_for_mask_and_open_water() -> None:
    values = np.array([[np.nan, 1.0], [0.0, 1.0]], dtype=np.float32)
    rows = np.array([[0.1, 0.9, 0.9]])
    columns = np.array([[0.1, 0.1, 0.9]])
    result = CopernicusIceRasterProvider._bilinear_with_nearest_mask(
        values,
        rows,
        columns,
        np.ones(rows.shape, dtype=bool),
    )

    assert np.isnan(result[0, 0])  # Nearest source is missing/land.
    assert result[0, 1] == 0.0  # Nearest source is explicit open water.
    assert 0.0 < result[0, 2] <= 1.0


def test_periodic_longitude_interpolation_closes_the_polar_dateline_seam() -> None:
    coordinates = np.array([-135.0, -45.0, 45.0, 135.0])
    indices = CopernicusIceRasterProvider._periodic_longitude_indices(
        np.array([[-180.0, 180.0, -179.0, 179.0]]),
        coordinates,
    )
    values = np.array(
        [[0.2, 0.4, 0.6, 1.0], [0.2, 0.4, 0.6, 1.0]],
        dtype=np.float32,
    )
    sampled = CopernicusIceRasterProvider._bilinear_with_nearest_mask_periodic_columns(
        values,
        np.full(indices.shape, 0.5),
        indices,
        np.ones(indices.shape, dtype=bool),
    )

    assert indices[0, 0] == pytest.approx(indices[0, 1])
    assert sampled[0, 0] == pytest.approx(sampled[0, 1])
    assert abs(float(sampled[0, 2] - sampled[0, 3])) < 0.02


def test_environment_time_manager_drives_copernicus_provider(tmp_path: Path) -> None:
    create_copernicus_file(tmp_path / "arctic_ice_20250215.nc")
    provider = CopernicusIceProvider(tmp_path)
    raster = CopernicusIceRasterProvider(tmp_path)
    service = EnvironmentService(
        providers=[provider],
        ice_raster_provider=raster,
        time_manager=EnvironmentTimeManager(
            simulation_time=datetime(2025, 2, 15, 14, tzinfo=timezone.utc)
        ),
    )
    try:
        state = service.query_ice(Position(latitude=80, longitude=0))

        assert state.timestamp == datetime(2025, 2, 15, 14, tzinfo=timezone.utc)
        assert state.source == "Copernicus Marine neXtSIM-F"
    finally:
        provider.close()
        raster.close()


def test_real_processed_copernicus_files_support_time_and_space_queries() -> None:
    _require_real_copernicus_dataset()
    index = CopernicusIceDatasetIndex(REAL_PROCESSED_DIRECTORY)
    provider = CopernicusIceProvider(REAL_PROCESSED_DIRECTORY)
    try:
        winter = provider.query(
            Position(latitude=80.0, longitude=0.0),
            datetime(2025, 2, 15, 12, tzinfo=timezone.utc),
        )
        summer = provider.query(
            Position(latitude=80.0, longitude=0.0),
            datetime(2025, 8, 15, 12, tzinfo=timezone.utc),
        )
        nearest = provider.query(
            Position(latitude=80.0, longitude=0.0),
            datetime(2025, 7, 1, 12, tzinfo=timezone.utc),
        )

        assert index.available_dates == [
            *(f"202502{day:02d}" for day in range(8, 23)),
            *(f"202508{day:02d}" for day in range(8, 23)),
        ]
        assert provider.get_metadata()["grid"] == "geographic"
        assert winter.source == "Copernicus Marine neXtSIM-F"
        assert winter.concentration > 0.8
        assert winter.thickness is not None and winter.thickness > 0.0
        assert 0.0 <= summer.concentration <= 1.0
        assert nearest.timestamp.date() == date(2025, 8, 8)
        with pytest.raises(ValueError, match="outside Copernicus sea-ice coverage"):
            provider.query(Position(latitude=40.0, longitude=0.0), winter.timestamp)
    finally:
        provider.close()


def test_real_copernicus_tiles_preserve_mask_continuity_and_date_cache_key() -> None:
    _require_real_copernicus_dataset()
    provider = CopernicusIceRasterProvider(REAL_PROCESSED_DIRECTORY)
    try:
        provider._render_tile.cache_clear()
        winter_png = provider.get_tile(2, 2, 0, "20250215")
        summer_png = provider.get_tile(2, 2, 0, "20250815")
        low_latitude_png = provider.get_tile(3, 4, 3, "20250215")
        winter = np.asarray(Image.open(BytesIO(winter_png)).convert("RGBA"))
        low_latitude = np.asarray(Image.open(BytesIO(low_latitude_png)).convert("RGBA"))
        visible = winter[..., 3] > 0

        assert winter_png != summer_png
        assert visible.any()
        assert not visible.all()
        assert (visible[:, 1:] & visible[:, :-1]).sum() > 1_000
        assert np.all(low_latitude[..., 3] == 0)
        assert provider._render_tile.cache_info().currsize == 3
    finally:
        provider.close()


def test_real_copernicus_thickness_tile_is_rgba_and_distinct_from_concentration() -> None:
    _require_real_copernicus_dataset()
    provider = CopernicusIceRasterProvider(REAL_PROCESSED_DIRECTORY)
    try:
        concentration_png = provider.get_tile(2, 2, 0, "20250215")
        thickness_png = provider.get_tile(
            2,
            2,
            0,
            "20250215",
            render_mode="thickness",
        )
        thickness = np.asarray(Image.open(BytesIO(thickness_png)).convert("RGBA"))

        assert thickness_png.startswith(b"\x89PNG\r\n\x1a\n")
        assert thickness_png != concentration_png
        assert (thickness[..., 3] > 0).any()
        assert (thickness[..., 3] == 0).any()
    finally:
        provider.close()


def test_real_native_polar_tile_covers_the_pole_without_extending_past_arctic_data() -> None:
    _require_real_copernicus_dataset()
    provider = CopernicusIceRasterProvider(REAL_PROCESSED_DIRECTORY)
    try:
        png = provider.get_polar_tile(0, 0, 0, "20250215")
        rgba = np.asarray(Image.open(BytesIO(png)).convert("RGBA"))

        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert rgba[128, 128, 3] > 0
        assert rgba[0, 0, 3] == 0
        assert rgba[-1, -1, 3] == 0
    finally:
        provider.close()
