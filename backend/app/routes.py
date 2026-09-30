"""HTTP routes. They depend on service interfaces, never on data files."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Path as ApiPath, Query, Response
from pydantic import BaseModel, Field

from core.models import (
    BathymetryState,
    CurrentState,
    DepthSafetyResult,
    EnvironmentTimeState,
    EnvironmentState,
    EnvironmentCell,
    LegacyEnvironmentState,
    Position,
    RouteResult,
    SeaIceState,
    WindState,
    VesselState,
    WaveState,
)
from core.vessel import VesselProfile
from services.chart_service import ChartService
from services.environment_service import EnvironmentService
from services.environment_service import EnvironmentGridBuilder
from services.planner_service import PlannerService
from services.vessel_service import VesselService

router = APIRouter(prefix="/api")


class WindFieldPoint(BaseModel):
    id: str
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class WindFieldRequest(BaseModel):
    time: datetime
    points: list[WindFieldPoint]


class CurrentFieldPoint(BaseModel):
    id: str
    lat: float
    lon: float


class CurrentFieldRequest(BaseModel):
    time: datetime
    points: list[CurrentFieldPoint]


class WaveFieldPoint(BaseModel):
    id: str
    lat: float
    lon: float


class WaveFieldRequest(BaseModel):
    time: datetime
    points: list[WaveFieldPoint]


class EnvironmentBatchPoint(BaseModel):
    id: str
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class EnvironmentBatchRequest(BaseModel):
    time: datetime
    points: list[EnvironmentBatchPoint]


class PlannerPoint(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class PlannerRequest(BaseModel):
    start: PlannerPoint
    goal: PlannerPoint
    departure_time: datetime
    grid_size: int = Field(default=20, ge=12, le=32)
    cell_size_m: int = Field(default=25000, ge=25000, le=25000, description="Fixed planning cell edge in metres")
    population_size: int = Field(default=36, ge=6, le=120)
    generations: int = Field(default=20, ge=1, le=100)
    seed: int = Field(default=42, ge=0)


class PlannerEnvironmentCellRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    time: datetime


chart_service = ChartService()
environment_service = EnvironmentService()
environment_grid = EnvironmentGridBuilder(environment_service)
vessel_service = VesselService()
planner_service = PlannerService()


@router.get("/status", tags=["system"])
def status() -> dict[str, str]:
    return {"system": "PolarOptionNav-System-V2", "status": "running"}


@router.get("/chart", tags=["chart"])
def chart() -> dict[str, object]:
    return chart_service.get_overview()


@router.get("/chart/layers", tags=["chart"])
def chart_layers() -> dict[str, list[dict[str, object]]]:
    """List authorised chart layers without exposing storage details."""

    return {"layers": chart_service.get_layers()}


@router.get("/chart/layers/{layer_id}", tags=["chart"])
def chart_layer_features(layer_id: str) -> dict[str, object]:
    """Serve one authorised chart layer as frontend-ready GeoJSON."""

    try:
        return chart_service.get_layer_features(layer_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Chart layer not found.") from error


@router.get("/environment", response_model=LegacyEnvironmentState, tags=["environment"])
def environment() -> LegacyEnvironmentState:
    return environment_service.get_state()


@router.get("/environment/layers", tags=["environment"])
def environment_layers() -> dict[str, list[dict[str, str]]]:
    """List currently registered environmental layers and their readiness state."""

    return {"layers": environment_service.get_available_layers()}


@router.get("/environment/time", response_model=EnvironmentTimeState, tags=["environment"])
def environment_time() -> EnvironmentTimeState:
    """Return the UTC clock used when a time-aware request omits ``time``."""

    return environment_service.get_time_state()


@router.get("/environment/query", response_model=EnvironmentState, tags=["environment"])
def query_complete_environment(
    lat: float = Query(..., ge=-90, le=90, description="WGS84 latitude in decimal degrees"),
    lon: float = Query(..., ge=-180, le=180, description="WGS84 longitude in decimal degrees"),
    time: datetime = Query(..., description="Requested UTC instant in ISO-8601 format"),
) -> EnvironmentState:
    """Return bathymetry, ice, wind, current and wave state in one response."""

    return environment_service.query_complete_environment(lat, lon, time)


@router.get("/environment/grid", tags=["environment"])
def environment_grid_metadata() -> dict[str, object]:
    """Describe the unified grid contract without exposing source files."""

    return environment_grid.metadata()


@router.get("/environment/grid/query", response_model=EnvironmentCell, tags=["environment"])
def query_environment_grid(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    time: datetime = Query(..., description="Requested UTC instant in ISO-8601 format"),
) -> EnvironmentCell:
    """Return one source-faithful unified environment cell."""

    return environment_grid.query(lat, lon, time)


@router.post("/environment/grid/query/batch", tags=["environment"])
def query_environment_grid_batch(request: EnvironmentBatchRequest) -> dict[str, object]:
    """Return up to 1000 unified environment cells."""

    points = [(point.id, Position(latitude=point.lat, longitude=point.lon)) for point in request.points]
    try:
        return {"results": environment_grid.query_many(points, request.time)}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/environment/query/batch", tags=["environment"])
def query_complete_environment_batch(request: EnvironmentBatchRequest) -> dict[str, object]:
    """Return complete environment states for up to 500 WGS84 points."""

    if not request.points:
        raise HTTPException(status_code=400, detail="环境采样点不能为空。")
    if len(request.points) > 500:
        raise HTTPException(status_code=400, detail="最多允许500个环境采样点。")
    points = [
        (point.id, Position(latitude=point.lat, longitude=point.lon))
        for point in request.points
    ]
    try:
        results = environment_service.query_complete_environment_batch(points, request.time)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"results": results}


@router.get("/environment/ice/query", response_model=SeaIceState, tags=["environment"])
def query_ice(
    lat: float = Query(..., ge=-90, le=90, description="WGS84 latitude in decimal degrees"),
    lon: float = Query(..., ge=-180, le=180, description="WGS84 longitude in decimal degrees"),
    time: datetime | None = Query(None, description="Requested UTC instant in ISO-8601 format"),
) -> SeaIceState:
    """Return the nearest available sea-ice state for requested or managed time."""

    try:
        return environment_service.query_ice(
            Position(latitude=lat, longitude=lon),
            time,
        )
    except (LookupError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/environment/wind/query", response_model=WindState, tags=["environment"])
def query_wind(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    time: datetime | None = Query(None, description="Requested UTC instant in ISO-8601 format"),
) -> WindState:
    try:
        return environment_service.query_wind(Position(latitude=lat, longitude=lon), time)
    except (LookupError, ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/environment/wind/field", tags=["environment"])
def query_wind_field(request: WindFieldRequest) -> dict[str, object]:
    """Return one batched 10 m wind sample for a map viewport."""
    if len(request.points) > 500:
        raise HTTPException(status_code=400, detail="最多允许500个风场采样点。")
    try:
        points = [(point.id, Position(latitude=point.lat, longitude=point.lon)) for point in request.points]
        result = environment_service.query_wind_field(points, request.time)
        return result
    except (LookupError, ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/environment/current/query", response_model=CurrentState, tags=["environment"])
def query_current(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    time: datetime | None = Query(None, description="Requested UTC instant in ISO-8601 format"),
) -> CurrentState:
    """Return geographic surface-current components at one WGS84 position."""

    try:
        return environment_service.query_current(Position(latitude=lat, longitude=lon), time)
    except (LookupError, ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/environment/current/field", tags=["environment"])
def query_current_field(request: CurrentFieldRequest) -> dict[str, object]:
    """Return one batched TOPAZ5 surface-current sample for a map viewport."""

    if not request.points:
        raise HTTPException(status_code=400, detail="海流采样点不能为空。")
    if len(request.points) > 500:
        raise HTTPException(status_code=400, detail="最多允许500个海流采样点。")
    if any(not -90 <= point.lat <= 90 or not -180 <= point.lon <= 180 for point in request.points):
        raise HTTPException(status_code=400, detail="海流采样点经纬度无效。")
    try:
        points = [(point.id, Position(latitude=point.lat, longitude=point.lon)) for point in request.points]
        return environment_service.query_current_field(points, request.time)
    except (LookupError, ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/environment/wave/query", response_model=WaveState, tags=["environment"])
def query_wave(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    time: datetime | None = Query(None, description="Requested UTC instant in ISO-8601 format"),
) -> WaveState:
    """Return significant height, peak period and mean wave-from direction."""

    try:
        return environment_service.query_wave(Position(latitude=lat, longitude=lon), time)
    except (LookupError, ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/environment/wave/field", tags=["environment"])
def query_wave_field(request: WaveFieldRequest) -> dict[str, object]:
    """Return one batched WAM Arctic sample for a map viewport."""

    if not request.points:
        raise HTTPException(status_code=400, detail="海浪采样点不能为空。")
    if len(request.points) > 500:
        raise HTTPException(status_code=400, detail="最多允许500个海浪采样点。")
    if any(not -90 <= point.lat <= 90 or not -180 <= point.lon <= 180 for point in request.points):
        raise HTTPException(status_code=400, detail="海浪采样点经纬度无效。")
    try:
        points = [(point.id, Position(latitude=point.lat, longitude=point.lon)) for point in request.points]
        return environment_service.query_wave_field(points, request.time)
    except (LookupError, ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/environment/ice/tile/{z}/{x}/{y}.png", tags=["environment"])
def ice_tile(
    z: int = ApiPath(..., ge=0, le=10),
    x: int = ApiPath(..., ge=0),
    y: int = ApiPath(..., ge=0),
    dataset_date: str | None = Query(None, alias="date", description="Processed sea-ice date: YYYYMMDD"),
    time: datetime | None = Query(None, description="Requested UTC instant in ISO-8601 format"),
    time_index: int = Query(0, ge=0, description="Reserved processed dataset time index"),
) -> Response:
    """Return a cached sea-ice concentration tile; the NC file remains private."""

    try:
        if dataset_date is not None and time is not None:
            raise ValueError("Use either date or time, not both.")
        png = environment_service.get_ice_tile(z, x, y, dataset_date, time_index, time)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/environment/ice/thickness/tile/{z}/{x}/{y}.png", tags=["environment"])
def ice_thickness_tile(
    z: int = ApiPath(..., ge=0, le=10),
    x: int = ApiPath(..., ge=0),
    y: int = ApiPath(..., ge=0),
    dataset_date: str | None = Query(None, alias="date", description="Processed sea-ice date: YYYYMMDD"),
    time: datetime | None = Query(None, description="Requested UTC instant in ISO-8601 format"),
    time_index: int = Query(0, ge=0, description="Reserved processed dataset time index"),
) -> Response:
    """Return a cached sea-ice thickness tile without changing concentration API behaviour."""

    try:
        if dataset_date is not None and time is not None:
            raise ValueError("Use either date or time, not both.")
        png = environment_service.get_ice_thickness_tile(
            z,
            x,
            y,
            dataset_date,
            time_index,
            time,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/environment/ice/polar/tile/{z}/{x}/{y}.png", tags=["environment"])
def ice_polar_tile(
    z: int = ApiPath(..., ge=0, le=10),
    x: int = ApiPath(..., ge=0),
    y: int = ApiPath(..., ge=0),
    dataset_date: str | None = Query(None, alias="date"),
    time: datetime | None = Query(None),
    time_index: int = Query(0, ge=0),
) -> Response:
    """Return a native EPSG:3413 sea-ice concentration tile."""

    try:
        if dataset_date is not None and time is not None:
            raise ValueError("Use either date or time, not both.")
        png = environment_service.get_ice_polar_tile(
            z,
            x,
            y,
            dataset_date,
            time_index,
            time,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/environment/ice/thickness/polar/tile/{z}/{x}/{y}.png", tags=["environment"])
def ice_thickness_polar_tile(
    z: int = ApiPath(..., ge=0, le=10),
    x: int = ApiPath(..., ge=0),
    y: int = ApiPath(..., ge=0),
    dataset_date: str | None = Query(None, alias="date"),
    time: datetime | None = Query(None),
    time_index: int = Query(0, ge=0),
) -> Response:
    """Return a native EPSG:3413 sea-ice thickness tile."""

    try:
        if dataset_date is not None and time is not None:
            raise ValueError("Use either date or time, not both.")
        png = environment_service.get_ice_polar_tile(
            z,
            x,
            y,
            dataset_date,
            time_index,
            time,
            render_mode="thickness",
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/environment/bathymetry/query", response_model=BathymetryState, tags=["environment"])
def query_bathymetry(
    lat: float = Query(..., ge=-90, le=90, description="WGS84 latitude in decimal degrees"),
    lon: float = Query(..., ge=-180, le=180, description="WGS84 longitude in decimal degrees"),
) -> BathymetryState:
    """Return positive-down GEBCO water depth at the nearest grid cell."""

    return environment_service.query_bathymetry(lat, lon)


@router.get(
    "/environment/bathymetry/safety",
    response_model=DepthSafetyResult,
    tags=["environment"],
)
def query_bathymetry_safety(
    lat: float = Query(..., ge=-90, le=90, description="WGS84 latitude in decimal degrees"),
    lon: float = Query(..., ge=-180, le=180, description="WGS84 longitude in decimal degrees"),
) -> DepthSafetyResult:
    """Evaluate GEBCO depth against the vessel's configured draft plus UKC."""

    bathymetry = environment_service.query_bathymetry(lat, lon)
    return vessel_service.evaluate_depth_safety(bathymetry.depth)


