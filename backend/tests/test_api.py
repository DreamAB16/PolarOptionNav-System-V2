from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from core.config.environment_config import get_dataset_path

client = TestClient(app)


def _require_dataset(name: str, pattern: str, reason: str, *, subdirectory: str = "raw") -> None:
    directory = get_dataset_path(name) / subdirectory
    if not directory.is_dir() or not any(directory.glob(pattern)):
        pytest.skip(reason)


def _require_ice_dataset() -> None:
    _require_dataset("ice", "arctic_ice_*.nc", "Copernicus sea-ice dataset not available", subdirectory="processed/copernicus")


def _require_gebco_dataset() -> None:
    path = get_dataset_path("bathymetry") / "raw" / "GEBCO_2026_sub_ice.nc"
    if not path.is_file():
        pytest.skip("GEBCO dataset not available")


def _require_all_environment_datasets() -> None:
    _require_gebco_dataset()
    _require_ice_dataset()
    _require_dataset("wind", "10m_wind_speed_*.nc", "CARRA2 dataset not available")
    _require_dataset("wind", "10m_wind_direction_*.nc", "CARRA2 dataset not available")
    _require_dataset("current", "Copernicus_current_*.nc", "TOPAZ5 dataset not available")
    _require_dataset("wave", "Copernicus_wave_*.nc", "WAM dataset not available")


def test_api_surface_has_no_experimental_routes():
    paths = sorted(
        route.path
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/")
    )
    print("API routes:")
    print("\n".join(paths))
    assert not any(path.startswith("/api/experimental/") for path in paths)
    assert "/api/environment/time" in paths
    assert "/api/environment/query" in paths
    assert "/api/environment/grid" in paths
    assert "/api/vessel" in paths
    assert "/api/vessel/current" in paths


def test_root_and_status():
    assert client.get("/").json()["status"] == "running"
    assert client.get("/api/status").json() == {"system": "PolarOptionNav-System-V2", "status": "running"}


def test_chart_layer_catalogue_and_geojson_are_available():
    catalogue = client.get("/api/chart/layers")
    assert catalogue.status_code == 200
    coastline = catalogue.json()["layers"][0]
    assert coastline["id"] == "coastline"
    assert coastline["format"] == "geojson"
    assert "base_map.gpkg" not in str(coastline)

    layer_data = client.get(coastline["url"])
    assert layer_data.status_code == 200
    geojson = layer_data.json()
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == coastline["feature_count"]
    assert geojson["features"][0]["geometry"]["type"] in {"LineString", "MultiLineString"}


def test_other_phase_zero_mock_endpoints():
    assert client.get("/api/chart").json()["status"] == "ready"
    assert client.get("/api/environment").json()["position"]["latitude"] == 69.65
    assert client.get("/api/vessel").json()["speed"] == 8.0
    assert client.post("/api/planner").json()["status"] == "mock"


def test_environment_layer_catalogue_is_available():
    _require_all_environment_datasets()
    response = client.get("/api/environment/layers")

    assert response.status_code == 200
    layers = response.json()["layers"]
    assert [layer["id"] for layer in layers] == ["bathymetry", "ice", "wind", "current", "wave"]
    assert layers[0]["status"] == "ready"
    assert layers[1]["status"] == "ready"
    assert layers[2]["status"] == "ready"  # Paired CARRA2 si10/wdir10 files are present.
    assert layers[3]["status"] == "ready"  # TOPAZ5 samples are present.
    assert layers[4]["status"] == "ready"  # Copernicus WAM Arctic samples are present.


def test_environment_time_status_is_available():
    response = client.get("/api/environment/time")

    assert response.status_code == 200
    assert response.json() == {
        "simulation_time": "2025-02-15T12:00:00Z",
        "forecast_time": "2025-02-15T12:00:00Z",
        "time_step_seconds": 3600,
        "scenario": "winter",
        "range_start": "2025-02-08T00:00:00Z",
        "range_end": "2025-02-22T23:00:00Z",
        "is_playing": False,
    }


