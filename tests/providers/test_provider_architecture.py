from datetime import datetime, timezone

import pytest

from core.contracts import (
    AvailabilityStatus,
    EvidenceRecord,
    EvidenceStatus,
    LocalENUFrameRef,
    LocalENUPosition,
    QualityMetadata,
    TimeMetadata,
    WGS84Position,
)
from core.environment import EnvironmentField, FieldMetadata
from core.providers import BaseProviderAdapter
from core.providers.common import (
    build_field_metadata,
    open_netcdf,
    resolve_lat_lon_names,
    resolve_variable,
    resolve_variable_name,
    wgs84_to_local_enu,
)


def test_base_provider_adapter_exposes_only_the_small_contract() -> None:
    assert BaseProviderAdapter.__abstractmethods__ == {
        "load",
        "read_metadata",
        "convert_to_environment_field",
    }


def test_common_provider_helpers_are_importable() -> None:
    assert callable(open_netcdf)
    assert callable(resolve_variable_name)
    assert callable(resolve_variable)
    assert callable(resolve_lat_lon_names)
    assert callable(wgs84_to_local_enu)
    assert callable(build_field_metadata)


def test_variable_alias_resolution_is_generic() -> None:
    variables = {"LAT": object(), "longitude": object(), "u10": object()}
    assert resolve_lat_lon_names(variables) == ("LAT", "longitude")
    assert resolve_variable_name(variables, ("latitude", "lat")) == "LAT"
    assert resolve_variable(variables, ("U10",)) is variables["u10"]
    assert resolve_variable_name(variables, ("depth", "elevation")) is None


def test_metadata_helper_reuses_environment_and_foundation_models() -> None:
    time = TimeMetadata(valid_time=datetime(2026, 1, 1, tzinfo=timezone.utc))
    quality = QualityMetadata(availability=AvailabilityStatus.AVAILABLE)
    evidence = EvidenceRecord(status=EvidenceStatus.UNKNOWN)
    metadata = build_field_metadata(
        source_id=None,
        native_resolution_m=None,
        representation_resolution_m=75,
        time=time,
        quality=quality,
        evidence=evidence,
    )

    assert isinstance(metadata, FieldMetadata)
    assert metadata.time is time
    assert metadata.quality is quality
    assert metadata.evidence is evidence
    assert metadata.availability is AvailabilityStatus.AVAILABLE


def test_coordinate_conversion_reuses_foundation_position_types() -> None:
    frame = LocalENUFrameRef(
        frame_id="origin",
        origin_lat_deg=70,
        origin_lon_deg=30,
        crs_or_projection_identifier="local-enu",
    )
    origin = WGS84Position(latitude_deg=70, longitude_deg=30)
    result = wgs84_to_local_enu(origin, frame)
    assert isinstance(result, LocalENUPosition)
    assert result.frame is frame
    assert result.x_east_m == pytest.approx(0, abs=1e-8)
    assert result.y_north_m == pytest.approx(0, abs=1e-8)


def test_coordinate_conversion_uses_east_and_north_axes() -> None:
    frame = LocalENUFrameRef(
        frame_id="equator",
        origin_lat_deg=0,
        origin_lon_deg=0,
        crs_or_projection_identifier="local-enu",
    )
    east = wgs84_to_local_enu(WGS84Position(latitude_deg=0, longitude_deg=0.001), frame)
    north = wgs84_to_local_enu(WGS84Position(latitude_deg=0.001, longitude_deg=0), frame)
    assert east.x_east_m > 100
    assert abs(east.y_north_m) < 1e-5
    assert north.y_north_m > 100
    assert abs(north.x_east_m) < 1e-5


def test_provider_layer_has_no_duplicate_contracts_or_planning_logic() -> None:
    import core.providers as providers
    import core.providers.common as common

    assert FieldMetadata.__module__ == "core.environment.metadata"
    assert TimeMetadata.__module__ == "core.contracts.time"
    assert QualityMetadata.__module__ == "core.contracts.quality"
    assert LocalENUPosition.__module__ == "core.contracts.coordinates"
    assert not hasattr(common, "ProviderMetadata")
    assert not any(hasattr(providers, name) for name in ("Risk", "Planner", "Route"))
