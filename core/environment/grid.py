"""Local ENU grid geometry for environment fields."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.contracts import LocalENUFrameRef


class GridSpec(BaseModel):
    """A rectangular cell grid whose extent is expressed in local ENU metres."""

    model_config = ConfigDict(frozen=True)

    frame: LocalENUFrameRef
    resolution_m: float = Field(gt=0)
    x_min_m: float
    y_min_m: float
    x_max_m: float
    y_max_m: float
    width_cells: int = Field(gt=0)
    height_cells: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_extent(self) -> "GridSpec":
        if self.x_max_m <= self.x_min_m or self.y_max_m <= self.y_min_m:
            raise ValueError("Grid extent must have positive width and height.")
        expected_width = self.width_cells * self.resolution_m
        expected_height = self.height_cells * self.resolution_m
        if abs((self.x_max_m - self.x_min_m) - expected_width) > 1e-6:
            raise ValueError("Grid x extent must equal width_cells * resolution_m.")
        if abs((self.y_max_m - self.y_min_m) - expected_height) > 1e-6:
            raise ValueError("Grid y extent must equal height_cells * resolution_m.")
        return self
