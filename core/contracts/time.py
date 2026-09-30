"""Strict timezone-aware UTC time metadata and arithmetic."""

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict, field_validator


def ensure_utc(value: datetime) -> datetime:
    """Reject naive datetimes and normalize aware values to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("V5 core datetimes must be timezone-aware; naive datetime rejected")
    return value.astimezone(timezone.utc)


class TimeMetadata(BaseModel):
    """Optional source timestamps with fixed V5 meanings, all stored in UTC."""

    model_config = ConfigDict(frozen=True)

    source_time: datetime | None = None
    issue_time: datetime | None = None
    valid_time: datetime | None = None
    observation_time: datetime | None = None
    ingest_time: datetime | None = None

    @field_validator("source_time", "issue_time", "valid_time", "observation_time", "ingest_time")
    @classmethod
    def normalize_datetime(cls, value: datetime | None) -> datetime | None:
        return None if value is None else ensure_utc(value)


def available_at_decision_time(metadata: TimeMetadata, decision_time: datetime) -> bool | None:
    """Return whether publication/ingest evidence permits use at a decision time.

    ``None`` means neither issue nor ingest time can establish availability.
    This is a foundation rule only; it does not select a forecast, fuse belief,
    or apply data-age policy.
    """

    decision_utc = ensure_utc(decision_time)
    known_times = (metadata.issue_time, metadata.ingest_time)
    if all(value is None for value in known_times):
        return None
    return all(value is None or value <= decision_utc for value in known_times)


def _delta(later: datetime, earlier: datetime) -> timedelta:
    return ensure_utc(later) - ensure_utc(earlier)


def lead_time(valid_time: datetime, issue_time: datetime) -> timedelta:
    return _delta(valid_time, issue_time)


def data_age(simulation_time: datetime, reference_time: datetime) -> timedelta:
    return _delta(simulation_time, reference_time)


def staleness(simulation_time: datetime, valid_time: datetime) -> timedelta:
    return _delta(simulation_time, valid_time)
