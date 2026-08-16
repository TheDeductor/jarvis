"""
thermal_model.py
================
Pure-function thermal and humidity simulation equations.

This module contains ONLY pure functions — no side effects, no global state.
BuildingTwin calls these functions each step and applies the results to RoomState.

DISCLAIMER
----------
This is a SIMPLIFIED BEHAVIORAL DIGITAL TWIN.
Equations are first-order discrete approximations chosen for:
  - internal consistency
  - plausible qualitative behavior
  - determinism

They are NOT:
  - derived from CFD or EnergyPlus
  - calibrated against real building measurements
  - compliant with ASHRAE 90.1 or any building standard

Every parameter and equation is labeled as a simulation assumption.

Units
-----
  temperature   → °C
  humidity      → %
  airflow       → L/s
  HVAC power    → kW
  heat          → kW
  time          → minutes
"""

from __future__ import annotations

import math

import numpy as np

from .models import RoomConfig, RoomState


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Hard safety clamps — extreme fail-safes only, not physically motivated.
# Simulation assumption: values outside this range indicate a model failure.
_TEMP_MIN_C: float = -10.0   # °C
_TEMP_MAX_C: float = 60.0    # °C

# HVAC proportional gain: full capacity engages when error >= this value.
# Simulation assumption: 5°C error → 100% HVAC effort.
# Units: °C (denominator in the gain expression).
_HVAC_GAIN_DENOMINATOR: float = 5.0

# Humidity response constants.
# Simulation assumption: each occupant adds ~0.5% humidity per step (breathing, perspiration proxy).
_HUMIDITY_PER_PERSON_PCT: float = 0.5   # % per occupant per step
# Simulation assumption: max airflow extracts up to 10% humidity above base.
_HUMIDITY_AIRFLOW_RANGE_PCT: float = 10.0  # %


# ---------------------------------------------------------------------------
# HVAC power calculation
# ---------------------------------------------------------------------------

def compute_hvac_power(
    temperature_c: float,
    setpoint_c: float,
    max_hvac_power_kw: float,
) -> float:
    """
    Compute instantaneous HVAC power using a proportional controller.

    EQUATION (Simulation Assumption):
    ----------------------------------
    temperature_error = setpoint_c - temperature_c          [°C]
    hvac_raw = temperature_error × (max_hvac_power_kw / _HVAC_GAIN_DENOMINATOR)
    hvac_power_kw = clip(hvac_raw, -max_hvac_power_kw, +max_hvac_power_kw)

    Sign convention (explicit):
      Positive (+) → heating mode (setpoint > current temperature)
      Negative (–) → cooling mode (setpoint < current temperature)

    Purpose:
      Models a simple P-controller.  Output is proportional to error,
      clamped to the equipment capacity.

    Parameters
    ----------
    temperature_c : float
        Current room temperature [°C].
    setpoint_c : float
        Desired HVAC target temperature [°C].
    max_hvac_power_kw : float
        Rated capacity of the HVAC unit [kW].

    Returns
    -------
    float
        Instantaneous HVAC power [kW].
        Positive = heating, Negative = cooling.
    """
    # Temperature error: positive means room is too cold (needs heating),
    # negative means room is too warm (needs cooling).
    # Units: °C
    temperature_error: float = setpoint_c - temperature_c

    # Proportional HVAC command.
    # Simulation assumption: full power at ±5°C error.
    # Units: °C × (kW / °C) = kW
    hvac_raw: float = temperature_error * (max_hvac_power_kw / _HVAC_GAIN_DENOMINATOR)

    # Clamp to equipment capacity.
    # Units: kW
    hvac_power_kw: float = float(np.clip(hvac_raw, -max_hvac_power_kw, max_hvac_power_kw))

    return hvac_power_kw


# ---------------------------------------------------------------------------
# Internal heat from occupancy
# ---------------------------------------------------------------------------

def compute_internal_heat(occupancy: int, heat_per_person_kw: float) -> float:
    """
    Compute internal heat load from room occupants.

    EQUATION (Simulation Assumption):
    ----------------------------------
    internal_heat_kw = occupancy × heat_per_person_kw

    Purpose:
      Represents combined metabolic heat and personal device load.
      Not a calibrated ASHRAE metabolic rate — a behavioral approximation.

    Parameters
    ----------
    occupancy : int
        Number of people currently in the room [dimensionless].
    heat_per_person_kw : float
        Heat generated per person [kW/person]. Simulation assumption.

    Returns
    -------
    float
        Total internal heat load [kW].
    """
    # Units: (persons) × (kW/person) = kW
    return float(occupancy) * heat_per_person_kw


# ---------------------------------------------------------------------------
# Temperature step
# ---------------------------------------------------------------------------

