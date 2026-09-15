"""
test_iaq.py — CO2 / IAQ acceptance tests (build phase P2).

Covers MASTER_PROMPT_3D §2.1:
  - CO2 mass-balance dynamics (rise, decay, steady state, numerical clamps)
  - iaq_score / overall_comfort_score mapping
  - per-room nominal volumes
  - the automatic IAQ rule in SimulationManager: trigger above 1000 ppm,
    no re-trigger while a constraint is active, no trigger when an NLP
    constraint owns the room, and restore of the base airflow on expiry.

The manager tests drive `_step_once()` directly instead of starting the
background thread, so they are deterministic (no wall-clock timing).
"""
from __future__ import annotations

import pytest

from backend.comfort_model import iaq_score, overall_comfort_score
from backend.digital_twin import ROOM_VOLUMES_M3, BuildingTwin
from backend.simulation_manager import (
    IAQ_MIN_AIRFLOW_DELTA_LPS,
    IAQ_TARGET_PPM,
    IAQ_TRIGGER_PPM,
    SimulationManager,
)
from backend.thermal_model import (
    CO2_GENERATION_LPS_PER_OCCUPANT,
    CO2_INITIAL_PPM,
    CO2_MAX_PPM,
    CO2_MIN_PPM,
    CO2_OUTDOOR_PPM,
    airflow_to_hold_co2,
    compute_next_co2,
)


# ──────────────────────────────────────────────
# CO2 mass balance
# ──────────────────────────────────────────────

class TestComputeNextCo2:
    def test_occupants_raise_co2_without_ventilation(self):
        next_ppm = compute_next_co2(
            450.0, occupancy=14, airflow_lps=0.0, volume_m3=150.0, dt_minutes=5.0
        )
        expected_rise = CO2_GENERATION_LPS_PER_OCCUPANT * 14 * 1e6 * 300.0 / (150.0 * 1000.0)
        assert next_ppm == pytest.approx(450.0 + expected_rise)
        assert next_ppm > 450.0

    def test_ventilation_pulls_co2_toward_outdoor(self):
        next_ppm = compute_next_co2(
            900.0, occupancy=0, airflow_lps=200.0, volume_m3=150.0, dt_minutes=5.0
        )
        assert CO2_OUTDOOR_PPM < next_ppm < 900.0

    def test_ventilated_co2_decays_monotonically(self):
        co2 = 2000.0
        for _ in range(20):
            new_co2 = compute_next_co2(
                co2, occupancy=0, airflow_lps=200.0, volume_m3=100.0, dt_minutes=5.0
            )
            assert new_co2 < co2
            co2 = new_co2

    def test_steady_state_matches_airflow_to_hold(self):
        airflow = airflow_to_hold_co2(occupancy=14, target_ppm=900.0)
        co2 = 450.0
        for _ in range(200):
            co2 = compute_next_co2(
                co2, occupancy=14, airflow_lps=airflow, volume_m3=150.0, dt_minutes=5.0
            )
        assert co2 == pytest.approx(900.0, abs=0.5)

    def test_clamped_to_numerical_bounds(self):
        assert compute_next_co2(
            2999.0, occupancy=100, airflow_lps=0.0, volume_m3=60.0, dt_minutes=5.0
        ) == CO2_MAX_PPM
        assert compute_next_co2(
            500.0, occupancy=0, airflow_lps=300.0, volume_m3=60.0, dt_minutes=5.0
        ) == CO2_MIN_PPM

    def test_airflow_to_hold_co2_analytic(self):
        # 12 occupants → 0.06 L/s generation → 0.06e6 / (900 − 420) = 125 L/s
        assert airflow_to_hold_co2(12, 900.0) == pytest.approx(125.0)
        assert airflow_to_hold_co2(14, IAQ_TARGET_PPM) == pytest.approx(70000.0 / 480.0)
        assert airflow_to_hold_co2(0, 900.0) == 0.0
        assert airflow_to_hold_co2(12, 400.0) == 0.0


# ──────────────────────────────────────────────
# IAQ scoring
# ──────────────────────────────────────────────

class TestIaqScore:
    def test_score_is_100_at_or_below_good_threshold(self):
        assert iaq_score(800.0) == 100.0
        assert iaq_score(400.0) == 100.0

    def test_score_is_0_at_or_above_bad_threshold(self):
        assert iaq_score(2000.0) == 0.0
        assert iaq_score(3000.0) == 0.0

    def test_linear_midpoint(self):
        assert iaq_score(1400.0) == pytest.approx(50.0)

    def test_monotonically_decreasing_with_co2(self):
        scores = [iaq_score(ppm) for ppm in range(400, 2100, 50)]
        assert all(later <= earlier for earlier, later in zip(scores, scores[1:]))
        assert scores[0] == 100.0
        assert scores[-1] == 0.0

    def test_overall_comfort_blend(self):
        assert overall_comfort_score(90.0, 50.0) == pytest.approx(78.0)
        assert overall_comfort_score(100.0, 100.0) == 100.0
        assert overall_comfort_score(0.0, 0.0) == 0.0


# ──────────────────────────────────────────────
# Digital twin integration
# ──────────────────────────────────────────────

