"""
building.py
===========
BuildingTwin — the main orchestrator of the Digital Twin simulation.

This class:
  1. Holds the state of all 5 rooms (A1, A2, B1, B2, C1)
  2. Calls thermal, comfort, and energy models each step
  3. Records history
  4. Exposes the public API used by demos, tests, and (later) the optimizer

SIMULATION STEP ORDER (documented, deterministic):
  For each room in each step:
    1.  Get outdoor temperature from weather profile
    2.  Calculate internal heat (occupancy × heat_per_person)
    3.  Calculate HVAC power (proportional controller)
    4.  Calculate temperature delta (first-order model)
    5.  Apply new temperature (clamped)
    6.  Calculate effective humidity target
    7.  Advance humidity (lag model)
    8.  Calculate comfort score
    9.  Calculate energy increment (kW × time = kWh)
    10. Accumulate energy
  Then:
    11. Advance simulation_time_minutes
    12. Snapshot state → append to history (capped at MAX_HISTORY)

CONSTRAINT APPLICATION:
  apply_constraint() changes ONLY setpoint_c, humidity_target_pct, airflow_lps.
  It NEVER changes temperature_c directly.
  Temperature changes only through the simulation equations in step().

Units
-----
  temperature  → °C
  humidity     → %
  airflow      → L/s
  HVAC power   → kW
  energy       → kWh
  time         → minutes
  cost         → currency (user-defined)
"""

from __future__ import annotations

