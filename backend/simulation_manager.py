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


VALID_SPEEDS = {1, 5, 20}


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
            current_time = state["simulation_time_minutes"]
            for rid, constraint in self.active_constraints.items():
                if constraint and current_time < constraint["expires_at"]:
                    state["rooms"][rid]["active_constraint"] = f"{constraint['action'].upper()}"
                else:
                    self.active_constraints[rid] = None
                    
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

    def set_occupancy(self, room_id: str, occupancy: int) -> None:
        with self._lock:
            self.twin.set_occupancy(room_id, occupancy)

    def set_airflow(self, room_id: str, airflow_lps: float) -> None:
        with self._lock:
            self.twin.set_airflow(room_id, airflow_lps)

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
            self.rl_mode = mode

    def set_nlp_constraint(self, room_id: str, action: str, urgency: str, setpoint_delta_c: float, duration_mins: float = 30.0) -> None:
        """Sets a temporary constraint on a room that overrides the RL agent."""
        with self._lock:
            state = self.twin.get_state()
            expires_at = state["simulation_time_minutes"] + duration_mins
            self.active_constraints[room_id] = {
                "action": action,
                "urgency": urgency,
                "setpoint_delta_c": setpoint_delta_c,
                "expires_at": expires_at,
            }

    # ─────────────────────────
    # Internal
    # ─────────────────────────

    def _run_loop(self) -> None:
        """Background thread: steps the simulation at a fixed wall-clock rate."""
        while not self._stop_event.is_set():
            start = time.monotonic()

            with self._lock:
                if self.running:
                    steps = self.speed
                    for _ in range(steps):
                        # ── Auto Mode: let agent set HVAC targets before physics step ──
                        if self.rl_mode == "auto" and self._rl_agent is not None:
                            try:
                                state = self.twin.get_state()
                                current_sim_time = state["simulation_time_minutes"]
                                actions = self._rl_agent.get_actions(state)
                                
                                for room_id, cmd in actions.items():
                                    target_sp = cmd["setpoint_c"]
                                    
                                    # ── NLP Constraint Clamping ──
                                    constraint = self.active_constraints.get(room_id)
                                    if constraint is not None:
                                        if current_sim_time >= constraint["expires_at"]:
                                            self.active_constraints[room_id] = None
                                        else:
                                            if constraint["action"] == "increase_temp":
                                                target_sp += constraint["setpoint_delta_c"]
                                            elif constraint["action"] == "decrease_temp":
                                                target_sp -= constraint["setpoint_delta_c"]
                                            elif constraint["action"] == "set_setpoint":
                                                target_sp = constraint["setpoint_delta_c"]
                                            elif constraint["action"] == "increase_airflow":
                                                cmd["airflow_lps"] += constraint["setpoint_delta_c"]
                                            elif constraint["action"] == "decrease_airflow":
                                                cmd["airflow_lps"] = max(0, cmd["airflow_lps"] - constraint["setpoint_delta_c"])
                                                
                                            target_sp = max(16.0, min(30.0, target_sp))
                                                
                                    self.twin.set_setpoint(room_id, target_sp)
                                    self.twin.set_airflow(room_id, cmd["airflow_lps"])
                            except Exception as e:
                                # Never crash the sim loop; log and continue
                                import sys
                                print(f"[RL Agent error] {e}", file=sys.stderr)

                        self.twin.step()

            elapsed = time.monotonic() - start
            sleep_time = max(0.0, self.tick_interval - elapsed)
            self._stop_event.wait(timeout=sleep_time)
