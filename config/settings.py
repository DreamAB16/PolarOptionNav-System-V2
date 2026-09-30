"""Application settings with environment-variable overrides."""

from pydantic_settings import BaseSettings, SettingsConfigDict


# Northeast Passage research extent.  It is intentionally configured once so
# rendering, static preprocessing and the global planner share the same area.
NORTHEAST_PASSAGE_REGION = {
    "south": 60.0,
    "north": 90.0,
    # Display longitudes remain WGS84 [-180, 180].  Planning code converts
    # these endpoints to a continuous [0, 360] interval (30--191.023056).
    "west": 30.0,
    "east": -168.976944,
    "planning_west": 30.0,
    "planning_east": 191.023056,
}
PLANNING_CELL_SIZE_M = 25_000


class Settings(BaseSettings):
    app_name: str = "PolarOptionNav-System-V2"
    environment: str = "development"
    api_prefix: str = "/api"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", extra="ignore")


settings = Settings()
