"""Unified environmental service facade with independent provider boundaries."""

from collections.abc import Iterable
from datetime import datetime
import logging
from pathlib import Path

from core.config.environment_config import get_dataset_path, get_environment_root
from core.models import (
    BathymetryState,
    CurrentState,
    EnvironmentQuery,
    EnvironmentState,
    EnvironmentTimeState,
    LegacyEnvironmentState,
    Position,
    SeaIceState,
    WaveState,
    WindState,
)
from .providers import (
    BathymetryProvider,
    CurrentProvider,
    EnvironmentProvider,
    IceProvider,
    RealBathymetryProvider,
    WaveProvider,
    WindProvider,
)
from .polar_bathymetry import PolarBathymetryProvider
from .copernicus_ice import CopernicusIceProvider, CopernicusIceRasterProvider
from .time_manager import EnvironmentTimeManager
from .wind import CARRA2WindProvider, RealWindProvider
from .current import RealCurrentProvider
from .wave import RealWaveProvider
from .environment_query import EnvironmentQueryService


LOGGER = logging.getLogger(__name__)


class _UnavailableBathymetryProvider(BathymetryProvider):
    """Keep service startup non-fatal when the external GEBCO file is absent."""

    def get_metadata(self) -> dict[str, object]:
        return {"provider": self.layer_id, "status": "not_found"}

    def get_available_layers(self) -> list[dict[str, str]]:
        return [{"id": self.layer_id, "name": self.layer_name, "status": "not_found"}]

    def query(self, latitude: float, longitude: float) -> BathymetryState:
        raise FileNotFoundError("Bathymetry data is not available in the configured environment root.")

    def get_tile(self, zoom: int, x: int, y: int) -> bytes:
        raise FileNotFoundError("Bathymetry data is not available in the configured environment root.")


class _UnavailableIceProvider(IceProvider):
    """Publish a non-fatal readiness state when no processed ice file exists."""

    def get_metadata(self) -> dict[str, object]:
        return {"provider": self.layer_id, "status": "not_found"}

    def get_available_layers(self) -> list[dict[str, str]]:
        return [{"id": self.layer_id, "name": self.layer_name, "status": "not_found"}]

    def query(
        self,
        position: Position | float,
        timestamp: datetime | float | None = None,
        legacy_timestamp: datetime | None = None,
    ) -> SeaIceState:
        raise FileNotFoundError("Sea-ice data is not available in the configured environment root.")


class _UnavailableIceRasterProvider:
    """Delay a missing external data error until an ice tile is requested."""

    def get_tile(self, *args: object, **kwargs: object) -> bytes:
        raise FileNotFoundError("Sea-ice raster data is not available in the configured environment root.")

    def get_polar_tile(self, *args: object, **kwargs: object) -> bytes:
        raise FileNotFoundError("Sea-ice raster data is not available in the configured environment root.")

    def close(self) -> None:
        return None


class SyntheticEnvironmentProvider:
    """Deterministic placeholder provider for UI and API smoke tests."""

    def get_state(self) -> LegacyEnvironmentState:
        return LegacyEnvironmentState(position=Position(latitude=69.65, longitude=18.96))


