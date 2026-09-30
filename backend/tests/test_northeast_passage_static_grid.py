from datetime import datetime, timezone

from core.models import Position
from services.planner_service.dnsga3 import DStarLite
from services.planner_service.static_grid import StaticGridRepository, to_planning_lon
from services.planner_service.service import PlannerService


def test_fixed_grid_has_stable_indices_and_nep_clip() -> None:
    grid = StaticGridRepository.load()
    first = grid.nearest_cell(70.0, 70.0)
    second = grid.nearest_cell(70.0, 70.0)
    assert first == second
    assert grid.nearest_cell(50.0, 70.0) is None
    assert grid.contains(89.9, 100.0)
    assert not grid.contains(90.1, 100.0)
    indices, clipped = grid.viewport_indices(70.0, 71.0, 70.0, 72.0)
    assert clipped is not None
    assert clipped["planning_intervals"] == [(70.0, 72.0)]
    assert len(indices) > 0


def test_viewport_outside_nep_returns_no_cells_without_dynamic_sampling() -> None:
    service = PlannerService()
    result = service.get_northern_grid(datetime(2025, 2, 15, 12, tzinfo=timezone.utc), 10, 20, -20, 20)
    assert result["cell_count"] == 0
    assert result["metrics"]["intersection"] is None


def test_planning_region_converts_display_longitudes_across_date_line() -> None:
    grid = StaticGridRepository.load()
    expected_inside = [(77.7962, 112.8972), (70.0, 179.0), (70.0, -179.0), (70.4663, -172.6194), (66.1, -168.976944)]
    assert all(grid.contains(latitude, longitude) for latitude, longitude in expected_inside)
    assert to_planning_lon(-172.6194) == 187.3806
    assert not grid.contains(70.0, -165.0)
    assert not grid.contains(70.0, 20.0)


def test_fixed_grid_and_dstar_are_continuous_across_date_line() -> None:
    service = PlannerService()
    timestamp = datetime(2025, 2, 15, 12, tzinfo=timezone.utc)
    grid = service.northern_grid.global_planning_grid(Position(latitude=70.0, longitude=179.0), Position(latitude=70.0, longitude=-179.0), timestamp)
    path = DStarLite(grid, "distance").plan()
    assert path
    assert any(abs(grid.coordinate(first)[1] - grid.coordinate(second)[1]) > 300.0 for first, second in zip(path, path[1:]))


def test_date_line_viewport_uses_a_continuous_planning_interval() -> None:
    service = PlannerService()
    result = service.get_northern_grid(datetime(2025, 2, 15, 12, tzinfo=timezone.utc), 69, 71, 170, -170)
    assert result["cell_count"] > 0
    assert result["bounds"]["planning_intervals"] == [(170.0, 190.0)]
