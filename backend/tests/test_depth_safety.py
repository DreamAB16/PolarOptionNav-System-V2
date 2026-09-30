from core.models import VesselDraftConfig
from services.vessel_service import DepthSafetyService


def test_depth_safety_accepts_sufficient_depth():
    result = DepthSafetyService().evaluate(
        depth=100,
        config=VesselDraftConfig(draft=10, ukc=5),
    )

    assert result.required_depth == 15
    assert result.safe is True
    assert result.margin == 85


def test_depth_safety_rejects_insufficient_depth():
    result = DepthSafetyService().evaluate(
        depth=12,
        config=VesselDraftConfig(draft=10, ukc=5),
    )

    assert result.required_depth == 15
    assert result.safe is False
    assert result.margin == -3
