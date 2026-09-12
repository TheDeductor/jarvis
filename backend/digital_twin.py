"""
digital_twin.py  —  4-room BuildingTwin orchestrator (2R1C model).

Rooms: A, B, C, D  arranged in 2×2 layout.

Adjacency (room-coupling heat transfer):
  A ↔ B  (horizontal, top row)
  A ↔ C  (vertical, left column)
  B ↔ D  (vertical, right column)
  C ↔ D  (horizontal, bottom row)

2R1C MODEL (per room):
  Each room has TWO temperature nodes:
    T_air  — room air temperature (fast, small capacitance ~0.1 kWh/K)
    T_mass — structural mass: walls/slab/furniture (slow, ~2.0 kWh/K)

  Mean radiant temperature ≈ T_mass → feeds PMV comfort model.

COMFORT:
  PMV (Fanger) → PPD → comfort_score = 100 − PPD
  Replaces simple distance-from-ideal penalty model.

IAQ (CO2):
  Per-room CO2 mass balance — respiration generation vs. fresh-air supply.
  iaq_score = 0–100 from CO2; overall_comfort_score = 0.7·comfort + 0.3·IAQ.

STOCHASTIC WEATHER (optional):
  When use_stochastic_weather=True, Gaussian noise (σ=0.5°C) is added
  to the diurnal temperature each step.  Seed is fixed (42) for
  reproducibility.  Does NOT create a random walk — noise is applied
  to the base diurnal value each step, not accumulated.

OCCUPANCY SCHEDULE (optional):
  When use_occupancy_schedule=True, time-of-day based occupancy replaces
  manual occupancy values.  Can be toggled at runtime.

STEP ORDER (deterministic, documented):
  For each room:
    1. Collect neighbor T_air values (from previous step — explicit Euler)
    2. Compute (T_air_new, T_mass_new, Q_HVAC) via 2R1C model
    3. Compute fan power
    4. Compute next humidity
    5. Compute next CO2 → IAQ score
    6. Compute air speed from airflow
    7. Compute PMV → comfort score
    8. Compute energy increment (HVAC + fan)
    9. Accumulate energy
  Building-level:
   10. Advance simulation_time_minutes
   11. Step baseline twin in parallel
   12. Snapshot → history (capped at MAX_HISTORY)

BASELINE:
  Runs on a SEPARATE BuildingTwin instance with the same initial state,
  same weather, same occupancy, but using a fixed ASHRAE-style schedule.
  Energy difference emerges from setpoint strategies only — never inflated.
"""
from __future__ import annotations

import copy
from collections import deque
from typing import Any, Dict, List, Optional

import numpy as np

from .baseline import (
    get_baseline_setpoint,
    get_diurnal_outside_temperature,
    get_scheduled_occupancy,
)
from .comfort_model import (
    compute_comfort_score,
    compute_pmv,
    iaq_score,
    overall_comfort_score,
)
from .energy_model import compute_cost, compute_energy_increment
from .thermal_model import (
    CO2_INITIAL_PPM,
    RoomConfig,
    RoomState,
    airflow_to_air_speed,
    clamp_airflow,
    compute_fan_power,
    compute_next_co2,
    compute_next_humidity,
    compute_next_temperature,
)

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

MAX_HISTORY: int = 300
DEFAULT_STEP_MINUTES: float = 5.0
DEFAULT_OUTSIDE_TEMP_C: float = 34.0
DEFAULT_ELECTRICITY_PRICE: float = 8.5   # INR/kWh (simulation assumption)

# Room adjacency (undirected, 2×2 layout):
#   A B
#   C D
ADJACENCY: Dict[str, List[str]] = {
    "A": ["B", "C"],
    "B": ["A", "D"],
    "C": ["A", "D"],
    "D": ["B", "C"],
}

# Nominal room air volumes [m³] — SIMULATION ASSUMPTIONS (MASTER_PROMPT_3D §2.1).
ROOM_VOLUMES_M3: Dict[str, float] = {
    "A": 80.0,    # Conference
    "B": 150.0,   # Engineering open-plan
    "C": 60.0,    # Server / IT
    "D": 100.0,   # Reception
}

