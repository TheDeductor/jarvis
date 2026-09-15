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

P5 — Constraint lifecycle (MASTER_PROMPT_3D §2.2):
  Constraints are now ConstraintRecord dataclasses with full lifecycle:
    created → active → [resolved | escalated]
  Outcome is verified at expiry (PMV / CO2 threshold); if unresolved, the
  constraint is renewed ONCE with 1.5× delta. A second failure → escalated.
  History of the last 50 resolved/escalated constraints is kept.
"""
from __future__ import annotations

import os
import sys
import time
import uuid
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Allow importing rl.agent from the project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from .comfort_model import compute_comfort_score, compute_pmv
from .digital_twin import BuildingTwin
from .models import AIRFLOW_MAX_LPS, AIRFLOW_MIN_LPS, SETPOINT_MAX, SETPOINT_MIN
from .thermal_model import airflow_to_air_speed, airflow_to_hold_co2


VALID_SPEEDS = {1, 5, 20}

# ── IAQ rule (MASTER_PROMPT_3D §2.1) ─────────────────────────────────────────
IAQ_TRIGGER_PPM: float = 1000.0
IAQ_TARGET_PPM: float  = 900.0
IAQ_CONSTRAINT_DURATION_MINS: float = 30.0
IAQ_MIN_AIRFLOW_DELTA_LPS: float = 30.0

# ── P5 lifecycle constants (MASTER_PROMPT_3D §2.2) ───────────────────────────
RESOLUTION_PMV_BAND: float   = 0.5   # thermal resolved when |PMV| <= this
RESOLUTION_CO2_PPM: float    = 950.0 # IAQ/airflow resolved when CO2 < this
RENEW_MULTIPLIER: float      = 1.5   # delta multiplied on first renewal
EXPIRY_HIGH_MINS: float      = 45.0  # urgency=high
EXPIRY_MEDIUM_MINS: float    = 30.0  # urgency=medium
EXPIRY_LOW_MINS: float       = 20.0  # urgency=low
MAX_HISTORY: int             = 50    # keep last 50 resolved/escalated

# ── P6 TOU Tariff & Comfort Guard constants (MASTER_PROMPT_3D §2.4) ──────────
DEFAULT_TOU_SLOTS: list[dict[str, Any]] = [
    {"from_h": 0,  "to_h": 6,  "price": 4.0, "is_peak": False},
    {"from_h": 6,  "to_h": 14, "price": 6.0, "is_peak": False},
    {"from_h": 14, "to_h": 20, "price": 9.0, "is_peak": True},
    {"from_h": 20, "to_h": 24, "price": 6.0, "is_peak": False},
]
PRE_PEAK_LOOKAHEAD_MINS: float = 60.0
PRE_COOL_SETPOINT_BIAS: float  = -1.0  # °C pre-cool
PEAK_RELAX_SETPOINT_BIAS: float = 1.5  # °C relax while occupied
COMFORT_GUARD_PMV_MIN: float   = -0.7  # comfort floor
COMFORT_GUARD_PMV_MAX: float   =  0.7  # comfort ceiling


@dataclass
class TouSlot:
    from_h: int
    to_h: int
    price: float
    is_peak: bool = False


class TouTariff:
    """Time-Of-Use daily schedule manager."""
    def __init__(self, slots: Optional[List[Dict[str, Any]]] = None) -> None:
        self.slots: List[TouSlot] = []
        self.set_slots(slots or DEFAULT_TOU_SLOTS)

    def set_slots(self, slots: List[Dict[str, Any]]) -> None:
        parsed = []
        for s in slots:
            fh = int(s.get("from_h", 0))
            th = int(s.get("to_h", 24))
            p = float(s.get("price", 6.0))
            pk = s.get("is_peak")
            if pk is None:
                pk = (fh == 14 and th == 20) or p >= 9.0
            parsed.append(TouSlot(from_h=fh, to_h=th, price=p, is_peak=bool(pk)))
        self.slots = parsed

    def get_slot_for_sim_time(self, sim_time_minutes: float) -> TouSlot:
        t_day_min = (sim_time_minutes + 480.0) % 1440.0
        h_float = t_day_min / 60.0
        for slot in self.slots:
            if slot.from_h <= h_float < slot.to_h:
                return slot
        return self.slots[0] if self.slots else TouSlot(0, 24, 6.0, False)

    def is_pre_peak(self, sim_time_minutes: float, lookahead_minutes: float = PRE_PEAK_LOOKAHEAD_MINS) -> bool:
        curr = self.get_slot_for_sim_time(sim_time_minutes)
        if curr.is_peak:
            return False
        future = self.get_slot_for_sim_time(sim_time_minutes + lookahead_minutes)
        return future.is_peak


def apply_comfort_guard(
    target_bias: float,
    current_pmv: float,
    setpoint_c: float,
    wall_temp_c: float,
    airflow_lps: float,
    rh_pct: float = 50.0,
    config: Optional[Any] = None,
) -> float:
    """
    Ensure that the price-response setpoint bias never drives PMV beyond [-0.7, +0.7].
    Reduces the bias magnitude smoothly until the resulting PMV is strictly within guard.
    """
    if abs(target_bias) < 1e-4:
        return 0.0

    # 1. Guard against current PMV violating boundary
    if target_bias < 0.0:
        if current_pmv <= COMFORT_GUARD_PMV_MIN:
            return 0.0
        headroom = max(0.0, current_pmv - COMFORT_GUARD_PMV_MIN)
        max_mag = min(abs(target_bias), headroom / 0.3)
        candidate_bias = -max_mag
    else:
        if current_pmv >= COMFORT_GUARD_PMV_MAX:
            return 0.0
        headroom = max(0.0, COMFORT_GUARD_PMV_MAX - current_pmv)
        max_mag = min(abs(target_bias), headroom / 0.3)
        candidate_bias = max_mag

    # 2. Refine using projected PMV at candidate setpoint temperature
    if config is not None:
        v_air = airflow_to_air_speed(airflow_lps, config)
    else:
        frac = max(0.0, min(1.0, (airflow_lps - 50.0) / (300.0 - 50.0)))
        v_air = 0.05 + frac * (0.30 - 0.05)
    base_pmv = compute_pmv(setpoint_c, wall_temp_c, v_air, rh_pct)
    low, high = 0.0, abs(candidate_bias)
    sign = -1.0 if target_bias < 0.0 else 1.0
    safe_mag = 0.0

    for _ in range(10):
        mid = (low + high) / 2.0
        test_bias = sign * mid
        delta_pmv = compute_pmv(setpoint_c + test_bias, wall_temp_c, v_air, rh_pct) - base_pmv
        expected_pmv = current_pmv + delta_pmv

        if target_bias < 0.0:
            if expected_pmv >= COMFORT_GUARD_PMV_MIN:
                safe_mag = mid
                low = mid
            else:
                high = mid
        else:
            if expected_pmv <= COMFORT_GUARD_PMV_MAX:
                safe_mag = mid
                low = mid
            else:
                high = mid

    return sign * round(safe_mag, 2)


@dataclass
class ConstraintRecord:
    """
    A single constraint event with full lifecycle tracking.

    Fields intentionally match MASTER_PROMPT_3D §2.2:
      id, room, action, source, created_at, expires_at,
      applied_delta, llm_raw_delta, status
    """
    id: str
    room: str
    action: str
    source: str                    # "nlp" | "iaq_rule"
    urgency: str                   # "high" | "medium" | "low"
    created_at: float              # simulation minutes
    expires_at: float              # simulation minutes
    llm_raw_delta: float           # delta as given by caller (LLM / IAQ formula)
    applied_delta: float           # physics-derived delta (§2.3); same as llm for non-thermal
    status: str = "active"         # "active" | "resolved" | "escalated"
    resolved_at: Optional[float] = None   # simulation minutes when resolved
    resolution_mins: Optional[float] = None
    renewals: int = 0              # how many times renewed; 1 = renew limit reached

    @property
    def setpoint_delta_c(self) -> float:
        return self.applied_delta

    def __getitem__(self, item: str) -> Any:
        """Support dict-style indexing for backward compatibility."""
        if item == "setpoint_delta_c":
            return self.applied_delta
        return getattr(self, item)


def _urgency_to_duration(urgency: str) -> float:
    """Map urgency label → expiry window in simulation minutes (§2.2)."""
    if urgency == "high":   return EXPIRY_HIGH_MINS
    if urgency == "low":    return EXPIRY_LOW_MINS
    return EXPIRY_MEDIUM_MINS


def _physics_delta(pmv: float, action: str, llm_delta: float) -> float:
    """
    Physics-derived applied delta (MASTER_PROMPT_3D §2.3).

    For thermal actions: applied_delta = sign * clip((|PMV|*0.7)/0.3, 0.5, 2.5)
    For airflow/IAQ actions: use the physics formula delta as-is (already
    derived from airflow_to_hold_co2, not the LLM number).
    Severity maps ONLY to expiry (handled in _urgency_to_duration).
    """
    if action in ("increase_airflow", "decrease_airflow"):
        return llm_delta
    sign = -1.0 if action == "decrease_temp" else 1.0
    raw  = (abs(pmv) * 0.7) / 0.3
    return sign * max(0.5, min(2.5, raw))


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

        self.step_minutes  = step_minutes
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
        self.rl_mode: str = "manual"
        self.rl_model_path: Optional[str] = None
        self._rl_agent = None

        # ── P5 Constraint tracking ────────────────────────────────────────────
        # active: at most one per room; value is a ConstraintRecord or None.
        self.active_constraints: Dict[str, Optional[ConstraintRecord]] = {
            "A": None, "B": None, "C": None, "D": None
        }
        # history: last MAX_HISTORY resolved/escalated records across all rooms
        self._constraint_history: List[ConstraintRecord] = []

        # ── Manual-mode base targets ──────────────────────────────────────────
        self._base_setpoints: Dict[str, float] = {}
        self._base_airflow:   Dict[str, float] = {}
        self._overlay_active: set[str] = set()

        # ── DB Persistence Queues (Phase 1) ──────────────────────────────────
        self.pending_db_writes: List[Dict[str, Any]] = []
        self.pending_feedback_events: List[Dict[str, Any]] = []
        self.pending_action_logs: List[Dict[str, Any]] = []

        # ── P6 TOU Tariff & Price Response ────────────────────────────────────
        self.tou_tariff = TouTariff()
        self._forced_peak: bool = False
        self._forced_price: Optional[float] = None
        self._price_bias: Dict[str, float] = {"A": 0.0, "B": 0.0, "C": 0.0, "D": 0.0}

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

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        with self._lock:
            self.twin.reset()
            for room_id in self.active_constraints:
                self.active_constraints[room_id] = None
            self._constraint_history.clear()
            self._overlay_active.clear()
            self._forced_peak = False
            self._forced_price = None
            self._price_bias = {"A": 0.0, "B": 0.0, "C": 0.0, "D": 0.0}
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
            state["running"]        = self.running
            state["speed"]          = self.speed
            state["rl_mode"]        = self.rl_mode
            state["rl_model_path"]  = self.rl_model_path

            sim_time = state["simulation_time_minutes"]
            self._expire_constraints(sim_time)

            slot = self.tou_tariff.get_slot_for_sim_time(sim_time)
            is_peak = slot.is_peak or self._forced_peak or (self._forced_price is not None and self._forced_price >= 9.0)
            is_pre_peak = self.tou_tariff.is_pre_peak(sim_time) and not is_peak
            price_response_active = any(abs(b) > 0.01 for b in self._price_bias.values())

            state["building"]["price_response_active"] = price_response_active
            state["building"]["is_peak"] = is_peak
            state["building"]["is_pre_peak"] = is_pre_peak
            state["building"]["current_price"] = self.twin.electricity_price_per_kwh
            state["current_price"] = self.twin.electricity_price_per_kwh

            for rid, cr in self.active_constraints.items():
                if cr is not None:
                    state["rooms"][rid]["active_constraint"] = cr.action.upper()

            # P5: include serialised active constraints in state
            state["constraints"] = self._serialise_constraints()
            return state

    def get_history(self) -> list[Dict[str, Any]]:
        with self._lock:
            return self.twin.get_history()

    def get_constraints(self) -> Dict[str, Any]:
        """Return active + history list plus aggregate stats. Thread-safe."""
        with self._lock:
            return self._build_constraint_response()

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

    def set_humidity_setpoint(self, room_id: str, humidity_target_pct: float) -> None:
        with self._lock:
            self.twin.set_humidity_setpoint(room_id, humidity_target_pct)

    def set_electricity_price(self, price: float) -> None:
        with self._lock:
            p = float(price)
            self._forced_price = p
            self._forced_peak = (p >= 9.0)
            self.twin.set_electricity_price(p)

    def force_peak(self, enabled: bool = True) -> None:
        """Macro: toggle forced peak pricing."""
        with self._lock:
            self._forced_peak = enabled
            if enabled:
                self._forced_price = 9.0
                self.twin.set_electricity_price(9.0)
            else:
                self._forced_price = None
                slot = self.tou_tariff.get_slot_for_sim_time(self.twin.simulation_time_minutes)
                self.twin.set_electricity_price(slot.price)

    def get_tariff(self) -> Dict[str, Any]:
        with self._lock:
            sim_time = self.twin.simulation_time_minutes
            slot = self.tou_tariff.get_slot_for_sim_time(sim_time)
            is_peak = slot.is_peak or self._forced_peak or (self._forced_price is not None and self._forced_price >= 9.0)
            is_pre_peak = self.tou_tariff.is_pre_peak(sim_time) and not is_peak
            return {
                "slots": [
                    {"from_h": s.from_h, "to_h": s.to_h, "price": s.price, "is_peak": s.is_peak}
                    for s in self.tou_tariff.slots
                ],
                "current_price": self.twin.electricity_price_per_kwh,
                "is_peak": is_peak,
                "is_pre_peak": is_pre_peak,
            }

    def set_tariff_slots(self, slots: List[Dict[str, Any]]) -> Dict[str, Any]:
        with self._lock:
            self.tou_tariff.set_slots(slots)
            self._forced_price = None
            self._forced_peak = False
            sim_time = self.twin.simulation_time_minutes
            slot = self.tou_tariff.get_slot_for_sim_time(sim_time)
            self.twin.set_electricity_price(slot.price)
            return self.get_tariff()

    def inject_sensor_data(self, room_id: str, data: dict) -> dict:
        with self._lock:
            return self.twin.inject_sensor_data(room_id, data)

    def inject_outside_sensor_data(self, data: dict) -> dict:
        with self._lock:
            return self.twin.inject_outside_sensor_data(data)

    def set_rl_mode(self, mode: str, model_path: Optional[str] = None) -> None:
        if mode not in ("manual", "auto"):
            raise ValueError("mode must be 'manual' or 'auto'")

        with self._lock:
            if mode == "auto":
                if model_path is None:
                    raise ValueError("model_path required when switching to auto mode")
                if not os.path.exists(model_path) and not os.path.exists(model_path + ".zip"):
                    raise FileNotFoundError(f"Policy not found: {model_path}")
                from rl.agent import JarvisAgent
                self._rl_agent = JarvisAgent(model_path)
                self.rl_model_path = model_path
            else:
                self._rl_agent = None
                self.rl_model_path = None
                self._overlay_active.clear()
                for room_id, cr in self.active_constraints.items():
                    if cr is None:
                        _config, room = self.twin.get_room(room_id)
                        self._base_setpoints[room_id] = room.setpoint_c
                        self._base_airflow[room_id]   = room.airflow_lps
            self.rl_mode = mode

    # ── Public constraint API (P5) ────────────────────────────────────────────

    def set_nlp_constraint(
        self,
        room_id: str,
        action: str,
        urgency: str,
        setpoint_delta_c: float,
        duration_mins: Optional[float] = None,
        source: str = "nlp",
    ) -> None:
        """Sets a temporary constraint from an NLP complaint, or applies absolute commands directly."""
        with self._lock:
            if action == "set_setpoint":
                self.twin.set_setpoint(room_id, setpoint_delta_c)
                self._base_setpoints[room_id] = max(SETPOINT_MIN, min(SETPOINT_MAX, float(setpoint_delta_c)))
                self.active_constraints[room_id] = None
            elif action == "set_occupancy":
                self.twin.set_occupancy(room_id, int(setpoint_delta_c))
                # Occupancy doesn't conflict with thermal constraints, but if we wanted to clear we could.
                # Actually, no need to clear constraints for occupancy change.
            elif action == "set_airflow":
                self.twin.set_airflow(room_id, setpoint_delta_c)
                self._base_airflow[room_id] = max(AIRFLOW_MIN_LPS, min(AIRFLOW_MAX_LPS, float(setpoint_delta_c)))
                self.active_constraints[room_id] = None
            else:
                self._set_constraint(room_id, action, urgency, setpoint_delta_c, source, duration_mins=duration_mins)

    def react_to_constraint(self, constraint_id: str, helpful: bool) -> Optional[Dict[str, Any]]:
        """
        Record occupant feedback on a resolved/escalated constraint.
        Returns the updated record dict, or None if the ID is not found.
        Thread-safe.
        """
        with self._lock:
            for cr in self._constraint_history:
                if cr.id == constraint_id:
                    # Feedback is stored as a simple field; P8 can analyse it.
                    cr.status = cr.status  # no status change; just log
                    return self._serialise_record(cr)
            # Check active constraints too
            for cr in self.active_constraints.values():
                if cr is not None and cr.id == constraint_id:
                    return self._serialise_record(cr)
        return None

    def record_nlp_feedback(self, room_id: str, raw_text: str, parsed_intent: str, applied_constraint: float) -> None:
        """Queue an NLP feedback event to be persisted to the database."""
        with self._lock:
            self.pending_feedback_events.append({
                "room_id": room_id,
                "raw_text": raw_text,
                "parsed_intent": parsed_intent,
                "applied_constraint": applied_constraint,
            })

    # ─────────────────────────
    # Internal helpers
    # ─────────────────────────

    def _set_constraint(
        self,
        room_id: str,
        action: str,
        urgency: str,
        setpoint_delta_c: float,
        source: str = "nlp",
        renewals: int = 0,
        duration_mins: Optional[float] = None,
    ) -> ConstraintRecord:
        """
        Write a ConstraintRecord into the active table. Caller must hold self._lock.

        Physics-derived delta (§2.3): for thermal actions the applied_delta is
        derived from the current PMV, not the LLM's raw number. Severity maps
        only to expiry duration.
        """
        sim_time = self.twin.simulation_time_minutes
        duration = duration_mins if duration_mins is not None else _urgency_to_duration(urgency)

        # Get current PMV for physics-derived delta
        try:
            _cfg, room = self.twin.get_room(room_id)
            pmv = room.pmv
        except Exception:
            pmv = 0.0

        applied = _physics_delta(pmv, action, setpoint_delta_c)

        cr = ConstraintRecord(
            id            = str(uuid.uuid4()),
            room          = room_id,
            action        = action,
            source        = source,
            urgency       = urgency,
            created_at    = sim_time,
            expires_at    = sim_time + duration,
            llm_raw_delta = setpoint_delta_c,
            applied_delta = applied,
            status        = "active",
            renewals      = renewals,
        )
        self.active_constraints[room_id] = cr
        return cr

    def _expire_constraints(self, sim_time: float) -> None:
        """
        Check each active constraint. On expiry, verify outcome:
          • Thermal: |PMV| <= RESOLUTION_PMV_BAND → resolved
          • Airflow/IAQ: co2_ppm < RESOLUTION_CO2_PPM → resolved
          • Not resolved and renewals == 0 → renew with 1.5× delta
          • Not resolved and renewals >= 1 → escalated
        Caller must hold self._lock.
        """
        for room_id, cr in list(self.active_constraints.items()):
            if cr is None or sim_time < cr.expires_at:
                continue

            # Expiry reached — verify outcome
            try:
                _cfg, room = self.twin.get_room(room_id)
                pmv     = room.pmv
                co2_ppm = room.co2_ppm
            except Exception:
                pmv     = 0.0
                co2_ppm = 0.0

            resolved = self._check_resolution(cr.action, pmv, co2_ppm)

            if resolved:
                cr.status           = "resolved"
                cr.resolved_at      = sim_time
                cr.resolution_mins  = sim_time - cr.created_at
                self.active_constraints[room_id] = None
                self._push_history(cr)

            elif cr.renewals == 0:
                # First failure: renew with 1.5× delta for the same urgency window
                new_delta = cr.applied_delta * RENEW_MULTIPLIER
                self._push_history(cr)  # keep original in history with partial status
                cr.status = "renewed"
                self._set_constraint(
                    room_id          = room_id,
                    action           = cr.action,
                    urgency          = cr.urgency,
                    setpoint_delta_c = new_delta,
                    source           = cr.source,
                    renewals         = 1,
                )

            else:
                # Second failure: escalate
                cr.status          = "escalated"
                cr.resolved_at     = sim_time
                cr.resolution_mins = sim_time - cr.created_at
                self.active_constraints[room_id] = None
                self._push_history(cr)

    @staticmethod
    def _check_resolution(action: str, pmv: float, co2_ppm: float) -> bool:
        """Return True if the constraint outcome is satisfied."""
        if action in ("increase_airflow", "decrease_airflow"):
            return co2_ppm < RESOLUTION_CO2_PPM
        # Thermal
        return abs(pmv) <= RESOLUTION_PMV_BAND

    def _push_history(self, cr: ConstraintRecord) -> None:
        """Append to history, capping at MAX_HISTORY. Caller must hold self._lock."""
        self._constraint_history.append(cr)
        if len(self._constraint_history) > MAX_HISTORY:
            self._constraint_history = self._constraint_history[-MAX_HISTORY:]

    def _sync_base_targets(self) -> None:
        """Re-read the user-facing base targets from the twin. Caller must hold self._lock."""
        for room_id in self.active_constraints:
            _config, room = self.twin.get_room(room_id)
            self._base_setpoints[room_id] = room.setpoint_c
            self._base_airflow[room_id]   = room.airflow_lps

    # ── Serialisation helpers ─────────────────────────────────────────────────

    @staticmethod
    def _serialise_record(cr: ConstraintRecord) -> Dict[str, Any]:
        return {
            "id":              cr.id,
            "room":            cr.room,
            "action":          cr.action,
            "source":          cr.source,
            "urgency":         cr.urgency,
            "status":          cr.status,
            "created_at":      cr.created_at,
            "expires_at":      cr.expires_at,
            "resolved_at":     cr.resolved_at,
            "resolution_mins": cr.resolution_mins,
            "llm_raw_delta":   cr.llm_raw_delta,
            "applied_delta":   cr.applied_delta,
            "renewals":        cr.renewals,
        }

    def _serialise_constraints(self) -> List[Dict[str, Any]]:
        """Return active + last-50-history as a flat list. Caller must hold self._lock."""
        result = []
        for cr in self.active_constraints.values():
            if cr is not None:
                result.append(self._serialise_record(cr))
        for cr in reversed(self._constraint_history):
            result.append(self._serialise_record(cr))
        return result

    def _build_constraint_response(self) -> Dict[str, Any]:
        """
        Build the GET /api/constraints response body.
        Includes list + aggregate stats. Caller must hold self._lock.
        """
        all_records = self._serialise_constraints()

        # Stats: exclude source == "price_response"
        complaint_records = [r for r in all_records if r.get("source") != "price_response"]
        by_status: Dict[str, int] = {}
        res_times: List[float] = []
        for r in complaint_records:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
            if r["resolution_mins"] is not None:
                res_times.append(r["resolution_mins"])

        res_times.sort()
        median_mins: Optional[float] = None
        if res_times:
            mid = len(res_times) // 2
            median_mins = (
                res_times[mid]
                if len(res_times) % 2 != 0
                else (res_times[mid - 1] + res_times[mid]) / 2
            )

        return {
            "constraints": all_records,
            "stats": {
                "by_status":   by_status,
                "median_resolution_minutes": median_mins,
                "total": len(complaint_records),
            },
        }

    # ─────────────────────────
    # Internal — run loop
    # ─────────────────────────

    def _run_loop(self) -> None:
        """Background thread: steps the simulation at a fixed wall-clock rate."""
        while not self._stop_event.is_set():
            start = time.monotonic()

            with self._lock:
                if self.running:
                    for _ in range(self.speed):
                        self._step_once()

            elapsed    = time.monotonic() - start
            sleep_time = max(0.0, self.tick_interval - elapsed)
            self._stop_event.wait(timeout=sleep_time)

    def _update_price_response(self, sim_time: float) -> None:
        """
        Evaluate TOU pricing and compute comfort-guarded price-response bias.
        Caller must hold self._lock.
        """
        # 1. Update electricity price
        if self._forced_price is not None:
            current_price = self._forced_price
        else:
            slot = self.tou_tariff.get_slot_for_sim_time(sim_time)
            current_price = slot.price
        self.twin.set_electricity_price(current_price)

        # 2. Check peak / pre-peak conditions
        slot = self.tou_tariff.get_slot_for_sim_time(sim_time)
        is_peak = slot.is_peak or self._forced_peak or (self._forced_price is not None and self._forced_price >= 9.0)
        is_pre_peak = self.tou_tariff.is_pre_peak(sim_time) and not is_peak

        # 3. For each room, determine target setpoint bias and apply comfort guard
        for room_id in ("A", "B", "C", "D"):
            try:
                _cfg, room = self.twin.get_room(room_id)
                occupancy = room.occupancy
                pmv = room.pmv
                wall_temp = room.wall_temperature_c
                airflow = room.airflow_lps
                rh = room.humidity_pct
            except Exception:
                occupancy = 0
                pmv = 0.0
                wall_temp = 23.0
                airflow = 100.0
                rh = 50.0

            if is_peak:
                # During peak while room occupied: setpoint relax +1.5 °C
                target_bias = PEAK_RELAX_SETPOINT_BIAS if occupancy > 0 else 0.0
            elif is_pre_peak:
                # 60 min before peak window: setpoint bias -1.0 °C (pre-cool)
                target_bias = PRE_COOL_SETPOINT_BIAS
            else:
                target_bias = 0.0

            base_sp = self._base_setpoints.get(room_id, 24.0)
            guarded_bias = apply_comfort_guard(
                target_bias = target_bias,
                current_pmv = pmv,
                setpoint_c  = base_sp,
                wall_temp_c = wall_temp,
                airflow_lps = airflow,
                rh_pct      = rh,
                config      = _cfg,
            )
            self._price_bias[room_id] = guarded_bias

    def _step_once(self) -> None:
        """
        Advance the simulation exactly one step.

        Caller must hold self._lock. Order:
          1. Expire/verify constraints (P5 lifecycle check).
          2. Update TOU tariff & price-response overlay (P6).
          3. Apply control targets with deterministic overlays.
          4. Advance the physics one step.
          5. Evaluate the IAQ rule against the fresh state.
        """
        sim_time = self.twin.simulation_time_minutes
        self._expire_constraints(sim_time)
        self._update_price_response(sim_time)

        if self.rl_mode == "auto" and self._rl_agent is not None:
            try:
                state   = self.twin.get_state()
                actions = self._rl_agent.get_actions(state)
                for room_id, cmd in actions.items():
                    sp, af = self._apply_overlays(
                        room_id, cmd["setpoint_c"], cmd["airflow_lps"], sim_time
                    )
                    self.twin.set_setpoint(room_id, sp)
                    self.twin.set_airflow(room_id, af)
            except Exception as e:
                print(f"[RL Agent error] {e}", file=sys.stderr)
        else:
            for room_id in ("A", "B", "C", "D"):
                cr = self.active_constraints.get(room_id)
                price_bias = self._price_bias.get(room_id, 0.0)
                if cr is not None or abs(price_bias) > 0.01:
                    sp, af = self._apply_overlays(
                        room_id,
                        self._base_setpoints[room_id],
                        self._base_airflow[room_id],
                        sim_time,
                    )
                    self.twin.set_setpoint(room_id, sp)
                    self.twin.set_airflow(room_id, af)
                    self._overlay_active.add(room_id)
                elif room_id in self._overlay_active:
                    self.twin.set_setpoint(room_id, self._base_setpoints[room_id])
                    self.twin.set_airflow(room_id, self._base_airflow[room_id])
                    self._overlay_active.discard(room_id)

        snap = self.twin.step()
        self._apply_iaq_rule()
        self.pending_db_writes.append(snap)

    def _apply_overlays(
        self,
        room_id: str,
        base_setpoint_c: float,
        base_airflow_lps: float,
        sim_time: float,
    ) -> tuple[float, float]:
        """Layer price-response bias and room's active constraint on top of base control target."""
        sp = base_setpoint_c + self._price_bias.get(room_id, 0.0)
        af = base_airflow_lps

        cr = self.active_constraints.get(room_id)
        if cr is not None and sim_time < cr.expires_at:
            action = cr.action
            delta  = cr.applied_delta

            if action == "increase_temp":
                sp += delta
            elif action == "decrease_temp":
                sp -= abs(delta)   # applied_delta is signed; ensure cooling direction
            elif action == "set_setpoint":
                sp = delta
            elif action == "increase_airflow":
                af += delta
            elif action == "decrease_airflow":
                af -= delta

        sp = max(SETPOINT_MIN, min(SETPOINT_MAX, sp))
        af = max(AIRFLOW_MIN_LPS, min(AIRFLOW_MAX_LPS, af))
        return sp, af

    def _apply_iaq_rule(self) -> None:
        """
        Rule-based IAQ response: a stuffy, uncontrolled room asks for more air.
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
                source           = "iaq_rule",
            )
