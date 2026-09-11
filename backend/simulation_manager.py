"""
simulation_manager.py  —  Controls run/pause/reset/speed.

DESIGN:
  The physics engine (BuildingTwin.step()) is independent of real time.
  The SimulationManager decides WHEN to call step() and how many times.

SPEED SEMANTICS:
  speed × → 1 real second ≈ speed simulated minutes  (at 1× polling interval)
  Each background tick calls ceil(speed) steps of 5 sim-minutes each.

  Actual behaviour:
    1× → 1 step per poll interval   (1 real-sec ≈ 5 sim-min)
    5× → 5 steps per poll interval  (1 real-sec ≈ 25 sim-min)
   20× → 20 steps per poll interval (1 real-sec ≈ 100 sim-min)

  The poll interval is driven by the frontend (default 1 s).
  The backend is stateless between ticks — it only steps when tick() is called.
"""
from __future__ import annotations

import os
import sys
import time
import threading
from typing import Any, Dict, Optional

# Allow importing rl.agent from the project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from .digital_twin import BuildingTwin
from .models import AIRFLOW_MAX_LPS, AIRFLOW_MIN_LPS, SETPOINT_MAX, SETPOINT_MIN
from .thermal_model import airflow_to_hold_co2


VALID_SPEEDS = {1, 5, 20}

# ── IAQ rule (MASTER_PROMPT_3D §2.1) ─────────────────────────────────────────
IAQ_TRIGGER_PPM: float = 1000.0            # above this, the room asks for more air
IAQ_TARGET_PPM: float = 900.0              # airflow sized to hold the room below this
IAQ_CONSTRAINT_DURATION_MINS: float = 30.0
IAQ_MIN_AIRFLOW_DELTA_LPS: float = 30.0    # floor so the response is always visible