def compute_next_temperature(
    temperature_c: float,
    setpoint_c: float,
    outside_temperature_c: float,
    internal_heat_kw: float,
    config: RoomConfig,
    step_minutes: float,
) -> float:
    """
    Advance room temperature by one discrete simulation step.

    EQUATIONS (First-Order Behavioral Model — Simulation Assumption):
    -----------------------------------------------------------------
    setpoint_effect  = (setpoint_c - temperature_c) × thermal_lag
    outside_effect   = (outside_temperature_c - temperature_c) × outdoor_gain
    internal_effect  = internal_heat_kw × thermal_gain

    new_temperature  = temperature_c
                       + setpoint_effect
                       + outside_effect
                       + internal_effect

    Variable descriptions and units:
      temperature_c         : current temperature [°C]
      setpoint_c            : HVAC target temperature [°C]
      outside_temperature_c : outdoor air temperature [°C]
      setpoint_effect       : HVAC-driven temperature change [°C/step]
      outside_effect        : envelope conduction effect [°C/step]
      internal_effect       : occupancy/device heat effect [°C/step]
      thermal_lag           : dimensionless gain [0–1], simulation assumption
      outdoor_gain          : dimensionless gain [0–1], simulation assumption
      thermal_gain          : °C/kW/step, simulation assumption

    Stability conditions (documented assumptions):
      thermal_lag  ∈ (0, 1) — ensures convergence, not oscillation
      outdoor_gain ∈ (0, 1) — ensures envelope effect is bounded
      Neither term can make temperature overshoot or diverge.

    Why step_minutes is accepted but not used in the formula:
      The thermal_lag and outdoor_gain already encode the per-step response.
      They are tuned for a 5-minute step.  If a different step size is used,
      these parameters should be rescaled (outside the scope of this task).
      step_minutes is accepted for API consistency and future extension.

    Parameters
    ----------
    temperature_c : float
        Current room temperature [°C].
    setpoint_c : float
        HVAC target temperature [°C].
    outside_temperature_c : float
        Outdoor air temperature [°C].
    internal_heat_kw : float
        Internal heat load from occupants [kW].
    config : RoomConfig
        Room simulation parameters.
    step_minutes : float
        Simulation timestep [minutes]. Accepted for API consistency.

    Returns
    -------
    float
        New room temperature [°C], clamped and validated.

    Raises
    ------
    ValueError
        If temperature_c or outside_temperature_c is not finite.
    """
    if not math.isfinite(temperature_c):
        raise ValueError(f"temperature_c is not finite: {temperature_c}")
    if not math.isfinite(outside_temperature_c):
        raise ValueError(f"outside_temperature_c is not finite: {outside_temperature_c}")

    # --- HVAC setpoint pull ---
    # Moves temperature toward setpoint.
    # Simulation assumption: first-order response with thermal_lag as gain.
    # Units: (°C) × (dimensionless) = °C
    setpoint_effect: float = (setpoint_c - temperature_c) * config.thermal_lag

    # --- Outdoor conduction effect ---
    # Models heat flow through building envelope.
    # Simulation assumption: proportional to indoor-outdoor temperature difference.
    # Units: (°C) × (dimensionless) = °C
    outside_effect: float = (outside_temperature_c - temperature_c) * config.outdoor_gain

    # --- Internal heat gain ---
    # From occupants and devices.
    # Units: (kW) × (°C/kW/step) = °C/step
    internal_effect: float = internal_heat_kw * config.thermal_gain

    # --- Aggregate ---
    # Units: °C + °C + °C + °C = °C
    new_temperature: float = temperature_c + setpoint_effect + outside_effect + internal_effect

    # --- Safety: check for NaN/Inf ---
    if not math.isfinite(new_temperature):
        # Fallback: return current temperature rather than propagate NaN.
        return temperature_c

    # --- Hard safety clamp (extreme fail-safe) ---
    # Simulation assumption: temperatures outside [_TEMP_MIN_C, _TEMP_MAX_C]
    # indicate a model error, not a valid physical state.
    new_temperature = float(np.clip(new_temperature, _TEMP_MIN_C, _TEMP_MAX_C))

    return new_temperature


# ---------------------------------------------------------------------------
# Humidity model
# ---------------------------------------------------------------------------