@router.get("/environment/bathymetry/tiles/{z}/{x}/{y}.png", tags=["environment"])
def bathymetry_tile(
    z: int = ApiPath(..., ge=0, le=14),
    x: int = ApiPath(..., ge=0),
    y: int = ApiPath(..., ge=0),
) -> Response:
    """Return a cached, dynamically downsampled GEBCO XYZ raster tile."""

    try:
        png = environment_service.get_bathymetry_tile(z, x, y)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/environment/bathymetry/polar/tile/{z}/{x}/{y}.png", tags=["environment"])
def polar_bathymetry_tile(
    z: int = ApiPath(..., ge=0, le=14),
    x: int = ApiPath(..., ge=0),
    y: int = ApiPath(..., ge=0),
) -> Response:
    """Return a native EPSG:3413 bathymetry PNG for Arctic map modes."""

    try:
        png = environment_service.get_polar_bathymetry_tile(z, x, y)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/vessel", response_model=VesselState, tags=["vessel"])
def vessel() -> VesselState:
    return vessel_service.get_state()


@router.get("/vessel/current", response_model=VesselProfile, tags=["vessel"])
def current_vessel() -> VesselProfile:
    """Return the configured vessel profile used by future environment-grid consumers."""

    return vessel_service.get_current_profile()


