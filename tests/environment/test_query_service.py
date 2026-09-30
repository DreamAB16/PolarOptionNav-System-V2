from datetime import datetime, timedelta, timezone

from core.contracts import AvailabilityStatus, EvidenceRecord, EvidenceStatus, LocalENUFrameRef, QualityMetadata, TimeMetadata, WGS84Position
from core.environment import EnvironmentScale, EnvironmentScaleSnapshot, EnvironmentSnapshotMetadata, EnvironmentVariable, FieldMetadata, GridSpec, WindField, WindFieldData
from core.environment.query import EnvironmentQueryRequest, EnvironmentQueryService, ScaleResolver, SpatialResolver, TimeResolver
from core.environment.repository import EnvironmentRepository


def _setup():
    frame = LocalENUFrameRef(frame_id="service", origin_lat_deg=80, origin_lon_deg=10, crs_or_projection_identifier="enu")
    grid = GridSpec(frame=frame, resolution_m=100, x_min_m=-5000, y_min_m=-5000, x_max_m=5000, y_max_m=5000, width_cells=100, height_cells=100)
    valid = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    field = WindField(data=WindFieldData(wind_east_mps=[[1]], wind_north_mps=[[2]]), grid=grid, metadata=FieldMetadata(source_id="test", representation_resolution_m=100, time=TimeMetadata(valid_time=valid), quality=QualityMetadata(availability=AvailabilityStatus.AVAILABLE), evidence=EvidenceRecord(status=EvidenceStatus.SYNTHETIC_MODEL)))
    snapshot = EnvironmentScaleSnapshot(scale=EnvironmentScale.NEAR, grid=grid, fields={EnvironmentVariable.WIND: field}, metadata=EnvironmentSnapshotMetadata(), time_context=TimeMetadata(valid_time=valid))
    repository = EnvironmentRepository()
    repository.register_snapshot(snapshot)
    service = EnvironmentQueryService(repository, ScaleResolver(), TimeResolver(), {EnvironmentScale.NEAR: SpatialResolver(grid)})
    return service, valid


def test_query_service_runs_full_flow_and_preserves_requested_fields():
    service, valid = _setup()
    result = service.query(EnvironmentQueryRequest(position=WGS84Position(latitude_deg=80, longitude_deg=10), target_time=valid, scale=EnvironmentScale.NEAR, requested_fields=[EnvironmentVariable.WIND, EnvironmentVariable.ICE]))
    assert result.availability is AvailabilityStatus.MISSING
    assert result.fields[EnvironmentVariable.WIND] is not None
    assert result.fields[EnvironmentVariable.ICE] is None
    assert result.time_match.status.value == "EXACT"


def test_query_service_reports_time_and_space_unknown():
    service, valid = _setup()
    late = service.query(EnvironmentQueryRequest(position=WGS84Position(latitude_deg=80, longitude_deg=10), target_time=valid + timedelta(days=1), scale=EnvironmentScale.NEAR, requested_fields=[EnvironmentVariable.WIND]))
    assert late.availability is AvailabilityStatus.AVAILABLE
    assert late.time_match.status.value == "NEAREST"
    far = service.query(EnvironmentQueryRequest(position=WGS84Position(latitude_deg=0, longitude_deg=0), target_time=valid, scale=EnvironmentScale.NEAR, requested_fields=[EnvironmentVariable.WIND]))
    assert far.availability is AvailabilityStatus.MISSING
