"""Chart service facade and GeoPackage provider implementation."""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Any

from shapely import wkb
from shapely.geometry import mapping


class ChartProvider(ABC):
    """Abstract source of chart layers; API consumers never see source paths."""

    @abstractmethod
    def list_layers(self) -> list[dict[str, object]]:
        """Return metadata for layers allowed to be loaded by clients."""

    @abstractmethod
    def get_layer_features(self, layer_id: str) -> dict[str, object]:
        """Return one authorised layer in RFC 7946 GeoJSON format."""


class GeoPackageChartProvider(ChartProvider):
    """Read selected vector layers from the configured local GeoPackage."""

    _LAYER_ID = "coastline"

    def __init__(self, geopackage_path: Path) -> None:
        self._geopackage_path = geopackage_path

    def list_layers(self) -> list[dict[str, object]]:
        self._ensure_available()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT data_type, srs_id FROM gpkg_contents WHERE table_name = ?",
                (self._LAYER_ID,),
            ).fetchone()
            count = connection.execute("SELECT COUNT(*) FROM coastline").fetchone()[0]
        if row is None:
            return []
        return [
            {
                "id": self._LAYER_ID,
                "name": "Coastline",
                "format": "geojson",
                "geometry_type": "MultiLineString",
                "feature_count": count,
                "source_crs": f"EPSG:{row['srs_id']}",
                "url": f"/api/chart/layers/{self._LAYER_ID}",
            }
        ]

    def get_layer_features(self, layer_id: str) -> dict[str, object]:
        if layer_id != self._LAYER_ID:
            raise KeyError(layer_id)
        return self._coastline_features()

    @lru_cache(maxsize=1)
    def _coastline_features(self) -> dict[str, object]:
        self._ensure_available()
        features: list[dict[str, Any]] = []
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT fid, geom, featurecla, scalerank, min_zoom FROM coastline"
            )
            for row in rows:
                if row["geom"] is None:
                    continue
                features.append(
                    {
                        "type": "Feature",
                        "id": row["fid"],
                        "properties": {
                            "featurecla": row["featurecla"],
                            "scalerank": row["scalerank"],
                            "min_zoom": row["min_zoom"],
                        },
                        "geometry": mapping(wkb.loads(self._wkb_from_geopackage(row["geom"]))),
                    }
                )
        return {"type": "FeatureCollection", "features": features}

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._geopackage_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_available(self) -> None:
        if not self._geopackage_path.is_file():
            raise FileNotFoundError("Configured chart data is unavailable.")

    @staticmethod
    def _wkb_from_geopackage(geometry: bytes) -> bytes:
        """Remove the GeoPackage binary header before passing standard WKB to Shapely."""

        if geometry[:2] != b"GP":
            raise ValueError("Invalid GeoPackage geometry header.")
        flags = geometry[3]
        envelope_indicator = (flags >> 1) & 0b111
        envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
        if envelope_indicator not in envelope_sizes:
            raise ValueError("Unsupported GeoPackage geometry envelope.")
        return geometry[8 + envelope_sizes[envelope_indicator] :]


class ChartService:
    """Application-facing chart facade with swappable provider dependency."""

    def __init__(self, provider: ChartProvider | None = None) -> None:
        data_path = Path(__file__).resolve().parents[2] / "data" / "charts" / "base_map.gpkg"
        self.provider = provider or GeoPackageChartProvider(data_path)

    def get_overview(self) -> dict[str, object]:
        return {"status": "ready", "layers": self.provider.list_layers()}

    def get_layers(self) -> list[dict[str, object]]:
        return self.provider.list_layers()

    def get_layer_features(self, layer_id: str) -> dict[str, object]:
        return self.provider.get_layer_features(layer_id)
