"""Fault-isolated point aggregation for all registered environment providers."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable
from datetime import datetime
from math import hypot
from threading import RLock

from core.models import (
    BathymetryState,
    CurrentState,
    EnvironmentCurrentState,
    EnvironmentIceState,
    EnvironmentSources,
    EnvironmentState,
    EnvironmentVector,
    EnvironmentWaveState,
    EnvironmentWindState,
    Position,
    SeaIceState,
    WaveState,
    WindState,
)

from .providers import EnvironmentProvider
from .time_manager import EnvironmentTimeManager


class EnvironmentQueryService:
    """Return a complete environment snapshot without coupling the providers.

    Providers remain responsible for their own temporal matching, coordinate
    transforms and interpolation. A failure in one component is represented by
    ``available=false`` and does not discard the remaining observations.
    """

    def __init__(
        self,
        providers: Iterable[EnvironmentProvider],
        time_manager: EnvironmentTimeManager,
        *,
        cache_size: int = 1000,
        coordinate_precision: int = 5,
    ) -> None:
        if cache_size <= 0:
            raise ValueError("cache_size must be positive")
        self._providers = providers
        self._time_manager = time_manager
        self._cache_size = cache_size
        self._coordinate_precision = coordinate_precision
        self._cache: OrderedDict[tuple[float, float, datetime], EnvironmentState] = OrderedDict()
        self._cache_lock = RLock()

    def query(self, latitude: float, longitude: float, timestamp: datetime) -> EnvironmentState:
        """Query all five sources at one validated WGS84 position and UTC time."""

        position = Position(latitude=latitude, longitude=longitude)
        requested_time = self._time_manager.resolve_timestamp(timestamp)
        key = (
            round(position.latitude, self._coordinate_precision),
            round(position.longitude, self._coordinate_precision),
            requested_time,
        )
        cached = self._cache_get(key)
        if cached is not None:
            # Cached values represent the rounded sampling location, but the
            # response must still echo the caller's exact WGS84 coordinate.
            cached.latitude = position.latitude
            cached.longitude = position.longitude
            return cached

        bathymetry_provider = self._provider("bathymetry")
        ice_provider = self._provider("ice")
        wind_provider = self._provider("wind")
        current_provider = self._provider("current")
        wave_provider = self._provider("wave")

        depth: float | None = None
        bathymetry_source = self._source(bathymetry_provider, "bathymetry")
        try:
            bathymetry = bathymetry_provider.query(position.latitude, position.longitude)
            if not isinstance(bathymetry, BathymetryState):
                raise TypeError("Bathymetry provider returned an invalid state.")
            depth = bathymetry.depth
            bathymetry_source = bathymetry.source
        except Exception:
            depth = None

        ice_source = self._source(ice_provider, "ice")
        try:
            ice_value = ice_provider.query(position, requested_time)
            if not isinstance(ice_value, SeaIceState):
                raise TypeError("Ice provider returned an invalid state.")
            ice_source = ice_value.source
            velocity = None
            if ice_value.drift_u is not None and ice_value.drift_v is not None:
                velocity = EnvironmentVector(
                    u=ice_value.drift_u,
                    v=ice_value.drift_v,
                    speed=hypot(ice_value.drift_u, ice_value.drift_v),
                )
            ice = EnvironmentIceState(
                available=True,
                matched_time=ice_value.timestamp,
                concentration=ice_value.concentration,
                thickness=ice_value.thickness,
                velocity=velocity,
            )
        except Exception as error:
            ice = EnvironmentIceState(available=False, reason=self._reason(error))

        wind_source = self._source(wind_provider, "wind")
        try:
            wind_value = wind_provider.query(position, requested_time)
            if not isinstance(wind_value, WindState):
                raise TypeError("Wind provider returned an invalid state.")
            wind_source = wind_value.source
            wind = EnvironmentWindState(
                available=True,
                matched_time=wind_value.matched_time or wind_value.timestamp,
                speed=wind_value.wind_speed,
                direction=wind_value.wind_direction_meteorological,
                u10=wind_value.u10,
                v10=wind_value.v10,
            )
        except Exception as error:
            wind = EnvironmentWindState(available=False, reason=self._reason(error))

        current_source = self._source(current_provider, "current")
        try:
            current_value = current_provider.query(position, requested_time)
            if not isinstance(current_value, CurrentState):
                raise TypeError("Current provider returned an invalid state.")
            current_source = current_value.source
            current = EnvironmentCurrentState(
                available=True,
                matched_time=current_value.timestamp,
                u=current_value.current_east,
                v=current_value.current_north,
                speed=current_value.current_speed,
            )
        except Exception as error:
            current = EnvironmentCurrentState(available=False, reason=self._reason(error))

        wave_source = self._source(wave_provider, "wave")
        try:
            wave_value = wave_provider.query(position, requested_time)
            if not isinstance(wave_value, WaveState):
                raise TypeError("Wave provider returned an invalid state.")
            wave_source = wave_value.source
            wave = EnvironmentWaveState(
                available=True,
                matched_time=wave_value.matched_time,
                height=wave_value.wave_height,
                period=wave_value.wave_period,
                direction=wave_value.wave_direction_from,
            )
        except Exception as error:
            wave = EnvironmentWaveState(available=False, reason=self._reason(error))

        result = EnvironmentState(
            timestamp=requested_time,
            requested_time=requested_time,
            latitude=position.latitude,
            longitude=position.longitude,
            depth=depth,
            ice=ice,
            wind=wind,
            current=current,
            wave=wave,
            sources=EnvironmentSources(
                bathymetry=bathymetry_source,
                ice=ice_source,
                wind=wind_source,
                current=current_source,
                wave=wave_source,
            ),
        )
        self._cache_put(key, result)
        return result.model_copy(deep=True)

    def query_many(
        self,
        points: list[tuple[str, Position]],
        timestamp: datetime,
    ) -> list[dict[str, object]]:
        """Aggregate up to 500 points while reusing provider and query caches."""

        if not points:
            raise ValueError("Environment query points cannot be empty.")
        if len(points) > 500:
            raise ValueError("A maximum of 500 environment query points is supported.")
        return [
            {
                "id": point_id,
                "environment": self.query(point.latitude, point.longitude, timestamp),
            }
            for point_id, point in points
        ]

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()

    def _provider(self, layer_id: str) -> EnvironmentProvider:
        for provider in self._providers:
            if any(layer.get("id") == layer_id for layer in provider.get_available_layers()):
                return provider
        raise LookupError(f"No {layer_id} provider is registered.")

    def _cache_get(self, key: tuple[float, float, datetime]) -> EnvironmentState | None:
        with self._cache_lock:
            cached = self._cache.pop(key, None)
            if cached is None:
                return None
            self._cache[key] = cached
            return cached.model_copy(deep=True)

    def _cache_put(self, key: tuple[float, float, datetime], value: EnvironmentState) -> None:
        with self._cache_lock:
            self._cache.pop(key, None)
            self._cache[key] = value.model_copy(deep=True)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)

    @staticmethod
    def _source(provider: EnvironmentProvider, fallback: str) -> str:
        source = getattr(provider, "source_name", None)
        if isinstance(source, str):
            return source
        try:
            metadata_source = provider.get_metadata().get("source")
        except Exception:
            metadata_source = None
        return metadata_source if isinstance(metadata_source, str) else fallback

    @staticmethod
    def _reason(error: Exception) -> str:
        message = str(error).lower()
        if "coverage" in message or "outside" in message:
            return "out_of_coverage"
        if "no data" in message or "unavailable" in message or "missing" in message:
            return "no_data"
        return "provider_error"
