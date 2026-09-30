"""Nearest-cell spatial resolution over an existing local ENU grid."""

from math import hypot

from pydantic import BaseModel, ConfigDict, Field

from core.contracts import LocalENUPosition, WGS84Position
from core.providers.common.coordinates import wgs84_to_local_enu
from core.environment.grid import GridSpec


class GridCellIndex(BaseModel):
    model_config = ConfigDict(frozen=True)

    row: int = Field(ge=0)
    column: int = Field(ge=0)
    distance_to_cell_center: float = Field(ge=0)


class SpatialResolver:
    """Resolve a local ENU position to its nearest grid cell without interpolation."""

    def __init__(self, grid: GridSpec) -> None:
        self.grid = grid

    def resolve(self, position: LocalENUPosition | WGS84Position) -> GridCellIndex | None:
        if isinstance(position, WGS84Position):
            position = wgs84_to_local_enu(position, self.grid.frame)
        if not isinstance(position, LocalENUPosition):
            raise TypeError("SpatialResolver expects a WGS84Position or LocalENUPosition")
        if position.frame.frame_id != self.grid.frame.frame_id:
            return None
        if not (
            self.grid.x_min_m <= position.x_east_m < self.grid.x_max_m
            and self.grid.y_min_m <= position.y_north_m < self.grid.y_max_m
        ):
            return None
        column = min(int((position.x_east_m - self.grid.x_min_m) / self.grid.resolution_m), self.grid.width_cells - 1)
        row = min(int((position.y_north_m - self.grid.y_min_m) / self.grid.resolution_m), self.grid.height_cells - 1)
        center_x = self.grid.x_min_m + (column + 0.5) * self.grid.resolution_m
        center_y = self.grid.y_min_m + (row + 0.5) * self.grid.resolution_m
        return GridCellIndex(
            row=row,
            column=column,
            distance_to_cell_center=hypot(position.x_east_m - center_x, position.y_north_m - center_y),
        )


__all__ = ["GridCellIndex", "SpatialResolver"]
