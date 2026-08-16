"""
energy_model.py
===============
HVAC energy accumulation and electricity cost calculation.

CRITICAL UNIT DISTINCTION
--------------------------
  kW  (kilowatt)      = instantaneous power   (how fast energy is consumed RIGHT NOW)
  kWh (kilowatt-hour) = accumulated energy    (total energy consumed OVER TIME)

The conversion is:
  energy_kwh = power_kw × time_hours

This module enforces that distinction throughout.

Units
-----
  HVAC power       → kW   (instantaneous)
  energy increment → kWh  (per step)
  accumulated      → kWh  (cumulative since reset)
  time             → minutes (then converted to hours internally)
  cost             → currency units (user-defined)
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Energy increment per step
# ---------------------------------------------------------------------------

def compute_energy_increment(
    hvac_power_kw: float,
    step_minutes: float,
) -> float:
    """
    Compute the energy consumed in one simulation step.

    EQUATION:
    ---------
    step_hours           = step_minutes / 60        [hours]
    energy_increment_kwh = |hvac_power_kw| × step_hours   [kWh]

    Why absolute value:
      hvac_power_kw is signed (positive = heating, negative = cooling).
      Energy consumption is always positive regardless of direction.

    Unit check:
      kW × hours = kWh  ✓
      (NOT kW × minutes, which would give kW·min, not kWh)

    Parameters
    ----------
    hvac_power_kw : float
        Instantaneous HVAC power [kW]. Signed (+ heating, – cooling).
    step_minutes : float
        Duration of the simulation step [minutes].

    Returns
    -------
    float
        Energy consumed during this step [kWh]. Always non-negative.

    Raises
    ------
    ValueError
        If step_minutes is not positive.
    """
    if step_minutes <= 0:
        raise ValueError(f"step_minutes must be positive, got {step_minutes}")

    # Convert minutes to hours for dimensional correctness.
    # Units: minutes × (1 hour / 60 minutes) = hours
    step_hours: float = step_minutes / 60.0

    # Energy = power × time.
    # Absolute value: energy is always non-negative.
    # Units: kW × hours = kWh ✓
    energy_increment_kwh: float = abs(hvac_power_kw) * step_hours

    return energy_increment_kwh


# ---------------------------------------------------------------------------
# Building total energy
# ---------------------------------------------------------------------------

def compute_total_energy(room_energies_kwh: list[float]) -> float:
    """
    Sum energy across all rooms to get building total.

    EQUATION:
    ---------
    total_energy_kwh = Σ room.energy_kwh  for all rooms

    Parameters
    ----------
    room_energies_kwh : list[float]
        Energy accumulated by each room [kWh].

    Returns
    -------
    float
        Total building energy [kWh].
    """
    # Units: Σ kWh = kWh ✓
    return sum(room_energies_kwh)


# ---------------------------------------------------------------------------
# Electricity cost
# ---------------------------------------------------------------------------

def compute_cost(
    energy_kwh: float,
    electricity_price_per_kwh: float,
) -> float:
    """
    Compute electricity cost from accumulated energy.

    EQUATION:
    ---------
    cost = energy_kwh × electricity_price_per_kwh

    Unit check:
      kWh × (currency / kWh) = currency  ✓
      (NOT kW × price, which omits time)

    Parameters
    ----------
    energy_kwh : float
        Accumulated energy [kWh].
    electricity_price_per_kwh : float
        Electricity tariff [currency per kWh].

    Returns
    -------
    float
        Total electricity cost [currency units].
    """
    # Units: kWh × (currency/kWh) = currency ✓
    return energy_kwh * electricity_price_per_kwh
