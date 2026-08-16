"""
comfort_model.py  —  ASHRAE-motivated PMV/PPD comfort scoring.

DISCLAIMER:
  This implements a SIMPLIFIED version of the Fanger PMV equation.
  It is physically motivated by ISO 7730 / ASHRAE Standard 55, but:
    - Metabolic rate is a fixed simulation assumption (1.2 met, sedentary).
    - Clothing insulation is a fixed simulation assumption (0.5 clo, light).
    - Mean radiant temperature is approximated from the 2R1C wall node.
    - Air velocity is derived from airflow using a simple linear mapping.
  It is NOT validated against real building measurements.
  It is NOT a substitute for a certified comfort assessment.

UNITS:
  temperature   → °C
  humidity      → %  (0–100)
  air speed     → m/s
  PMV           → dimensionless [-3, +3]  (Fanger scale)
  PPD           → %  (0–100, Predicted Percentage Dissatisfied)
  comfort score → dimensionless [0, 100]  (100 − PPD, for convenience)

REFERENCES:
  Fanger, P.O. (1970). Thermal Comfort.
  ISO 7730:2005 — Ergonomics of the thermal environment.
  ASHRAE Standard 55-2020.
"""
from __future__ import annotations

import math

import numpy as np


# ---------------------------------------------------------------------------
# Fixed simulation assumptions
# ---------------------------------------------------------------------------

# Metabolic rate [met]. 1 met = 58.15 W/m² body surface area.
# 1.2 met = light sedentary office work. Simulation assumption.
MET_OFFICE: float = 1.2

# Clothing insulation [clo]. 1 clo ≈ 0.155 m²·K/W.
# 0.5 clo = light indoor clothing (shirt + trousers). Simulation assumption.
CLO_OFFICE: float = 0.5

# External mechanical work [W/m²]. Assumed zero for sedentary occupants.
EXTERNAL_WORK_W_M2: float = 0.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _saturated_vapor_pressure_pa(t_air_c: float) -> float:
    """
    Approximate saturated water vapour pressure [Pa] at t_air_c [°C].

    Equation: Antoine approximation (valid ≈ 0–60 °C).
    pa_sat = exp(16.6536 − 4030.18 / (t + 235))  [Pa]

    Simulation assumption — not a rigorous psychrometric table.
    """
    return math.exp(16.6536 - 4030.18 / (t_air_c + 235.0))


def _clothing_area_factor(clo: float) -> float:
    """
    Clothing area factor f_cl (dimensionless).

    ISO 7730 Eq. (3):
      f_cl = 1.00 + 0.2 × clo   if clo ≤ 0.5
      f_cl = 1.05 + 0.1 × clo   if clo > 0.5
    """
    if clo <= 0.5:
        return 1.0 + 0.2 * clo
    return 1.05 + 0.1 * clo


