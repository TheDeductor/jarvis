"""
models.py
=========
Data structures for the Digital Twin Building Simulation Engine.

This module defines:
  - RoomConfig : frozen dataclass holding per-room simulation parameters.
                 These are treated as SIMULATION ASSUMPTIONS, not
                 calibrated building-physics coefficients.
  - RoomState  : mutable dataclass holding the live state of a room.
                 Updated every simulation step by building.py.

Units used throughout:
  temperature  → °C
  humidity     → %  (percent, 0–100)
  airflow      → L/s (litres per second)
  HVAC power   → kW  (kilowatts, instantaneous)
  energy       → kWh (kilowatt-hours, accumulated)
  time         → minutes (simulation time)
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# RoomConfig — immutable simulation parameters
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RoomConfig:
    """
    Immutable configuration for a single room.

    All numeric parameters are SIMULATION ASSUMPTIONS unless explicitly stated.
    They are not derived from real building measurements.
    """

    room_id: str
    """Unique identifier for this room (e.g. 'B2')."""

    # ------------------------------------------------------------------
    # Thermal response parameters
    # ------------------------------------------------------------------

    thermal_lag: float = 0.08
    """
    Fraction of the temperature error resolved per simulation step.

    Simulation assumption: 0.08 means 8% of the (setpoint - current_temp)
    gap is closed each 5-minute step.  At this rate, a room takes roughly
    60–80 steps (~5–6 hours) to fully equilibrate — plausible for a
    commercial HVAC system.

    Dimensionless.  Must be in (0, 1) to keep the system stable.
    """

    outdoor_gain: float = 0.02
    """
    Fraction of the outdoor-indoor temperature difference that leaks
    through the envelope per simulation step.

    Simulation assumption: 0.02 means 2% leakage per 5-minute step.
    Represents envelope conductance in a qualitative, not physical, sense.

    Dimensionless.  Must be in (0, 1).
    """

    thermal_gain: float = 0.05
    """
    Temperature rise (°C) per kW of internal heat per simulation step.

    Simulation assumption.  Represents how quickly internal heat sources
    (occupants, equipment) warm the room air.  Units: °C / kW / step.
    """

    max_hvac_power_kw: float = 5.0
    """
    Maximum rated HVAC power for this room.  Units: kW.

    Simulation assumption — not derived from equipment datasheets.
    Acts as both the cooling and heating capacity limit.
    """

    # ------------------------------------------------------------------
    # Airflow limits
    # ------------------------------------------------------------------

    min_airflow_lps: float = 50.0
    """Minimum allowed supply airflow.  Units: L/s.  Simulation assumption."""

    max_airflow_lps: float = 300.0
    """Maximum allowed supply airflow.  Units: L/s.  Simulation assumption."""

    # ------------------------------------------------------------------
    # Occupancy heat generation
    # ------------------------------------------------------------------

    heat_per_person_kw: float = 0.1
    """
    Internal heat generated per occupant.  Units: kW/person.

    Simulation assumption.  Represents combined metabolic heat and
    personal device load in a rough qualitative sense.
    NOT a calibrated ASHRAE metabolic rate.
    """

    # ------------------------------------------------------------------
    # Humidity response
    # ------------------------------------------------------------------

    humidity_lag: float = 0.05
    """
    Fraction of the humidity gap resolved per simulation step.

    Simulation assumption: 0.05 means humidity moves 5% toward its target
    per step — slower than temperature, representing moisture inertia.

    Dimensionless.
    """

    base_humidity_pct: float = 45.0
    """
    Baseline indoor humidity in the absence of occupancy or airflow effects.
    Units: %.  Simulation assumption.
    """


# ---------------------------------------------------------------------------
# RoomState — mutable live state
# ---------------------------------------------------------------------------

@dataclass
class RoomState:
    """
    Mutable live state for a single room.

    Updated every call to BuildingTwin.step().
    Each field carries explicit unit documentation.
    """

    room_id: str
    """Unique identifier — must match the corresponding RoomConfig.room_id."""

    # ------------------------------------------------------------------
    # Primary state variables
    # ------------------------------------------------------------------

    temperature_c: float = 24.0
    """Current room air temperature.  Units: °C."""

    humidity_pct: float = 50.0
    """Current room relative humidity.  Units: %."""

    setpoint_c: float = 22.0
    """
    HVAC target (desired) temperature.  Units: °C.

    Changed by:
      - building.set_setpoint()
      - building.apply_constraint()  ← changes this, NOT temperature_c
    """

    humidity_target_pct: float = 50.0
    """
    Target humidity for the humidity controller.  Units: %.

    Adjusted by apply_constraint() via humidity_offset_pct.
    The actual humidity_pct moves toward this value each step.
    """

    airflow_lps: float = 120.0
    """Current supply airflow rate.  Units: L/s."""

    occupancy: int = 5
    """Number of occupants currently in the room.  Dimensionless (count)."""

    # ------------------------------------------------------------------
    # Derived / accumulated quantities
    # ------------------------------------------------------------------

    hvac_power_kw: float = 0.0
    """
    Instantaneous HVAC power at the last simulation step.  Units: kW.

    Sign convention (explicit):
      Positive (+) → heating   (HVAC adding heat to the room)
      Negative (–) → cooling   (HVAC removing heat from the room)

    Magnitude is clamped to [0, max_hvac_power_kw] for energy calculation.
    """

    energy_kwh: float = 0.0
    """
    Accumulated HVAC energy consumption since simulation start or last reset.
    Units: kWh.  Monotonically non-decreasing.

    Calculated as:
      energy_kwh += |hvac_power_kw| × (step_minutes / 60)

    Note: energy_kwh and hvac_power_kw are DIFFERENT quantities.
    kW is instantaneous power; kWh is energy integrated over time.
    """

    comfort_score: float = 100.0
    """
    Simplified comfort score.  Dimensionless, range [0, 100].

    Higher is more comfortable.
    Calculated by comfort_model.compute_comfort_score().
    This is NOT ASHRAE PMV — it is a simplified behavioral metric.
    """
