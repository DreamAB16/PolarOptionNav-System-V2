"""Resolve environment-data paths without embedding storage locations in providers."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "environment.yaml"
DATA_ROOT_ENVIRONMENT_VARIABLE = "POLAR_ENVIRONMENT_DATA_ROOT"


@lru_cache(maxsize=1)
def _configuration() -> dict[str, Any]:
    """Load the small, non-secret environment-data configuration file."""

    if not CONFIG_PATH.is_file():
        raise FileNotFoundError(f"Environment configuration is unavailable: {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream) or {}
    if not isinstance(value, dict):
        raise ValueError("environment.yaml must contain a mapping at its root.")
    return value


def get_environment_root() -> Path:
    """Return the configured environment repository root, with env override."""

    configured = os.getenv(DATA_ROOT_ENVIRONMENT_VARIABLE)
    if not configured:
        environment = _configuration().get("environment")
        if not isinstance(environment, dict) or not environment.get("data_root"):
            raise ValueError("environment.yaml must define environment.data_root.")
        configured = str(environment["data_root"])
    return Path(configured).expanduser()


def get_dataset_path(name: str) -> Path:
    """Resolve one named dataset directory below ``get_environment_root()``."""

    datasets = _configuration().get("datasets")
    if not isinstance(datasets, dict) or name not in datasets:
        raise KeyError(f"Unknown environment dataset: {name}")
    dataset = datasets[name]
    if not isinstance(dataset, dict) or not dataset.get("path"):
        raise ValueError(f"environment.yaml must define datasets.{name}.path.")
    return get_environment_root() / Path(str(dataset["path"]))
