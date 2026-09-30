"""Small, self-contained D* Lite + NSGA-III planner for the V2 service.

The research implementation in ``G:\\D-NSGA3`` is intentionally kept as a
reproducibility reference. This module contains the service-facing variant so
the API does not depend on a second checkout or on the current working folder.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

Point = tuple[int, int]


@dataclass(slots=True)
class PlanningGrid:
    latitudes: np.ndarray
    longitudes: np.ndarray
    risk: np.ndarray
    speed_kn: np.ndarray
    obstacle: np.ndarray
    factors: dict[str, np.ndarray]
    start: Point = (0, 0)
    goal: Point = (0, 0)
    cell_size_m: float = 25_000.0
    cell_metadata: dict[Point, dict[str, object]] | None = None

    @property
    def width(self) -> int:
        return int(self.risk.shape[1])

    @property
    def height(self) -> int:
        return int(self.risk.shape[0])

    def in_bounds(self, point: Point) -> bool:
        x, y = point
        return 0 <= x < self.width and 0 <= y < self.height

    def traversable(self, point: Point) -> bool:
        return self.in_bounds(point) and not bool(self.obstacle[point[1], point[0]])

    def coordinate(self, point: Point) -> tuple[float, float]:
        """Return a cell centre for either legacy 1-D or corridor 2-D axes."""

        x, y = point
        if self.latitudes.ndim == 2:
            return float(self.latitudes[y, x]), float(self.longitudes[y, x])
        return float(self.latitudes[y]), float(self.longitudes[x])

    def neighbors(self, point: Point) -> Iterable[Point]:
        x, y = point
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            candidate = (x + dx, y + dy)
            if not self.traversable(candidate):
                continue
            if dx and dy and (
                not self.traversable((x + dx, y))
                or not self.traversable((x, y + dy))
            ):
                continue
            yield candidate

    def distance_km(self, a: Point, b: Point) -> float:
        """Great-circle distance between two cell centres."""

        lat1_deg, lon1_deg = self.coordinate(a)
        lat2_deg, lon2_deg = self.coordinate(b)
        lat1, lon1 = math.radians(lat1_deg), math.radians(lon1_deg)
        lat2, lon2 = math.radians(lat2_deg), math.radians(lon2_deg)
        dlat, dlon = lat2 - lat1, lon2 - lon1
        hav = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(hav)))

    def edge(self, a: Point, b: Point) -> tuple[float, float, float]:
        distance = self.distance_km(a, b)
        risk = 0.5 * (float(self.risk[a[1], a[0]]) + float(self.risk[b[1], b[0]]))
        speed = max(0.1, 0.5 * (float(self.speed_kn[a[1], a[0]]) + float(self.speed_kn[b[1], b[0]])))
        return risk, distance, distance / (1.852 * speed)


class DStarLite:
    """D* Lite search with the three service objectives."""

    def __init__(self, grid: PlanningGrid, mode: str, start: Point | None = None, goal: Point | None = None):
        if mode not in {"risk", "distance", "time"}:
            raise ValueError(f"Unsupported planner mode: {mode}")
        self.grid, self.mode = grid, mode
        self.start, self.goal = start or grid.start, goal or grid.goal
        self.g: dict[Point, float] = {}
        self.rhs: dict[Point, float] = {self.goal: 0.0}
        self.queue: list[tuple[float, float, int, Point]] = []
        self.entries: dict[Point, tuple[float, float]] = {}
        self.counter = 0
        self.expanded = 0
        self._push(self.goal, self._key(self.goal))

    def _g(self, p: Point) -> float:
        return self.g.get(p, math.inf)

    def _rhs(self, p: Point) -> float:
        return self.rhs.get(p, math.inf)

    def _cost(self, a: Point, b: Point) -> float:
        risk, distance, time_h = self.grid.edge(a, b)
        return {"risk": max(risk, 1e-9), "distance": distance, "time": time_h}[self.mode]

    def _heuristic(self, a: Point, b: Point) -> float:
        if self.mode == "risk":
            return 0.0
        distance = self.grid.distance_km(a, b)
        return distance if self.mode == "distance" else distance / (1.852 * max(float(self.grid.speed_kn.max()), 0.1))

    def _key(self, p: Point) -> tuple[float, float]:
        value = min(self._g(p), self._rhs(p))
        return value + self._heuristic(self.start, p), value

    def _push(self, p: Point, key: tuple[float, float]) -> None:
        self.counter += 1
        self.entries[p] = key
        heapq.heappush(self.queue, (key[0], key[1], self.counter, p))

    def _discard(self) -> None:
        while self.queue and self.entries.get(self.queue[0][3]) != (self.queue[0][0], self.queue[0][1]):
            heapq.heappop(self.queue)

    def _update(self, p: Point) -> None:
        if p != self.goal:
            self.rhs[p] = min((self._cost(p, q) + self._g(q) for q in self.grid.neighbors(p)), default=math.inf)
        self.entries.pop(p, None)
        if not math.isclose(self._g(p), self._rhs(p), rel_tol=1e-12, abs_tol=1e-12):
            self._push(p, self._key(p))

    def _compute(self) -> bool:
        limit = self.grid.width * self.grid.height * 20
        while True:
            self._discard()
            top = (self.queue[0][0], self.queue[0][1]) if self.queue else (math.inf, math.inf)
            if not (top < self._key(self.start) or not math.isclose(self._rhs(self.start), self._g(self.start), rel_tol=1e-12, abs_tol=1e-12)):
                return math.isfinite(self._g(self.start)) or math.isfinite(self._rhs(self.start))
            if self.expanded >= limit or not self.queue:
                return False
            old_key_1, old_key_2, _, current = heapq.heappop(self.queue)
            self.entries.pop(current, None)
            old_key = (old_key_1, old_key_2)
            new_key = self._key(current)
            if old_key < new_key:
                self._push(current, self._key(current))
                continue
            if self._g(current) > self._rhs(current):
                self.g[current] = self._rhs(current)
                for predecessor in self.grid.neighbors(current):
                    self._update(predecessor)
            else:
                self.g[current] = math.inf
                self._update(current)
                for predecessor in self.grid.neighbors(current):
                    self._update(predecessor)
            self.expanded += 1

    def plan(self) -> list[Point]:
        if not self.grid.traversable(self.start) or not self.grid.traversable(self.goal) or not self._compute():
            return []
        current, path = self.start, [self.start]
        visited = {current}
        for _ in range(self.grid.width * self.grid.height):
            if current == self.goal:
                return path
            candidates = [q for q in self.grid.neighbors(current) if q not in visited]
            if not candidates:
                return []
            nxt = min(candidates, key=lambda q: (self._cost(current, q) + self._g(q), self._heuristic(q, self.goal), q))
            if not math.isfinite(self._cost(current, nxt) + self._g(nxt)):
                return []
            path.append(nxt)
            visited.add(nxt)
            current = nxt
        return []


def evaluate_path(grid: PlanningGrid, path: Sequence[Point]) -> np.ndarray:
    if len(path) < 2:
        return np.full(3, np.inf, dtype=float)
    risk_total = 0.0
    distance_total = 0.0
    time_total = 0.0
    for a, b in zip(path, path[1:]):
        if not grid.traversable(a) or not grid.traversable(b):
            return np.full(3, np.inf, dtype=float)
        risk, distance, time_h = grid.edge(a, b)
        risk_total += risk
        distance_total += distance
        time_total += time_h
    return np.array([risk_total, distance_total, time_total], dtype=float)


@dataclass(slots=True)
class Individual:
    path: list[Point]
    objectives: np.ndarray

    @classmethod
    def from_path(cls, grid: PlanningGrid, path: Sequence[Point]) -> "Individual":
        return cls(list(path), evaluate_path(grid, path))


def _dominates(a: np.ndarray, b: np.ndarray) -> bool:
    return bool(np.all(a <= b) and np.any(a < b))


def _front(population: Sequence[Individual]) -> list[Individual]:
    return [candidate for index, candidate in enumerate(population)
            if not any(_dominates(other.objectives, candidate.objectives)
                       for other_index, other in enumerate(population) if index != other_index)]


def _references(divisions: int = 8) -> np.ndarray:
    points = [(i, j, divisions - i - j) for i in range(divisions + 1) for j in range(divisions - i + 1)]
    return np.asarray(points, dtype=float) / divisions


def _select(population: list[Individual], size: int, rng: np.random.Generator) -> list[Individual]:
    fronts: list[list[Individual]] = []
    remaining = list(population)
    while remaining:
        current = _front(remaining)
        fronts.append(current)
        keys = {id(item) for item in current}
        remaining = [item for item in remaining if id(item) not in keys]
    selected: list[Individual] = []
    for current in fronts:
        if len(selected) + len(current) <= size:
            selected.extend(current)
            continue
        values = np.vstack([item.objectives for item in current])
        ideal = np.min(np.vstack([item.objectives for item in population]), axis=0)
        scale = np.ptp(values, axis=0)
        scale = np.where(scale > 1e-12, scale, 1.0)
        normalized = (values - ideal) / scale
        references = _references()
        units = references / np.maximum(np.linalg.norm(references, axis=1, keepdims=True), 1e-12)
        projection = normalized @ units.T
        distances = np.sqrt(np.maximum(np.sum(normalized * normalized, axis=1) - np.max(projection, axis=1) ** 2, 0.0))
        assigned = np.argmax(projection, axis=1)
        niche_count = np.zeros(len(references), dtype=int)
        for item in selected:
            value = (item.objectives - ideal) / scale
            niche_count[int(np.argmax(value @ units.T))] += 1
        candidates = set(range(len(current)))
        while len(selected) < size and candidates:
            min_count = min(niche_count[assigned[i]] for i in candidates)
            # Select a reference-point index, not the count stored at that
            # index.  Using the count here can produce an empty choice set.
            niche = min(assigned[i] for i in candidates if niche_count[assigned[i]] == min_count)
            choices = [i for i in candidates if assigned[i] == niche]
            index = min(choices, key=lambda i: distances[i]) if niche_count[niche] == 0 else int(rng.choice(choices))
            selected.append(current[index])
            candidates.remove(index)
            niche_count[niche] += 1
        return selected
    return selected[:size]


def _mutate(grid: PlanningGrid, individual: Individual, rng: np.random.Generator) -> Individual:
    path = individual.path
    if len(path) < 4:
        return Individual.from_path(grid, path)
    index = int(rng.integers(1, len(path) - 1))
    previous, following = path[index - 1], path[index + 1]
    choices = [candidate for candidate in grid.neighbors(previous) if following in set(grid.neighbors(candidate))]
    if choices:
        candidate_path = list(path)
        candidate_path[index] = choices[int(rng.integers(len(choices)))]
        return Individual.from_path(grid, candidate_path)
    return Individual.from_path(grid, path)


def _crossover(grid: PlanningGrid, first: Individual, second: Individual, rng: np.random.Generator) -> tuple[Individual, Individual]:
    positions = {node: index for index, node in enumerate(second.path[1:-1], start=1)}
    common = [(index, positions[node]) for index, node in enumerate(first.path[1:-1], start=1) if node in positions]
    if not common:
        return Individual.from_path(grid, first.path), Individual.from_path(grid, second.path)
    left, right = common[int(rng.integers(len(common)))]
    child_a = first.path[:left] + second.path[right:]
    child_b = second.path[:right] + first.path[left:]
    valid = lambda path: path and path[0] == grid.start and path[-1] == grid.goal and all(
        b in set(grid.neighbors(a)) for a, b in zip(path, path[1:])
    )
    return (
        Individual.from_path(grid, child_a if valid(child_a) else first.path),
        Individual.from_path(grid, child_b if valid(child_b) else second.path),
    )


def run_nsga3(grid: PlanningGrid, population_size: int = 36, generations: int = 20, seed: int = 42) -> list[Individual]:
    """Run D* Lite seeded NSGA-III and return a unique Pareto front."""

    rng = np.random.default_rng(seed)
    seed_paths = [DStarLite(grid, mode).plan() for mode in ("risk", "distance", "time")]
    if any(not path for path in seed_paths):
        raise RuntimeError("No feasible path exists for one of the D* Lite objectives")
    population = [Individual.from_path(grid, seed_paths[index % 3]) for index in range(population_size)]
    for index in range(3, population_size):
        population[index] = _mutate(grid, population[index], rng)
    for _ in range(generations):
        offspring: list[Individual] = []
        while len(offspring) < population_size:
            first, second = rng.choice(population, 2, replace=False)
            child_a, child_b = _crossover(grid, first, second, rng)
            if rng.random() < 0.85:
                child_a = _mutate(grid, child_a, rng)
            if rng.random() < 0.85:
                child_b = _mutate(grid, child_b, rng)
            offspring.extend((child_a, child_b))
        population = _select(population + offspring[:population_size], population_size, rng)
    front = _front(population)
    unique: dict[tuple[Point, ...], Individual] = {}
    for item in front:
        unique.setdefault(tuple(item.path), item)
    return sorted(unique.values(), key=lambda item: tuple(float(x) for x in item.objectives))


def representative_routes(front: Sequence[Individual]) -> dict[str, Individual]:
    if not front:
        return {}
    return {
        "lowest_risk": min(front, key=lambda item: item.objectives[0]),
        "shortest_distance": min(front, key=lambda item: item.objectives[1]),
        "fastest_time": min(front, key=lambda item: item.objectives[2]),
    }