def compute_humidity_target(
    occupancy: int,
    airflow_lps: float,
    humidity_target_pct: float,
    config: RoomConfig,
) -> float:
    """
    Compute the effective humidity target based on occupancy and airflow.

    EQUATIONS (Behavioral Model — Simulation Assumption):
    -----------------------------------------------------
    occupancy_contrib  = occupancy × _HUMIDITY_PER_PERSON_PCT
    airflow_frac       = airflow_lps / config.max_airflow_lps
    airflow_reduction  = airflow_frac × _HUMIDITY_AIRFLOW_RANGE_PCT
    effective_target   = humidity_target_pct + occupancy_contrib - airflow_reduction
    effective_target   = clip(effective_target, 30, 70)

    Purpose:
      Occupants raise humidity (breathing, perspiration proxy).
      Higher airflow dilutes/removes moisture, lowering humidity.
      This is a behavioral approximation — NOT psychrometric calculation.

    Parameters
    ----------
    occupancy : int
        Current occupancy [persons].
    airflow_lps : float
        Current supply airflow [L/s].
    humidity_target_pct : float
        Base humidity target set by the controller or constraint [%].
    config : RoomConfig
        Room simulation parameters.

    Returns
    -------
    float
        Effective humidity target [%], clamped to [30, 70].
    """
    # Occupancy raises humidity.
    # Simulation assumption: each person adds 0.5% per step.
    # Units: (persons) × (%/person) = %
    occupancy_contrib: float = float(occupancy) * _HUMIDITY_PER_PERSON_PCT

    # Airflow reduces humidity (ventilation/dilution effect).
    # Simulation assumption: max airflow removes up to 10% above base.
    # Units: (L/s) / (L/s) × % = % (dimensionless fraction × %)
    airflow_frac: float = airflow_lps / config.max_airflow_lps
    airflow_reduction: float = airflow_frac * _HUMIDITY_AIRFLOW_RANGE_PCT

    # Effective target: base ± corrections.
    # Units: %
    effective_target: float = humidity_target_pct + occupancy_contrib - airflow_reduction

    # Clamp to valid humidity range.
    # Simulation assumption: 30–70% is the plausible indoor range.
    return float(np.clip(effective_target, 30.0, 70.0))


def compute_next_humidity(
    humidity_pct: float,
    effective_humidity_target: float,
    humidity_lag: float,
) -> float:
    """
    Advance room humidity by one discrete simulation step.

    EQUATION (Behavioral Model — Simulation Assumption):
    ----------------------------------------------------
    new_humidity = humidity_pct + (effective_humidity_target - humidity_pct) × humidity_lag
    new_humidity = clip(new_humidity, 30, 70)

    Purpose:
      First-order lag response toward the effective humidity target.
      Represents slow moisture dynamics (adsorption, ventilation mixing).
      NOT a psychrometric or mass-balance calculation.

    Parameters
    ----------
    humidity_pct : float
        Current room relative humidity [%].
    effective_humidity_target : float
        Target humidity this step [%].
    humidity_lag : float
        Fractional response per step [dimensionless]. Simulation assumption.

    Returns
    -------
    float
        New room relative humidity [%], clamped to [30, 70].
    """
    # First-order lag toward effective target.
    # Units: % + (% × dimensionless) = %
    new_humidity: float = humidity_pct + (effective_humidity_target - humidity_pct) * humidity_lag

    # Clamp to valid range.
    return float(np.clip(new_humidity, 30.0, 70.0))


# ---------------------------------------------------------------------------
# Airflow operations (pure helpers)
# ---------------------------------------------------------------------------

def clamp_airflow(airflow_lps: float, config: RoomConfig) -> float:
    """
    Clamp airflow to the valid range for this room.

    Parameters
    ----------
    airflow_lps : float
        Requested airflow [L/s].
    config : RoomConfig
        Room simulation parameters (contains min/max limits).

    Returns
    -------
    float
        Clamped airflow [L/s], within [config.min_airflow_lps, config.max_airflow_lps].
    """
    return float(np.clip(airflow_lps, config.min_airflow_lps, config.max_airflow_lps))


def apply_airflow_boost(
    current_airflow_lps: float,
    boost_pct: float,
    config: RoomConfig,
) -> float:
    """
    Apply a percentage airflow boost and clamp to valid range.

    EQUATION:
    ---------
    new_airflow = current_airflow_lps × (1 + boost_pct / 100)
    new_airflow = clip(new_airflow, min_airflow_lps, max_airflow_lps)

    Parameters
    ----------
    current_airflow_lps : float
        Current airflow [L/s].
    boost_pct : float
        Percentage change in airflow. Positive = increase, Negative = decrease.
        Clamped internally to [-30%, +50%] per specification.
    config : RoomConfig
        Room simulation parameters.

    Returns
    -------
    float
        New airflow [L/s], within valid bounds.
    """
    # Clamp boost to specification limits: -30% to +50%.
    # Simulation assumption from project specification.
    boost_pct_clamped: float = float(np.clip(boost_pct, -30.0, 50.0))

    # Apply boost factor.
    # Units: L/s × dimensionless = L/s
    new_airflow: float = current_airflow_lps * (1.0 + boost_pct_clamped / 100.0)

    return clamp_airflow(new_airflow, config)
