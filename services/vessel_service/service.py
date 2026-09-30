"""Vessel profile, state and draft configuration service."""

import json
from pathlib import Path

from core.models import DepthSafetyResult, Position, VesselDraftConfig, VesselState
from core.vessel import VesselProfile
from .depth_safety import DepthSafetyService


class MockVesselProvider:
    def get_state(self) -> VesselState:
        return VesselState(position=Position(latitude=69.65, longitude=18.96), heading=45, speed=8)


class VesselService:
    def __init__(
        self,
        provider: MockVesselProvider | None = None,
        draft_config: VesselDraftConfig | None = None,
        depth_safety_service: DepthSafetyService | None = None,
        profile_path: Path | None = None,
    ) -> None:
        self.provider = provider or MockVesselProvider()
        self.profile = self._load_profile(profile_path or self._default_profile_path())
        # Keep the legacy depth-safety contract stable while the profile exposes
        # the published design draft for future EnvironmentGrid consumers.
        self.draft_config = draft_config or VesselDraftConfig(draft=10, ukc=2)
        self.depth_safety_service = depth_safety_service or DepthSafetyService()

    @staticmethod
    def _default_profile_path() -> Path:
        return Path(__file__).resolve().parents[2] / "data" / "vessel" / "xuelong2.json"

    @staticmethod
    def _load_profile(path: Path) -> VesselProfile:
        with path.open(encoding="utf-8") as file:
            return VesselProfile.model_validate(json.load(file))

    def get_current_profile(self) -> VesselProfile:
        """Return the configured vessel profile; selection is extensible for multi-vessel support."""

        return self.profile

    def get_state(self) -> VesselState:
        return self.provider.get_state()

    def evaluate_depth_safety(self, depth: float) -> DepthSafetyResult:
        """Evaluate depth using the vessel's configured draft and UKC."""

        return self.depth_safety_service.evaluate(depth, self.draft_config)
