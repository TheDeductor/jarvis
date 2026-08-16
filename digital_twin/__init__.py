"""
digital_twin — Simplified Behavioral Building Simulation Engine
===============================================================

DISCLAIMER:
  This is a simplified behavioral digital twin.
  It is NOT physically calibrated, NOT EnergyPlus, NOT CFD.
  It uses deterministic first-order equations for plausible behavior.

Public API:
  from digital_twin import BuildingTwin
  from digital_twin.models import RoomConfig, RoomState
  from digital_twin.scenario import WeatherProfile, get_outside_temperature
"""

from .building import BuildingTwin
from .models import RoomConfig, RoomState
from .scenario import WeatherProfile

__all__ = ["BuildingTwin", "RoomConfig", "RoomState", "WeatherProfile"]
__version__ = "1.0.0"
