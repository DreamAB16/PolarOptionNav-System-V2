from datetime import datetime, timedelta, timezone

import pytest

from core.contracts import LocalENUFrameRef, LocalENUPosition
from core.environment import GridSpec
from core.environment.query import (
    EnvironmentScale,
    GridCellIndex,
    ScaleResolver,
    SpatialResolver,
    TimeMatchStatus,
    TimeResolver,
)


@pytest.fixture
def grid() -> GridSpec:
    frame = LocalENUFrameRef(frame_id="resolver", origin_lat_deg=80, origin_lon_deg=10, crs_or_projection_identifier="enu")
    return GridSpec(frame=frame, resolution_m=10, x_min_m=0, y_min_m=0, x_max_m=30, y_max_m=20, width_cells=3, height_cells=2)


def test_spatial_resolver_uses_nearest_cell(grid: GridSpec) -> None:
    position = LocalENUPosition(frame=grid.frame, x_east_m=14, y_north_m=6)
    result = SpatialResolver(grid).resolve(position)
    assert isinstance(result, GridCellIndex)
    assert (result.row, result.column) == (0, 1)
    assert result.distance_to_cell_center == pytest.approx(2**0.5)


def test_spatial_resolver_returns_unavailable_outside_grid(grid: GridSpec) -> None:
    position = LocalENUPosition(frame=grid.frame, x_east_m=30, y_north_m=5)
    assert SpatialResolver(grid).resolve(position) is None


def test_time_resolver_exact_and_nearest() -> None:
    requested = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    available = [requested - timedelta(hours=1), requested, requested + timedelta(hours=1)]
    resolver = TimeResolver()
    assert resolver.resolve(requested, available).status is TimeMatchStatus.EXACT
    nearest = resolver.resolve(requested + timedelta(minutes=40), available)
    assert nearest.status is TimeMatchStatus.NEAREST
    assert nearest.matched_time == requested + timedelta(hours=1)


def test_time_resolver_unavailable_and_rejects_naive() -> None:
    requested = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert TimeResolver().resolve(requested, []).status is TimeMatchStatus.UNAVAILABLE
    with pytest.raises(ValueError, match="timezone-aware"):
        TimeResolver().resolve(datetime(2026, 1, 1), [])


def test_scale_resolver_requires_supported_explicit_scale() -> None:
    resolver = ScaleResolver()
    assert resolver.resolve(EnvironmentScale.NEAR) is EnvironmentScale.NEAR
    assert resolver.resolve("remote") is EnvironmentScale.REMOTE
    with pytest.raises(ValueError, match="Unsupported environment scale"):
        resolver.resolve("invalid")
