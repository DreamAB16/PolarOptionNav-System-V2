"""Small NetCDF I/O helpers shared by runtime adapters and offline tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from netCDF4 import Dataset


def open_netcdf(path: str | Path, mode: str = "r", **kwargs: Any) -> Dataset:
    """Open NetCDF safely when a Windows parent directory contains Unicode."""

    nc_path = Path(path).resolve()
    if os.name != "nt" or str(nc_path).isascii():
        return Dataset(nc_path, mode=mode, **kwargs)

    previous_directory = Path.cwd()
    try:
        os.chdir(nc_path.parent)
        return Dataset(nc_path.name, mode=mode, **kwargs)
    finally:
        os.chdir(previous_directory)
