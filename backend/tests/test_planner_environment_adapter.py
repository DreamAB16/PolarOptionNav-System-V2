from datetime import datetime, timezone

from core.models import Position
from services.planner_service.environment_adapter import PlannerEnvironmentAdapter


class MissingEnvironment:
    def query_complete_environment(self, *args, **kwargs):
        raise LookupError("outside provider coverage")


def test_gap_fill_is_deterministic_and_exposes_provenance():
    adapter = PlannerEnvironmentAdapter(MissingEnvironment())
    position = Position(latitude=12.5, longitude=45.0)
    timestamp = datetime(2025, 2, 15, 12, tzinfo=timezone.utc)
    first = adapter.sample(position, timestamp)
    second = adapter.sample(position, timestamp)
    assert first.state.model_dump() == second.state.model_dump()
    assert set(first.quality) == {"depth", "ice", "wind", "current", "wave"}
    assert all(value == "synthetic" for value in first.quality.values())
    assert all(source == adapter.source_name for source in first.sources.values())
    assert first.state.wave.height is not None
    assert first.state.wind.speed is not None


def test_frequency_varies_by_cell_but_is_bounded():
    adapter = PlannerEnvironmentAdapter(MissingEnvironment())
    timestamp = datetime(2025, 2, 15, 12, tzinfo=timezone.utc)
    left = adapter.frequency(Position(latitude=0.0, longitude=0.0), timestamp)
    right = adapter.frequency(Position(latitude=40.0, longitude=90.0), timestamp)
    assert left != right
    assert all(0.0 <= value <= 1.0 for value in left.values())
    assert all(0.0 <= value <= 1.0 for value in right.values())
