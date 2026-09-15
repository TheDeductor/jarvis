"""
test_price_response.py  —  Unit tests for Phase 6 (MASTER_PROMPT_3D §2.4, docs/PHASES.md P6):
  1. TOU tariff defaults, schedule lookup, and slot modification.
  2. Comfort guard (±0.7 PMV floor and ceiling with smooth bias reduction).
  3. Pre-cool (-1.0°C) 60 min before peak and peak-relax (+1.5°C) during peak.
  4. Building metrics: current_price, cost_today, baseline_cost_today, peak_kw_15min, baseline_average_comfort.
  5. Constraint stats exclusion for source="price_response".
"""
import pytest
from backend.simulation_manager import (
    DEFAULT_TOU_SLOTS,
    PRE_COOL_SETPOINT_BIAS,
    PEAK_RELAX_SETPOINT_BIAS,
    COMFORT_GUARD_PMV_MIN,
    COMFORT_GUARD_PMV_MAX,
    TouTariff,
    apply_comfort_guard,
    SimulationManager,
)


def _make_manager() -> SimulationManager:
    m = SimulationManager(
        step_minutes=5.0,
        tick_interval_seconds=0.01,
        outside_temperature_c=34.0,
        electricity_price_per_kwh=6.0,
    )
    return m


# ─────────────────────────────────────────────────────────────────────────────
# 1. TOU Tariff & Schedule Lookup
# ─────────────────────────────────────────────────────────────────────────────

class TestTouTariff:
    def test_default_slots_structure(self):
        tariff = TouTariff()
        assert len(tariff.slots) == 4
        assert tariff.slots[0].price == 4.0
        assert tariff.slots[0].is_peak is False
        assert tariff.slots[1].price == 6.0
        assert tariff.slots[2].price == 9.0
        assert tariff.slots[2].is_peak is True
        assert tariff.slots[3].price == 6.0

    def test_time_lookup(self):
        tariff = TouTariff()
        # sim_time = 0.0 is 08:00 AM -> slot 06-14 (price 6.0)
        slot_8am = tariff.get_slot_for_sim_time(0.0)
        assert slot_8am.from_h == 6
        assert slot_8am.to_h == 14
        assert slot_8am.price == 6.0
        assert slot_8am.is_peak is False
        assert tariff.is_pre_peak(0.0) is False

        # sim_time = 300.0 is 13:00 PM (60 min before 14:00 peak) -> is_pre_peak is True
        slot_1pm = tariff.get_slot_for_sim_time(300.0)
        assert slot_1pm.price == 6.0
        assert slot_1pm.is_peak is False
        assert tariff.is_pre_peak(300.0) is True

        # sim_time = 360.0 is 14:00 PM -> Peak slot
        slot_2pm = tariff.get_slot_for_sim_time(360.0)
        assert slot_2pm.from_h == 14
        assert slot_2pm.to_h == 20
        assert slot_2pm.price == 9.0
        assert slot_2pm.is_peak is True
        assert tariff.is_pre_peak(360.0) is False

        # sim_time = 720.0 is 20:00 PM -> slot 20-24 (price 6.0)
        slot_8pm = tariff.get_slot_for_sim_time(720.0)
        assert slot_8pm.price == 6.0
        assert slot_8pm.is_peak is False

        # sim_time = 1000.0 is 00:40 AM -> slot 00-06 (price 4.0)
        slot_midnight = tariff.get_slot_for_sim_time(1000.0)
        assert slot_midnight.price == 4.0
        assert slot_midnight.is_peak is False

    def test_custom_tariff_slots(self):
        tariff = TouTariff([
            {"from_h": 0, "to_h": 12, "price": 5.0, "is_peak": False},
            {"from_h": 12, "to_h": 24, "price": 11.0, "is_peak": True},
        ])
        assert len(tariff.slots) == 2
        # At 08:00 (sim_time = 0.0) -> first slot (5.0)
        assert tariff.get_slot_for_sim_time(0.0).price == 5.0
        # At 13:00 (sim_time = 300.0) -> second slot (11.0, peak)
        assert tariff.get_slot_for_sim_time(300.0).price == 11.0
        assert tariff.get_slot_for_sim_time(300.0).is_peak is True


# ─────────────────────────────────────────────────────────────────────────────
# 2. Comfort Guard Math (±0.7 PMV)
# ─────────────────────────────────────────────────────────────────────────────