# Initial conditions — SIMULATION ASSUMPTIONS (demo values, not real data).
# T_air and T_mass start equal (assumes the building was in steady-state).
_INITIAL_CONDITIONS: Dict[str, Dict[str, Any]] = {
    "A": {
        "temperature_c":      23.0,   # T_air  [°C]
        "wall_temperature_c": 23.0,   # T_mass [°C]
        "humidity_pct":       50.0,
        "setpoint_c":         22.0,
        "occupancy":          8,
        "airflow_lps":        100.0,
    },
    "B": {
        "temperature_c":      27.0,
        "wall_temperature_c": 27.0,
        "humidity_pct":       62.0,
        "setpoint_c":         24.0,
        "occupancy":          12,
        "airflow_lps":        120.0,
    },
    "C": {
        "temperature_c":      22.0,
        "wall_temperature_c": 22.0,
        "humidity_pct":       48.0,
        "setpoint_c":         22.0,
        "occupancy":          4,
        "airflow_lps":        90.0,
    },
    "D": {
        "temperature_c":      25.0,
        "wall_temperature_c": 25.0,
        "humidity_pct":       55.0,
        "setpoint_c":         23.0,
        "occupancy":          10,
        "airflow_lps":        110.0,
    },
}


def _make_configs() -> Dict[str, RoomConfig]:
    return {
        rid: RoomConfig(room_id=rid, nominal_volume_m3=ROOM_VOLUMES_M3[rid])
        for rid in "ABCD"
    }


def _make_states(
    initial: Optional[Dict[str, Dict[str, Any]]] = None,
    configs: Optional[Dict[str, RoomConfig]] = None,
) -> Dict[str, RoomState]:
    src = initial or _INITIAL_CONDITIONS
    cfgs = configs or _make_configs()
    states: Dict[str, RoomState] = {}

    for rid, cond in src.items():
        cfg = cfgs[rid]
        t_air  = cond["temperature_c"]
        t_mass = cond.get("wall_temperature_c", t_air)
        rh     = cond["humidity_pct"]
        af     = cond["airflow_lps"]

        # Initial PMV uses T_mass as radiant temperature
        v_air = airflow_to_air_speed(af, cfg)
        pmv   = compute_pmv(t_air, t_mass, v_air, rh)
        score = compute_comfort_score(pmv)

        # Initial IAQ from the initial CO2 concentration
        iaq = iaq_score(CO2_INITIAL_PPM)

        states[rid] = RoomState(
            room_id            = rid,
            temperature_c      = t_air,
            wall_temperature_c = t_mass,
            humidity_pct       = rh,
            setpoint_c         = cond["setpoint_c"],
            humidity_target_pct= rh,
            airflow_lps        = af,
            occupancy          = cond["occupancy"],
            hvac_power_kw      = 0.0,
            fan_power_kw       = 0.0,
            energy_kwh         = 0.0,
            comfort_score      = score,
            pmv                = pmv,
            co2_ppm            = CO2_INITIAL_PPM,
            iaq_score          = iaq,
            overall_comfort_score = overall_comfort_score(score, iaq),
        )
    return states


# ──────────────────────────────────────────────
# BuildingTwin
# ──────────────────────────────────────────────

