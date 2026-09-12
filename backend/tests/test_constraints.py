"""
test_constraints.py — P5 lifecycle tests for ConstraintRecord.

Three scenarios (MASTER_PROMPT_3D §P5 acceptance criteria):
  1. resolution-success : constraint resolves before expiry when CO2 drops.
  2. renew              : first expiry fails, constraint renewed with 1.5× delta.
  3. escalate           : second expiry fails, constraint escalated.

The tests drive SimulationManager in isolation (no background thread) by calling
_step_once() directly and manipulating the twin state. They import SimulationManager
from the backend package, so run from the project root with:

    py -3 -m pytest backend/tests/test_constraints.py -v
"""
from __future__ import annotations

import math
import sys
import os

# ── Path setup ────────────────────────────────────────────────────────────────
# Allow importing backend.* from the project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.simulation_manager import (
    SimulationManager,
    IAQ_TRIGGER_PPM,
    IAQ_CONSTRAINT_DURATION_MINS,
    RESOLUTION_CO2_PPM,
    RENEW_MULTIPLIER,
    MAX_HISTORY,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_manager() -> SimulationManager:
    """Fresh manager, not running (no background thread)."""
    return SimulationManager(
        step_minutes=5.0,
        tick_interval_seconds=1.0,
        outside_temperature_c=34.0,
        electricity_price_per_kwh=8.5,
    )


def inject_active_constraint(
    mgr: SimulationManager,
    room_id: str = "B",
    action: str = "increase_airflow",
    urgency: str = "high",
    delta: float = 50.0,
    source: str = "iaq_rule",
) -> None:
    """Directly write a constraint without going through the IAQ rule."""
    with mgr._lock:
        mgr._set_constraint(room_id, action, urgency, delta, source)


def fast_forward_past_expiry(mgr: SimulationManager, room_id: str = "B") -> None:
    """Advance sim time past the constraint expiry by mutating the twin clock."""
    with mgr._lock:
        cr = mgr.active_constraints.get(room_id)
        if cr is not None:
            # Push the clock just past expiry
            mgr.twin.simulation_time_minutes = cr.expires_at + 1.0


def set_co2(mgr: SimulationManager, room_id: str, ppm: float) -> None:
    """Directly set the room's co2_ppm for test purposes."""
    with mgr._lock:
        _cfg, room = mgr.twin.get_room(room_id)
        room.co2_ppm = ppm


def get_active(mgr: SimulationManager, room_id: str = "B"):
    with mgr._lock:
        return mgr.active_constraints.get(room_id)


def get_history(mgr: SimulationManager):
    with mgr._lock:
        return list(mgr._constraint_history)


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestConstraintResolutionSuccess:
    """Constraint resolves cleanly when CO2 drops below RESOLUTION_CO2_PPM."""

    def test_constraint_active_before_expiry(self) -> None:
        mgr = make_manager()
        inject_active_constraint(mgr, "B")
        cr = get_active(mgr, "B")
        assert cr is not None
        assert cr.status == "active"
        assert cr.room == "B"

    def test_resolves_when_co2_is_good(self) -> None:
        mgr = make_manager()
        inject_active_constraint(mgr, "B")

        # CO2 already low → at expiry the outcome check passes → resolved
        set_co2(mgr, "B", RESOLUTION_CO2_PPM - 10)  # e.g. 940 ppm
        fast_forward_past_expiry(mgr, "B")

        with mgr._lock:
            sim_time = mgr.twin.simulation_time_minutes
            mgr._expire_constraints(sim_time)

        assert get_active(mgr, "B") is None, "Constraint should be cleared"
        history = get_history(mgr)
        assert len(history) == 1
        assert history[0].status == "resolved"
        assert history[0].resolution_mins is not None
        assert history[0].resolution_mins > 0

    def test_resolution_time_recorded(self) -> None:
        mgr = make_manager()
        inject_active_constraint(mgr, "B")
        set_co2(mgr, "B", 800.0)
        fast_forward_past_expiry(mgr, "B")

        with mgr._lock:
            sim_time = mgr.twin.simulation_time_minutes
            cr_before = mgr.active_constraints["B"]
            expected_duration = sim_time - cr_before.created_at
            mgr._expire_constraints(sim_time)

        history = get_history(mgr)
        assert history[0].resolution_mins == pytest_approx(expected_duration, abs=1.0)


