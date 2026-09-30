"""Draft and under-keel-clearance safety calculation."""

from core.models import DepthSafetyResult, VesselDraftConfig


class DepthSafetyService:
    """Compare positive-down water depth with the configured required depth."""

    def evaluate(self, depth: float, config: VesselDraftConfig) -> DepthSafetyResult:
        required_depth = config.draft + config.ukc
        margin = depth - required_depth
        return DepthSafetyResult(
            depth=depth,
            required_depth=required_depth,
            safe=margin >= 0,
            margin=margin,
        )
