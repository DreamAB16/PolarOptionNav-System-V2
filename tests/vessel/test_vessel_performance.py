import inspect
from datetime import datetime, timezone
from typing import get_type_hints

import pytest
from pydantic import ValidationError

from core.contracts import (
    AvailabilityStatus,
    EvidenceRecord,
    EvidenceStatus,
    QualityMetadata,
    TimeMetadata,
    WGS84Position,
)
from core.vessel import (
    HullGeometry,
    HydrodynamicParameters,
    IceClass,
    MassProperties,
    PropulsionSystem,
    PropulsionType,
    VesselCapability,
    VesselState,
)
from core.vessel.performance import (
    PerformanceInput,
    PerformanceOutputField,
    VesselPerformanceModel,
    VesselPerformanceState,
    VesselPhysicalModel,
)
import core.vessel.performance as performance_module


def performance_input() -> PerformanceInput:
    return PerformanceInput(
        vessel_capability=VesselCapability(
            vessel_id="polar-1",
            ice_class=IceClass.UNKNOWN,
        ),
        vessel_state=VesselState(
            position=WGS84Position(latitude_deg=80, longitude_deg=10),
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        physical_model=VesselPhysicalModel(
            geometry=HullGeometry(),
            mass=MassProperties(),
            hydrodynamics=HydrodynamicParameters(),
        ),
        propulsion_system=PropulsionSystem(
            propulsion_type=PropulsionType.UNKNOWN,
            number_of_propellers=1,
        ),
    )


def performance_state(**overrides: object) -> VesselPerformanceState:
    values: dict[str, object] = {
        "quality": QualityMetadata(availability=AvailabilityStatus.MISSING),
        "evidence": EvidenceRecord(status=EvidenceStatus.UNKNOWN),
        "timestamp": TimeMetadata(valid_time=datetime(2026, 1, 1, tzinfo=timezone.utc)),
    }
    values.update(overrides)
    return VesselPerformanceState(**values)


def test_performance_input_reuses_existing_contracts() -> None:
    value = performance_input()
    assert isinstance(value.vessel_capability, VesselCapability)
    assert isinstance(value.vessel_state, VesselState)
    assert isinstance(value.physical_model.geometry, HullGeometry)
    assert isinstance(value.physical_model.mass, MassProperties)
    assert isinstance(value.physical_model.hydrodynamics, HydrodynamicParameters)
    assert isinstance(value.propulsion_system, PropulsionSystem)
    assert value.environment_context is None


def test_performance_state_preserves_unknown_values_as_none() -> None:
    value = performance_state()
    assert value.available_power_kw is None
    assert value.operating_power_kw is None
    assert value.effective_power_kw is None
    assert value.propulsion_efficiency is None
    assert value.timestamp.valid_time is not None
    assert value.timestamp.valid_time.tzinfo is not None


def test_zero_is_explicit_and_distinct_from_unknown() -> None:
    value = performance_state(
        operating_power_kw=0,
        propulsion_efficiency=0,
    )
    assert value.operating_power_kw == 0
    assert value.propulsion_efficiency == 0


@pytest.mark.parametrize(
    "field",
    ["available_power_kw", "operating_power_kw", "effective_power_kw"],
)
def test_power_fields_reject_negative_values(field: str) -> None:
    with pytest.raises(ValidationError):
        performance_state(**{field: -1})


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_propulsion_efficiency_is_bounded(value: float) -> None:
    with pytest.raises(ValidationError):
        performance_state(propulsion_efficiency=value)


def test_performance_timestamp_requires_aware_utc_time() -> None:
    with pytest.raises(ValidationError):
        performance_state(timestamp=TimeMetadata(valid_time=datetime(2026, 1, 1)))


def test_performance_model_is_an_evaluate_protocol() -> None:
    assert hasattr(VesselPerformanceModel, "evaluate")
    hints = get_type_hints(VesselPerformanceModel.evaluate)
    assert hints["input"] is PerformanceInput
    assert hints["return"] is VesselPerformanceState
    assert not hasattr(performance_module, "DefaultPerformanceModel")


@pytest.mark.parametrize(
    "name",
    [
        "calculate_speed",
        "calculate_resistance",
        "calculate_thrust",
        "calculate_eta",
        "ice_speed_limit",
        "wave_resistance",
        "wind_resistance",
    ],
)
def test_performance_interface_exposes_no_calculations(name: str) -> None:
    assert not hasattr(VesselPerformanceModel, name)
    assert not hasattr(PerformanceInput, name)
    assert not hasattr(VesselPerformanceState, name)


def test_performance_output_fields_match_contract_names() -> None:
    assert list(PerformanceOutputField) == [
        PerformanceOutputField.AVAILABLE_POWER_KW,
        PerformanceOutputField.OPERATING_POWER_KW,
        PerformanceOutputField.EFFECTIVE_POWER_KW,
        PerformanceOutputField.PROPULSION_EFFICIENCY,
    ]
    signature = inspect.signature(VesselPerformanceModel.evaluate)
    assert list(signature.parameters) == ["self", "input"]