@router.post("/planner", response_model=RouteResult, tags=["planner"])
def planner(request: PlannerRequest | None = None) -> RouteResult:
    if request is None:
        return planner_service.plan()
    start = Position(latitude=request.start.lat, longitude=request.start.lon)
    goal = Position(latitude=request.goal.lat, longitude=request.goal.lon)
    if abs(start.latitude - goal.latitude) < 1e-8 and abs(start.longitude - goal.longitude) < 1e-8:
        raise HTTPException(status_code=422, detail="起点与终点不能相同。")
    result = planner_service.plan(
        start=start,
        goal=goal,
        timestamp=request.departure_time,
        grid_size=request.grid_size,
        cell_size_m=request.cell_size_m,
        population_size=request.population_size,
        generations=request.generations,
        seed=request.seed,
    )
    if result.status == "failed":
        raise HTTPException(status_code=422, detail=result.risk)
    return result


@router.get("/planner/grid/spec", tags=["planner"])
def planner_grid_spec() -> dict[str, object]:
    """Stable contract for the planner raster and replaceable data sources."""

    return {
        "cell_size_m": 25_000,
        "coordinate_reference": "WGS84 cell centres with geodesic bounds",
        "risk_layers": ["rio", "fog", "wind", "wave", "depth", "combined"],
        "environment_fields": ["depth", "ice", "wind", "wave", "current"],
        "missing_data_policy": "deterministic_gap_fill_v1_with_quality=synthetic",
        "provider_policy": "real provider first; adapter fills only unavailable fields",
    }