def _clothing_surface_temperature(
    t_air_c: float,
    t_radiant_c: float,
    v_air_ms: float,
    M: float,    # Metabolic rate [W/m²]
    W: float,    # External work [W/m²]
    icl: float,  # Clothing resistance [m²·K/W]
    fcl: float,  # Clothing area factor
) -> float:
    """
    Iterative solution for clothing surface temperature T_cl [°C].

    ISO 7730 Eq. (2):
      T_cl = 35.7 − 0.028(M−W) − Rcl × {3.96×10⁻⁸ × f_cl × [(T_cl+273)⁴ − (T_r+273)⁴]
                                          + f_cl × h_c × (T_cl − T_a)}

    Convergence tolerance: 0.001 °C. Max 150 iterations.
    """
    tr_k = t_radiant_c + 273.15

    # Initial guess
    tcl = t_air_c + (35.5 - t_air_c) / (3.5 * (6.45 * icl + 0.1))

    for _ in range(150):
        tcl_k = tcl + 273.15

        # Convective heat transfer coefficient [W/(m²·K)]
        hcf = 12.1 * math.sqrt(max(v_air_ms, 0.0))      # forced convection
        hcn = 2.38 * (abs(tcl - t_air_c) ** 0.25)        # natural convection
        hc = max(hcf, hcn)

        tcl_new = (
            35.7
            - 0.028 * (M - W)
            - icl * (
                3.96e-8 * fcl * (tcl_k ** 4 - tr_k ** 4)
                + fcl * hc * (tcl - t_air_c)
            )
        )

        if abs(tcl_new - tcl) < 0.001:
            return tcl_new
        tcl = tcl_new

    # Return unconverged estimate (numerical safety)
    return tcl


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_pmv(
    t_air_c: float,
    t_radiant_c: float,
    v_air_ms: float,
    rh_pct: float,
    met: float = MET_OFFICE,
    clo: float = CLO_OFFICE,
) -> float:
    """
    Compute Predicted Mean Vote (PMV) using the Fanger equation.

    EQUATION (ISO 7730 / Fanger 1970):
      PMV = (0.303·exp(−0.036·M) + 0.028) ×
            [(M−W)
             − 3.05×10⁻³·(5733 − 6.99(M−W) − pa)
             − 0.42·((M−W) − 58.15)
             − 1.7×10⁻⁵·M·(5867 − pa)
             − 0.0014·M·(34 − T_a)
             − 3.96×10⁻⁸·f_cl·(T_cl⁴ − T_r⁴)    (in Kelvin)
             − f_cl·h_c·(T_cl − T_a)]

    PMV scale:
      −3 = Cold      −2 = Cool     −1 = Slightly Cool
       0 = Neutral
      +1 = Slightly Warm  +2 = Warm  +3 = Hot

    Parameters
    ----------
    t_air_c     : Air temperature [°C].
    t_radiant_c : Mean radiant temperature [°C]. Approximated as wall temperature.
    v_air_ms    : Air speed [m/s]. Derived from airflow L/s.
    rh_pct      : Relative humidity [%].
    met         : Metabolic rate [met]. Default 1.2 (sedentary office).
    clo         : Clothing insulation [clo]. Default 0.5 (light clothing).

    Returns
    -------
    float : PMV in [−3, +3].
    """
    M = met * 58.15            # [W/m²]
    W = EXTERNAL_WORK_W_M2     # [W/m²]
    icl = 0.155 * clo          # clothing resistance [m²·K/W]
    fcl = _clothing_area_factor(clo)

    # Partial pressure of water vapour [Pa]
    pa = rh_pct / 100.0 * _saturated_vapor_pressure_pa(t_air_c)

    # Clothing surface temperature [°C]
    tcl = _clothing_surface_temperature(t_air_c, t_radiant_c, v_air_ms, M, W, icl, fcl)

    # Convective coefficient for final PMV calc (must match tcl solution)
    hcf = 12.1 * math.sqrt(max(v_air_ms, 0.0))
    hcn = 2.38 * (abs(tcl - t_air_c) ** 0.25)
    hc = max(hcf, hcn)

    tcl_k = tcl + 273.15
    tr_k  = t_radiant_c + 273.15

    pmv = (0.303 * math.exp(-0.036 * M) + 0.028) * (
        (M - W)
        - 3.05e-3 * (5733.0 - 6.99 * (M - W) - pa)
        - 0.42 * ((M - W) - 58.15)
        - 1.7e-5 * M * (5867.0 - pa)
        - 0.0014 * M * (34.0 - t_air_c)
        - 3.96e-8 * fcl * (tcl_k ** 4 - tr_k ** 4)
        - fcl * hc * (tcl - t_air_c)
    )

    # Clamp to [-3, 3] (Fanger scale limits)
    return float(np.clip(pmv, -3.0, 3.0))


def compute_ppd(pmv: float) -> float:
    """
    Predicted Percentage of Dissatisfied (PPD) from PMV.

    EQUATION (ISO 7730):
      PPD = 100 − 95 × exp(−0.03353·PMV⁴ − 0.2179·PMV²)

    Minimum PPD ≈ 5% at PMV=0 (5% of people are always dissatisfied).
    Maximum PPD = 100% at PMV = ±3.

    Returns
    -------
    float : PPD in [5, 100].
    """
    pmv_c = float(np.clip(pmv, -3.0, 3.0))
    return 100.0 - 95.0 * math.exp(-0.03353 * pmv_c ** 4 - 0.2179 * pmv_c ** 2)


def compute_comfort_score(pmv: float) -> float:
    """
    Convert PMV to a 0–100 comfort score (100 − PPD).

    Score interpretation:
      95  → PMV ≈ 0  (neutral, ~5% dissatisfied)
      80  → PMV ≈ ±1 (slightly warm/cool)
      45  → PMV ≈ ±2 (warm/cool)
       0  → PMV ≈ ±3 (hot/cold)

    Returns
    -------
    float : Comfort score [0, 100]. Higher is more comfortable.
    """
    ppd = compute_ppd(pmv)
    return float(np.clip(100.0 - ppd, 0.0, 100.0))


def comfort_label(comfort_score: float) -> str:
    """
    Human-readable label for a comfort score.

    Thresholds:
      ≥ 90  → Excellent   (PMV near neutral, < 10% dissatisfied)
      ≥ 75  → Good        (PMV < ±0.85)
      ≥ 55  → Moderate    (PMV < ±1.5)
      ≥ 30  → Poor
       < 30 → Very Poor
    """
    if comfort_score >= 90:
        return "Excellent"
    elif comfort_score >= 75:
        return "Good"
    elif comfort_score >= 55:
        return "Moderate"
    elif comfort_score >= 30:
        return "Poor"
    else:
        return "Very Poor"
