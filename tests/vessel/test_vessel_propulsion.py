import pytest
from pydantic import ValidationError

from core.vessel import PropulsionSystem, PropulsionType


def test_propulsion_types_are_explicit() -> None:
    assert list(PropulsionType) == [
        PropulsionType.DIESEL,
        PropulsionType.DIESEL_ELECTRIC,
        PropulsionType.HYBRID,
        PropulsionType.NUCLEAR,
        PropulsionType.UNKNOWN,
    ]
    with pytest.raises(ValidationError):
        PropulsionSystem(propulsion_type="DIESEL", number_of_propellers=1)


def test_propulsion_system_accepts_valid_parameters() -> None:
    system = PropulsionSystem(
        propulsion_type=PropulsionType.DIESEL_ELECTRIC,
        rated_power_kw=15000,
        maximum_continuous_power_kw=12000,
        minimum_operating_power_kw=1000,
        propeller_efficiency=0.7,
        shaft_efficiency=0.95,
        number_of_propellers=2,
    )
    assert system.rated_power_kw == 15000
    assert system.number_of_propellers == 2


@pytest.mark.parametrize("field", ["rated_power_kw", "maximum_continuous_power_kw", "minimum_operating_power_kw"])
def test_power_fields_allow_none_and_reject_negative(field: str) -> None:
    assert PropulsionSystem(propulsion_type=PropulsionType.UNKNOWN, number_of_propellers=1, **{field: None})
    with pytest.raises(ValidationError):
        PropulsionSystem(propulsion_type=PropulsionType.UNKNOWN, number_of_propellers=1, **{field: -1})


@pytest.mark.parametrize("field", ["propeller_efficiency", "shaft_efficiency"])
@pytest.mark.parametrize("value", [0, -0.1, 1.1])
def test_efficiency_requires_open_closed_unit_interval(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        PropulsionSystem(propulsion_type=PropulsionType.HYBRID, number_of_propellers=1, **{field: value})


@pytest.mark.parametrize("value", [0, -1])
def test_number_of_propellers_must_be_positive(value: int) -> None:
    with pytest.raises(ValidationError):
        PropulsionSystem(propulsion_type=PropulsionType.NUCLEAR, number_of_propellers=value)


def test_unknown_parameters_remain_none_and_no_performance_methods_exist() -> None:
    system = PropulsionSystem(propulsion_type=PropulsionType.UNKNOWN, number_of_propellers=1)
    assert system.rated_power_kw is None
    assert system.propeller_efficiency is None
    for name in ("power_to_speed", "calculate_thrust", "effective_power", "resistance", "ice_speed_limit", "feasible", "risk", "planner"):
        assert not hasattr(PropulsionSystem, name)
