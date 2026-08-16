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

import time
import threading
from typing import Any, Dict, Optional

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
        self.speed: int = 1          # steps-per-tick

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

    # ─────────────────────────
    # Internal
    # ─────────────────────────

    def _run_loop(self) -> None:
        """Background thread: steps the simulation at a fixed wall-clock rate."""
        while not self._stop_event.is_set():
            start = time.monotonic()

            with self._lock:
                if self.running:
                    steps = self.speed  # speed = steps per tick
                    for _ in range(steps):
                        self.twin.step()

            elapsed = time.monotonic() - start
            sleep_time = max(0.0, self.tick_interval - elapsed)
            self._stop_event.wait(timeout=sleep_time)
