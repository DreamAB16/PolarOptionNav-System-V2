from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from core.contracts import (
    AvailabilityStatus,
    LocalENUFrameRef,
    LocalENUPosition,
    QualityMetadata,
    TimeMetadata,
    WGS84Position,
)
from core.environment.query.models import (
    EnvironmentSample,
    TimeMatchInfo,
    TimeMatchStatus,
)
from core.vessel import IceClass, VesselState
from core.vessel.performance import PerformanceContext


UTC = timezone.utc


def vessel_state(position: WGS84Position, timestamp: datetime) -> VesselState:
    return VesselState(
        position=position,
        timestamp=timestamp,
    )


def environment_sample(position: WGS84Position, valid_time: datetime) -> EnvironmentSample:
    frame = LocalENUFrameRef(
        frame_id="test-frame",
        origin_lat_deg=position.latitude_deg,
        origin_lon_deg=position.longitude_deg,
        crs_or_projection_identifier="Local ENU",
    )
    local_position = LocalENUPosition(frame=frame, x_east_m=0, y_north_m=0)
    return EnvironmentSample(
        position=local_position,
        requested_time=valid_time,
        matched_time=valid_time,
        fields={},
        quality=QualityMetadata(availability=AvailabilityStatus.MISSING),
        availability=AvailabilityStatus.MISSING,
        time_match=TimeMatchInfo(
            requested_time=valid_time,
            matched_time=valid_time,
            offset_seconds=0,
            status=TimeMatchStatus.EXACT,
        ),
    )


def test_context_reuses_vessel_position_and_time_contracts() -> None:
    valid_time = datetime(2026, 1, 1, tzinfo=UTC)
    position = WGS84Position(latitude_deg=80, longitude_deg=10)
    state = vessel_state(position, valid_time)
    time = TimeMetadata(valid_time=valid_time)

    context = PerformanceContext(
        vessel_state=state,
        position=position,
        time=time,
    )

    assert context.vessel_state is state
    assert context.position is position
    assert context.time is time
    assert context.environment is None


def test_context_accepts_pre_resolved_environment_sample() -> None:
    valid_time = datetime(2026, 1, 1, tzinfo=UTC)
    position = WGS84Position(latitude_deg=80, longitude_deg=10)
    state = vessel_state(position, valid_time)
    environment = environment_sample(position, valid_time)

    context = PerformanceContext(
        vessel_state=state,
        position=position,
        time=TimeMetadata(valid_time=valid_time),
        environment=environment,
    )

    assert context.environment is environment


def test_context_optional_and_unknown_values_remain_none() -> None:
    valid_time = datetime(2026, 1, 1, tzinfo=UTC)
    position = WGS84Position(latitude_deg=80, longitude_deg=10)
    context = PerformanceContext(
        vessel_state=vessel_state(position, valid_time),
        position=position,
        time=TimeMetadata(valid_time=valid_time),
    )

    assert context.environment is None
    assert context.vessel_state.heading is None
    assert context.vessel_state.speed_mps is None
    assert context.vessel_state.power_fraction is None
    assert context.vessel_state.draft_m is None
    assert context.time.issue_time is None
    assert context.time.observation_time is None
    assert context.time.ingest_time is None


def test_context_requires_valid_time() -> None:
    valid_time = datetime(2026, 1, 1, tzinfo=UTC)
    position = WGS84Position(latitude_deg=80, longitude_deg=10)
    with pytest.raises(ValidationError):
        PerformanceContext(
            vessel_state=vessel_state(position, valid_time),
            position=position,
            time=TimeMetadata(),
        )


def test_context_time_is_normalized_to_utc() -> None:
    valid_time = datetime(2026, 1, 1, 8, tzinfo=timezone(timedelta(hours=8)))
    position = WGS84Position(latitude_deg=80, longitude_deg=10)
    context = PerformanceContext(
        vessel_state=vessel_state(position, valid_time),
        position=position,
        time=TimeMetadata(valid_time=valid_time),
    )

    assert context.time.valid_time == datetime(2026, 1, 1, tzinfo=UTC)


def test_context_has_no_timestamp_or_performance_methods() -> None:
    assert "timestamp" not in PerformanceContext.model_fields
    for name in (
        "calculate_speed",
        "calculate_resistance",
        "predict_speed",
        "calculate_thrust",
        "calculate_eta",
        "assess_risk",
        "plan_route",
    ):
        assert not hasattr(PerformanceContext, name)