@router.get("/planner/{plan_id}/grid", tags=["planner"])
def planner_grid(plan_id: str) -> dict[str, object]:
    """Return the planner matrix snapshot; map rendering uses viewport cells."""

    grid = planner_service.get_plan_grid(plan_id)
    if grid is None:
        raise HTTPException(status_code=404, detail="规划结果不存在或已过期。")
    return {"plan_id": plan_id, **grid}


@router.get("/planner/{plan_id}/grid/{cell_id}", tags=["planner"])
def planner_grid_cell_detail(plan_id: str, cell_id: str) -> dict[str, object]:
    """Return one complete fixed-grid cell from a planning snapshot."""

    cell = planner_service.get_plan_cell(plan_id, cell_id)
    if cell is None:
        raise HTTPException(status_code=404, detail="规划栅格或栅格单元不存在。")
    return {"plan_id": plan_id, **cell}


@router.post("/planner/grid/cell", tags=["planner"])
def planner_grid_cell(request: PlannerEnvironmentCellRequest) -> dict[str, object]:
    """Return one planner cell's complete environment sample and provenance."""

    position = Position(latitude=request.lat, longitude=request.lon)
    sample = planner_service.environment_model.adapter.sample(position, request.time, planner_service.vessel_profile)
    return {
        "center": {"latitude": request.lat, "longitude": request.lon},
        "cell_size_m": 25_000,
        "environment": sample.state.model_dump(mode="json"),
        "quality": sample.quality,
        "sources": sample.sources,
    }


@router.get("/environment/grid/northern", tags=["environment"])
def northern_environment_grid(
    time: datetime = Query(default=datetime(2025, 2, 15, 12), description="One-day UTC environment timestamp"),
    south: float = Query(default=60.0, ge=0.0, le=90.0),
    north: float = Query(default=80.0, ge=0.0, le=90.0),
    west: float = Query(default=-180.0, ge=-180.0, le=180.0),
    east: float = Query(default=180.0, ge=-180.0, le=180.0),
    max_cells: int = Query(default=1600, ge=100, le=3000),
) -> dict[str, object]:
    """Query fixed Northeast Passage 25 km cells visible in a viewport."""

    try:
        return planner_service.get_northern_grid(time, south, north, west, east, max_cells)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/environment/grid/cell", tags=["environment"])
def inspect_environment_grid_cell(
    lat: float = Query(..., ge=0.0, le=90.0),
    lon: float = Query(..., ge=-180.0, le=180.0),
    time: datetime = Query(default=datetime(2025, 2, 15, 12)),
) -> dict[str, object]:
    """Inspect one fixed Northeast Passage cell without creating a task."""

    return planner_service.inspect_environment_cell(Position(latitude=lat, longitude=lon), time)
