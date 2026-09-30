from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image
import pytest
import rasterio
from rasterio.transform import from_origin

from core.models import Position
from core.config.environment_config import get_dataset_path
from services.environment_service import (
    CopernicusIceProvider,
    CopernicusIceRasterProvider,
    CARRA2WindProvider,
    EnvironmentService,
    MockIceProvider,
    PolarBathymetryProvider,
    RealBathymetryProvider,
    RealCurrentProvider,
    RealWindProvider,
    RealWaveProvider,
)


def test_environment_service_loads_default_provider_set():
    gebco_path = get_dataset_path("bathymetry") / "raw" / "GEBCO_2026_sub_ice.nc"
    if not gebco_path.is_file():
        pytest.skip("GEBCO dataset not available")
    ice_directory = get_dataset_path("ice") / "processed" / "copernicus"
    if not ice_directory.is_dir() or not any(ice_directory.glob("arctic_ice_*.nc")):
        pytest.skip("Copernicus sea-ice dataset not available")
    wind_directory = get_dataset_path("wind") / "raw"
    if not any(wind_directory.glob("10m_wind_speed_*.nc")) or not any(wind_directory.glob("10m_wind_direction_*.nc")):
        pytest.skip("CARRA2 dataset not available")
    if not any((get_dataset_path("current") / "raw").glob("Copernicus_current_*.nc")):
        pytest.skip("TOPAZ5 dataset not available")
    if not any((get_dataset_path("wave") / "raw").glob("Copernicus_wave_*.nc")):
        pytest.skip("WAM dataset not available")
    service = EnvironmentService()

    assert type(service.providers[0]) is RealBathymetryProvider
    assert type(service.providers[1]) is CopernicusIceProvider
    assert type(service.ice_raster_provider) is CopernicusIceRasterProvider
    assert [type(provider) for provider in service.providers[2:]] == [
        CARRA2WindProvider, RealCurrentProvider, RealWaveProvider,
    ]
    assert [layer["id"] for layer in service.get_available_layers()] == [
        "bathymetry",
        "ice",
        "wind",
        "current",
        "wave",
    ]
    assert service.get_metadata()[0]["status"] == "ready"
    assert [metadata["status"] for metadata in service.get_metadata()] == [
        "ready",
        "ready",
        "ready",
        "ready",
        "ready",
    ]
    for provider in service.providers:
        if hasattr(provider, "close"):
            provider.close()
    service.ice_raster_provider.close()


def test_environment_service_registers_and_queries_ice_provider():
    service = EnvironmentService(providers=[])
    try:
        mock_provider = MockIceProvider()
        service.register_provider(mock_provider)

        result = service.query_ice(
            Position(latitude=72.5, longitude=15.25),
            datetime(2026, 9, 11, tzinfo=timezone.utc),
        )

        assert service.providers == [mock_provider]
        assert result.latitude == 72.5
        assert result.longitude == 15.25
        assert result.concentration == 0.78
        assert result.thickness == 1.2
        assert result.source == "mock"
    finally:
        service.ice_raster_provider.close()


def test_real_gebco_dataset_opens_and_answers_point_query():
    dataset_path = get_dataset_path("bathymetry") / "raw" / "GEBCO_2026_sub_ice.nc"
    if not dataset_path.is_file():
        pytest.skip("GEBCO dataset not available")
    provider = RealBathymetryProvider(
        dataset_path
    )
    try:
        metadata = provider.get_metadata()
        state = provider.query(75.0, 0.0)

        assert metadata["crs"] == "EPSG:4326"
        assert metadata["depth_units"] == "m"
        assert metadata["resolution_degrees"][0] == pytest.approx(1 / 240)
        assert state.depth == 3709.0
        assert state.source == "GEBCO_2026_sub_ice"
    finally:
        provider.close()


def test_polar_bathymetry_tile_keeps_nodata_and_land_transparent(tmp_path: Path):
    path = tmp_path / "polar_bathymetry.tif"
    with rasterio.open(
        str(path.relative_to(Path.cwd())),
        mode="w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="int16",
        crs="EPSG:3413",
        transform=from_origin(-7_150_000, 7_150_000, 7_150_000, 7_150_000),
        nodata=-32768,
    ) as dataset:
        dataset.write(np.array([[-100, 25], [-32768, -300]], dtype=np.int16), 1)

    provider = PolarBathymetryProvider(path)
    try:
        image = Image.open(BytesIO(provider.get_tile(0, 0, 0))).convert("RGBA")
        alpha = np.asarray(image)[..., 3]

        assert provider.get_metadata()["crs"] == "EPSG:3413"
        assert alpha.max() == 175
        assert alpha.min() == 0
        assert np.count_nonzero(alpha == 0) > 0
        assert np.count_nonzero(alpha == 175) > 0
    finally:
        provider.close()
