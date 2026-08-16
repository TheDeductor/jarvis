"""
baseline.py  —  Baseline fixed-schedule HVAC controller.

The baseline runs on a separate BuildingTwin instance with a predetermined
setpoint schedule.  It does NOT respond to occupant feedback or the optimizer.

IMPORTANT:
  - Baseline and adaptive run on identical weather, occupancy, and physics.
  - Energy difference emerges purely from different setpoint strategies.
  - We do NOT inflate baseline energy artificially.
"""
from __future__ import annotations

import numpy as np


# Baseline setpoint schedule — simulation assumption.
# Represents a conventional building management system (BMS) schedule.
#
# Format: list of (start_minute_in_day, end_minute_in_day, setpoint_c)
# Times are minutes from midnight (0 = 00:00).
_SCHEDULE: list[tuple[float, float, float]] = [
    (0.0,    480.0,  26.0),   # 00:00–08:00  unoccupied night
    (480.0,  1080.0, 22.0),   # 08:00–18:00  occupied daytime
    (1080.0, 1320.0, 24.0),   # 18:00–22:00  evening
    (1320.0, 1440.0, 26.0),   # 22:00–24:00  night
]
_DEFAULT_SETPOINT: float = 24.0


def get_baseline_setpoint(simulation_time_minutes: float) -> float:
    """
    Return the baseline fixed HVAC setpoint for the given simulation time.

    Repeats with a 24-hour (1440-minute) period.
    Deterministic: same input → same output.

    Parameters
    ----------
    simulation_time_minutes : float
        Elapsed simulation time [minutes from simulation start].
        Simulation assumes start = 08:00 local time.
        So simulation_time=0 → 08:00 → 480 minutes from midnight.

    Returns
    -------
    float  — setpoint [°C]
    """
    # Add 480 min (08:00 offset) then wrap to 24h cycle.
    time_from_midnight = (simulation_time_minutes + 480.0) % 1440.0

    for start, end, sp in _SCHEDULE:
        if start <= time_from_midnight < end:
            return sp
    return _DEFAULT_SETPOINT


# ──────────────────────────────────────────────
# Diurnal weather profile
# ──────────────────────────────────────────────

# Waypoints for a simulated hot-day outdoor temperature profile.
# NOT real weather data — simulation inputs only.
_WEATHER_TIME_MIN = np.array([0.0, 120.0, 240.0, 360.0, 480.0, 600.0, 720.0, 840.0])
_WEATHER_TEMP_C   = np.array([28.0, 30.0, 33.0, 35.0, 34.0, 31.0, 29.0, 27.0])



# ──────────────────────────────────────────────
# Time-of-day occupancy schedules
# ──────────────────────────────────────────────

# Occupancy schedule per room — simulation assumptions.
# simulation_time_minutes=0 corresponds to 08:00.
# Time-of-day = (sim_time + 480) % 1440   [minutes from midnight]
#
# Room A: Conference room — peaks mid-morning and mid-afternoon
# Room B: Open-plan office — steady during work hours
# Room C: Server/equipment room — constant low occupancy
# Room D: Reception/lobby — peaks morning and lunch
#
# Format: list of (start_min_from_midnight, end_min_from_midnight, n_people)
_OCCUPANCY_SCHEDULES: dict[str, list[tuple[float, float, int]]] = {
    "A": [
        (0,    480,  0),   # 00:00–08:00  empty
        (480,  600,  4),   # 08:00–10:00  early arrivals
        (600,  720,  10),  # 10:00–12:00  morning meeting
        (720,  780,  2),   # 12:00–13:00  lunch break
        (780,  900,  12),  # 13:00–15:00  afternoon meeting
        (900,  1080, 3),   # 15:00–18:00  winding down
        (1080, 1440, 0),   # 18:00–24:00  empty
    ],
    "B": [
        (0,    480,  0),   # 00:00–08:00  empty
        (480,  540,  4),   # 08:00–09:00  early arrivals
        (540,  720,  12),  # 09:00–12:00  full morning
        (720,  780,  5),   # 12:00–13:00  lunch break
        (780,  1080, 12),  # 13:00–18:00  full afternoon
        (1080, 1440, 0),   # 18:00–24:00  empty
    ],
    "C": [
        (0,    1440, 4),   # 24h  constant (server room — always staffed minimally)
    ],
    "D": [
        (0,    480,  0),   # 00:00–08:00  empty
        (480,  600,  6),   # 08:00–10:00  morning arrivals
        (600,  780,  10),  # 10:00–13:00  peak lobby
        (780,  900,  8),   # 13:00–15:00  post-lunch
        (900,  1080, 5),   # 15:00–18:00  winding down
        (1080, 1320, 2),   # 18:00–22:00  evening minimal
        (1320, 1440, 0),   # 22:00–24:00  empty
    ],
}
_DEFAULT_OCCUPANCY: int = 0


def get_scheduled_occupancy(room_id: str, simulation_time_minutes: float) -> int:
    """
    Return time-of-day occupancy count for a room.

    Schedule repeats with a 24-hour (1440-minute) period.
    Simulation assumes start at 08:00, so minute 0 = 08:00.

    Parameters
    ----------
    room_id : str
        Room identifier ('A', 'B', 'C', or 'D').
    simulation_time_minutes : float
        Elapsed simulation time [minutes from simulation start (08:00)].

    Returns
    -------
    int : Occupancy [persons].
    """
    time_of_day = (simulation_time_minutes + 480.0) % 1440.0
    schedule = _OCCUPANCY_SCHEDULES.get(room_id.upper(), [])
    for start, end, occ in schedule:
        if start <= time_of_day < end:
            return occ
    return _DEFAULT_OCCUPANCY


def get_diurnal_outside_temperature(simulation_time_minutes: float) -> float:
    """
    Deterministic diurnal outdoor temperature.

    Linearly interpolates between:
      sim_min 0   → 28°C  (08:00)
      sim_min 120 → 30°C  (10:00)
      sim_min 240 → 33°C  (12:00)
      sim_min 360 → 35°C  (14:00)
      sim_min 480 → 34°C  (16:00)
      sim_min 600 → 31°C  (18:00)
      sim_min 720 → 29°C  (20:00)
      sim_min 840 → 27°C  (22:00)

    Clamps to boundary values outside the range.
    NOT real weather — simulation input only.
    """
    t = simulation_time_minutes % 960.0  # wrap at ~16-hour cycle
    return float(np.interp(t, _WEATHER_TIME_MIN, _WEATHER_TEMP_C))
