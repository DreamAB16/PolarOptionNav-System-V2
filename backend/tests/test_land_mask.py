from datetime import datetime, timezone

from core.models import BathymetryState
from services.planner_service.land_mask import GebcoLandMaskProvider


class DepthField:
    def __init__(self, land: bool = False, coastal: bool = False):
        self.land, self.coastal = land, coastal

    def query_bathymetry(self, latitude: float, longitude: float) -> BathymetryState:
        is_land = self.land or (self.coastal and longitude > 0.0)
        return BathymetryState(latitude=latitude, longitude=longitude, depth=0.0 if is_land else 120.0, timestamp=datetime.now(timezone.utc), source="test")


def test_ocean_cell_is_traversable_in_static_land_mask() -> None:
    result = GebcoLandMaskProvider(DepthField()).check_cell(60.0, 10.0)
    assert result.is_land is False
    assert result.land_ratio == 0.0


def test_land_cell_is_a_hard_obstacle() -> None:
    result = GebcoLandMaskProvider(DepthField(land=True)).check_cell(60.0, 10.0)
    assert result.is_land is True
    assert result.land_ratio == 1.0


def test_coastal_intersection_uses_conservative_land_ratio_threshold() -> None:
    result = GebcoLandMaskProvider(DepthField(coastal=True)).check_cell(60.0, 0.0)
    assert result.land_ratio > 0.05
    assert result.is_land is True
