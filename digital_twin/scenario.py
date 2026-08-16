"""
scenario.py
===========
Weather profiles and baseline HVAC controller for the Digital Twin.

This module provides:
  - WeatherProfile        : deterministic outdoor temperature over simulation time
  - BaselineController    : fixed HVAC schedule (no complaint response)
  - get_baseline_setpoint : returns setpoint for a given simulation time

DISCLAIMER
----------
Weather data here is a SIMULATION INPUT, not real weather data.
It is NOT from a weather API, sensor, or historical record.
Values are chosen to create a plausible hot-day scenario for testing.

Units
-----
  temperature  → °C
  time         → minutes (simulation time, 0 = midnight or start of day)
"""

from __future__ import annotations

from enum import Enum

import numpy as np


# ---------------------------------------------------------------------------
# Weather profiles
# ---------------------------------------------------------------------------

class WeatherProfile(Enum):
    """Available weather scenarios."""
    CONSTANT_HOT = "constant_hot"          # 34°C constant
    DIURNAL_HOT_DAY = "diurnal_hot_day"   # Time-varying hot day


def get_outside_temperature(
    simulation_time_minutes: float,
    profile: WeatherProfile = WeatherProfile.CONSTANT_HOT,
    constant_temp_c: float = 34.0,
) -> float:
    """
    Return outdoor temperature for a given simulation time.

    This function is DETERMINISTIC: the same inputs always produce the same output.

    CONSTANT_HOT profile:
      Returns constant_temp_c regardless of time.
      Default: 34°C (hot-day scenario from project specification).

    DIURNAL_HOT_DAY profile:
      Piecewise linear interpolation over a simulated hot day.
      Waypoints (simulation assumption — NOT real weather data):

        08:00 (480 min)  → 28°C
        10:00 (600 min)  → 30°C
        12:00 (720 min)  → 33°C
        14:00 (840 min)  → 35°C
        16:00 (960 min)  → 34°C
        18:00 (1080 min) → 31°C
        20:00 (1200 min) → 29°C

      Outside these times, the boundary values are used (no extrapolation).

    Parameters
    ----------
    simulation_time_minutes : float
        Current simulation time [minutes from start].
    profile : WeatherProfile
        Which weather scenario to use.
    constant_temp_c : float
        Temperature for CONSTANT_HOT profile [°C].

    Returns
    -------
    float
        Outdoor temperature [°C].
    """
    if profile == WeatherProfile.CONSTANT_HOT:
        return constant_temp_c

    elif profile == WeatherProfile.DIURNAL_HOT_DAY:
        # Waypoints: simulation assumption — NOT real weather data.
        # time_minutes represents the simulation time, assumed to start at 08:00.
        # Offset: 0 simulation minutes = 08:00 local time = 480 minutes from midnight.
        time_offsets_min = np.array([
            0.0,    # 08:00
            120.0,  # 10:00
            240.0,  # 12:00
            360.0,  # 14:00
            480.0,  # 16:00
            600.0,  # 18:00
            720.0,  # 20:00
        ])
        temperatures_c = np.array([28.0, 30.0, 33.0, 35.0, 34.0, 31.0, 29.0])

        # np.interp clamps to boundary values outside the range.
        # This is deterministic and requires no external data.
        return float(np.interp(simulation_time_minutes, time_offsets_min, temperatures_c))

    else:
        raise ValueError(f"Unknown WeatherProfile: {profile}")


# ---------------------------------------------------------------------------
# Baseline HVAC controller
# ---------------------------------------------------------------------------

# Baseline schedule — simulation assumption.
# A fixed schedule that does NOT respond to complaints or occupant feedback.
# Represents a conventional building management system (BMS) setpoint schedule.
#
# Format: (start_minute_inclusive, end_minute_exclusive, setpoint_c)
# Times are offsets from simulation start (0 = 08:00 in the diurnal scenario,
# or simply minute-0 for the constant scenario).
#
# Schedule interpretation:
#   Daytime   (08:00–18:00, 0–600 min)   → 22°C (occupied hours, comfort focus)
#   Evening   (18:00–22:00, 600–840 min) → 24°C (reduced occupation)
#   Night     (22:00–08:00, 840–1440 min)→ 26°C (unoccupied, energy save)

_BASELINE_SCHEDULE: list[tuple[float, float, float]] = [
    (0.0,    600.0,  22.0),   # Daytime:  0–600 min   → 22°C
    (600.0,  840.0,  24.0),   # Evening:  600–840 min → 24°C
    (840.0, 1440.0,  26.0),   # Night:    840–1440 min→ 26°C
]

# Default setpoint when no schedule entry matches.
_BASELINE_DEFAULT_SETPOINT: float = 24.0  # °C


def get_baseline_setpoint(simulation_time_minutes: float) -> float:
    """
    Return the baseline fixed HVAC setpoint for the given simulation time.

    This controller does NOT respond to occupant complaints.
    It represents a conventional fixed-schedule BMS for comparison.

    DETERMINISTIC: same input always produces same output.

    Schedule (simulation assumption — not from a real building):
      Daytime   (0–600 min)    → 22°C
      Evening   (600–840 min)  → 24°C
      Night     (840–1440 min) → 26°C

    The schedule repeats with a period of 1440 minutes (24 hours).

    Parameters
    ----------
    simulation_time_minutes : float
        Current simulation time [minutes].

    Returns
    -------
    float
        Fixed baseline HVAC setpoint [°C].
    """
    # Wrap time to a 24-hour (1440-minute) cycle.
    # Units: minutes % minutes = minutes
    time_in_day: float = simulation_time_minutes % 1440.0

    for start, end, setpoint in _BASELINE_SCHEDULE:
        if start <= time_in_day < end:
            return setpoint

    # Should not reach here if schedule covers [0, 1440), but provide fallback.
    return _BASELINE_DEFAULT_SETPOINT


# ---------------------------------------------------------------------------
# Adaptive controller (simple — more sophisticated version for optimizer later)
# ---------------------------------------------------------------------------

def get_adaptive_setpoint(
    room_setpoint_c: float,
) -> float:
    """
    Return the current adaptive setpoint for a room.

    In this task, the adaptive setpoint is simply the room's current setpoint_c,
    which is modified by apply_constraint() when occupant feedback arrives.

    This function exists as a named hook for the later optimization layer to
    replace with a more sophisticated controller.

    Parameters
    ----------
    room_setpoint_c : float
        Current HVAC setpoint for the room [°C].

    Returns
    -------
    float
        Setpoint to use this step [°C].
    """
    return room_setpoint_c
