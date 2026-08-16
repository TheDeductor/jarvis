"""
energy_model.py  —  Energy accumulation (kW → kWh).

CRITICAL UNIT DISTINCTION:
  kW  = instantaneous power (rate of energy use)
  kWh = accumulated energy  (power × time)

NEVER add kW directly to kWh.
"""
from __future__ import annotations


def compute_energy_increment(power_kw: float, dt_minutes: float) -> float:
    """
    Energy consumed in one simulation step.

    EQUATION:
      E = |P| * dt_hours        [kWh]
      dt_hours = dt_minutes / 60

    Absolute value: energy is always non-negative.
    Units: kW * hours = kWh  ✓
    """
    if dt_minutes <= 0:
        raise ValueError(f"dt_minutes must be positive, got {dt_minutes}")
    dt_hours = dt_minutes / 60.0
    return abs(power_kw) * dt_hours


def compute_cost(energy_kwh: float, price_per_kwh: float) -> float:
    """
    Electricity cost.

    EQUATION:  cost = E * price   [currency]
    Units: kWh * (currency/kWh) = currency  ✓
    """
    return energy_kwh * price_per_kwh