def test_ice_query_returns_time_aware_sea_ice_state():
    _require_ice_dataset()
    response = client.get("/api/environment/ice/query", params={"lat": 80.0, "lon": 0.0})

    assert response.status_code == 200
    body = response.json()
    assert body["latitude"] == 80.0
    assert body["longitude"] == 0.0
    assert 0.0 <= body["concentration"] <= 1.0
    assert body["thickness"] is None or body["thickness"] >= 0.0
    assert set(("ice_type", "drift_u", "drift_v", "snow_thickness")).issubset(body)
    assert body["source"] == "Copernicus Marine neXtSIM-F"
    assert body["timestamp"].endswith("Z")


def test_ice_query_accepts_an_iso_environment_time():
    _require_ice_dataset()
    response = client.get(
        "/api/environment/ice/query",
        params={"lat": 80.0, "lon": 0.0, "time": "2025-02-15T12:00:00Z"},
    )

    assert response.status_code == 200
    assert response.json()["timestamp"].startswith("2025-02-15T12:00:00")


def test_ice_query_selects_the_nearest_copernicus_file() -> None:
    _require_ice_dataset()
    response = client.get(
        "/api/environment/ice/query",
        params={"lat": 80.0, "lon": 0.0, "time": "2025-07-01T12:00:00Z"},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "Copernicus Marine neXtSIM-F"
    assert response.json()["timestamp"].startswith("2025-08-08T12:00:00")


def test_ice_raster_tile_is_available():
    _require_ice_dataset()
    response = client.get("/api/environment/ice/tile/2/2/0.png")
    nearest_date_response = client.get("/api/environment/ice/tile/2/2/0.png", params={"date": "20250215"})

    assert response.status_code == 200
    assert nearest_date_response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert nearest_date_response.content == response.content


def test_ice_raster_tile_accepts_time_and_retains_date_debug_compatibility():
    _require_ice_dataset()
    by_time = client.get(
        "/api/environment/ice/tile/2/2/0.png",
        params={"time": "2025-02-15T12:00:00Z"},
    )
    by_date = client.get("/api/environment/ice/tile/2/2/0.png", params={"date": "20250215"})
    ambiguous = client.get(
        "/api/environment/ice/tile/2/2/0.png",
        params={"date": "20250215", "time": "2025-02-15T12:00:00Z"},
    )

    assert by_time.status_code == 200
    assert by_time.content == by_date.content
    assert ambiguous.status_code == 422


def test_ice_thickness_raster_tile_is_available() -> None:
    _require_ice_dataset()
    response = client.get(
        "/api/environment/ice/thickness/tile/2/2/0.png",
        params={"time": "2025-02-15T12:00:00Z"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_native_polar_ice_tiles_are_available_for_both_modes() -> None:
    _require_ice_dataset()
    concentration = client.get(
        "/api/environment/ice/polar/tile/0/0/0.png",
        params={"time": "2025-02-15T12:00:00Z"},
    )
    thickness = client.get(
        "/api/environment/ice/thickness/polar/tile/0/0/0.png",
        params={"time": "2025-02-15T12:00:00Z"},
    )

    assert concentration.status_code == 200
    assert thickness.status_code == 200
    assert concentration.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert thickness.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert concentration.content != thickness.content


def test_bathymetry_query_and_tile_are_available():
    _require_gebco_dataset()
    query = client.get("/api/environment/bathymetry/query", params={"lat": 75, "lon": 0})
    assert query.status_code == 200
    assert query.json()["depth"] == 3709.0
    assert query.json()["source"] == "GEBCO_2026_sub_ice"

    tile = client.get("/api/environment/bathymetry/tiles/2/2/0.png")
    assert tile.status_code == 200
    assert tile.headers["content-type"] == "image/png"
    assert tile.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_bathymetry_safety_uses_vessel_draft_config():
    _require_gebco_dataset()
    response = client.get("/api/environment/bathymetry/safety", params={"lat": 75, "lon": 0})
    assert response.status_code == 200
    assert response.json() == {
        "depth": 3709.0,
        "required_depth": 12.0,
        "safe": True,
        "margin": 3697.0,
    }
