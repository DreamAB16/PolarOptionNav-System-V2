"""Environment query identifiers reusing the shared environment contracts."""

from core.environment.enums import EnvironmentScale, EnvironmentVariable


# Query field kinds intentionally share the canonical environment variable enum.
EnvironmentFieldType = EnvironmentVariable

__all__ = ["EnvironmentFieldType", "EnvironmentScale"]
