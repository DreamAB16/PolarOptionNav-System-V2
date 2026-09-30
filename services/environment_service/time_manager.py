"""Clock ownership for time-aware environment requests.

The manager is deliberately independent of data providers: it supplies a UTC
instant, while each provider decides how to resolve that instant against its
own forecast or observation catalogue.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Literal

from core.models import EnvironmentQuery, EnvironmentTimeState


DEFAULT_SIMULATION_TIME = datetime(2025, 2, 15, 12, tzinfo=timezone.utc)
EnvironmentScenario = Literal["winter", "summer"]
SCENARIO_RANGES: dict[EnvironmentScenario, tuple[datetime, datetime]] = {
    "winter": (
        datetime(2025, 2, 8, 0, tzinfo=timezone.utc),
        datetime(2025, 2, 22, 23, tzinfo=timezone.utc),
    ),
    "summer": (
        datetime(2025, 8, 8, 0, tzinfo=timezone.utc),
        datetime(2025, 8, 22, 23, tzinfo=timezone.utc),
    ),
}


def _utc(value: datetime) -> datetime:
    """Interpret naive inputs as UTC and normalize aware inputs to UTC."""

    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class EnvironmentTimeManager:
    """Manage simulation time, forecast reference time and fixed time step."""

    def __init__(
        self,
        simulation_time: datetime = DEFAULT_SIMULATION_TIME,
        forecast_time: datetime | None = None,
        time_step: timedelta = timedelta(hours=1),
        scenario: EnvironmentScenario | None = None,
    ) -> None:
        if time_step.total_seconds() <= 0:
            raise ValueError("time_step must be positive")
        self._lock = RLock()
        self._simulation_time = _utc(simulation_time)
        self._forecast_time = _utc(forecast_time) if forecast_time is not None else self._simulation_time
        self._time_step = time_step
        self._scenario = scenario or self._scenario_for(self._simulation_time)
        self._is_playing = False
        self._validate_in_active_range(self._simulation_time)

    @property
    def simulation_time(self) -> datetime:
        return self.get_time()

    @property
    def scenario(self) -> EnvironmentScenario:
        return self._scenario

    def get_time(self) -> datetime:
        with self._lock:
            return self._simulation_time

    def set_time(self, value: datetime) -> datetime:
        """Set one UTC instant and select the scenario that contains it."""

        selected = _utc(value)
        scenario = self._scenario_for(selected)
        with self._lock:
            self._scenario = scenario
            self._simulation_time = selected
            return self._simulation_time

    def set_scenario(self, scenario: EnvironmentScenario) -> datetime:
        """Switch winter/summer playback and reset to its first available hour."""

        if scenario not in SCENARIO_RANGES:
            raise ValueError(f"Unknown environment scenario: {scenario}")
        with self._lock:
            self._scenario = scenario
            self._simulation_time = SCENARIO_RANGES[scenario][0]
            return self._simulation_time

    def play(self) -> None:
        with self._lock:
            self._is_playing = True

    def pause(self) -> None:
        with self._lock:
            self._is_playing = False

    def resolve_timestamp(self, timestamp: datetime | None = None) -> datetime:
        """Return an explicit request instant or the current simulation instant."""

        return _utc(timestamp) if timestamp is not None else self.get_time()

    def make_query(self, latitude: float, longitude: float, timestamp: datetime | None = None) -> EnvironmentQuery:
        """Build the unified provider query object using the managed clock by default."""

        return EnvironmentQuery(
            latitude=latitude,
            longitude=longitude,
            timestamp=self.resolve_timestamp(timestamp),
        )

    def advance(self, steps: int = 1) -> datetime:
        """Move by integral time steps, clamped to the active scenario range."""

        with self._lock:
            start, end = SCENARIO_RANGES[self._scenario]
            candidate = self._simulation_time + self._time_step * steps
            self._simulation_time = min(end, max(start, candidate))
            if self._simulation_time == end and steps > 0:
                self._is_playing = False
            return self._simulation_time

    def next(self) -> datetime:
        return self.advance(1)

    def previous(self) -> datetime:
        return self.advance(-1)

    def state(self) -> EnvironmentTimeState:
        """Return frontend/API-safe clock metadata."""

        with self._lock:
            start, end = SCENARIO_RANGES[self._scenario]
            return EnvironmentTimeState(
                simulation_time=self._simulation_time,
                forecast_time=self._forecast_time,
                time_step_seconds=int(self._time_step.total_seconds()),
                scenario=self._scenario,
                range_start=start,
                range_end=end,
                is_playing=self._is_playing,
            )

    def _validate_in_active_range(self, value: datetime) -> None:
        start, end = SCENARIO_RANGES[self._scenario]
        if not start <= value <= end:
            raise ValueError(f"simulation_time is outside the {self._scenario} scenario range")

    @staticmethod
    def _scenario_for(value: datetime) -> EnvironmentScenario:
        for scenario, (start, end) in SCENARIO_RANGES.items():
            if start <= value <= end:
                return scenario
        raise ValueError("Environment time is outside the configured winter/summer ranges")
