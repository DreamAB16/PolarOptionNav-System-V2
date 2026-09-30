"""In-memory repository for provider-neutral environment snapshots."""

from datetime import datetime

from core.contracts import ensure_utc
from core.environment.enums import EnvironmentScale, EnvironmentVariable
from core.environment.fields import EnvironmentField
from core.environment.snapshot import EnvironmentScaleSnapshot

from .models import EnvironmentSnapshotKey


class EnvironmentRepository:
    def __init__(self) -> None:
        self._snapshots: dict[EnvironmentSnapshotKey, EnvironmentScaleSnapshot] = {}

    def register_snapshot(self, snapshot: EnvironmentScaleSnapshot) -> None:
        valid_time = snapshot.time_context.valid_time
        if valid_time is None:
            raise ValueError("Snapshot must define time_context.valid_time")
        key = EnvironmentSnapshotKey(scale=snapshot.scale, valid_time=valid_time)
        self._snapshots[key] = snapshot

    def get_snapshot(self, scale: EnvironmentScale, valid_time: datetime) -> EnvironmentScaleSnapshot | None:
        key = EnvironmentSnapshotKey(scale=scale, valid_time=ensure_utc(valid_time))
        return self._snapshots.get(key)

    def available_times(self, scale: EnvironmentScale) -> tuple[datetime, ...]:
        """Return registered valid times for one scale in deterministic order."""

        return tuple(sorted(key.valid_time for key in self._snapshots if key.scale == scale))

    def get_field(
        self,
        snapshot: EnvironmentScaleSnapshot,
        field_type: EnvironmentVariable,
    ) -> EnvironmentField | None:
        return snapshot.fields.get(field_type)


__all__ = ["EnvironmentRepository"]
