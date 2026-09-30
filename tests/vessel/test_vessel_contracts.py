from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from core.contracts import WGS84Position
from core.vessel import IceClass, VesselCapability, VesselState


def test_ice_class_values_are_explicit() -> None:
    assert list(IceClass) == [
        IceClass.PC1, IceClass.PC2, IceClass.PC3, IceClass.PC4,
        IceClass.PC5, IceClass.PC6, IceClass.PC7, IceClass.NONE, IceClass.UNKNOWN,
    ]
    with pytest.raises(ValidationError):
        VesselCapability(vessel_id="vessel", ice_class="PC1")


def test_capability_uses_si_fields_and_allows_unknown_facts() -> None:
    capability = VesselCapability(
        vessel_id="polar-1",
        length_m=200,
        beam_m=32,
        draft_m=9,
        displacement_t=None,
        propulsion_power_kw=None,
        ice_class=IceClass.PC5,
    )
    assert capability.length_m == 200
    assert capability.propulsion_power_kw is None


@pytest.mark.parametrize("field", ["length_m", "beam_m", "draft_m"])
def test_capability_rejects_nonpositive_dimensions(field: str) -> None:
    values = dict(vessel_id="vessel", ice_class=IceClass.UNKNOWN, length_m=1, beam_m=1, draft_m=1)
    values[field] = 0
    with pytest.raises(ValidationError):
        VesselCapability(**values)


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_power_fraction_is_bounded(value: float) -> None:
    with pytest.raises(ValidationError):
        VesselState(
            position=WGS84Position(latitude_deg=80, longitude_deg=10),
            power_fraction=value,
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def test_state_reuses_position_and_requires_aware_time() -> None:
    state = VesselState(
        position=WGS84Position(latitude_deg=80, longitude_deg=10),
        heading=1.2,
        speed_mps=5,
        power_fraction=0.5,
        draft_m=None,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert isinstance(state.position, WGS84Position)
    assert state.timestamp.tzinfo is not None
    with pytest.raises(ValidationError):
        VesselState(position=state.position, timestamp=datetime(2026, 1, 1))