import copy
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .comfort_model import compute_comfort_score
from .energy_model import compute_cost, compute_energy_increment, compute_total_energy
from .models import RoomConfig, RoomState
from .scenario import WeatherProfile, get_baseline_setpoint, get_outside_temperature
from .thermal_model import (
    apply_airflow_boost,
    clamp_airflow,
    compute_humidity_target,
    compute_hvac_power,
    compute_internal_heat,
    compute_next_humidity,
    compute_next_temperature,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_HISTORY: int = 200
"""Maximum number of history snapshots retained.  Older entries are discarded."""

DEFAULT_STEP_MINUTES: float = 5.0
"""Default simulation timestep [minutes]. Simulation assumption."""

DEFAULT_ELECTRICITY_PRICE: float = 0.12
"""Default electricity price [currency/kWh]. Simulation assumption."""

DEFAULT_OUTSIDE_TEMP_C: float = 34.0
"""Default outdoor temperature [°C]. Hot-day scenario from project specification."""

# Setpoint safety bounds [°C].
# Simulation assumption: setpoints outside [16, 30] are rejected as unsafe.
SETPOINT_MIN_C: float = 16.0
SETPOINT_MAX_C: float = 30.0

# Constraint limits from project specification.
TEMP_OFFSET_MAX_C: float = 5.0     # °C
TEMP_OFFSET_MIN_C: float = -5.0    # °C


# ---------------------------------------------------------------------------
# Room defaults (initial conditions)
# ---------------------------------------------------------------------------

def _make_default_rooms() -> tuple[dict[str, RoomConfig], dict[str, RoomState]]:
    """
    Create the 5 default rooms with initial state.

    Room IDs: A1, A2, B1, B2, C1  (from project specification).

    Initial conditions (simulation assumptions):
      temperature_c    = 24.0°C
      humidity_pct     = 50.0%
      setpoint_c       = 22.0°C
      airflow_lps      = 120.0 L/s
      occupancy        = 5
      energy_kwh       = 0.0
      comfort_score    = computed at start

    Returns
    -------
    tuple[dict[str, RoomConfig], dict[str, RoomState]]
        (configs, states) dictionaries keyed by room_id.
    """
    room_ids = ["A1", "A2", "B1", "B2", "C1"]

    configs: dict[str, RoomConfig] = {}
    states: dict[str, RoomState] = {}

    for rid in room_ids:
        configs[rid] = RoomConfig(room_id=rid)
        state = RoomState(
            room_id=rid,
            temperature_c=24.0,
            humidity_pct=50.0,
            setpoint_c=22.0,
            humidity_target_pct=50.0,
            airflow_lps=120.0,
            occupancy=5,
            hvac_power_kw=0.0,
            energy_kwh=0.0,
            comfort_score=compute_comfort_score(24.0, 50.0),
        )
        states[rid] = state

    return configs, states


# ---------------------------------------------------------------------------
# BuildingTwin
# ---------------------------------------------------------------------------

class BuildingTwin:
    """
    Digital twin of a 5-room building with HVAC simulation.

    This class orchestrates all simulation modules:
      - thermal_model  (temperature, humidity)
      - comfort_model  (comfort score)
      - energy_model   (HVAC energy accumulation)
      - scenario       (weather, baseline controller)

    It maintains two independent histories:
      - history          : simulation under the adaptive/constraint controller
      - baseline_history : simulation under the fixed baseline schedule

    IMPORTANT: The baseline simulation runs on a SEPARATE BuildingTwin instance
    created internally.  This ensures the comparison is fair and unmodified.

    Parameters
    ----------
    step_minutes : float
        Simulation timestep [minutes]. Default: 5.
    electricity_price_per_kwh : float
        Electricity tariff [currency/kWh]. Default: 0.12.
    outside_temperature_c : float
        Initial outdoor temperature [°C]. Default: 34.0.
    weather_profile : WeatherProfile
        Deterministic weather scenario. Default: CONSTANT_HOT.
    """

    def __init__(
        self,
        step_minutes: float = DEFAULT_STEP_MINUTES,
        electricity_price_per_kwh: float = DEFAULT_ELECTRICITY_PRICE,
        outside_temperature_c: float = DEFAULT_OUTSIDE_TEMP_C,
        weather_profile: WeatherProfile = WeatherProfile.CONSTANT_HOT,
    ) -> None:
        self.step_minutes: float = step_minutes
        self.electricity_price_per_kwh: float = electricity_price_per_kwh
        self.outside_temperature_c: float = outside_temperature_c
        self.weather_profile: WeatherProfile = weather_profile

        # Remember the initial outside temperature for reset() to restore.
        self._initial_outside_temperature_c: float = outside_temperature_c

        # Simulation clock [minutes]
        self.simulation_time_minutes: float = 0.0

        # Room data
        self._configs: dict[str, RoomConfig]
        self._states: dict[str, RoomState]
        self._configs, self._states = _make_default_rooms()

        # History: deque with max length to prevent unbounded memory.
        self.history: deque[dict[str, Any]] = deque(maxlen=MAX_HISTORY)
        self.baseline_history: deque[dict[str, Any]] = deque(maxlen=MAX_HISTORY)

        # Record initial state.
        self.history.append(self._snapshot())

    # -----------------------------------------------------------------------
    # Public API — building-level controls
    # -----------------------------------------------------------------------

    def set_outside_temperature(self, temp_c: float) -> None:
        """
        Override the outdoor temperature.

        This bypasses the weather profile and sets a fixed value.
        Useful for scenario testing (e.g., simulate a sudden heat spike).

        Parameters
        ----------
        temp_c : float
            New outdoor temperature [°C].
        """
        self.outside_temperature_c = float(temp_c)

    def set_occupancy(self, room_id: str, occupancy: int) -> None:
        """
        Change the number of occupants in a room.

        Internal heat load changes immediately; temperature changes on next step().

        Parameters
        ----------
        room_id : str
            Room identifier (e.g. 'B2').
        occupancy : int
            New occupant count. Must be >= 0.

        Raises
        ------
        KeyError  If room_id is not found.
        ValueError If occupancy < 0.
        """
        self._require_room(room_id)
        if occupancy < 0:
            raise ValueError(f"Occupancy must be >= 0, got {occupancy}")
        self._states[room_id].occupancy = int(occupancy)

    def set_setpoint(self, room_id: str, setpoint_c: float) -> None:
        """
        Directly set the HVAC target temperature for a room.

        IMPORTANT: This changes the setpoint only.
        The room temperature changes only through the simulation equations.

        Parameters
        ----------
        room_id : str
            Room identifier.
        setpoint_c : float
            New HVAC setpoint [°C]. Clamped to [SETPOINT_MIN_C, SETPOINT_MAX_C].

        Raises
        ------
        KeyError  If room_id is not found.
        """
        self._require_room(room_id)
        clamped = float(np.clip(setpoint_c, SETPOINT_MIN_C, SETPOINT_MAX_C))
        self._states[room_id].setpoint_c = clamped

    def set_airflow(self, room_id: str, airflow_lps: float) -> None:
        """
        Set airflow for a room (clamped to valid range).

        Parameters
        ----------
        room_id : str
            Room identifier.
        airflow_lps : float
            New airflow [L/s]. Clamped to [min_airflow_lps, max_airflow_lps].

        Raises
        ------
        KeyError  If room_id is not found.
        """
        self._require_room(room_id)
        cfg = self._configs[room_id]
        self._states[room_id].airflow_lps = clamp_airflow(airflow_lps, cfg)

    def increase_airflow(self, room_id: str, delta_lps: float) -> None:
        """
        Increase airflow by a fixed amount (clamped to max).

        Parameters
        ----------
        room_id : str
            Room identifier.
        delta_lps : float
            Amount to add to current airflow [L/s].
        """
        self._require_room(room_id)
        current = self._states[room_id].airflow_lps
        self.set_airflow(room_id, current + delta_lps)

    def decrease_airflow(self, room_id: str, delta_lps: float) -> None:
        """
        Decrease airflow by a fixed amount (clamped to min).

        Parameters
        ----------
        room_id : str
            Room identifier.
        delta_lps : float
            Amount to subtract from current airflow [L/s].
        """
        self._require_room(room_id)
        current = self._states[room_id].airflow_lps
        self.set_airflow(room_id, current - delta_lps)

    def apply_constraint(
        self,
        room_id: str,
        temp_offset_c: float = 0.0,
        humidity_offset_pct: float = 0.0,
        airflow_boost_pct: float = 0.0,
    ) -> dict[str, Any]:
        """
        Apply a parsed comfort constraint to a room.

        This is the hook for the LLM layer (which will call this with
        already-parsed constraints extracted from occupant complaints).

        CRITICAL BEHAVIOR:
          - Changes ONLY setpoint_c, humidity_target_pct, airflow_lps
          - Does NOT change temperature_c
          - Temperature changes only through future step() calls

        Constraint limits (from project specification):
          temp_offset_c    : clamped to [TEMP_OFFSET_MIN_C, TEMP_OFFSET_MAX_C] = [-5, +5] °C
          humidity_offset_pct : clamped to [-20, +20] %
          airflow_boost_pct   : clamped to [-30, +50] %

        Parameters
        ----------
        room_id : str
            Room to modify.
        temp_offset_c : float
            Change to HVAC setpoint [°C]. Clamped to [-5, +5].
        humidity_offset_pct : float
            Change to humidity target [%]. Clamped to [-20, +20].
        airflow_boost_pct : float
            Percentage change to airflow [%]. Clamped to [-30, +50].

        Returns
        -------
        dict[str, Any]
            Summary of what changed (before/after values).

        Raises
        ------
        KeyError  If room_id is not found.
        """
        self._require_room(room_id)
        state = self._states[room_id]
        cfg = self._configs[room_id]

        # Capture before-values for the return summary.
        before_setpoint = state.setpoint_c
        before_humidity_target = state.humidity_target_pct
        before_airflow = state.airflow_lps
        before_temp = state.temperature_c  # NOT changed — just for reporting

        # --- Temperature setpoint ---
        # Clamp offset to specification limits.
        # IMPORTANT: this changes setpoint_c, NOT temperature_c.
        temp_offset_clamped = float(np.clip(temp_offset_c, TEMP_OFFSET_MIN_C, TEMP_OFFSET_MAX_C))
        new_setpoint = state.setpoint_c + temp_offset_clamped
        state.setpoint_c = float(np.clip(new_setpoint, SETPOINT_MIN_C, SETPOINT_MAX_C))

        # --- Humidity target ---
        # Clamp offset to [-20, +20] %.
        humidity_offset_clamped = float(np.clip(humidity_offset_pct, -20.0, 20.0))
        new_humidity_target = state.humidity_target_pct + humidity_offset_clamped
        state.humidity_target_pct = float(np.clip(new_humidity_target, 30.0, 70.0))

        # --- Airflow ---
        # Apply percentage boost via thermal_model helper (clamped to [-30%, +50%]).
        state.airflow_lps = apply_airflow_boost(state.airflow_lps, airflow_boost_pct, cfg)

        return {
            "room_id": room_id,
            "temperature_c_unchanged": before_temp,  # proof temperature was not touched
            "setpoint_c_before": before_setpoint,
            "setpoint_c_after": state.setpoint_c,
            "humidity_target_before": before_humidity_target,
            "humidity_target_after": state.humidity_target_pct,
            "airflow_lps_before": before_airflow,
            "airflow_lps_after": state.airflow_lps,
        }

    # -----------------------------------------------------------------------
    # Public API — simulation control
    # -----------------------------------------------------------------------

    def step(self) -> dict[str, Any]:
        """
        Advance the simulation by one timestep.

        STEP ORDER (deterministic, fully documented):
          For each room:
            1.  Get outdoor temperature from weather profile
            2.  Calculate internal heat (occupancy × heat_per_person)
            3.  Calculate HVAC power (proportional controller)
            4.  Calculate temperature change (first-order model)
            5.  Apply new temperature (clamped, validated)
            6.  Calculate effective humidity target
            7.  Advance humidity (lag model)
            8.  Calculate comfort score
            9.  Calculate energy increment (kW × time_hours = kWh)
            10. Accumulate energy
          Building-level:
            11. Advance simulation_time_minutes
            12. Snapshot state → append to history

        Returns
        -------
        dict[str, Any]
            The state snapshot recorded at this step.
        """
        # --- Step 1: Update outdoor temperature from weather profile ---
        # The profile overrides only if we're not using a manually set temperature.
        # For CONSTANT_HOT, get_outside_temperature just returns the constant.
        # For DIURNAL_HOT_DAY, it returns the interpolated value.
        # If the user called set_outside_temperature(), that value is already in
        # self.outside_temperature_c and will be used below directly.
        # Note: for DIURNAL profile, outside_temperature_c is updated from the profile.
        if self.weather_profile != WeatherProfile.CONSTANT_HOT:
            self.outside_temperature_c = get_outside_temperature(
                self.simulation_time_minutes, self.weather_profile
            )

        for room_id, state in self._states.items():
            cfg = self._configs[room_id]

            # --- Step 2: Internal heat from occupancy ---
            # Units: persons × kW/person = kW
            internal_heat_kw: float = compute_internal_heat(
                state.occupancy, cfg.heat_per_person_kw
            )

            # --- Step 3: HVAC power (proportional controller) ---
            # Sign: + = heating, – = cooling.
            # Units: kW
            hvac_power_kw: float = compute_hvac_power(
                state.temperature_c, state.setpoint_c, cfg.max_hvac_power_kw
            )

            # --- Step 4 & 5: New temperature (first-order model) ---
            # HVAC power is embedded in the setpoint_effect via the thermal_lag.
            # The separate hvac_power_kw variable is for energy accounting only.
            # Units: °C
            new_temperature: float = compute_next_temperature(
                temperature_c=state.temperature_c,
                setpoint_c=state.setpoint_c,
                outside_temperature_c=self.outside_temperature_c,
                internal_heat_kw=internal_heat_kw,
                config=cfg,
                step_minutes=self.step_minutes,
            )
            state.temperature_c = new_temperature

            # --- Step 6 & 7: Humidity update ---
            effective_humidity_target: float = compute_humidity_target(
                state.occupancy, state.airflow_lps, state.humidity_target_pct, cfg
            )
            state.humidity_pct = compute_next_humidity(
                state.humidity_pct, effective_humidity_target, cfg.humidity_lag
            )

            # --- Step 8: Comfort score ---
            # Units: dimensionless [0, 100]
            state.comfort_score = compute_comfort_score(
                state.temperature_c, state.humidity_pct
            )

            # --- Step 9: Energy increment ---
            # energy = |power| × time.  |.| because energy is always positive.
            # Units: kW × hours = kWh
            energy_increment: float = compute_energy_increment(
                hvac_power_kw, self.step_minutes
            )

            # --- Step 10: Accumulate energy ---
            # Units: kWh
            state.energy_kwh += energy_increment
            state.hvac_power_kw = hvac_power_kw

        # --- Step 11: Advance simulation time ---
        # Units: minutes
        self.simulation_time_minutes += self.step_minutes

        # --- Step 12: Snapshot ---
        snapshot = self._snapshot()
        self.history.append(snapshot)

        return snapshot

    def reset(self) -> None:
        """
        Reset the simulation to its initial state.

        Resets:
          - All room temperatures, energies, etc. to defaults
          - simulation_time_minutes to 0
          - history and baseline_history cleared
          - outside_temperature_c reset to DEFAULT_OUTSIDE_TEMP_C

        Does NOT change step_minutes or electricity_price_per_kwh.
        """
        self.simulation_time_minutes = 0.0
        # Restore the outside temperature to the constructor-supplied value,
        # not to the global DEFAULT.  This ensures reset() is idempotent
        # with respect to the constructor arguments.
        self.outside_temperature_c = self._initial_outside_temperature_c
        self._configs, self._states = _make_default_rooms()
        self.history.clear()
        self.baseline_history.clear()
        self.history.append(self._snapshot())

    # -----------------------------------------------------------------------
    # Public API — state access
    # -----------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        """
        Return the current building state as a plain dict.

        Returns
        -------
        dict[str, Any]
            Current snapshot (same format as history entries).
        """
        return self._snapshot()

    def get_history(self) -> list[dict[str, Any]]:
        """
        Return the full recorded history as a list.

        Returns
        -------
        list[dict[str, Any]]
            Ordered list of state snapshots (oldest first).
            Maximum length: MAX_HISTORY (200).
        """
        return list(self.history)

    def get_room(self, room_id: str) -> tuple[RoomConfig, RoomState]:
        """
        Return the config and current state for a room.

        Parameters
        ----------
        room_id : str
            Room identifier.

        Returns
        -------
        tuple[RoomConfig, RoomState]
            (config, state) for the room.

        Raises
        ------
        KeyError  If room_id is not found.
        """
        self._require_room(room_id)
        return self._configs[room_id], self._states[room_id]

    # -----------------------------------------------------------------------
    # Baseline simulation
    # -----------------------------------------------------------------------

    def run_baseline(self, n_steps: int) -> list[dict[str, Any]]:
        """
        Run the baseline fixed-schedule controller for n_steps on a fresh copy.

        The baseline uses get_baseline_setpoint() and does NOT respond to
        apply_constraint() calls.

        This creates a SEPARATE BuildingTwin instance so the main simulation
        state is not affected.

        Parameters
        ----------
        n_steps : int
            Number of simulation steps to run.

        Returns
        -------
        list[dict[str, Any]]
            History from the baseline simulation.
        """
        baseline_twin = BuildingTwin(
            step_minutes=self.step_minutes,
            electricity_price_per_kwh=self.electricity_price_per_kwh,
            outside_temperature_c=self.outside_temperature_c,
            weather_profile=self.weather_profile,
        )
        # Copy current occupancy to baseline (same scenario).
        for room_id, state in self._states.items():
            baseline_twin.set_occupancy(room_id, state.occupancy)

        for _ in range(n_steps):
            # Apply baseline fixed setpoints to all rooms before each step.
            for room_id in baseline_twin._states:
                sp = get_baseline_setpoint(baseline_twin.simulation_time_minutes)
                baseline_twin.set_setpoint(room_id, sp)
            baseline_twin.step()

        self.baseline_history = baseline_twin.history
        return list(baseline_twin.history)

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _require_room(self, room_id: str) -> None:
        """Raise KeyError if room_id is not in this building."""
        if room_id not in self._states:
            available = list(self._states.keys())
            raise KeyError(f"Room '{room_id}' not found. Available: {available}")

    def _snapshot(self) -> dict[str, Any]:
        """
        Capture the current building state as a JSON-serializable dict.

        Format matches the project specification:
        {
          "simulation_time_minutes": float,
          "outside_temperature_c": float,
          "rooms": {
            "<room_id>": {
              "temperature_c": float,
              "humidity_pct": float,
              "airflow_lps": float,
              "comfort_score": float,
              "setpoint_c": float,
              "hvac_power_kw": float,
              "energy_kwh": float,
              "occupancy": int
            },
            ...
          },
          "total_energy_kwh": float,
          "baseline_energy_kwh": float,   (0 if baseline not yet run)
          "cost": float
        }
        """
        room_snapshots: dict[str, dict[str, Any]] = {}
        energies: list[float] = []

        for room_id, state in self._states.items():
            room_snapshots[room_id] = {
                "temperature_c": round(state.temperature_c, 4),
                "humidity_pct": round(state.humidity_pct, 4),
                "airflow_lps": round(state.airflow_lps, 4),
                "comfort_score": round(state.comfort_score, 4),
                "setpoint_c": round(state.setpoint_c, 4),
                "hvac_power_kw": round(state.hvac_power_kw, 4),
                "energy_kwh": round(state.energy_kwh, 6),
                "occupancy": state.occupancy,
            }
            energies.append(state.energy_kwh)

        total_energy = compute_total_energy(energies)
        cost = compute_cost(total_energy, self.electricity_price_per_kwh)

        # Baseline energy: last entry of baseline_history if available.
        baseline_energy = 0.0
        if self.baseline_history:
            baseline_energy = self.baseline_history[-1].get("total_energy_kwh", 0.0)

        return {
            "simulation_time_minutes": self.simulation_time_minutes,
            "outside_temperature_c": self.outside_temperature_c,
            "rooms": room_snapshots,
            "total_energy_kwh": round(total_energy, 6),
            "baseline_energy_kwh": round(baseline_energy, 6),
            "cost": round(cost, 4),
        }
