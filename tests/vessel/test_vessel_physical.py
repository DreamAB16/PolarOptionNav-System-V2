import pytest
from pydantic import ValidationError

from core.vessel import HullGeometry, HydrodynamicParameters, MassProperties


def test_hull_geometry_uses_si_dimensions() -> None:
    hull = HullGeometry(
        length_overall_m=200,
        length_waterline_m=190,
        beam_m=32,
        draft_m=9,
        depth_m=18,
        block_coefficient=0.72,
    )
    assert hull.length_overall_m == 200
    assert hull.beam_m == 32
    assert 0 < hull.block_coefficient <= 1


@pytest.mark.parametrize("field", ["length_overall_m", "length_waterline_m", "beam_m", "draft_m", "depth_m"])
def test_hull_geometry_rejects_nonpositive_dimensions(field: str) -> None:
    with pytest.raises(ValidationError):
        HullGeometry(**{field: 0})


@pytest.mark.parametrize("value", [0, 1.1, -0.1])
def test_block_coefficient_range(value: float) -> None:
    with pytest.raises(ValidationError):
        HullGeometry(block_coefficient=value)


def test_mass_properties_allow_unknown_and_reject_negative_mass() -> None:
    properties = MassProperties(lightship_mass_t=10000, deadweight_t=None, displacement_t=None)
    assert properties.deadweight_t is None
    with pytest.raises(ValidationError):
        MassProperties(displacement_t=-100)


def test_hydrodynamic_parameters_are_si_fields_only() -> None:
    parameters = HydrodynamicParameters(
        wetted_surface_area_m2=9000,
        reference_area_m2=640,
        underwater_volume_m3=12000,
    )
    assert parameters.wetted_surface_area_m2 == 9000
    assert parameters.underwater_volume_m3 == 12000
    assert parameters.model_dump().keys() == {
        "wetted_surface_area_m2", "reference_area_m2", "underwater_volume_m3",
    }


def test_all_physical_models_preserve_unknown_as_none() -> None:
    assert HullGeometry().length_overall_m is None
    assert MassProperties().displacement_t is None
    assert HydrodynamicParameters().wetted_surface_area_m2 is None


def test_physical_models_have_no_resistance_calculations() -> None:
    assert not hasattr(HydrodynamicParameters, "calculate_resistance")
    assert not hasattr(HydrodynamicParameters, "friction_resistance")
    assert not hasattr(HydrodynamicParameters, "wave_resistance")
    assert not hasattr(HydrodynamicParameters, "total_resistance")
