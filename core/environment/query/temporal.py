"""Deterministic exact/nearest time matching for environment queries."""

from datetime import datetime

from core.contracts import ensure_utc

from .models import TimeMatchInfo, TimeMatchStatus


class TimeResolver:
    def resolve(self, requested_time: datetime, available_times: list[datetime] | tuple[datetime, ...]) -> TimeMatchInfo:
        requested = ensure_utc(requested_time)
        normalized = sorted({ensure_utc(value) for value in available_times})
        if not normalized:
            return TimeMatchInfo(requested_time=requested, status=TimeMatchStatus.UNAVAILABLE)
        matched = min(normalized, key=lambda value: (abs((value - requested).total_seconds()), value))
        offset = abs((matched - requested).total_seconds())
        status = TimeMatchStatus.EXACT if offset == 0 else TimeMatchStatus.NEAREST
        return TimeMatchInfo(
            requested_time=requested,
            matched_time=matched,
            offset_seconds=offset,
            status=status,
        )


__all__ = ["TimeResolver"]
