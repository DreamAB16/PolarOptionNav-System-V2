"""Create a masked EPSG:3413 GEBCO GeoTIFF for Arctic raster tiles.

The source GEBCO file stays untouched. GDAL performs the reprojection in
blocks, avoiding Python-level random source-cell reads. Nearest-neighbour
sampling prevents bathymetry values from crossing source NoData or land masks.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
from pyproj import Transformer
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.windows import Window
from rasterio.warp import reproject

from core.config.environment_config import get_dataset_path

DEFAULT_SOURCE = get_dataset_path("bathymetry") / "raw" / "GEBCO_2026_sub_ice.nc"
DEFAULT_OUTPUT = get_dataset_path("bathymetry") / "processed" / "bathymetry_polar_3413.tif"
POLAR_EXTENT = (-7_150_000.0, -7_150_000.0, 7_150_000.0, 7_150_000.0)
FILL_VALUE = np.int16(-32768)


def _raster_path(path: Path) -> str:
    """Use a CWD-relative path when possible (GDAL on Windows and Unicode)."""

    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def preprocess(
    source_path: Path,
    output_path: Path,
    *,
    resolution_metres: float = 1_000.0,
    south_latitude: float = 30.0,
    row_chunk: int = 32,
) -> Path:
    """Project the requested northern GEBCO domain into a compressed GeoTIFF."""

    if not source_path.is_file():
        raise FileNotFoundError(f"GEBCO source file does not exist: {source_path}")
    if resolution_metres <= 0:
        raise ValueError("resolution_metres must be positive")
    if not 0 <= south_latitude < 90:
        raise ValueError("south_latitude must be in the range 0 <= latitude < 90")
    if row_chunk <= 0:
        raise ValueError("row_chunk must be positive")

    min_x, min_y, max_x, max_y = POLAR_EXTENT
    x_size = int(np.ceil((max_x - min_x) / resolution_metres))
    y_size = int(np.ceil((max_y - min_y) / resolution_metres))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(".tmp.tif")
    transformer = Transformer.from_crs("EPSG:3413", "EPSG:4326", always_xy=True)
    target_crs = CRS.from_epsg(3413)
    target_transform = Affine(resolution_metres, 0.0, min_x, 0.0, -resolution_metres, max_y)

    try:
        with rasterio.open(_raster_path(source_path), mode="r") as source, rasterio.open(
            _raster_path(temporary_path),
            mode="w",
            driver="GTiff",
            width=x_size,
            height=y_size,
            count=1,
            dtype="int16",
            crs=target_crs,
            transform=target_transform,
            nodata=int(FILL_VALUE),
            tiled=True,
            blockxsize=256,
            blockysize=256,
            compress="deflate",
            predictor=2,
            BIGTIFF="IF_SAFER",
        ) as output:
            reprojected = np.full((y_size, x_size), FILL_VALUE, dtype=np.int16)
            reproject(
                source=rasterio.band(source, 1),
                destination=reprojected,
                src_transform=source.transform,
                src_crs="EPSG:4326",
                src_nodata=source.nodata,
                dst_transform=target_transform,
                dst_crs=target_crs,
                dst_nodata=int(FILL_VALUE),
                resampling=Resampling.nearest,
                init_dest_nodata=True,
                num_threads=4,
            )
            x_centres = min_x + (np.arange(x_size, dtype=np.float64) + 0.5) * resolution_metres
            for row_start in range(0, y_size, row_chunk):
                row_end = min(row_start + row_chunk, y_size)
                window = Window(0, row_start, x_size, row_end - row_start)
                destination = reprojected[row_start:row_end, :]
                y_centres = max_y - (row_start + np.arange(int(window.height), dtype=np.float64) + 0.5) * resolution_metres
                _, latitude = transformer.transform(
                    np.broadcast_to(x_centres, destination.shape),
                    np.broadcast_to(y_centres[:, None], destination.shape),
                )
                destination[(~np.isfinite(latitude)) | (latitude < south_latitude) | (latitude > 90.0)] = FILL_VALUE
                output.write(destination, 1, window=window)
            output.update_tags(
                TITLE="GEBCO polar bathymetry display grid",
                SOURCE=source_path.name,
                SOURCE_CRS="EPSG:4326",
                SOUTHERN_LATITUDE_LIMIT=south_latitude,
                RESOLUTION_METRES=resolution_metres,
                NODATA_POLICY="NoData renders transparent; never depth zero",
                UNITS="m",
            )
        temporary_path.replace(output_path)
    except BaseException:
        if temporary_path.exists():
            temporary_path.unlink()
        raise
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--resolution-metres",
        type=float,
        default=1_000.0,
        help="EPSG:3413 GeoTIFF cell size; default: 1000 m",
    )
    parser.add_argument("--south-latitude", type=float, default=30.0)
    parser.add_argument("--row-chunk", type=int, default=32)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = preprocess(
            args.source.resolve(),
            args.output.resolve(),
            resolution_metres=args.resolution_metres,
            south_latitude=args.south_latitude,
            row_chunk=args.row_chunk,
        )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Polar bathymetry preprocessing failed: {error}", file=sys.stderr)
        return 1
    print(f"Created EPSG:3413 polar bathymetry grid: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