class EnvironmentService:
    """Expose state and layer discovery without binding callers to data formats."""

    def __init__(
        self,
        provider: SyntheticEnvironmentProvider | None = None,
        providers: Iterable[EnvironmentProvider] | None = None,
        ice_raster_provider: CopernicusIceRasterProvider | None = None,
        polar_bathymetry_provider: PolarBathymetryProvider | None = None,
        time_manager: EnvironmentTimeManager | None = None,
    ) -> None:
        # `provider` retains the Phase 0 state endpoint's behaviour.
        self.provider = provider or SyntheticEnvironmentProvider()
        self.providers = list(providers) if providers is not None else self._default_providers()
        self.ice_raster_provider = ice_raster_provider or self._default_ice_raster_provider()
        self.polar_bathymetry_provider = polar_bathymetry_provider or self._default_polar_bathymetry_provider()
        self.time_manager = time_manager or EnvironmentTimeManager()
        self.environment_query_service = EnvironmentQueryService(self.providers, self.time_manager)
        LOGGER.info("Loading environment data from %s", get_environment_root())
        for metadata in self.get_metadata():
            LOGGER.info(
                "Environment dataset %s: %s",
                metadata.get("provider", "unknown"),
                metadata.get("status", "unknown"),
            )

    def get_state(self) -> LegacyEnvironmentState:
        return self.provider.get_state()

    def get_metadata(self) -> list[dict[str, object]]:
        """Return readiness metadata for each registered environmental provider."""

        return [provider.get_metadata() for provider in self.providers]

    def get_available_layers(self) -> list[dict[str, str]]:
        """Return a unified list of layers published by all registered providers."""

        return [layer for provider in self.providers for layer in provider.get_available_layers()]

    def register_provider(self, provider: EnvironmentProvider) -> None:
        """Add or replace a provider that publishes the same environment layer."""

        provider_layer_ids = {layer["id"] for layer in provider.get_available_layers()}
        for index, current_provider in enumerate(self.providers):
            current_layer_ids = {layer["id"] for layer in current_provider.get_available_layers()}
            if provider_layer_ids & current_layer_ids:
                self.providers[index] = provider
                self.environment_query_service.clear_cache()
                return
        self.providers.append(provider)
        self.environment_query_service.clear_cache()

    def get_time_state(self) -> EnvironmentTimeState:
        """Expose the managed environmental clock without exposing provider internals."""

        return self.time_manager.state()

    def query_environment(self, layer_id: str, query: EnvironmentQuery) -> object:
        """Use the unified position/timestamp contract for time-aware providers."""

        for provider in self.providers:
            if any(layer["id"] == layer_id for layer in provider.get_available_layers()):
                return provider.query(query.position, query.timestamp)
        raise LookupError(f"No {layer_id} provider is registered.")

    def query_complete_environment(
        self,
        latitude: float,
        longitude: float,
        timestamp: datetime,
    ) -> EnvironmentState:
        """Return one fault-isolated snapshot assembled from all five providers."""

        return self.environment_query_service.query(latitude, longitude, timestamp)

    def query_complete_environment_batch(
        self,
        points: list[tuple[str, Position]],
        timestamp: datetime,
    ) -> list[dict[str, object]]:
        """Return unified environment snapshots for no more than 500 points."""

        return self.environment_query_service.query_many(points, timestamp)

    def query_ice(
        self,
        position: Position | EnvironmentQuery,
        time: datetime | None = None,
    ) -> SeaIceState:
        """Delegate an ice query using the managed clock when a timestamp is omitted."""

        query = (
            position
            if isinstance(position, EnvironmentQuery)
            else self.time_manager.make_query(position.latitude, position.longitude, time)
        )

        result = self.query_environment("ice", query)
        if not isinstance(result, SeaIceState):
            raise TypeError("The registered ice provider returned an invalid state.")
        return result

    def query_bathymetry(self, latitude: float, longitude: float) -> BathymetryState:
        """Delegate a point query to the registered bathymetry provider."""

        return self._bathymetry_provider().query(latitude, longitude)

    def query_wind(self, position: Position | EnvironmentQuery, time: datetime | None = None) -> WindState:
        query = position if isinstance(position, EnvironmentQuery) else self.time_manager.make_query(position.latitude, position.longitude, time)
        try:
            result = self.query_environment("wind", query)
        except NotImplementedError as error:
            raise LookupError("Wind data is not available from the configured provider.") from error
        if not isinstance(result, WindState):
            raise TypeError("The registered wind provider returned an invalid state.")
        return result

    def query_wind_field(self, points: list[tuple[str, Position]], time: datetime) -> dict[str, object]:
        for provider in self.providers:
            if any(layer["id"] == "wind" for layer in provider.get_available_layers()):
                query_many = getattr(provider, "query_many", None)
                if query_many is None:
                    raise LookupError("当前风场数据源不支持批量查询。")
                return query_many(points, time)
        raise LookupError("Wind data is not available from the configured provider.")

    def query_current(self, position: Position | EnvironmentQuery, time: datetime | None = None) -> CurrentState:
        """Query TOPAZ5 current using the shared environmental clock."""

        query = position if isinstance(position, EnvironmentQuery) else self.time_manager.make_query(position.latitude, position.longitude, time)
        try:
            result = self.query_environment("current", query)
        except NotImplementedError as error:
            raise LookupError("Current data is not available; prepare a TOPAZ5 sample first.") from error
        if not isinstance(result, CurrentState):
            raise TypeError("The registered current provider returned an invalid state.")
        return result

    def query_current_field(self, points: list[tuple[str, Position]], time: datetime) -> dict[str, object]:
        """Batch-query one TOPAZ5 hour without reopening the source per point."""

        for provider in self.providers:
            if any(layer["id"] == "current" for layer in provider.get_available_layers()):
                query_many = getattr(provider, "query_many", None)
                if query_many is None:
                    raise LookupError("当前海流数据源不支持批量查询。")
                return query_many(points, time)
        raise LookupError("Current data is not available; prepare a TOPAZ5 sample first.")

    def query_wave(self, position: Position | EnvironmentQuery, time: datetime | None = None) -> WaveState:
        """Query WAM Arctic waves using the shared environmental clock."""

        query = position if isinstance(position, EnvironmentQuery) else self.time_manager.make_query(position.latitude, position.longitude, time)
        try:
            result = self.query_environment("wave", query)
        except NotImplementedError as error:
            raise LookupError("Wave data is not available; prepare a Copernicus wave sample first.") from error
        if not isinstance(result, WaveState):
            raise TypeError("The registered wave provider returned an invalid state.")
        return result

    def query_wave_field(self, points: list[tuple[str, Position]], time: datetime) -> dict[str, object]:
        """Batch-query one WAM Arctic hour without reopening the source per point."""

        for provider in self.providers:
            if any(layer["id"] == "wave" for layer in provider.get_available_layers()):
                query_many = getattr(provider, "query_many", None)
                if query_many is None:
                    raise LookupError("当前海浪数据源不支持批量查询。")
                return query_many(points, time)
        raise LookupError("Wave data is not available; prepare a Copernicus wave sample first.")

    def get_bathymetry_tile(self, zoom: int, x: int, y: int) -> bytes:
        """Delegate a raster tile request without exposing the backing dataset."""

        return self._bathymetry_provider().get_tile(zoom, x, y)

    def get_polar_bathymetry_tile(self, zoom: int, x: int, y: int) -> bytes:
        """Return a native EPSG:3413 bathymetry tile for Arctic map modes."""

        if self.polar_bathymetry_provider is None:
            # The offline product may be generated while this long-running API
            # process is up. Discover it on the first polar-tile request rather
            # than forcing an operational server restart.
            dataset_path = self._polar_bathymetry_path()
            if dataset_path.is_file():
                self.polar_bathymetry_provider = PolarBathymetryProvider(dataset_path)
            else:
                raise ValueError(
                    "Polar bathymetry is not prepared. Run "
                    "tools.data_tools.preprocess.preprocess_bathymetry_polar first."
                )
        return self.polar_bathymetry_provider.get_tile(zoom, x, y)

    def get_ice_tile(
        self,
        zoom: int,
        x: int,
        y: int,
        dataset_date: str | None = None,
        time_index: int = 0,
        timestamp: datetime | None = None,
    ) -> bytes:
        """Return one cached XYZ PNG tile without exposing the processed NC file."""

        selected_time = (
            timestamp
            if timestamp is not None
            else dataset_date
            if dataset_date is not None
            else self.time_manager.simulation_time
        )
        return self.ice_raster_provider.get_tile(zoom, x, y, selected_time, time_index)

    def get_ice_thickness_tile(
        self,
        zoom: int,
        x: int,
        y: int,
        dataset_date: str | None = None,
        time_index: int = 0,
        timestamp: datetime | None = None,
    ) -> bytes:
        """Return a thickness tile while preserving the existing concentration API."""

        selected_time = (
            timestamp
            if timestamp is not None
            else dataset_date
            if dataset_date is not None
            else self.time_manager.simulation_time
        )
        return self.ice_raster_provider.get_tile(
            zoom,
            x,
            y,
            selected_time,
            time_index,
            render_mode="thickness",
        )

    def get_ice_polar_tile(
        self,
        zoom: int,
        x: int,
        y: int,
        dataset_date: str | None = None,
        time_index: int = 0,
        timestamp: datetime | None = None,
        *,
        render_mode: str = "concentration",
    ) -> bytes:
        """Return a native EPSG:3413 tile for the optional Arctic tactical view."""

        selected_time = (
            timestamp
            if timestamp is not None
            else dataset_date
            if dataset_date is not None
            else self.time_manager.simulation_time
        )
        return self.ice_raster_provider.get_polar_tile(
            zoom,
            x,
            y,
            selected_time,
            time_index,
            render_mode=render_mode,
        )

    def _bathymetry_provider(self) -> BathymetryProvider:
        for provider in self.providers:
            if isinstance(provider, BathymetryProvider):
                return provider
        raise LookupError("No bathymetry provider is registered.")

    @staticmethod
    def _copernicus_ice_path() -> Path:
        return get_dataset_path("ice") / "processed" / "copernicus"

    @staticmethod
    def _polar_bathymetry_path() -> Path:
        return get_dataset_path("bathymetry") / "processed" / "bathymetry_polar_3413.tif"

    @staticmethod
    def _wind_path() -> Path:
        return get_dataset_path("wind") / "raw"

    @staticmethod
    def _current_path() -> Path:
        return get_dataset_path("current") / "raw"

    @staticmethod
    def _wave_path() -> Path:
        return get_dataset_path("wave") / "raw"

    @classmethod
    def _default_polar_bathymetry_provider(cls) -> PolarBathymetryProvider | None:
        dataset_path = cls._polar_bathymetry_path()
        return PolarBathymetryProvider(dataset_path) if dataset_path.is_file() else None
    @classmethod
    def _default_providers(cls) -> list[EnvironmentProvider]:
        dataset_path = get_dataset_path("bathymetry") / "raw" / "GEBCO_2026_sub_ice.nc"
        return [
            cls._default_bathymetry_provider(dataset_path),
            cls._default_ice_provider(),
            cls._default_wind_provider(),
            cls._default_current_provider(),
            cls._default_wave_provider(),
        ]

    @staticmethod
    def _default_bathymetry_provider(dataset_path: Path) -> BathymetryProvider:
        try:
            return RealBathymetryProvider(dataset_path)
        except (FileNotFoundError, ValueError, OSError):
            return _UnavailableBathymetryProvider()

    @classmethod
    def _default_ice_provider(cls) -> EnvironmentProvider:
        try:
            return CopernicusIceProvider(cls._copernicus_ice_path())
        except (FileNotFoundError, ValueError, OSError):
            return _UnavailableIceProvider()

    @classmethod
    def _default_ice_raster_provider(cls) -> CopernicusIceRasterProvider | _UnavailableIceRasterProvider:
        try:
            return CopernicusIceRasterProvider(cls._copernicus_ice_path())
        except (FileNotFoundError, ValueError, OSError):
            return _UnavailableIceRasterProvider()

    @classmethod
    def _default_wind_provider(cls) -> EnvironmentProvider:
        try:
            return CARRA2WindProvider(cls._wind_path())
        except (FileNotFoundError, ValueError):
            pass
        try:
            return RealWindProvider(cls._wind_path())
        except (FileNotFoundError, ValueError):
            return WindProvider()

    @classmethod
    def _default_current_provider(cls) -> EnvironmentProvider:
        try:
            return RealCurrentProvider(cls._current_path())
        except (FileNotFoundError, ValueError):
            return CurrentProvider()

    @classmethod
    def _default_wave_provider(cls) -> EnvironmentProvider:
        try:
            return RealWaveProvider(cls._wave_path())
        except (FileNotFoundError, ValueError):
            return WaveProvider()
