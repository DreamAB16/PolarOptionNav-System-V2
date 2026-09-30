"""Configuration readers shared by runtime data adapters."""

from .environment_config import get_dataset_path, get_environment_root

__all__ = ["get_dataset_path", "get_environment_root"]
