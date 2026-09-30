"""Provider-neutral orchestration for environment queries."""

from core.contracts import AvailabilityStatus, EvidenceRecord, EvidenceStatus, QualityMetadata
from core.environment.repository import EnvironmentRepository
from core.providers.common.coordinates import wgs84_to_local_enu

from .models import EnvironmentQueryRequest, EnvironmentSample
from .scale import ScaleResolver
from .spatial import SpatialResolver
from .temporal import TimeResolver


class EnvironmentQueryService:
    def __init__(
        self,
        repository: EnvironmentRepository,
        scale_resolver: ScaleResolver,
        time_resolver: TimeResolver,
        spatial_resolvers: dict,
    ) -> None:
        self.repository = repository
        self.scale_resolver = scale_resolver
        self.time_resolver = time_resolver
        self.spatial_resolvers = spatial_resolvers

    def query(self, request: EnvironmentQueryRequest) -> EnvironmentSample:
        scale = self.scale_resolver.resolve(request.scale)
        spatial = self.spatial_resolvers.get(scale)
        if spatial is None:
            raise ValueError(f"No spatial resolver configured for scale: {scale.value}")

        time_match = self.time_resolver.resolve(
            request.target_time,
            self.repository.available_times(scale),
        )
        local_position = wgs84_to_local_enu(request.position, spatial.grid.frame)
        fields = {field_type: None for field_type in request.requested_fields}
        snapshot = (
            self.repository.get_snapshot(scale, time_match.matched_time)
            if time_match.matched_time is not None
            else None
        )
        cell = spatial.resolve(request.position)
        if snapshot is not None and cell is not None:
            for field_type in request.requested_fields:
                fields[field_type] = self.repository.get_field(snapshot, field_type)

        available = snapshot is not None and cell is not None and all(value is not None for value in fields.values())
        status = AvailabilityStatus.AVAILABLE if available else AvailabilityStatus.MISSING
        return EnvironmentSample(
            position=local_position,
            requested_time=request.target_time,
            matched_time=time_match.matched_time,
            fields=fields,
            quality=QualityMetadata(
                availability=status,
                source="environment-query",
                reason=None if available else "requested environment data unavailable",
            ),
            availability=status,
            time_match=time_match,
        )


__all__ = ["EnvironmentQueryService"]
