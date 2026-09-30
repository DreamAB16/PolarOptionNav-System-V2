from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from services.planner_service.historical_frequency import compute_historical_frequency


def test_same_day_frequency_counts_one_event_per_year_and_uses_cache(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_download(url: str, timeout: float) -> dict[str, object]:
        calls.append(url)
        query = parse_qs(urlparse(url).query)
        if "archive-api" in url:
            return {
                "hourly": {
                    "wind_speed_10m": [12.0, 1.0],
                    "visibility": [2000.0, 500.0],
                    "weather_code": [0, 0],
                }
            }
        return {"hourly": {"wave_height": [5.1, 0.5]}}

    result = compute_historical_frequency(
        datetime(2025, 2, 15, 12, tzinfo=timezone.utc),
        70.0,
        20.0,
        cache_dir=tmp_path,
        downloader=fake_download,
    )

    assert result.hazards["strong_wind"].count == 9
    assert result.hazards["strong_wind"].available_years == 9
    assert result.hazards["strong_wind"].frequency == 1.0
    assert result.hazards["high_wave"].count == 9
    assert result.hazards["high_wave"].frequency == 1.0
    assert result.hazards["high_wave"].threshold == 5.0
    assert result.hazards["fog"].count == 9
    assert result.hazards["fog"].frequency == 1.0
    assert len(calls) == 18

    def fail_if_network(url: str, timeout: float) -> dict[str, object]:
        raise AssertionError("cached history should not access the network")

    cached = compute_historical_frequency(
        datetime(2025, 2, 15, 12, tzinfo=timezone.utc),
        70.0,
        20.0,
        cache_dir=tmp_path,
        downloader=fail_if_network,
    )
    assert cached.as_dict() == result.as_dict()


def test_missing_wave_observations_are_not_zero_risk(tmp_path: Path) -> None:
    def fake_download(url: str, timeout: float) -> dict[str, object]:
        if "archive-api" in url:
            return {"hourly": {"wind_speed_10m": [5.0], "visibility": [10000.0]}}
        return {"hourly": {"wave_height": [None, None]}}

    result = compute_historical_frequency(
        datetime(2025, 2, 15, tzinfo=timezone.utc),
        80.0,
        0.0,
        cache_dir=tmp_path,
        downloader=fake_download,
    )

    wave = result.hazards["high_wave"]
    assert wave.count == 0
    assert wave.available_years == 0
    assert wave.frequency is None
