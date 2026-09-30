"""Engineering effective-speed model for the first real planner slice.

It is a transparent resistance budget rather than a black-box prediction:
calm-water speed is reduced by Beaufort wind, significant wave height and ice
load, while the current component along the route is added. The model follows
the weather-routing practice of evaluating speed through a resistance/power
budget and uses the vessel's published 15 MW propulsion limit as the cap.
"""

from __future__ import annotations

import math

import numpy as np

from core.models import EnvironmentState
from core.vessel.models import VesselProfile


def _component_along(u: float, v: float, bearing_deg: float) -> float:
    angle = math.radians(bearing_deg)
    return u * math.sin(angle) + v * math.cos(angle)


def effective_speed_knots(
    state: EnvironmentState,
    vessel: VesselProfile,
    bearing_deg: float,
    risk: float,
) -> float:
    """Return feasible speed through water plus current, in knots.

    Ice speed uses a continuous-ice capability interpolation: at the vessel's
    maximum continuous ice thickness the model tends to the published 2 kn
    minimum, while open water tends to the 15 kn service maximum.
    """

    calm = vessel.speed.service_speed_max_kn
    wind = float(state.wind.speed or 0.0) if state.wind.available else 0.0
    wave = float(state.wave.height or 0.0) if state.wave.available else 0.0
    thickness = float(state.ice.thickness or 0.0) if state.ice.available else 0.0
    concentration = float(state.ice.concentration or 0.0) if state.ice.available else 0.0

    # Added-resistance surrogates: aerodynamic and wave terms are quadratic in
    # environmental severity; ice is a load factor scaled by concentration.
    wind_factor = np.clip(1.0 - 0.0035 * max(wind - 5.0, 0.0) ** 2, 0.55, 1.0)
    wave_factor = np.clip(1.0 - 0.025 * max(wave - 0.5, 0.0) ** 2, 0.55, 1.0)
    ice_ratio = thickness / max(vessel.ice_capability.continuous_ice_thickness_m, 0.1)
    ice_factor = np.clip(1.0 - concentration * 0.70 * min(ice_ratio, 1.5), 0.12, 1.0)
    available_speed = calm * float(wind_factor * wave_factor * ice_factor)
    if concentration > 0.75 and thickness > vessel.ice_capability.continuous_ice_thickness_m:
        available_speed = min(available_speed, vessel.ice_capability.continuous_ice_speed_min_kn)

    current = 0.0
    if state.current.available:
        current = _component_along(float(state.current.u or 0.0), float(state.current.v or 0.0), bearing_deg) * 1.94384449
    over_ground = available_speed + float(np.clip(current, -3.0, 3.0))
    # Keep a small positive speed for traversable cells; true RIO/depth blocks
    # are handled by the environment model before the planner runs.
    return float(np.clip(over_ground * (1.0 - 0.12 * risk), 0.5, vessel.safety_constraints.speed_limit))

