from datetime import datetime, timedelta, timezone

import pytest

from core.contracts.time import TimeMetadata, available_at_decision_time, data_age, ensure_utc, lead_time, staleness


def test_timezone_aware_values_normalize_to_utc() -> None:
    value = datetime(2025, 1, 1, 8, tzinfo=timezone(timedelta(hours=8)))
    assert ensure_utc(value) == datetime(2025, 1, 1, 0, tzinfo=timezone.utc)
    assert ensure_utc(datetime(2025, 1, 1, 5, tzinfo=timezone(timedelta(hours=-5)))) == datetime(2025, 1, 1, 10, tzinfo=timezone.utc)


def test_naive_datetime_is_rejected_by_core_contract() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ensure_utc(datetime(2025, 1, 1))
    with pytest.raises(ValueError, match="timezone-aware"):
        TimeMetadata(valid_time=datetime(2025, 1, 1))


def test_time_metadata_has_optional_fixed_semantics() -> None:
    metadata = TimeMetadata(issue_time=datetime(2025, 1, 1, 8, tzinfo=timezone(timedelta(hours=8))))
    assert metadata.issue_time == datetime(2025, 1, 1, 0, tzinfo=timezone.utc)
    assert metadata.valid_time is None


def test_time_arithmetic_crosses_calendar_boundaries_without_threshold_policy() -> None:
    issue = datetime(2024, 12, 31, 23, tzinfo=timezone.utc)
    valid = datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
    assert lead_time(valid, issue) == timedelta(hours=2)
    assert data_age(valid, issue) == timedelta(hours=2)
    assert staleness(valid, issue) == timedelta(hours=2)


def test_future_forecast_issue_or_ingest_time_is_not_available_at_decision_time() -> None:
    decision = datetime(2025, 1, 1, 10, tzinfo=timezone.utc)
    assert available_at_decision_time(TimeMetadata(valid_time=decision, issue_time=decision + timedelta(hours=1)), decision) is False
    assert available_at_decision_time(TimeMetadata(valid_time=decision, ingest_time=decision + timedelta(minutes=1)), decision) is False
    assert available_at_decision_time(TimeMetadata(issue_time=decision, ingest_time=decision), decision) is True
    assert available_at_decision_time(TimeMetadata(valid_time=decision), decision) is None
