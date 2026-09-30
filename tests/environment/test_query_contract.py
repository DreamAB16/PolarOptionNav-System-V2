from datetime import datetime, timezone

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
from core.environment import EnvironmentField, FieldMetadata, GridSpec
from core.environment.query import (
    EnvironmentFieldType,
    EnvironmentQueryRequest,
    EnvironmentSample,
    EnvironmentScale,
    TimeMatchInfo,
    TimeMatchStatus,
)


def _grid() -> GridSpec:
    frame = LocalENUFrameRef(
        frame_id="query-test",
        origin_lat_deg=80,
        origin_lon_deg=10,
        crs_or_projection_identifier="local-enu",
    )
    return GridSpec(
        frame=frame, resolution_m=75, x_min_m=0, y_min_m=0,
        x_max_m=75, y_max_m=75, width_cells=1, height_cells=1,
    )


def _field() -> EnvironmentField:
    return EnvironmentField(
        variable=EnvironmentFieldType.WIND,
        data=None,
        grid=_grid(),
        metadata=FieldMetadata(
            source_id=None,
            time=TimeMetadata(),
            quality=QualityMetadata(availability=AvailabilityStatus.MISSING),
            evidence=EvidenceRecord(status=EvidenceStatus.UNKNOWN),
        ),
    )


def test_query_enums_reuse_environment_contracts() -> None:
    from core.environment.enums import EnvironmentScale as CanonicalScale, EnvironmentVariable

    assert EnvironmentFieldType is EnvironmentVariable
    assert EnvironmentScale is CanonicalScale
    assert set(EnvironmentFieldType) == set(EnvironmentVariable)


def test_request_requires_aware_target_time_and_foundation_position() -> None:
    request = EnvironmentQueryRequest(
        position=WGS84Position(latitude_deg=80, longitude_deg=10),
        target_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        scale=EnvironmentScale.NEAR,
        requested_fields=[EnvironmentFieldType.WIND, EnvironmentFieldType.CURRENT],
    )
    assert request.target_time.tzinfo is not None
    assert isinstance(request.position, WGS84Position)


def test_time_match_info_supports_exact_nearest_and_unavailable() -> None:
    requested = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert TimeMatchInfo(requested_time=requested, matched_time=requested, offset_seconds=0, status=TimeMatchStatus.EXACT)
    assert TimeMatchInfo(requested_time=requested, matched_time=None, offset_seconds=None, status=TimeMatchStatus.UNAVAILABLE)


def test_sample_preserves_unknown_values_as_none_and_unknown_availability() -> None:
    requested = datetime(2026, 1, 1, tzinfo=timezone.utc)
    sample = EnvironmentSample(
        position=LocalENUPosition(frame=_grid().frame, x_east_m=0, y_north_m=0),
        requested_time=requested,
        matched_time=None,
        fields={EnvironmentFieldType.WIND: _field()},
        quality=QualityMetadata(availability=AvailabilityStatus.MISSING),
        availability=AvailabilityStatus.MISSING,
        time_match=TimeMatchInfo(requested_time=requested, status=TimeMatchStatus.UNAVAILABLE),
    )
    assert sample.fields[EnvironmentFieldType.WIND].data is None
    assert sample.availability is AvailabilityStatus.MISSING


def test_query_contract_contains_no_planning_or_risk_types() -> None:
    import core.environment.query as query

    assert not hasattr(query, "Risk")
    assert not hasattr(query, "Planner")
