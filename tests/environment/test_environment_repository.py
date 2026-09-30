from datetime import datetime, timedelta, timezone

from core.contracts import AvailabilityStatus, EvidenceRecord, EvidenceStatus, LocalENUFrameRef, QualityMetadata, TimeMetadata
from core.environment import (
    EnvironmentScale,
    EnvironmentScaleSnapshot,
    EnvironmentVariable,
    EnvironmentSnapshotMetadata,
    FieldMetadata,
    GridSpec,
    WindField,
    WindFieldData,
)
from core.environment.repository import EnvironmentRepository, EnvironmentSnapshotKey


def _snapshot(scale: EnvironmentScale, valid_time: datetime, *, include_wind: bool = True) -> EnvironmentScaleSnapshot:
    frame = LocalENUFrameRef(frame_id="repository", origin_lat_deg=80, origin_lon_deg=10, crs_or_projection_identifier="enu")
    grid = GridSpec(frame=frame, resolution_m=75, x_min_m=0, y_min_m=0, x_max_m=75, y_max_m=75, width_cells=1, height_cells=1)
    fields = {}
    if include_wind:
        fields[EnvironmentVariable.WIND] = WindField(
            data=WindFieldData(wind_east_mps=[[1.0]], wind_north_mps=[[2.0]]),
            grid=grid,
            metadata=FieldMetadata(
                source_id="test",
                representation_resolution_m=75,
                time=TimeMetadata(valid_time=valid_time),
                quality=QualityMetadata(availability=AvailabilityStatus.AVAILABLE),
                evidence=EvidenceRecord(status=EvidenceStatus.SYNTHETIC_MODEL),
            ),
        )
    return EnvironmentScaleSnapshot(
        scale=scale,
        grid=grid,
        fields=fields,
        metadata=EnvironmentSnapshotMetadata(),
        time_context=TimeMetadata(valid_time=valid_time),
    )


def test_snapshot_registration_and_lookup_normalizes_time() -> None:
    repository = EnvironmentRepository()
    valid_time = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    snapshot = _snapshot(EnvironmentScale.NEAR, valid_time)
    repository.register_snapshot(snapshot)
    assert repository.get_snapshot(EnvironmentScale.NEAR, valid_time.astimezone(timezone(timedelta(hours=8)))) is snapshot
    assert EnvironmentSnapshotKey(scale=EnvironmentScale.NEAR, valid_time=valid_time).valid_time == valid_time


def test_repository_supports_multiple_scales_and_times() -> None:
    repository = EnvironmentRepository()
    first = datetime(2026, 1, 1, tzinfo=timezone.utc)
    second = first + timedelta(hours=1)
    snapshots = [_snapshot(scale, time) for scale in EnvironmentScale for time in (first, second)]
    for snapshot in snapshots:
        repository.register_snapshot(snapshot)
    assert all(repository.get_snapshot(scale, time) is not None for scale in EnvironmentScale for time in (first, second))


def test_field_lookup_and_missing_field_return_none() -> None:
    repository = EnvironmentRepository()
    valid_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snapshot = _snapshot(EnvironmentScale.MIDDLE, valid_time)
    repository.register_snapshot(snapshot)
    assert repository.get_field(snapshot, EnvironmentVariable.WIND) is snapshot.fields[EnvironmentVariable.WIND]
    assert repository.get_field(snapshot, EnvironmentVariable.ICE) is None
    assert repository.get_snapshot(EnvironmentScale.REMOTE, valid_time) is None
