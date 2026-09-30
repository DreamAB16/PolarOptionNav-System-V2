"""Explicit environment scale resolution."""

from core.environment.enums import EnvironmentScale


class ScaleResolver:
    """Validate a caller-selected scale; no automatic scale selection is performed."""

    def resolve(self, scale: EnvironmentScale) -> EnvironmentScale:
        try:
            return scale if isinstance(scale, EnvironmentScale) else EnvironmentScale(scale)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Unsupported environment scale: {scale!r}") from exc


__all__ = ["ScaleResolver"]
