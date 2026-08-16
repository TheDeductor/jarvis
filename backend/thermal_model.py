"""
thermal_model.py  —  2R1C grey-box thermal model for the Digital Twin.

UPGRADE from 1R1C to 2R1C:
  The building now has TWO temperature nodes per room:
    T_air  — room air temperature (fast node, small capacitance)
    T_mass — structural/wall/floor thermal mass (slow node, large capacitance)

  Thermal circuit:
    T_out --[R_out]--> T_air <--[R_am]--> T_mass
                         |
                      Q_hvac + Q_internal + Q_vent + Q_neighbor

  Mean radiant temperature ≈ T_mass (walls and floors radiate at mass temp).
  T_mass feeds directly into the PMV comfort model for realistic "feels-like".

DISCLAIMER:
  Simplified grey-box first-order thermal model.
  NOT EnergyPlus, NOT CFD, NOT physically calibrated to any real building.
  All parameters are SIMULATION ASSUMPTIONS unless explicitly stated.

UNIT CONVENTION (strictly enforced):
  temperature         → °C
  time (internal)     → hours  (dt_hours = dt_minutes / 60)
  thermal resistance  → K/kW
  thermal capacitance → kWh/K
  heat / power        → kW
  energy              → kWh
  airflow             → L/s
  air speed           → m/s
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List

import numpy as np


# ──────────────────────────────────────────────
# Room configuration (immutable simulation parameters)
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class RoomConfig:
    """
    Immutable per-room simulation parameters.
    All values are SIMULATION ASSUMPTIONS unless noted.
    """
    room_id: str

    # ------------------------------------------------------------------
    # Thermal resistances [K/kW]
    # ------------------------------------------------------------------

    # Envelope: outside air ↔ room air. Higher = better insulated.
    # Simulation assumption: 2.0 K/kW ≈ modest commercial envelope.
    thermal_resistance_k_per_kw: float = 2.0

    # Air ↔ structural mass (walls, slab, furniture).
    # Simulation assumption: 0.5 K/kW represents good surface contact.
    air_to_mass_resistance_k_per_kw: float = 0.5

    # Inter-room shared wall. Higher = better partition insulation.
    # Simulation assumption.
    inter_room_resistance_k_per_kw: float = 8.0

    # ------------------------------------------------------------------
    # Thermal capacitances [kWh/K]
    # ------------------------------------------------------------------

    # Air node: air + fast-reacting light furniture.
    # Simulation assumption: ~0.5 kWh/K ensures numerical stability for dt=5min.
    # (pure air would be ~0.1, but requires dt < 1min to avoid divergence).
    thermal_capacitance_air_kwh_per_k: float = 0.5

    # Mass node: walls, slab, furniture — large thermal reservoir.
    # Simulation assumption: ~2.0 kWh/K for a commercial office room.
    thermal_capacitance_mass_kwh_per_k: float = 2.0

    # ------------------------------------------------------------------
    # HVAC parameters
    # ------------------------------------------------------------------

    # Maximum cooling/heating capacity [kW]. Simulation assumption.
    max_hvac_power_kw: float = 10.0

    # Proportional gain [kW/K]. Full power at error ≥ max_hvac/kp.
    # Simulation assumption.
    hvac_kp: float = 2.0

    # Maximum fan power at full airflow [kW]. Simulation assumption.
    max_fan_power_kw: float = 0.5

    # ------------------------------------------------------------------
    # Airflow [L/s]
    # ------------------------------------------------------------------

    min_airflow_lps: float = 50.0
    max_airflow_lps: float = 300.0

    # ------------------------------------------------------------------
    # Internal heat generation
    # ------------------------------------------------------------------

    # Heat per occupant [kW/person]. Simulation assumption.
    heat_per_person_kw: float = 0.1

    # Fixed equipment load (lighting, computers) [kW]. Simulation assumption.
    equipment_load_kw: float = 0.3

    # ------------------------------------------------------------------
    # Ventilation heat exchange
    # ------------------------------------------------------------------

    # Ventilation sensible heat coefficient [kW / (L/s · K)].
    # Simulation assumption: small secondary effect; primary is fan energy.
    ventilation_coeff_kw_per_lps_k: float = 0.0003

    # ------------------------------------------------------------------
    # Humidity model
    # ------------------------------------------------------------------

    humidity_lag: float = 0.05          # first-order lag per step
    humidity_per_person_pct: float = 0.4  # moisture per occupant [%/person/step]
    base_humidity_pct: float = 42.0     # baseline RH with no occupancy [%]

    # ------------------------------------------------------------------
    # Air speed derivation
    # ------------------------------------------------------------------

    # Air speed mapping [m/s]: min_airflow → air_speed_min, max_airflow → air_speed_max.
    # Simulation assumption. PMV uses air speed in [m/s].
    air_speed_min_ms: float = 0.05   # m/s at minimum airflow
    air_speed_max_ms: float = 0.30   # m/s at maximum airflow


# ──────────────────────────────────────────────
# Room state (mutable)
# ──────────────────────────────────────────────

@dataclass
class RoomState:
    """
    Mutable live state for one room. Updated every simulation step.

    2R1C model: T_air (fast) and T_mass (slow) are tracked separately.
    T_mass approximates mean radiant temperature for PMV calculation.
    """
    room_id: str
    temperature_c: float        # T_air [°C]  — room air temperature
    wall_temperature_c: float   # T_mass [°C] — structural/wall thermal mass
    humidity_pct: float         # [%]
    setpoint_c: float           # HVAC target [°C]
    humidity_target_pct: float  # internal humidity target [%]
    airflow_lps: float          # supply airflow [L/s]
    occupancy: int              # persons

    hvac_power_kw: float = 0.0   # [kW]  signed: negative=cooling, positive=heating
    fan_power_kw: float  = 0.0   # [kW]  always >= 0
    energy_kwh: float    = 0.0   # [kWh] accumulated
    comfort_score: float = 95.0  # [0–100]  100 − PPD
    pmv: float           = 0.0   # [-3, +3] Fanger PMV


# ──────────────────────────────────────────────
# Pure thermal functions
# ──────────────────────────────────────────────

def compute_hvac_power(
    temperature_c: float,
    setpoint_c: float,
    config: RoomConfig,
) -> float:
    """
    Proportional HVAC controller.

    EQUATION:
      error  = T_room − T_setpoint   [K]
      Q_HVAC = −clip(Kp × error, −Q_max, +Q_max)

    Sign convention (explicit):
      Positive Q_HVAC → heating   (adds heat to room air)
      Negative Q_HVAC → cooling   (removes heat from room air)

    Units: [kW]
    """
    error: float = temperature_c - setpoint_c   # positive = too hot
    raw: float   = -config.hvac_kp * error       # negative when too hot
    return float(np.clip(raw, -config.max_hvac_power_kw, config.max_hvac_power_kw))


def compute_fan_power(airflow_lps: float, config: RoomConfig) -> float:
    """
    Fan power — simplified quadratic fan law.

    EQUATION (simulation assumption — simplified from full cubic fan law):
      P_fan = P_fan_max × (airflow / airflow_max)²

    Note: Real fan law uses the cube. Square is used for simplicity.
    Explicitly documented as a simulation assumption.

    Units: [kW]
    """
    frac = airflow_lps / config.max_airflow_lps
    return config.max_fan_power_kw * (frac ** 2)


def compute_internal_heat(occupancy: int, config: RoomConfig) -> float:
    """
    Internal heat from occupants + fixed equipment.

    EQUATION:
      Q_internal = N × q_person + Q_equipment   [kW]

    q_person = 0.1 kW/person — simulation assumption.
    Q_equipment — simulation assumption.
    """
    return float(occupancy) * config.heat_per_person_kw + config.equipment_load_kw


def compute_outside_heat(
    temperature_c: float,
    outside_temperature_c: float,
    config: RoomConfig,
) -> float:
    """
    Envelope heat flow (outside ↔ room air).

    EQUATION:
      Q_outside = (T_out − T_air) / R_out   [kW]

    Positive → heat gain from outside (T_out > T_air).
    Negative → heat loss to outside  (T_out < T_air).
    """
    return (outside_temperature_c - temperature_c) / config.thermal_resistance_k_per_kw


def compute_neighbor_heat(
    temperature_c: float,
    neighbor_temperatures: list[float],
    config: RoomConfig,
) -> float:
    """
    Sum of heat flows from adjacent rooms.

    EQUATION (per neighbor j):
      Q_ij = (T_j − T_i) / R_ij   [kW]

    Positive → net heat gain from hotter neighbors.
    Negative → net heat loss to cooler neighbors.
    """
    total = 0.0
    for t_j in neighbor_temperatures:
        total += (t_j - temperature_c) / config.inter_room_resistance_k_per_kw
    return total


def compute_ventilation_heat(
    temperature_c: float,
    outside_temperature_c: float,
    airflow_lps: float,
    config: RoomConfig,
) -> float:
    """
    Simplified ventilation sensible heat exchange.

    EQUATION (simulation assumption):
      Q_vent = k_vent × airflow × (T_out − T_air)   [kW]

    Secondary effect — primarily airflow affects fan power.
    NOT a full duct model.
    """
    return (
        config.ventilation_coeff_kw_per_lps_k
        * airflow_lps
        * (outside_temperature_c - temperature_c)
    )


def airflow_to_air_speed(airflow_lps: float, config: RoomConfig) -> float:
    """
    Convert supply airflow [L/s] to approximate room air speed [m/s].

    Linear mapping (simulation assumption):
      min_airflow → air_speed_min
      max_airflow → air_speed_max

    Used as input to the PMV comfort model.
    Typical office range: 0.05 – 0.30 m/s near occupants.

    Units: [m/s]
    """
    frac = (airflow_lps - config.min_airflow_lps) / (
        config.max_airflow_lps - config.min_airflow_lps
    )
    frac = float(np.clip(frac, 0.0, 1.0))
    return config.air_speed_min_ms + frac * (config.air_speed_max_ms - config.air_speed_min_ms)


# ──────────────────────────────────────────────
# 2R1C Temperature integration
# ──────────────────────────────────────────────

def compute_next_temperature(
    state: RoomState,
    outside_temperature_c: float,
    neighbor_temperatures: list[float],
    config: RoomConfig,
    dt_minutes: float,
) -> tuple[float, float, float]:
    """
    Advance room temperatures by one timestep using the 2R1C model.

    TWO-NODE EQUATIONS:
      Air node (fast):
        C_air × dT_air/dt = Q_outside + Q_internal + Q_hvac
                            + Q_neighbor + Q_vent + Q_air_mass

      Mass node (slow):
        C_mass × dT_mass/dt = −Q_air_mass

      where:
        Q_air_mass = (T_mass − T_air) / R_am    [kW]
          (heat flows from mass to air when mass is warmer, vice versa)

    Discretised (Euler forward):
      T_air_new  = T_air  + (dt_h / C_air ) × Q_air_total
      T_mass_new = T_mass + (dt_h / C_mass) × (−Q_air_mass)

    Returns (new_t_air, new_t_wall, hvac_power_kw).

    Units:
      dt_hours = dt_minutes / 60   [hours]
      C [kWh/K], Q [kW] → dT = dt_h/C × Q = K  ✓
    """
    dt_hours: float = dt_minutes / 60.0

    # Individual heat terms [kW]
    Q_outside  = compute_outside_heat(state.temperature_c, outside_temperature_c, config)
    Q_internal = compute_internal_heat(state.occupancy, config)
    Q_hvac     = compute_hvac_power(state.temperature_c, state.setpoint_c, config)
    Q_neighbor = compute_neighbor_heat(state.temperature_c, neighbor_temperatures, config)
    Q_vent     = compute_ventilation_heat(
        state.temperature_c, outside_temperature_c, state.airflow_lps, config
    )

    # Air ↔ mass exchange: flows from hotter node to cooler [kW]
    Q_air_mass: float = (
        (state.wall_temperature_c - state.temperature_c)
        / config.air_to_mass_resistance_k_per_kw
    )

    # Air node update (Euler forward)
    Q_air_total: float = Q_outside + Q_internal + Q_hvac + Q_neighbor + Q_vent + Q_air_mass
    delta_t_air: float = (dt_hours / config.thermal_capacitance_air_kwh_per_k) * Q_air_total
    new_t_air: float   = state.temperature_c + delta_t_air

    # Mass node update — only exchanges with air node (Euler forward)
    # Q into mass = -Q_air_mass (equal and opposite to what left mass)
    delta_t_mass: float = (dt_hours / config.thermal_capacitance_mass_kwh_per_k) * (-Q_air_mass)
    new_t_mass: float   = state.wall_temperature_c + delta_t_mass

    # Numerical safety clamps (physical limits, not physics)
    if not math.isfinite(new_t_air):
        new_t_air = state.temperature_c
    if not math.isfinite(new_t_mass):
        new_t_mass = state.wall_temperature_c

    new_t_air  = float(np.clip(new_t_air,  -10.0, 60.0))
    new_t_mass = float(np.clip(new_t_mass, -10.0, 60.0))

    return new_t_air, new_t_mass, Q_hvac


# ──────────────────────────────────────────────
# Humidity model
# ──────────────────────────────────────────────

def compute_humidity_target(state: RoomState, config: RoomConfig) -> float:
    """
    Effective humidity target driven by occupancy and airflow.

    EQUATION (simulation assumption):
      target = base
               + occupancy × humidity_per_person
               − (airflow / max_airflow) × ventilation_range

    ventilation_range = 12% (simulation assumption).
    Bounded to [20, 80]%.
    """
    ventilation_removal = (state.airflow_lps / config.max_airflow_lps) * 12.0
    occupancy_contribution = state.occupancy * config.humidity_per_person_pct

    raw_target = (
        state.humidity_target_pct
        + occupancy_contribution
        - ventilation_removal
    )
    return float(np.clip(raw_target, 20.0, 80.0))


def compute_next_humidity(state: RoomState, config: RoomConfig) -> float:
    """
    Advance humidity toward effective target — first-order lag.

    EQUATION:
      RH_new = RH + (RH_target − RH) × lag

    lag = 0.05 (simulation assumption — slow moisture dynamics).
    Bounded to [20, 80]%.
    """
    effective_target = compute_humidity_target(state, config)
    new_rh = state.humidity_pct + (effective_target - state.humidity_pct) * config.humidity_lag
    return float(np.clip(new_rh, 20.0, 80.0))


# ──────────────────────────────────────────────
# Airflow utility
# ──────────────────────────────────────────────

def clamp_airflow(airflow_lps: float, config: RoomConfig) -> float:
    """Clamp airflow to configured [min, max] range."""
    return float(np.clip(airflow_lps, config.min_airflow_lps, config.max_airflow_lps))
