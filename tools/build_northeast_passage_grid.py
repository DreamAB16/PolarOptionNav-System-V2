"""Build the persistent fixed 25 km Northeast Passage planning grid."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.planner_service.static_grid import build_static_grid

if __name__ == "__main__":
    print(build_static_grid())
