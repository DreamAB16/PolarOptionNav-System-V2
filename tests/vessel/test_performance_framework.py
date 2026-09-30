from datetime import datetime, timezone
from pathlib import Path
from typing import get_type_hints

import pytest
from pydantic import ValidationError

import core.vessel.performance as performance_package
from core.contracts import (
    AvailabilityStatus,
    EvidenceRecord,
    EvidenceStatus,
    QualityMetadata,
    TimeMetadata,
    WGS84Position,
)
from core.vessel import IceClass, VesselState
from core.vessel.performance import (
    PerformanceContext,
    PerformanceEvaluator,
    PerformanceMetric,
    PerformanceModelRegistry,
    PerformanceRequest,
    PerformanceResult,
)


UTC = timezone.utc


def performance_context(timestamp: datetime | None = None) -> PerformanceContext:
    instant = timestamp or datetime(2026, 1, 1, tzinfo=UTC)
    position = WGS84Position(latitude_deg=80, longitude_deg=10)
    return PerformanceContext(
        vessel_state=VesselState(position=position, timestamp=instant),
        position=position,
        time=TimeMetadata(valid_time=instant),
    )


def performance_request() -> PerformanceRequest:
    return PerformanceRequest(
        context=performance_context(),
        requested_metrics=[
            PerformanceMetric.SPEED_CAPABILITY,
            PerformanceMetric.POWER_REQUIREMENT,
        ],
        timestamp=TimeMetadata(valid_time=datetime(2026, 1, 1, tzinfo=UTC)),
    )


def performance_result(**overrides: object) -> PerformanceResult:
    values: dict[str, object] = {
        "quality": QualityMetadata(availability=AvailabilityStatus.MISSING),
        "evidence": EvidenceRecord(status=EvidenceStatus.UNKNOWN),
        "time": TimeMetadata(valid_time=datetime(2026, 1, 1, tzinfo=UTC)),
    }
    values.update(overrides)
    return PerformanceResult(**values)


def test_performance_request_can_be_created() -> None:
    request = performance_request()
    assert isinstance(request.context, PerformanceContext)
    assert request.requested_metrics == [
        PerformanceMetric.SPEED_CAPABILITY,
        PerformanceMetric.POWER_REQUIREMENT,
    ]
    assert request.timestamp.valid_time is not None
    assert request.timestamp.valid_time.tzinfo is not None


def test_performance_request_requires_metrics_and_aware_time() -> None:
    with pytest.raises(ValidationError):
        PerformanceRequest(
            context=performance_context(),
            requested_metrics=[],
            timestamp=TimeMetadata(valid_time=datetime(2026, 1, 1, tzinfo=UTC)),
        )
    with pytest.raises(ValidationError):
        PerformanceRequest(
            context=performance_context(),
            requested_metrics=[PerformanceMetric.CONFIDENCE],
            timestamp=TimeMetadata(valid_time=datetime(2026, 1, 1)),
        )


def test_performance_result_can_be_created_and_preserves_unknown_values() -> None:
    result = performance_result()
    assert result.speed_mps is None
    assert result.power_required_kw is None
    assert result.energy_rate_kw is None
    assert result.ice_capability is None
    assert result.time.valid_time is not None
    assert result.time.valid_time.tzinfo is not None


def test_zero_is_explicit_and_distinct_from_unknown() -> None:
    result = performance_result()
    explicit_zero = result.model_copy(
        update={
            "speed_mps": 0,
            "power_required_kw": 0,
            "energy_rate_kw": 0,
        }
    )
    assert explicit_zero.speed_mps == 0
    assert explicit_zero.power_required_kw == 0
    assert explicit_zero.energy_rate_kw == 0


@pytest.mark.parametrize(
    "field",
    ["speed_mps", "power_required_kw", "energy_rate_kw"],
)
def test_performance_result_rejects_negative_values(field: str) -> None:
    with pytest.raises(ValidationError):
        performance_result(**{field: -1})


def test_performance_metrics_are_request_types_only() -> None:
    assert list(PerformanceMetric) == [
        PerformanceMetric.SPEED_CAPABILITY,
        PerformanceMetric.POWER_REQUIREMENT,
        PerformanceMetric.ENERGY_ESTIMATE,
        PerformanceMetric.ICE_CAPABILITY,
        PerformanceMetric.CONFIDENCE,
    ]


def test_performance_evaluator_is_an_evaluate_protocol() -> None:
    assert hasattr(PerformanceEvaluator, "evaluate")
    hints = get_type_hints(PerformanceEvaluator.evaluate)
    assert hints["request"] is PerformanceRequest
    assert hints["return"] is PerformanceResult


class _NeverCalledEvaluator:
    def evaluate(self, request: PerformanceRequest) -> PerformanceResult:
        raise AssertionError("Registry lookup must not evaluate a model")


def test_model_registry_registers_and_returns_evaluators() -> None:
    registry = PerformanceModelRegistry()
    evaluator = _NeverCalledEvaluator()
    registry.register("generic-vessel-model", evaluator)

    assert registry.get("generic-vessel-model") is evaluator
    assert registry.get("missing-model") is None
    assert registry.model_ids() == ("generic-vessel-model",)
    assert not hasattr(registry, "load")

    with pytest.raises(ValueError):
        registry.register("generic-vessel-model", evaluator)


def test_performance_package_has_no_provider_or_data_source_imports() -> None:
    package_path = Path(performance_package.__file__).parent
    source = "\n".join(path.read_text(encoding="utf-8") for path in package_path.glob("*.py"))
    forbidden_imports = (
        "core.providers",
        "GEBCO",
        "CARRA2",
        "TOPAZ5",
        "neXtSIM",
        "WAM",
        "netCDF4",
        "xarray",
    )
    assert all(item not in source for item in forbidden_imports)


@pytest.mark.parametrize(
    "name",
    [
        "calculate_resistance",
        "friction_resistance",
        "wave_resistance",
        "ice_resistance",
        "predict_speed",
        "power_to_speed",
        "wind_penalty",
        "wave_penalty",
        "current_effect",
        "assess_risk",
        "check_feasibility",
        "plan_route",
    ],
)
def test_performance_framework_exposes_no_calculations(name: str) -> None:
    assert not hasattr(PerformanceRequest, name)
    assert not hasattr(PerformanceResult, name)
    assert not hasattr(PerformanceEvaluator, name)
    assert not hasattr(PerformanceModelRegistry, name)