class TestConstraintRenew:
    """First expiry with bad outcome triggers a renewal with 1.5× delta."""

    def test_renewal_created_on_first_failure(self) -> None:
        mgr = make_manager()
        inject_active_constraint(mgr, "B", delta=60.0)

        # High CO2 at expiry → not resolved → should renew
        set_co2(mgr, "B", IAQ_TRIGGER_PPM + 200)  # still high
        fast_forward_past_expiry(mgr, "B")

        with mgr._lock:
            sim_time = mgr.twin.simulation_time_minutes
            mgr._expire_constraints(sim_time)

        new_cr = get_active(mgr, "B")
        assert new_cr is not None, "Renewed constraint should be active"
        assert new_cr.renewals == 1, "renewals count should be 1"
        assert new_cr.status == "active"

    def test_renewed_delta_is_15x(self) -> None:
        mgr = make_manager()
        original_delta = 60.0
        inject_active_constraint(mgr, "B", delta=original_delta)

        set_co2(mgr, "B", IAQ_TRIGGER_PPM + 200)
        fast_forward_past_expiry(mgr, "B")

        with mgr._lock:
            sim_time = mgr.twin.simulation_time_minutes
            mgr._expire_constraints(sim_time)

        new_cr = get_active(mgr, "B")
        assert new_cr is not None
        # applied_delta for airflow actions equals the passed delta
        # The renewal delta = original applied_delta * RENEW_MULTIPLIER
        # The original record's applied_delta was original_delta (airflow type)
        history = get_history(mgr)
        assert len(history) >= 1
        original_record = history[0]
        expected_renewal = original_record.applied_delta * RENEW_MULTIPLIER
        assert abs(new_cr.applied_delta - expected_renewal) < 0.01

    def test_first_record_in_history_after_renewal(self) -> None:
        mgr = make_manager()
        inject_active_constraint(mgr, "B", delta=60.0)
        set_co2(mgr, "B", IAQ_TRIGGER_PPM + 200)
        fast_forward_past_expiry(mgr, "B")

        with mgr._lock:
            sim_time = mgr.twin.simulation_time_minutes
            mgr._expire_constraints(sim_time)

        history = get_history(mgr)
        # Original record pushed to history with status 'renewed'
        assert any(r.status == "renewed" for r in history)


class TestConstraintEscalate:
    """Second failure (renewals==1) → escalated."""

    def _get_to_escalated(self, mgr: SimulationManager, room_id: str = "B") -> None:
        """Drive the manager through: active → renewed → escalated."""
        # First constraint
        inject_active_constraint(mgr, room_id, delta=60.0)
        set_co2(mgr, room_id, IAQ_TRIGGER_PPM + 300)
        fast_forward_past_expiry(mgr, room_id)

        with mgr._lock:
            mgr._expire_constraints(mgr.twin.simulation_time_minutes)

        # Now renewed — fail the renewed constraint too
        set_co2(mgr, room_id, IAQ_TRIGGER_PPM + 300)
        fast_forward_past_expiry(mgr, room_id)

        with mgr._lock:
            mgr._expire_constraints(mgr.twin.simulation_time_minutes)

    def test_escalated_after_second_failure(self) -> None:
        mgr = make_manager()
        self._get_to_escalated(mgr)

        assert get_active(mgr, "B") is None, "Escalated constraint should be removed from active"
        history = get_history(mgr)
        escalated = [r for r in history if r.status == "escalated"]
        assert len(escalated) >= 1, "At least one escalated record in history"

    def test_no_third_renewal(self) -> None:
        mgr = make_manager()
        self._get_to_escalated(mgr)
        # After escalation, no active constraint remains
        assert get_active(mgr, "B") is None

    def test_escalated_resolution_time_recorded(self) -> None:
        mgr = make_manager()
        self._get_to_escalated(mgr)
        history = get_history(mgr)
        escalated = [r for r in history if r.status == "escalated"]
        assert escalated[0].resolved_at is not None
        assert escalated[0].resolution_mins is not None


class TestConstraintStats:
    """get_constraints() returns stats including by_status counts and median."""

    def test_empty_stats(self) -> None:
        mgr = make_manager()
        result = mgr.get_constraints()
        assert result["stats"]["total"] == 0
        assert result["stats"]["median_resolution_minutes"] is None

    def test_active_appears_in_list(self) -> None:
        mgr = make_manager()
        inject_active_constraint(mgr, "A")
        result = mgr.get_constraints()
        active_list = [r for r in result["constraints"] if r["status"] == "active"]
        assert len(active_list) == 1
        assert active_list[0]["room"] == "A"

    def test_stats_count_resolved(self) -> None:
        mgr = make_manager()
        inject_active_constraint(mgr, "A")
        set_co2(mgr, "A", 800.0)
        fast_forward_past_expiry(mgr, "A")

        with mgr._lock:
            mgr._expire_constraints(mgr.twin.simulation_time_minutes)

        result = mgr.get_constraints()
        assert result["stats"]["by_status"].get("resolved", 0) == 1
        assert result["stats"]["median_resolution_minutes"] is not None

    def test_history_capped_at_max(self) -> None:
        mgr = make_manager()
        # Stuff MAX_HISTORY + 5 resolved records in
        for _ in range(MAX_HISTORY + 5):
            inject_active_constraint(mgr, "B")
            set_co2(mgr, "B", 800.0)
            fast_forward_past_expiry(mgr, "B")
            with mgr._lock:
                mgr._expire_constraints(mgr.twin.simulation_time_minutes)

        history = get_history(mgr)
        assert len(history) <= MAX_HISTORY


# ── Tiny helper imported above ─────────────────────────────────────────────────
def pytest_approx(value, abs=None, rel=None):
    """
    Shim so the test file works without importing pytest at module level.
    Real runs use pytest.approx; for basic assertion coverage this is fine.
    """
    try:
        import pytest
        return pytest.approx(value, abs=abs, rel=rel)
    except ImportError:
        return value  # fall back to exact check
