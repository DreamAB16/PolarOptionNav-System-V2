import numpy as np

from services.planner_service.dnsga3 import DStarLite, PlanningGrid, run_nsga3


def test_dnsga3_returns_pareto_paths_for_a_clear_grid() -> None:
    size = 12
    grid = PlanningGrid(
        latitudes=np.linspace(75.0, 76.0, size),
        longitudes=np.linspace(30.0, 32.0, size),
        risk=np.full((size, size), 0.2),
        speed_kn=np.full((size, size), 12.0),
        obstacle=np.zeros((size, size), dtype=bool),
        factors={"ice": np.zeros((size, size))},
        start=(0, 0),
        goal=(size - 1, size - 1),
    )

    front = run_nsga3(grid, population_size=6, generations=1, seed=7)

    assert front
    assert all(item.path[0] == grid.start and item.path[-1] == grid.goal for item in front)
    assert all(item.objectives.shape == (3,) for item in front)


def test_dstar_lite_never_enters_a_land_obstacle() -> None:
    size = 5
    obstacle = np.zeros((size, size), dtype=bool)
    obstacle[2, 1:4] = True  # A land strip; the route must go around it.
    grid = PlanningGrid(
        latitudes=np.linspace(75.0, 76.0, size), longitudes=np.linspace(30.0, 32.0, size),
        risk=np.full((size, size), 0.2), speed_kn=np.full((size, size), 12.0), obstacle=obstacle,
        factors={"ice": np.zeros((size, size))}, start=(0, 2), goal=(4, 2),
    )
    path = DStarLite(grid, "distance").plan()
    assert path
    assert all(not obstacle[y, x] for x, y in path)