class SimulationManager:
    """
    Manages the lifecycle of the BuildingTwin simulation.

    Thread-safety:
      A background thread calls tick() at a fixed wall-clock interval.
      All public methods acquire self._lock before touching shared state.
    """

    def __init__(
        self,
        step_minutes: float = 5.0,
        tick_interval_seconds: float = 1.0,
        outside_temperature_c: float = 34.0,
        electricity_price_per_kwh: float = 8.5,
    ) -> None:
        self._lock = threading.Lock()

        self.step_minutes = step_minutes
        self.tick_interval = tick_interval_seconds

        self.twin = BuildingTwin(
            step_minutes=step_minutes,
            outside_temperature_c=outside_temperature_c,
            electricity_price_per_kwh=electricity_price_per_kwh,
        )
        self.twin.start_baseline()

        self.running = False
        self.speed: int = 1

        # ── RL Auto Mode ──────────────────────────────────────────────────────
        self.rl_mode: str = "manual"          # "manual" | "auto"
        self.rl_model_path: Optional[str] = None
        self._rl_agent = None                 # JarvisAgent instance (lazy load)
        
        # ── NLP Constraints ───────────────────────────────────────────────────
        self.active_constraints: Dict[str, Optional[Dict[str, Any]]] = {
            "A": None, "B": None, "C": None, "D": None
        }

        # ── Manual-mode base targets ──────────────────────────────────────────
        # The user's requested setpoint/airflow BEFORE deterministic overlays
        # (NLP / IAQ / price rules) are layered on top. Overlays never mutate
        # the base, so removing a constraint restores the user's intent.
        self._base_setpoints: Dict[str, float] = {}
        self._base_airflow:   Dict[str, float] = {}
        self._overlay_active: set[str] = set()
        self._sync_base_targets()

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ─────────────────────────
    # Lifecycle
    # ─────────────────────────

    def start(self) -> None:
        with self._lock:
            if self.running:
                return
            self.running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def pause(self) -> None:
        with self._lock:
            self.running = False
            self._stop_event.set()

    def reset(self) -> None:
        with self._lock:
            was_running = self.running
            self.running = False
            self._stop_event.set()

        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        with self._lock:
            self.twin.reset()
            for room_id in self.active_constraints:
                self.active_constraints[room_id] = None
            self._overlay_active.clear()
            self._sync_base_targets()
            self._stop_event.clear()
            if was_running:
                self.running = True
                self._thread = threading.Thread(target=self._run_loop, daemon=True)
                self._thread.start()

    def set_speed(self, speed: int) -> None:
        if speed not in VALID_SPEEDS:
            raise ValueError(f"speed must be one of {VALID_SPEEDS}")
        with self._lock:
            self.speed = speed

    # ─────────────────────────
    # State access
    # ─────────────────────────

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            state = self.twin.get_state()
            state["running"] = self.running
            state["speed"] = self.speed
            state["rl_mode"] = self.rl_mode
            state["rl_model_path"] = self.rl_model_path
            
            # Inject constraints into room state for UI
            self._expire_constraints(state["simulation_time_minutes"])
            for rid, constraint in self.active_constraints.items():
                if constraint is not None:
                    state["rooms"][rid]["active_constraint"] = constraint["action"].upper()

            return state

    def get_history(self) -> list[Dict[str, Any]]:
        with self._lock:
            return self.twin.get_history()

    # ─────────────────────────
    # Room controls (thread-safe)
    # ─────────────────────────

    def set_setpoint(self, room_id: str, setpoint_c: float) -> None:
        with self._lock:
            self.twin.set_setpoint(room_id, setpoint_c)
            self._base_setpoints[room_id] = max(SETPOINT_MIN, min(SETPOINT_MAX, float(setpoint_c)))

    def set_occupancy(self, room_id: str, occupancy: int) -> None:
        with self._lock:
            self.twin.set_occupancy(room_id, occupancy)

    def set_airflow(self, room_id: str, airflow_lps: float) -> None:
        with self._lock:
            self.twin.set_airflow(room_id, airflow_lps)
            self._base_airflow[room_id] = max(AIRFLOW_MIN_LPS, min(AIRFLOW_MAX_LPS, float(airflow_lps)))

    def set_outside_temperature(self, temp_c: float) -> None:
        with self._lock:
            self.twin.set_outside_temperature(temp_c)

    def set_electricity_price(self, price: float) -> None:
        with self._lock:
            self.twin.set_electricity_price(price)

    def inject_sensor_data(self, room_id: str, data: dict) -> dict:
        """Thread-safe hardware sensor override for a room."""
        with self._lock:
            return self.twin.inject_sensor_data(room_id, data)

    def inject_outside_sensor_data(self, data: dict) -> dict:
        """Thread-safe hardware sensor override for outdoor environment."""
        with self._lock:
            return self.twin.inject_outside_sensor_data(data)

    def set_rl_mode(self, mode: str, model_path: Optional[str] = None) -> None:
        """
        Switch between 'manual' and 'auto' (RL agent) control.

        When switching to 'auto', the JarvisAgent is loaded from model_path.
        The agent then controls setpoints and airflow on every simulation step.
        Manual user overrides (setpoint, airflow, sensor data) still work —
        they apply to the twin state before the next agent step.
        """
        if mode not in ("manual", "auto"):
            raise ValueError("mode must be 'manual' or 'auto'")

        with self._lock:
            if mode == "auto":
                if model_path is None:
                    raise ValueError("model_path required when switching to auto mode")
                if not os.path.exists(model_path) and not os.path.exists(model_path + ".zip"):
                    raise FileNotFoundError(f"Policy not found: {model_path}")
                # Lazy-import to avoid loading torch at startup
                from rl.agent import JarvisAgent
                self._rl_agent = JarvisAgent(model_path)
                self.rl_model_path = model_path
            else:
                self._rl_agent = None
                self.rl_model_path = None
                self._overlay_active.clear()
                # Adopt the current (agent-controlled) targets as the new manual
                # base, except in rooms an active constraint is still driving.
                for room_id, constraint in self.active_constraints.items():
                    if constraint is None:
                        _config, room = self.twin.get_room(room_id)
                        self._base_setpoints[room_id] = room.setpoint_c
                        self._base_airflow[room_id] = room.airflow_lps
            self.rl_mode = mode

    def set_nlp_constraint(
        self,
        room_id: str,
        action: str,
        urgency: str,
        setpoint_delta_c: float,
        duration_mins: float = 30.0,
        source: str = "nlp",
    ) -> None:
        """Sets a temporary constraint on a room that overrides the RL agent."""
        with self._lock:
            self._set_constraint(room_id, action, urgency, setpoint_delta_c, duration_mins, source)

    def _set_constraint(
        self,
        room_id: str,
        action: str,
        urgency: str,
        setpoint_delta_c: float,
        duration_mins: float,
        source: str = "nlp",
    ) -> None:
        """
        Write a constraint into the active table. Caller must hold self._lock.

        `source` records where the constraint came from: "nlp" (occupant
        complaint), "iaq_rule" (automatic CO2 response), "price_response" (P6).
        """
        sim_time = self.twin.simulation_time_minutes
        self.active_constraints[room_id] = {
            "action":           action,
            "urgency":          urgency,
            "setpoint_delta_c": setpoint_delta_c,
            "expires_at":       sim_time + duration_mins,
            "source":           source,
        }

    def _expire_constraints(self, sim_time: float) -> None:
        """Null out constraints past their expiry. Caller must hold self._lock."""
        for room_id, constraint in self.active_constraints.items():
            if constraint is not None and sim_time >= constraint["expires_at"]:
                self.active_constraints[room_id] = None

    def _sync_base_targets(self) -> None:
        """Re-read the user-facing base targets from the twin. Caller must hold self._lock."""
        for room_id in self.active_constraints:
            _config, room = self.twin.get_room(room_id)
            self._base_setpoints[room_id] = room.setpoint_c
            self._base_airflow[room_id] = room.airflow_lps

    # ─────────────────────────
    # Internal
    # ─────────────────────────

    def _run_loop(self) -> None:
        """Background thread: steps the simulation at a fixed wall-clock rate."""
        while not self._stop_event.is_set():
            start = time.monotonic()

            with self._lock:
                if self.running:
                    for _ in range(self.speed):
                        self._step_once()

            elapsed = time.monotonic() - start
            sleep_time = max(0.0, self.tick_interval - elapsed)
            self._stop_event.wait(timeout=sleep_time)

    def _step_once(self) -> None:
        """
        Advance the simulation exactly one step.

        Caller must hold self._lock. Order:
          1. Expire constraints whose expiry time has passed.
          2. Apply control targets — the RL agent's command in auto mode, the
             user's base target in manual mode — with deterministic overlays
             (NLP / IAQ / price response) layered on top.
          3. Advance the physics one step.
          4. Evaluate the IAQ rule against the fresh state.
        """
        sim_time = self.twin.simulation_time_minutes
        self._expire_constraints(sim_time)

        if self.rl_mode == "auto" and self._rl_agent is not None:
            try:
                state = self.twin.get_state()
                actions = self._rl_agent.get_actions(state)

                for room_id, cmd in actions.items():
                    setpoint_c, airflow_lps = self._apply_overlays(
                        room_id, cmd["setpoint_c"], cmd["airflow_lps"], sim_time
                    )
                    self.twin.set_setpoint(room_id, setpoint_c)
                    self.twin.set_airflow(room_id, airflow_lps)
            except Exception as e:
                # Never crash the sim loop; log and continue
                print(f"[RL Agent error] {e}", file=sys.stderr)
        else:
            for room_id, constraint in self.active_constraints.items():
                if constraint is not None:
                    setpoint_c, airflow_lps = self._apply_overlays(
                        room_id,
                        self._base_setpoints[room_id],
                        self._base_airflow[room_id],
                        sim_time,
                    )
                    self.twin.set_setpoint(room_id, setpoint_c)
                    self.twin.set_airflow(room_id, airflow_lps)
                    self._overlay_active.add(room_id)
                elif room_id in self._overlay_active:
                    # Constraint finished — hand control back to the manual base
                    self.twin.set_setpoint(room_id, self._base_setpoints[room_id])
                    self.twin.set_airflow(room_id, self._base_airflow[room_id])
                    self._overlay_active.discard(room_id)

        self.twin.step()
        self._apply_iaq_rule()

    def _apply_overlays(
        self,
        room_id: str,
        base_setpoint_c: float,
        base_airflow_lps: float,
        sim_time: float,
    ) -> tuple[float, float]:
        """
        Layer the room's active constraint on top of a base control target.

        The base target is the RL agent's command in auto mode and the user's
        base setpoint/airflow in manual mode. Overlays are deterministic and
        never mutate the base, so an expiring constraint simply restores the
        target underneath it. Shared by both modes (docs/PHASES.md P2 decision).

        Returns (setpoint_c, airflow_lps) after the overlay.
        """
        constraint = self.active_constraints.get(room_id)
        if constraint is None or sim_time >= constraint["expires_at"]:
            return base_setpoint_c, base_airflow_lps

        action = constraint["action"]
        delta  = constraint["setpoint_delta_c"]

        setpoint_c  = base_setpoint_c
        airflow_lps = base_airflow_lps

        if action == "increase_temp":
            setpoint_c += delta
        elif action == "decrease_temp":
            setpoint_c -= delta
        elif action == "set_setpoint":
            setpoint_c = delta
        elif action == "increase_airflow":
            airflow_lps += delta
        elif action == "decrease_airflow":
            airflow_lps -= delta

        setpoint_c  = max(SETPOINT_MIN, min(SETPOINT_MAX, setpoint_c))
        airflow_lps = max(AIRFLOW_MIN_LPS, min(AIRFLOW_MAX_LPS, airflow_lps))

        return setpoint_c, airflow_lps

    def _apply_iaq_rule(self) -> None:
        """
        Rule-based IAQ response: a stuffy, uncontrolled room asks for more air.

        Trigger : room CO2 > IAQ_TRIGGER_PPM and no active constraint on the room.
        Action  : the existing `increase_airflow` constraint path (same clamp and
                  expiry code as NLP complaints), sized to hold the room at
                  IAQ_TARGET_PPM for its current occupancy.

        Caller must hold self._lock.
        """
        for room_id in self.active_constraints:
            if self.active_constraints[room_id] is not None:
                continue

            _config, room = self.twin.get_room(room_id)
            if room.co2_ppm <= IAQ_TRIGGER_PPM:
                continue

            target_airflow = airflow_to_hold_co2(room.occupancy, IAQ_TARGET_PPM)
            delta = max(IAQ_MIN_AIRFLOW_DELTA_LPS, target_airflow - room.airflow_lps)
            self._set_constraint(
                room_id          = room_id,
                action           = "increase_airflow",
                urgency          = "high",
                setpoint_delta_c = delta,
                duration_mins    = IAQ_CONSTRAINT_DURATION_MINS,
                source           = "iaq_rule",
            )