class TestDigitalTwinIaq:
    def test_per_room_volumes_match_spec(self):
        assert ROOM_VOLUMES_M3 == {"A": 80.0, "B": 150.0, "C": 60.0, "D": 100.0}
        twin = BuildingTwin()
        for room_id, volume in ROOM_VOLUMES_M3.items():
            config, _state = twin.get_room(room_id)
            assert config.nominal_volume_m3 == volume

    def test_rooms_start_at_initial_co2_with_full_iaq(self):
        twin = BuildingTwin()
        for room_id in "ABCD":
            room = twin.get_state()["rooms"][room_id]
            assert room["co2_ppm"] == CO2_INITIAL_PPM
            assert room["iaq_score"] == 100.0

    def test_co2_climbs_and_feeds_iaq_in_room_b(self):
        twin = BuildingTwin()
        twin.set_occupancy("B", 14)
        twin.set_airflow("B", 60.0)

        _config, before = twin.get_room("B")
        co2_before = before.co2_ppm
        twin.step()
        _config, after = twin.get_room("B")

        assert after.co2_ppm > co2_before
        assert after.iaq_score == pytest.approx(iaq_score(after.co2_ppm))
        assert after.overall_comfort_score == pytest.approx(
            overall_comfort_score(after.comfort_score, after.iaq_score)
        )

    def test_history_points_include_co2(self):
        twin = BuildingTwin()
        twin.step()
        assert "co2_ppm" in twin.get_history()[-1]["rooms"]["B"]


# ──────────────────────────────────────────────
# IAQ rule in the simulation manager
# ──────────────────────────────────────────────

def _make_manager() -> SimulationManager:
    return SimulationManager(outside_temperature_c=34.0, electricity_price_per_kwh=8.5)


def _step_until_constraint(manager: SimulationManager, room_id: str, max_steps: int = 40):
    """Step the manager until an IAQ constraint appears. Returns steps taken or None."""
    for steps in range(1, max_steps + 1):
        manager._step_once()
        if manager.active_constraints[room_id] is not None:
            return steps
    return None


class TestIaqRule:
    def test_default_scenario_climbs_but_stays_below_trigger(self):
        manager = _make_manager()
        for _ in range(60):
            manager._step_once()

        _config, room_b = manager.twin.get_room("B")
        assert room_b.co2_ppm > CO2_INITIAL_PPM    # climbing at 12 occupants
        assert room_b.co2_ppm < IAQ_TRIGGER_PPM    # but not stuffy
        assert all(c is None for c in manager.active_constraints.values())

    def test_rule_triggers_above_1000_ppm(self):
        manager = _make_manager()
        manager.set_occupancy("B", 14)
        manager.set_airflow("B", 60.0)

        assert _step_until_constraint(manager, "B") is not None, "IAQ rule did not fire"

        constraint = manager.active_constraints["B"]
        assert constraint["action"] == "increase_airflow"
        assert constraint["source"] == "iaq_rule"
        assert constraint["setpoint_delta_c"] >= IAQ_MIN_AIRFLOW_DELTA_LPS

        # The constraint surfaces in the UI state payload ...
        state = manager.get_state()
        assert state["rooms"]["B"]["active_constraint"] == "INCREASE_AIRFLOW"

        # ... and the overlay raises airflow above the user's base
        manager._step_once()
        _config, room_b = manager.twin.get_room("B")
        assert room_b.airflow_lps > 60.0

    def test_co2_falls_below_trigger_while_constraint_active(self):
        manager = _make_manager()
        manager.set_occupancy("B", 14)
        manager.set_airflow("B", 60.0)
        assert _step_until_constraint(manager, "B") is not None

        for _ in range(3):
            manager._step_once()

        _config, room_b = manager.twin.get_room("B")
        assert room_b.co2_ppm < IAQ_TRIGGER_PPM

    def test_rule_does_not_replace_active_constraint(self):
        manager = _make_manager()
        manager.set_occupancy("B", 14)
        manager.set_airflow("B", 60.0)
        assert _step_until_constraint(manager, "B") is not None

        constraint = manager.active_constraints["B"]
        for _ in range(3):
            manager._step_once()

        assert manager.active_constraints["B"] is constraint
        assert manager.active_constraints["B"]["source"] == "iaq_rule"

    def test_rule_skips_room_with_active_nlp_constraint(self):
        manager = _make_manager()
        manager.set_occupancy("B", 14)
        manager.set_airflow("B", 60.0)
        manager.set_nlp_constraint("B", "decrease_temp", "medium", 1.5, duration_mins=120.0)

        for _ in range(15):
            manager._step_once()

        constraint = manager.active_constraints["B"]
        assert constraint is not None
        assert constraint["source"] == "nlp"
        assert constraint["action"] == "decrease_temp"

    def test_airflow_restores_to_base_on_expiry(self):
        manager = _make_manager()
        manager.set_occupancy("B", 14)
        manager.set_airflow("B", 60.0)
        assert _step_until_constraint(manager, "B") is not None

        expires_at = manager.active_constraints["B"]["expires_at"]
        while manager.twin.simulation_time_minutes < expires_at:
            manager._step_once()
        manager._step_once()   # the expiry step: control handed back before physics

        _config, room_b = manager.twin.get_room("B")
        assert room_b.airflow_lps == pytest.approx(60.0)


# ──────────────────────────────────────────────
# API surface
# ──────────────────────────────────────────────

class TestApiSurface:
    def test_state_endpoint_exposes_iaq_fields(self):
        from fastapi.testclient import TestClient

        from backend.main import app

        with TestClient(app) as client:
            response = client.get("/api/simulation/state")

        assert response.status_code == 200
        rooms = response.json()["rooms"]
        for room_id in "ABCD":
            room = rooms[room_id]
            assert "co2_ppm" in room
            assert "iaq_score" in room
            assert "overall_comfort_score" in room
