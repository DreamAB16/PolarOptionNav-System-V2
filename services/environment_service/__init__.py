"""Environment service facade and provider boundary."""

from .providers import (
    BathymetryProvider,
    CurrentProvider,
    EnvironmentProvider,
    IceProvider,
    MockIceProvider,
    RealBathymetryProvider,
    WaveProvider,
    WindProvider,
)
from .wind import CARRA2WindProvider, RealWindProvider
from .current import RealCurrentProvider
from .wave import RealWaveProvider
from .polar_bathymetry import PolarBathymetryProvider
from .service import EnvironmentService
from .time_manager import EnvironmentTimeManager
from .environment_query import EnvironmentQueryService
from .grid import EnvironmentGridBuilder
from .copernicus_ice import (
    CopernicusIceDatasetIndex,
    CopernicusIceProvider,
    CopernicusIceRasterProvider,
    CopernicusIceVariables,
    discover_copernicus_variables,
)

__all__ = [
    "BathymetryProvider",
    "CurrentProvider",
    "EnvironmentProvider",
    "EnvironmentService",
    "EnvironmentQueryService",
    "EnvironmentGridBuilder",
    "EnvironmentTimeManager",
    "CopernicusIceDatasetIndex",
    "CopernicusIceProvider",
    "CopernicusIceRasterProvider",
    "CopernicusIceVariables",
    "discover_copernicus_variables",
    "IceProvider",
    "MockIceProvider",
    "RealBathymetryProvider",
    "PolarBathymetryProvider",
    "WaveProvider",
    "WindProvider",
    "RealWindProvider",
    "CARRA2WindProvider",
    "RealCurrentProvider",
    "RealWaveProvider",
]
