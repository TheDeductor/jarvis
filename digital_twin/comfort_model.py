"""
comfort_model.py
================
Simplified comfort scoring for the Digital Twin Building Simulation Engine.

DISCLAIMER
----------
The comfort score produced here is a SIMPLIFIED BEHAVIORAL METRIC.

It is NOT:
  - ASHRAE Standard 55 PMV (Predicted Mean Vote)
  - ASHRAE Standard 62.1 indoor air quality index
  - ISO 7730
  - Any validated thermal comfort standard

It IS:
  - A transparent, explainable 0–100 score
  - Based on deviation from an idealized comfortable state
  - Useful as a proxy signal for the later optimization layer

Units
-----
  temperature  → °C
  humidity     → %
  comfort      → dimensionless score [0, 100]
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Comfort model constants (simulation assumptions)
# ---------------------------------------------------------------------------

# Ideal indoor conditions — simulation assumptions.
# NOT derived from ASHRAE tables or experimental data.
IDEAL_TEMPERATURE_C: float = 22.0   # °C
IDEAL_HUMIDITY_PCT: float = 50.0    # %

# Penalty rates — simulation assumptions.
# Temperature: 5 points lost per °C of deviation from ideal.
# Chosen so that a 12°C deviation causes maximum penalty (60 points).
TEMP_PENALTY_PER_DEG: float = 5.0   # points / °C

# Humidity: 0.8 points lost per % deviation from ideal.
# Chosen so that a 25% deviation causes maximum penalty (20 points).
HUMIDITY_PENALTY_PER_PCT: float = 0.8  # points / %

# Maximum penalties (cap individual contributions).
# Together: max_temp + max_humidity = 60 + 40 = 100 → score can reach 0.
MAX_TEMP_PENALTY: float = 60.0      # points
MAX_HUMIDITY_PENALTY: float = 40.0  # points


# ---------------------------------------------------------------------------
# Core comfort function
# ---------------------------------------------------------------------------

def compute_comfort_score(
    temperature_c: float,
    humidity_pct: float,
    ideal_temp_c: float = IDEAL_TEMPERATURE_C,
    ideal_humidity_pct: float = IDEAL_HUMIDITY_PCT,
) -> float:
    """
    Compute a simplified comfort score in the range [0, 100].

    EQUATION (Simplified Behavioral Model — Simulation Assumption):
    ---------------------------------------------------------------
    temp_deviation      = |temperature_c - ideal_temp_c|          [°C]
    humidity_deviation  = |humidity_pct  - ideal_humidity_pct|    [%]

    temp_penalty        = min(temp_deviation × TEMP_PENALTY_PER_DEG,
                              MAX_TEMP_PENALTY)                    [points]
    humidity_penalty    = min(humidity_deviation × HUMIDITY_PENALTY_PER_PCT,
                              MAX_HUMIDITY_PENALTY)                [points]

    comfort_score       = clip(100 - temp_penalty - humidity_penalty, 0, 100)

    Interpretation:
      100 → perfectly comfortable (at ideal temp and humidity)
        0 → maximally uncomfortable

    Penalty weights (simulation assumptions):
      Temperature deviation contributes more than humidity (60 vs 40 max).
      This reflects the typical human sensitivity to air temperature being
      stronger than humidity sensitivity in indoor comfort — but the
      specific weights are simulation assumptions, not experimental data.

    Parameters
    ----------
    temperature_c : float
        Current room temperature [°C].
    humidity_pct : float
        Current room relative humidity [%].
    ideal_temp_c : float, optional
        Ideal comfortable temperature [°C]. Default: 22.0.
    ideal_humidity_pct : float, optional
        Ideal comfortable humidity [%]. Default: 50.0.

    Returns
    -------
    float
        Simplified comfort score [0, 100]. Higher is more comfortable.
    """
    # --- Temperature deviation ---
    # How far the current temperature is from ideal.
    # Units: |°C - °C| = °C
    temp_deviation: float = abs(temperature_c - ideal_temp_c)

    # Temperature penalty: capped at MAX_TEMP_PENALTY.
    # Units: °C × (points/°C) = points
    temp_penalty: float = min(temp_deviation * TEMP_PENALTY_PER_DEG, MAX_TEMP_PENALTY)

    # --- Humidity deviation ---
    # How far the current humidity is from ideal.
    # Units: |% - %| = %
    humidity_deviation: float = abs(humidity_pct - ideal_humidity_pct)

    # Humidity penalty: capped at MAX_HUMIDITY_PENALTY.
    # Units: % × (points/%) = points
    humidity_penalty: float = min(
        humidity_deviation * HUMIDITY_PENALTY_PER_PCT, MAX_HUMIDITY_PENALTY
    )

    # --- Aggregate ---
    # Total penalty deducted from 100.
    # Units: dimensionless score [0, 100]
    raw_score: float = 100.0 - temp_penalty - humidity_penalty

    # Final clamp — ensures score is always in [0, 100].
    comfort_score: float = float(np.clip(raw_score, 0.0, 100.0))

    return comfort_score


# ---------------------------------------------------------------------------
# Utility: describe comfort level
# ---------------------------------------------------------------------------

def comfort_label(comfort_score: float) -> str:
    """
    Return a human-readable label for a comfort score.

    Parameters
    ----------
    comfort_score : float
        Simplified comfort score [0, 100].

    Returns
    -------
    str
        Descriptive label.
    """
    if comfort_score >= 85:
        return "Excellent"
    elif comfort_score >= 70:
        return "Good"
    elif comfort_score >= 50:
        return "Moderate"
    elif comfort_score >= 30:
        return "Poor"
    else:
        return "Very Poor"
