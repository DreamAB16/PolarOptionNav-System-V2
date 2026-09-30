"""Download and cache eight-year same-day weather occurrence frequencies.

The planner is intentionally a single-day experiment.  Historical data is not
mixed into the planning field; it is reduced to one regional frequency for
each hazard and used as a conservative risk prior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from core.config.environment_config import get_environment_root


WIND_THRESHOLD_MS = 11.7
WAVE_THRESHOLD_M = 5.0
FOG_VISIBILITY_THRESHOLD_M = 1000.0
FOG_WEATHER_CODES = frozenset({45, 48})
# The reproducible experiment window: 2017 through 2025, inclusive (nine
# same-calendar-day samples; the target day is supplied by the timestamp).
HISTORICAL_START_YEAR = 2017
HISTORICAL_END_YEAR = 2025
HISTORICAL_YEARS = HISTORICAL_END_YEAR - HISTORICAL_START_YEAR + 1
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"


@dataclass(frozen=True, slots=True)
class HazardFrequency:
    """Occurrence count and denominator for one threshold hazard."""

    count: int
    available_years: int
    frequency: float | None
    threshold: float
    unit: str

    def as_dict(self) -> dict[str, object]:
        return {
            "count": self.count,
            "available_years": self.available_years,
            "frequency": self.frequency,
            "threshold": self.threshold,
            "unit": self.unit,
        }


@dataclass(frozen=True, slots=True)
class HistoricalFrequencyResult:
    """Frequency reduction plus provenance and any per-year download errors."""

    hazards: dict[str, HazardFrequency]
    requested_years: list[int]
    available_years: list[int]
    source: str
    latitude: float
    longitude: float
    errors: list[str]
    cache_dir: str

    def as_dict(self) -> dict[str, object]:
        return {
            "hazards": {name: value.as_dict() for name, value in self.hazards.items()},
            "requested_years": self.requested_years,
            "available_years": self.available_years,
            "source": self.source,
            "representative_point": {
                "latitude": self.latitude,
                "longitude": self.longitude,
            },
            "errors": self.errors,
            "cache_dir": self.cache_dir,
        }


def default_cache_dir() -> Path:
    """Keep downloaded history alongside the configured PolarData repository."""

    return get_environment_root() / "planner" / "historical_frequency"


def _request_json(url: str, timeout: float) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": "PolarOptionNav/2.0 planner"})
    with urlopen(request, timeout=timeout) as response:  # nosec B310: fixed HTTPS endpoints
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Open-Meteo returned a non-object response")
    if value.get("error"):
        raise ValueError(str(value.get("reason", "Open-Meteo request failed")))
    return value


def _cache_path(cache_dir: Path, prefix: str, latitude: float, longitude: float, day: date) -> Path:
    return cache_dir / f"{prefix}_{latitude:.4f}_{longitude:.4f}_{day:%Y%m%d}.json"


def _load_or_download(
    url: str,
    path: Path,
    timeout: float,
    downloader: Callable[[str, float], dict[str, object]],
) -> dict[str, object]:
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return value
        except (OSError, json.JSONDecodeError):
            # A partial cache is discarded and refreshed below.
            pass
    value = downloader(url, timeout)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=True), encoding="utf-8")
    temporary.replace(path)
    return value


def _hourly_values(payload: dict[str, object], name: str) -> list[float | int]:
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        return []
    values = hourly.get(name)
    if not isinstance(values, list):
        return []
    result: list[float | int] = []
    for value in values:
        if isinstance(value, (int, float)) and value == value:
            result.append(value)
    return result


def _has_threshold(values: list[float | int], threshold: float) -> bool:
    return any(float(value) >= threshold for value in values)


def _has_fog(payload: dict[str, object]) -> bool | None:
    visibility = _hourly_values(payload, "visibility")
    weather_codes = _hourly_values(payload, "weather_code")
    if visibility:
        return any(float(value) < FOG_VISIBILITY_THRESHOLD_M for value in visibility)
    if weather_codes:
        return any(int(value) in FOG_WEATHER_CODES for value in weather_codes)
    return None


def _date_for_year(timestamp: datetime, year: int) -> date | None:
    try:
        return date(year, timestamp.month, timestamp.day)
    except ValueError:
        # February 29 has no same-day observation in non-leap years.
        return None


def compute_historical_frequency(
    timestamp: datetime,
    latitude: float,
    longitude: float,
    *,
    years: int | None = None,
    start_year: int = HISTORICAL_START_YEAR,
    end_year: int = HISTORICAL_END_YEAR,
    cache_dir: Path | None = None,
    timeout: float = 20.0,
    downloader: Callable[[str, float], dict[str, object]] | None = None,
) -> HistoricalFrequencyResult:
    """Fetch same-calendar-day records and reduce them to event frequencies.

    A year contributes one occurrence when *any* hourly observation on that
    day crosses the hazard threshold.  Each hazard has its own denominator so
    missing marine data does not silently become a zero-wave year.
    """

    # ``years`` remains as a compatibility override for callers that want a
    # rolling window.  The experiment default is the explicit 2017-2025 range.
    if years is not None:
        if years < 1 or years > 20:
            raise ValueError("years must be between 1 and 20")
        start_year = timestamp.year - years + 1
        end_year = timestamp.year
    if start_year > end_year or end_year - start_year + 1 > 20:
        raise ValueError("start_year/end_year must define 1-20 years")
    latitude = float(latitude)
    longitude = float(longitude)
    cache = cache_dir or default_cache_dir()
    fetch = downloader or _request_json
    requested_years = list(range(start_year, end_year + 1))
    wind_count = wave_count = fog_count = 0
    wind_available = wave_available = fog_available = 0
    available_years: set[int] = set()
    errors: list[str] = []

    for year in requested_years:
        day = _date_for_year(timestamp, year)
        if day is None:
            continue
        query = {
            "latitude": f"{latitude:.4f}",
            "longitude": f"{longitude:.4f}",
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
            "hourly": "wind_speed_10m,visibility,weather_code",
            "wind_speed_unit": "ms",
            "timezone": "UTC",
        }
        archive_path = _cache_path(cache, "archive", latitude, longitude, day)
        archive: dict[str, object] | None = None
        try:
            archive = _load_or_download(
                f"{ARCHIVE_URL}?{urlencode(query)}", archive_path, timeout, fetch
            )
            wind_values = _hourly_values(archive, "wind_speed_10m")
            if wind_values:
                wind_available += 1
                wind_count += int(_has_threshold(wind_values, WIND_THRESHOLD_MS))
            fog_event = _has_fog(archive)
            if fog_event is not None:
                fog_available += 1
                fog_count += int(fog_event)
            if wind_values or fog_event is not None:
                available_years.add(year)
        except (OSError, ValueError, TimeoutError, json.JSONDecodeError) as error:
            errors.append(f"{year} archive: {error}")

        marine_query = {
            "latitude": f"{latitude:.4f}",
            "longitude": f"{longitude:.4f}",
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
            "hourly": "wave_height",
            "timezone": "UTC",
        }
        marine_path = _cache_path(cache, "marine", latitude, longitude, day)
        try:
            marine = _load_or_download(
                f"{MARINE_URL}?{urlencode(marine_query)}", marine_path, timeout, fetch
            )
            wave_values = _hourly_values(marine, "wave_height")
            if wave_values:
                wave_available += 1
                wave_count += int(_has_threshold(wave_values, WAVE_THRESHOLD_M))
                available_years.add(year)
        except (OSError, ValueError, TimeoutError, json.JSONDecodeError) as error:
            errors.append(f"{year} marine: {error}")

    def _stats(count: int, denominator: int, threshold: float, unit: str) -> HazardFrequency:
        return HazardFrequency(
            count=count,
            available_years=denominator,
            frequency=(count / denominator) if denominator else None,
            threshold=threshold,
            unit=unit,
        )

    return HistoricalFrequencyResult(
        hazards={
            "strong_wind": _stats(wind_count, wind_available, WIND_THRESHOLD_MS, "m/s"),
            "high_wave": _stats(wave_count, wave_available, WAVE_THRESHOLD_M, "m"),
            "fog": _stats(fog_count, fog_available, FOG_VISIBILITY_THRESHOLD_M, "m_visibility"),
        },
        requested_years=requested_years,
        available_years=sorted(available_years),
        source="Open-Meteo Archive + Open-Meteo Marine",
        latitude=latitude,
        longitude=longitude,
        errors=errors,
        cache_dir=str(cache),
    )


__all__ = [
    "FOG_VISIBILITY_THRESHOLD_M",
    "HISTORICAL_YEARS",
    "HistoricalFrequencyResult",
    "HazardFrequency",
    "WAVE_THRESHOLD_M",
    "WIND_THRESHOLD_MS",
    "compute_historical_frequency",
]