class BuildingTwin:
    """
    4-room digital twin building simulator.

    Thermal model : 2R1C grey-box (two nodes per room, Euler discretisation).
    Comfort model : PMV/PPD (Fanger) — NOT ASHRAE PMV compliant (simplified).
    Energy model  : P × dt_hours = kWh accumulation.
    """

    def __init__(
        self,
        step_minutes: float = DEFAULT_STEP_MINUTES,
        outside_temperature_c: float = DEFAULT_OUTSIDE_TEMP_C,
        electricity_price_per_kwh: float = DEFAULT_ELECTRICITY_PRICE,
        use_diurnal_weather: bool = False,
        use_stochastic_weather: bool = False,
        use_occupancy_schedule: bool = False,
        rng_seed: int = 42,
    ) -> None:
        self.step_minutes             = step_minutes
        self.outside_temperature_c    = outside_temperature_c
        self.electricity_price_per_kwh = electricity_price_per_kwh
        self.use_diurnal_weather      = use_diurnal_weather
        self.use_stochastic_weather   = use_stochastic_weather
        self.use_occupancy_schedule   = use_occupancy_schedule

        self._initial_outside_temp    = outside_temperature_c
        self._rng                     = np.random.default_rng(rng_seed)

        self.simulation_time_minutes: float = 0.0

        self._configs: Dict[str, RoomConfig] = _make_configs()
        self._states:  Dict[str, RoomState]  = _make_states(configs=self._configs)

        self.history:          deque[Dict[str, Any]] = deque(maxlen=MAX_HISTORY)
        self.baseline_history: deque[Dict[str, Any]] = deque(maxlen=MAX_HISTORY)

        # ── P6 building state metrics ───────────────────────────────────────
        self.cost_today: float = 0.0
        self.baseline_cost_today: float = 0.0
        self._recent_powers: deque[float] = deque(maxlen=3)  # rolling 15-min window
        self.peak_kw_15min: float = 0.0
        self.baseline_average_comfort: float = 0.0

        self._baseline_twin: Optional["BuildingTwin"] = None
        self._snapshot_and_record()

    # ─────────────────────────
    # Public controls
    # ─────────────────────────

    def set_outside_temperature(self, temp_c: float) -> None:
        """Override outdoor temperature. Disables diurnal/stochastic profile."""
        self.outside_temperature_c = float(temp_c)
        self.use_diurnal_weather   = False
        self.use_stochastic_weather = False
        if self._baseline_twin:
            self._baseline_twin.outside_temperature_c = float(temp_c)
            self._baseline_twin.use_diurnal_weather   = False
            self._baseline_twin.use_stochastic_weather = False

    def set_setpoint(self, room_id: str, setpoint_c: float) -> None:
        """
        Change HVAC setpoint for a room.
        CRITICAL: changes setpoint only. T_air changes on next step().
        """
        self._require_room(room_id)
        clamped = float(np.clip(setpoint_c, 16.0, 30.0))
        self._states[room_id].setpoint_c = clamped

    def set_occupancy(self, room_id: str, occupancy: int) -> None:
        self._require_room(room_id)
        self._states[room_id].occupancy = max(0, min(100, int(occupancy)))

    def set_airflow(self, room_id: str, airflow_lps: float) -> None:
        self._require_room(room_id)
        cfg = self._configs[room_id]
        self._states[room_id].airflow_lps = clamp_airflow(airflow_lps, cfg)

    def set_electricity_price(self, price: float) -> None:
        self.electricity_price_per_kwh = max(0.0, float(price))

    def inject_sensor_data(self, room_id: str, data: dict) -> dict:
        """
        Override room state with real hardware sensor readings.

        DESIGN INTENT:
          In simulation mode: all state values are computed by physics.
          In hardware mode:   real sensors push values here each second.
                              Physics still runs normally on the NEXT step(),
                              but starts from the real measured values
                              instead of the simulated ones.

        Only fields present in `data` (not None) are overwritten.
        Fields not provided keep their last simulated value — so you
        can start with just a temperature sensor and add more over time.

        Returns a dict of which fields were updated and their new values.
        """
        self._require_room(room_id)
        state = self._states[room_id]
        cfg   = self._configs[room_id]
        updated: dict = {}

        if data.get("temperature_c") is not None:
            state.temperature_c = float(data["temperature_c"])
            updated["temperature_c"] = state.temperature_c

        if data.get("wall_temperature_c") is not None:
            state.wall_temperature_c = float(data["wall_temperature_c"])
            updated["wall_temperature_c"] = state.wall_temperature_c

        if data.get("humidity_pct") is not None:
            state.humidity_pct = float(np.clip(data["humidity_pct"], 0.0, 100.0))
            updated["humidity_pct"] = state.humidity_pct

        if data.get("occupancy") is not None:
            state.occupancy = max(0, int(data["occupancy"]))
            updated["occupancy"] = state.occupancy

        if data.get("airflow_lps") is not None:
            state.airflow_lps = clamp_airflow(float(data["airflow_lps"]), cfg)
            updated["airflow_lps"] = state.airflow_lps

        if data.get("hvac_power_kw") is not None:
            # When a real energy meter provides HVAC power, trust it directly.
            # The physics model still computes its own estimate next step —
            # this is a one-shot override for the current snapshot.
            state.hvac_power_kw = float(data["hvac_power_kw"])
            updated["hvac_power_kw"] = state.hvac_power_kw

        return updated

    def inject_outside_sensor_data(self, data: dict) -> dict:
        """
        Override outdoor environment with real weather station data.

        Disables diurnal/stochastic weather generation for the fields provided.
        """
        updated: dict = {}

        if data.get("temperature_c") is not None:
            self.outside_temperature_c = float(data["temperature_c"])
            self.use_diurnal_weather   = False
            self.use_stochastic_weather = False
            if self._baseline_twin:
                self._baseline_twin.outside_temperature_c = float(data["temperature_c"])
                self._baseline_twin.use_diurnal_weather   = False
                self._baseline_twin.use_stochastic_weather = False
            updated["temperature_c"] = self.outside_temperature_c

        # outdoor humidity is stored for future use / display; not yet
        # consumed by the 2R1C thermal model (which uses temperature only).
        if data.get("humidity_pct") is not None:
            updated["humidity_pct"] = float(data["humidity_pct"])  # logged only

        return updated

    # ─────────────────────────
    # Simulation control
    # ─────────────────────────

    def step(self) -> Dict[str, Any]:
        """
        Advance simulation by one timestep (step_minutes).

        STEP ORDER (fully documented):
          1. Update outdoor temperature (diurnal ± stochastic noise)
          2. Optionally update occupancy from schedule
          3. For each room (using old T_air values for neighbor terms):
             a. Collect neighbor T_air values
             b. Compute (T_air_new, T_mass_new, Q_HVAC) — 2R1C model
             c. Compute fan power
             d. Compute next humidity
             e. Compute next CO2 → IAQ score
             f. Compute air speed from airflow
             g. Compute PMV → comfort score
             h. Compute energy increment (HVAC + fan power)
             i. Accumulate energy, apply all state updates
          4. Advance simulation_time_minutes
          5. Step baseline twin in parallel
          6. Snapshot → history
        """
        # ── Step 1: outdoor temperature ──────────────────────────────
        if self.use_diurnal_weather:
            base_temp = get_diurnal_outside_temperature(self.simulation_time_minutes)
            if self.use_stochastic_weather:
                # Gaussian noise on diurnal base — NOT a random walk
                noise = float(self._rng.normal(0.0, 0.5))
                self.outside_temperature_c = float(np.clip(base_temp + noise, -10.0, 55.0))
            else:
                self.outside_temperature_c = base_temp

        # ── Step 2: occupancy schedule (optional) ────────────────────
        if self.use_occupancy_schedule:
            for rid in self._states:
                scheduled_occ = get_scheduled_occupancy(rid, self.simulation_time_minutes)
                self._states[rid].occupancy = scheduled_occ

        # ── Step 3: thermal physics ───────────────────────────────────
        # Collect OLD T_air values before any updates (explicit Euler — prevents
        # a room's new temperature from affecting its neighbor in the same step).
        old_air_temps = {rid: s.temperature_c for rid, s in self._states.items()}
        step_energy_total: float = 0.0
        step_power_total: float = 0.0

        for room_id, state in self._states.items():
            cfg = self._configs[room_id]

            # 3a. Neighbor temperatures from previous step
            neighbor_temps = [old_air_temps[n] for n in ADJACENCY[room_id]]

            # 3b. 2R1C temperature update
            new_t_air, new_t_mass, hvac_power = compute_next_temperature(
                state,
                self.outside_temperature_c,
                neighbor_temps,
                cfg,
                self.step_minutes,
            )

            # 3c. Fan power
            fan_power = compute_fan_power(state.airflow_lps, cfg)

            # 3d. Humidity update
            new_humidity = compute_next_humidity(state, cfg)

            # 3e. CO2 mass balance → IAQ sub-score
            new_co2 = compute_next_co2(
                state.co2_ppm,
                state.occupancy,
                state.airflow_lps,
                cfg.nominal_volume_m3,
                self.step_minutes,
            )
            iaq = iaq_score(new_co2)

            # 3f. Air speed from airflow [m/s]
            v_air = airflow_to_air_speed(state.airflow_lps, cfg)

            # 3g. PMV (uses new T_air, new T_mass as radiant, current RH)
            pmv   = compute_pmv(new_t_air, new_t_mass, v_air, new_humidity)
            score = compute_comfort_score(pmv)

            # 3h. Energy increment: |HVAC power| + fan power [kWh]
            total_power = abs(hvac_power) + fan_power
            energy_inc  = compute_energy_increment(total_power, self.step_minutes)
            step_energy_total += energy_inc
            step_power_total  += total_power

            # 3i. Apply all state updates atomically
            state.temperature_c         = new_t_air
            state.wall_temperature_c    = new_t_mass
            state.humidity_pct          = new_humidity
            state.hvac_power_kw         = hvac_power
            state.fan_power_kw          = fan_power
            state.comfort_score         = score
            state.pmv                   = pmv
            state.co2_ppm               = new_co2
            state.iaq_score             = iaq
            state.overall_comfort_score = overall_comfort_score(score, iaq)
            state.energy_kwh           += energy_inc

        # P6: accumulate cost and 15-min rolling power
        self.cost_today += step_energy_total * self.electricity_price_per_kwh
        self._recent_powers.append(step_power_total)
        self.peak_kw_15min = max(self._recent_powers) if self._recent_powers else step_power_total

        # ── Step 4: advance simulation clock ─────────────────────────
        self.simulation_time_minutes += self.step_minutes

        # ── Step 5: baseline twin ─────────────────────────────────────
        if self._baseline_twin is not None:
            prev_base_energy = sum(s.energy_kwh for s in self._baseline_twin._states.values())
            for rid in self._baseline_twin._states:
                sp = get_baseline_setpoint(self._baseline_twin.simulation_time_minutes)
                self._baseline_twin._states[rid].setpoint_c = sp
            self._baseline_twin.step()
            new_base_energy = sum(s.energy_kwh for s in self._baseline_twin._states.values())
            base_energy_inc = max(0.0, new_base_energy - prev_base_energy)
            self.baseline_cost_today += base_energy_inc * self.electricity_price_per_kwh
            if self._baseline_twin._states:
                self.baseline_average_comfort = sum(
                    s.comfort_score for s in self._baseline_twin._states.values()
                ) / len(self._baseline_twin._states)

        # ── Step 6: snapshot ──────────────────────────────────────────
        return self._snapshot_and_record()

    def reset(self) -> None:
        """Return to initial conditions. Clears history and energy."""
        self.simulation_time_minutes  = 0.0
        self.outside_temperature_c    = self._initial_outside_temp
        self._states = _make_states(configs=self._configs)
        self.history.clear()
        self.baseline_history.clear()
        self.cost_today = 0.0
        self.baseline_cost_today = 0.0
        self._recent_powers.clear()
        self.peak_kw_15min = 0.0
        self.baseline_average_comfort = 0.0
        self._baseline_twin = self._create_baseline_twin()
        self._snapshot_and_record()

    def start_baseline(self) -> None:
        """Create and arm the baseline twin for parallel tracking."""
        self._baseline_twin = self._create_baseline_twin()

    # ─────────────────────────
    # State access
    # ─────────────────────────

    def get_state(self) -> Dict[str, Any]:
        return self._snapshot()

    def get_history(self) -> List[Dict[str, Any]]:
        return list(self.history)

    def get_room(self, room_id: str) -> tuple[RoomConfig, RoomState]:
        self._require_room(room_id)
        return self._configs[room_id], self._states[room_id]

    # ─────────────────────────
    # Private helpers
    # ─────────────────────────

    def _require_room(self, room_id: str) -> None:
        if room_id not in self._states:
            raise KeyError(
                f"Room '{room_id}' not found. Available: {list(self._states)}"
            )

    def _create_baseline_twin(self) -> "BuildingTwin":
        """Fresh building with same params/occupancy, but baseline setpoints only."""
        twin = BuildingTwin(
            step_minutes              = self.step_minutes,
            outside_temperature_c     = self.outside_temperature_c,
            electricity_price_per_kwh = self.electricity_price_per_kwh,
            use_diurnal_weather       = self.use_diurnal_weather,
            use_stochastic_weather    = False,   # baseline is deterministic
            use_occupancy_schedule    = self.use_occupancy_schedule,
        )
        # Copy current occupancy so both twins face the same scenario
        for rid in twin._states:
            twin._states[rid].occupancy = self._states[rid].occupancy

        # Apply initial baseline setpoints
        for rid in twin._states:
            twin._states[rid].setpoint_c = get_baseline_setpoint(0.0)

        twin._baseline_twin = None  # prevent infinite recursion
        return twin

    def _snapshot(self) -> Dict[str, Any]:
        """Build JSON-serialisable state dict."""
        rooms_data: Dict[str, Any] = {}
        total_energy  = 0.0
        total_power   = 0.0
        comfort_sum   = 0.0

        for rid, state in self._states.items():
            total_power_kw = abs(state.hvac_power_kw) + state.fan_power_kw
            rooms_data[rid] = {
                "room_id":            rid,
                "temperature_c":      round(state.temperature_c,      3),
                "wall_temperature_c": round(state.wall_temperature_c, 3),
                "humidity_pct":       round(state.humidity_pct,       2),
                "setpoint_c":         round(state.setpoint_c,         1),
                "airflow_lps":        round(state.airflow_lps,        1),
                "occupancy":          state.occupancy,
                "hvac_power_kw":      round(state.hvac_power_kw,      3),
                "fan_power_kw":       round(state.fan_power_kw,       3),
                "total_power_kw":     round(total_power_kw,           3),
                "energy_kwh":         round(state.energy_kwh,         4),
                "comfort_score":      round(state.comfort_score,      1),
                "pmv":                round(state.pmv,                3),
                "co2_ppm":               round(state.co2_ppm,                1),
                "iaq_score":             round(state.iaq_score,              1),
                "overall_comfort_score": round(state.overall_comfort_score,  1),
            }
            total_energy += state.energy_kwh
            total_power  += total_power_kw
            comfort_sum  += state.comfort_score

        n = len(self._states)
        avg_comfort = comfort_sum / n if n > 0 else 0.0

        baseline_energy = 0.0
        if self._baseline_twin:
            for s in self._baseline_twin._states.values():
                baseline_energy += s.energy_kwh

        cost = self.cost_today if self.cost_today > 0 else compute_cost(total_energy, self.electricity_price_per_kwh)

        return {
            "simulation_time_minutes":   self.simulation_time_minutes,
            "outside_temperature_c":     round(self.outside_temperature_c, 2),
            "electricity_price_per_kwh": self.electricity_price_per_kwh,
            "rooms": rooms_data,
            "building": {
                "total_energy_kwh":         round(total_energy,    4),
                "baseline_energy_kwh":      round(baseline_energy, 4),
                "current_power_kw":         round(total_power,     3),
                "average_comfort":          round(avg_comfort,     1),
                "estimated_cost":           round(cost,            2),
                "current_price":            round(self.electricity_price_per_kwh, 2),
                "cost_today":               round(self.cost_today, 2),
                "baseline_cost_today":      round(self.baseline_cost_today, 2),
                "peak_kw_15min":            round(self.peak_kw_15min, 3),
                "baseline_average_comfort": round(self.baseline_average_comfort, 1),
            },
        }

    def _snapshot_and_record(self) -> Dict[str, Any]:
        snap = self._snapshot()
        hist_point = {
            "simulation_time_minutes": snap["simulation_time_minutes"],
            "rooms": {
                rid: {
                    "temperature_c":      data["temperature_c"],
                    "wall_temperature_c": data["wall_temperature_c"],
                    "setpoint_c":         data["setpoint_c"],
                    "comfort_score":      data["comfort_score"],
                    "pmv":                data["pmv"],
                    "energy_kwh":         data["energy_kwh"],
                    "hvac_power_kw":      data["hvac_power_kw"],
                    "humidity_pct":       data["humidity_pct"],
                    "co2_ppm":            data["co2_ppm"],
                }
                for rid, data in snap["rooms"].items()
            },
            "total_energy_kwh":         snap["building"]["total_energy_kwh"],
            "baseline_energy_kwh":      snap["building"]["baseline_energy_kwh"],
            "cost":                     round(self.cost_today, 2),
            "baseline_cost":            round(self.baseline_cost_today, 2),
            "peak_kw_15min":            round(self.peak_kw_15min, 3),
            "baseline_average_comfort": round(self.baseline_average_comfort, 1),
            "electricity_price":        round(self.electricity_price_per_kwh, 2),
        }
        self.history.append(hist_point)
        return snap
