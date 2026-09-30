"""Vessel service facade and provider boundary."""

from .depth_safety import DepthSafetyService
from .service import VesselService
from core.vessel import VesselProfile

__all__ = ["DepthSafetyService", "VesselProfile", "VesselService"]
