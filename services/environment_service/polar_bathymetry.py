"""Native EPSG:3413 raster tiles backed by a preprocessed GEBCO GeoTIFF."""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
from threading import RLock

import numpy as np
from PIL import Image
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import from_bounds


POLAR_BATHYMETRY_CRS = "EPSG:3413"
# This is deliberately shared with the front-end polar View, not the smaller
# Copernicus ice extent.  It covers the requested 30°N--90°N operating domain.
POLAR_BATHYMETRY_EXTENT = (-7_150_000.0, -7_150_000.0, 7_150_000.0, 7_150_000.0)


class PolarBathymetryProvider:
    """Serve native polar XYZ tiles from a projected, masked GeoTIFF grid.

    The provider is intentionally separate from ``RealBathymetryProvider``:
    point depth and global Web Mercator tiles continue to use the original
    GEBCO geographic grid, while this class is only responsible for display
    tiles in the Arctic map modes.
    """

    source_name = "GEBCO_2026_polar_3413"
    max_tile_zoom = 14
    tile_size = 256

    def __init__(self, dataset_path: Path | str) -> None:
        dataset_path = Path(dataset_path)
        if not dataset_path.is_file():
            raise FileNotFoundError(
                "Polar bathymetry dataset is unavailable. Run "
                "tools.data_tools.preprocess.preprocess_bathymetry_polar first."
            )
        self.dataset_path = dataset_path
        self._lock = RLock()
        self._dataset = rasterio.open(self._raster_path(dataset_path), mode="r")
        self._validate_grid()

    def close(self) -> None:
        with self._lock:
            if not self._dataset.closed:
                self._dataset.close()

    def get_metadata(self) -> dict[str, object]:
        return {
            "provider": "bathymetry-polar",
            "status": "ready",
            "source": self.source_name,
            "crs": POLAR_BATHYMETRY_CRS,
            "extent": list(POLAR_BATHYMETRY_EXTENT),
            "depth_units": "m",
        }

    @lru_cache(maxsize=256)
    def get_tile(self, zoom: int, x: int, y: int) -> bytes:
        """Return an EPSG:3413 XYZ PNG whose invalid samples stay transparent."""

        if zoom < 0 or zoom > self.max_tile_zoom:
            raise ValueError(f"Tile zoom must be between 0 and {self.max_tile_zoom}.")
        tile_count = 1 << zoom
        if x < 0 or y < 0 or x >= tile_count or y >= tile_count:
            raise ValueError("Tile coordinate is outside the requested zoom level.")

        min_x, min_y, max_x, max_y = POLAR_BATHYMETRY_EXTENT
        tile_span = (max_x - min_x) / tile_count
        west = min_x + x * tile_span
        east = west + tile_span
        north = max_y - y * tile_span
        south = north - tile_span
        return self._render_depth_png(self._read_window(south, west, north, east))

    def _read_window(self, south: float, west: float, north: float, east: float) -> np.ma.MaskedArray:
        window = from_bounds(west, south, east, north, transform=self._dataset.transform)
        with self._lock:
            return np.ma.asarray(
                self._dataset.read(
                    1,
                    window=window,
                    out_shape=(self.tile_size, self.tile_size),
                    boundless=True,
                    masked=True,
                    fill_value=self._dataset.nodata,
                    resampling=Resampling.nearest,
                )
            )

    @staticmethod
    def _render_depth_png(elevations: np.ma.MaskedArray) -> bytes:
        """Colour only valid water; land and every NoData cell have alpha zero."""

        masked = np.ma.asarray(elevations, dtype=np.float32)
        values = np.asarray(masked.filled(np.nan), dtype=np.float32)
        valid_water = (~np.ma.getmaskarray(masked)) & np.isfinite(values) & (values < 0)
        depth = np.maximum(-values, 0.0)
        render_depth = np.where(valid_water, depth, 0.0)
        scale = np.clip(np.log1p(render_depth) / np.log1p(6000.0), 0.0, 1.0)
        rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
        rgba[..., 0] = (105 - 90 * scale).astype(np.uint8)
        rgba[..., 1] = (205 - 135 * scale).astype(np.uint8)
        rgba[..., 2] = (235 - 95 * scale).astype(np.uint8)
        rgba[..., 3] = np.where(valid_water, 175, 0).astype(np.uint8)

        # Nearest-neighbour preserves a hard transparent NoData mask.  Bilinear
        # interpolation would leak alpha and colour across the land/NoData edge.
        image = Image.fromarray(rgba, mode="RGBA").resize(
            (256, 256), Image.Resampling.NEAREST
        )
        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()

    def _validate_grid(self) -> None:
        if self._dataset.count != 1:
            raise ValueError("Polar bathymetry GeoTIFF must contain exactly one elevation band.")
        if self._dataset.crs is None or self._dataset.crs.to_epsg() != 3413:
            raise ValueError("Polar bathymetry GeoTIFF must declare EPSG:3413.")
        if self._dataset.nodata is None:
            raise ValueError("Polar bathymetry GeoTIFF must declare a NoData value.")
        if self._dataset.width < 2 or self._dataset.height < 2:
            raise ValueError("Polar bathymetry grid must contain at least two cells per axis.")

    @staticmethod
    def _raster_path(path: Path) -> str:
        """Use a workspace-relative path for GDAL on Windows and Unicode paths."""

        try:
            return str(path.resolve().relative_to(Path.cwd().resolve()))
        except ValueError:
            return str(path)
