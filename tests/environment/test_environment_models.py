from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from core.contracts import (
    AvailabilityStatus,
    EvidenceRecord,
    EvidenceStatus,
    LocalENUFrameRef,
    LocalENUPosition,
    QualityMetadata,
    TimeMetadata,
)
from core.environment import (
    ENVIRONMENT_SCALE_SPECS,
    EnvironmentField,
    EnvironmentSample,
    EnvironmentScale,
    EnvironmentScaleSnapshot,
    EnvironmentSnapshotMetadata,
    EnvironmentVariable,
    FieldMetadata,
    GridSpec,
    MultiScaleEnvironmentState,
)


@pytest.fixture
def frame() -> LocalENUFrameRef:
    return LocalENUFrameRef(
        frame_id="test-enu",
        origin_lat_deg=80,
        origin_lon_deg=10,
        crs_or_projection_identifier="local-tangent-plane",
    )


@pytest.fixture
def grid(frame: LocalENUFrameRef) -> GridSpec:
    return GridSpec(
        frame=frame,
        resolution_m=75,
        x_min_m=-150,
        y_min_m=-75,
        x_max_m=150,
        y_max_m=75,
        width_cells=4,
        height_cells=2,
    )


@pytest.fixture
def field_metadata() -> FieldMetadata:
    return FieldMetadata(
        source_id=None,
        native_resolution_m=None,
        representation_resolution_m=75,
        time=TimeMetadata(),
        quality=QualityMetadata(availability=AvailabilityStatus.MISSING),
        evidence=EvidenceRecord(status=EvidenceStatus.UNKNOWN),
    )


def _snapshot(scale: EnvironmentScale, grid: GridSpec) -> EnvironmentScaleSnapshot:
    return EnvironmentScaleSnapshot(
        scale=scale,
        grid=grid,
        fields={},
        metadata=EnvironmentSnapshotMetadata(),
        time_context=TimeMetadata(valid_time=datetime(2026, 1, 1, tzinfo=timezone.utc)),
    )


def test_three_environment_scales_are_defined() -> None:
    assert set(ENVIRONMENT_SCALE_SPECS) == {
        EnvironmentScale.NEAR,
        EnvironmentScale.MIDDLE,
        EnvironmentScale.REMOTE,
    }


@pytest.mark.parametrize(
    ("scale", "range_nm", "resolution_m", "refresh_s"),
    [
        (EnvironmentScale.NEAR, (0, 3), 75, (1, 5)),
        (EnvironmentScale.MIDDLE, (2, 15), 250, (300, 600)),
        (EnvironmentScale.REMOTE, (12, 50), 1000, (1800, 3600)),
    ],
)
def test_scale_targets(scale, range_nm, resolution_m, refresh_s) -> None:
    spec = ENVIRONMENT_SCALE_SPECS[scale]
    assert (spec.range_min_nm, spec.range_max_nm) == range_nm
    assert spec.representation_resolution_m == resolution_m
    assert (spec.refresh_min_s, spec.refresh_max_s) == refresh_s


def test_grid_spec_reuses_local_enu_and_si_semantics(grid: GridSpec) -> None:
    assert grid.frame.frame_id == "test-enu"
    assert grid.resolution_m == 75
    assert (grid.x_max_m - grid.x_min_m) == grid.width_cells * grid.resolution_m
    assert (grid.y_max_m - grid.y_min_m) == grid.height_cells * grid.resolution_m


def test_grid_rejects_extent_size_mismatch(frame: LocalENUFrameRef) -> None:
    with pytest.raises(ValidationError):
        GridSpec(
            frame=frame,
            resolution_m=75,
            x_min_m=0,
            y_min_m=0,
            x_max_m=100,
            y_max_m=75,
            width_cells=2,
            height_cells=1,
        )


def test_field_metadata_reuses_foundation_contracts(field_metadata: FieldMetadata) -> None:
    assert isinstance(field_metadata.time, TimeMetadata)
    assert isinstance(field_metadata.quality, QualityMetadata)
    assert isinstance(field_metadata.evidence, EvidenceRecord)
    assert field_metadata.availability is AvailabilityStatus.MISSING


def test_unknown_values_remain_none(
    grid: GridSpec, field_metadata: FieldMetadata, frame: LocalENUFrameRef
) -> None:
    field = EnvironmentField(
        variable=EnvironmentVariable.WIND,
        data=None,
        grid=grid,
        metadata=field_metadata,
    )
    sample = EnvironmentSample(
        position=LocalENUPosition(frame=frame, x_east_m=0, y_north_m=0),
        time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        variable=EnvironmentVariable.WIND,
        value=None,
        metadata=field_metadata,
    )
    assert field.data is None
    assert sample.value is None


def test_environment_scale_snapshot_can_be_composed(grid: GridSpec) -> None:
    snapshot = _snapshot(EnvironmentScale.NEAR, grid)
    assert snapshot.scale is EnvironmentScale.NEAR
    assert snapshot.grid == grid
    assert snapshot.fields == {}


def test_multiscale_state_requires_all_correctly_typed_scales(grid: GridSpec) -> None:
    state = MultiScaleEnvironmentState(
        near=_snapshot(EnvironmentScale.NEAR, grid),
        middle=_snapshot(EnvironmentScale.MIDDLE, grid),
        remote=_snapshot(EnvironmentScale.REMOTE, grid),
    )
    assert state.near.scale is EnvironmentScale.NEAR
    assert state.middle.scale is EnvironmentScale.MIDDLE
    assert state.remote.scale is EnvironmentScale.REMOTE


def test_environment_contract_does_not_export_risk_or_planner() -> None:
    import core.environment as environment

    assert not hasattr(environment, "Risk")
    assert not hasattr(environment, "Planner")