class TestComfortGuard:
    def test_pre_cool_near_neutral_pmv(self):
        # Room at neutral PMV ~ 0.0: full pre-cooling (-1.0 °C) allowed
        bias = apply_comfort_guard(
            target_bias=-1.0,
            current_pmv=0.0,
            setpoint_c=24.0,
            wall_temp_c=24.0,
            airflow_lps=100.0,
            rh_pct=50.0,
        )
        assert bias == pytest.approx(-1.0, abs=0.1)

    def test_pre_cool_guard_blocks_when_already_too_cold(self):
        # Room PMV <= -0.7: pre-cool bias MUST be 0.0 (no further cooling)
        bias = apply_comfort_guard(
            target_bias=-1.0,
            current_pmv=-0.75,
            setpoint_c=22.0,
            wall_temp_c=21.0,
            airflow_lps=100.0,
            rh_pct=50.0,
        )
        assert bias == 0.0

    def test_pre_cool_guard_reduces_bias_smoothly(self):
        # Room PMV = -0.60: headroom is 0.10 PMV -> bias reduced
        bias = apply_comfort_guard(
            target_bias=-1.0,
            current_pmv=-0.60,
            setpoint_c=23.0,
            wall_temp_c=22.5,
            airflow_lps=100.0,
            rh_pct=50.0,
        )
        assert -0.5 <= bias < 0.0

    def test_peak_relax_near_neutral_pmv(self):
        # Room at neutral PMV ~ 0.0: full peak relax (+1.5 °C) allowed
        bias = apply_comfort_guard(
            target_bias=1.5,
            current_pmv=0.0,
            setpoint_c=23.0,
            wall_temp_c=23.0,
            airflow_lps=100.0,
            rh_pct=50.0,
        )
        assert bias == pytest.approx(1.5, abs=0.1)

    def test_peak_relax_guard_blocks_when_already_too_warm(self):
        # Room PMV >= +0.7: peak relax bias MUST be 0.0 (no further warming)
        bias = apply_comfort_guard(
            target_bias=1.5,
            current_pmv=0.75,
            setpoint_c=25.0,
            wall_temp_c=26.0,
            airflow_lps=100.0,
            rh_pct=50.0,
        )
        assert bias == 0.0

    def test_peak_relax_guard_reduces_bias_smoothly(self):
        # Room PMV = +0.60: headroom is 0.10 PMV -> bias reduced
        bias = apply_comfort_guard(
            target_bias=1.5,
            current_pmv=0.60,
            setpoint_c=24.0,
            wall_temp_c=25.0,
            airflow_lps=100.0,
            rh_pct=50.0,
        )
        assert 0.0 < bias <= 0.60


# ─────────────────────────────────────────────────────────────────────────────
# 3. Price Response Overlay Execution
# ─────────────────────────────────────────────────────────────────────────────

class TestPriceResponseOverlay:
    def test_force_peak_applies_relax_bias(self):
        manager = _make_manager()
        manager.set_occupancy("A", 8)
        base_sp = manager._base_setpoints["A"]

        manager.force_peak(True)
        manager._step_once()

        state = manager.get_state()
        assert state["building"]["is_peak"] is True
        assert state["building"]["price_response_active"] is True
        # Room A is occupied: setpoint should increase by relax bias
        _cfg, room = manager.twin.get_room("A")
        assert room.setpoint_c > base_sp
        assert room.setpoint_c <= base_sp + 1.5

    def test_unoccupied_room_not_relaxed(self):
        manager = _make_manager()
        manager.set_occupancy("C", 0)  # unoccupied
        base_sp = manager._base_setpoints["C"]

        manager.force_peak(True)
        manager._step_once()

        _cfg, room = manager.twin.get_room("C")
        # Unoccupied room gets 0 relax bias
        assert room.setpoint_c == pytest.approx(base_sp, abs=0.01)

    def test_pre_cool_window_triggers_cooling_bias(self):
        manager = _make_manager()
        # Advance simulation time to 13:00 PM (sim_time = 300.0 min)
        manager.twin.simulation_time_minutes = 300.0
        base_sp = manager._base_setpoints["B"]

        manager._step_once()
        state = manager.get_state()

        assert state["building"]["is_pre_peak"] is True
        assert state["building"]["price_response_active"] is True
        _cfg, room = manager.twin.get_room("B")
        # Pre-cooling bias reduces setpoint
        assert room.setpoint_c < base_sp
        assert room.setpoint_c >= base_sp - 1.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Building Metrics & Parity Fields (P6)
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildingStateMetrics:
    def test_p6_state_fields_exist_and_populate(self):
        manager = _make_manager()
        for _ in range(5):
            manager._step_once()

        state = manager.get_state()
        b = state["building"]

        assert "current_price" in b
        assert "cost_today" in b
        assert "baseline_cost_today" in b
        assert "peak_kw_15min" in b
        assert "baseline_average_comfort" in b
        assert "price_response_active" in b
        assert "is_peak" in b
        assert "is_pre_peak" in b

        assert b["cost_today"] > 0.0
        assert b["baseline_cost_today"] > 0.0
        assert b["peak_kw_15min"] > 0.0
        assert b["baseline_average_comfort"] > 0.0

    def test_history_includes_cost_and_parity_data(self):
        manager = _make_manager()
        for _ in range(4):
            manager._step_once()

        history = manager.get_history()
        assert len(history) >= 4
        latest = history[-1]

        assert "cost" in latest
        assert "baseline_cost" in latest
        assert "peak_kw_15min" in latest
        assert "baseline_average_comfort" in latest
        assert "electricity_price" in latest

    def test_complaint_stats_exclude_price_response(self):
        manager = _make_manager()
        manager.force_peak(True)
        manager._step_once()

        # Constraints response
        res = manager.get_constraints()
        # Complaint stats should have 0 complaints (price_response excluded from complaint count)
        assert res["stats"]["total"] == 0
        assert res["stats"]["by_status"] == {}
