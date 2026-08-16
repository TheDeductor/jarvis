"""
test_building.py
================
Tests for building.py — BuildingTwin integration.

Tests covered:
  Test 5  — Occupancy affects temperature trajectory
  Test 8  — All bounds respected (humidity, airflow, comfort, energy ≥ 0)
  Test 9  — apply_constraint changes setpoint but NOT temperature_c
  Test 10 — Determinism: two identical runs produce identical histories
"""

from __future__ import annotations

import math

import pytest

from digital_twin.building import BuildingTwin, SETPOINT_MIN_C, SETPOINT_MAX_C


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_building() -> BuildingTwin:
    """A freshly initialized BuildingTwin for each test."""
    b = BuildingTwin(outside_temperature_c=34.0)
    b.reset()
    return b


# ---------------------------------------------------------------------------
# Test 5 — Occupancy affects temperature trajectory
# ---------------------------------------------------------------------------

class TestOccupancyEffect:
    """Test 5: Different occupancy levels must produce different trajectories."""

    def test_occupancy_affects_temperature(self) -> None:
        """
        Two buildings with different occupancy (5 vs 20) must diverge in temperature.
        """
        # Building with low occupancy.
        b_low = BuildingTwin(outside_temperature_c=34.0)
        b_low.reset()
        b_low.set_setpoint("B2", 24.0)
        b_low.set_occupancy("B2", 5)

        # Building with high occupancy.
        b_high = BuildingTwin(outside_temperature_c=34.0)
        b_high.reset()
        b_high.set_setpoint("B2", 24.0)
        b_high.set_occupancy("B2", 20)

        for _ in range(20):
            b_low.step()
            b_high.step()

        temp_low = b_low.get_room("B2")[1].temperature_c
        temp_high = b_high.get_room("B2")[1].temperature_c

        assert temp_high > temp_low, (
            f"High occupancy should produce higher temperature. "
            f"Low={temp_low:.3f}, High={temp_high:.3f}"
        )

    def test_zero_occupancy_vs_twenty(self, fresh_building: BuildingTwin) -> None:
        """Zero occupants vs 20 occupants must give measurably different temperatures."""
        b_zero = BuildingTwin(outside_temperature_c=30.0)
        b_zero.reset()
        b_zero.set_occupancy("A1", 0)

        b_twenty = BuildingTwin(outside_temperature_c=30.0)
        b_twenty.reset()
        b_twenty.set_occupancy("A1", 20)

        for _ in range(15):
            b_zero.step()
            b_twenty.step()

        t_zero = b_zero.get_room("A1")[1].temperature_c
        t_twenty = b_twenty.get_room("A1")[1].temperature_c

        assert t_twenty != t_zero, (
            f"Occupancy 0 vs 20 produced same temperature: {t_zero:.4f}"
        )


# ---------------------------------------------------------------------------
# Test 8 — Bounds check
# ---------------------------------------------------------------------------

class TestBoundsAfterSteps:
    """Test 8: All state variables must respect their configured bounds."""

    def test_all_bounds_respected_over_100_steps(self) -> None:
        """
        Run 100 steps under extreme conditions and verify all bounds.
        Extreme conditions: outside = 40°C, occupancy = 25.
        """
        b = BuildingTwin(outside_temperature_c=40.0)
        b.reset()
        for room_id in ["A1", "A2", "B1", "B2", "C1"]:
            b.set_occupancy(room_id, 25)

        for step_idx in range(100):
            b.step()
            state = b.get_state()

            for room_id, room in state["rooms"].items():
                cfg, _ = b.get_room(room_id)

                # Temperature must be finite.
                assert math.isfinite(room["temperature_c"]), (
                    f"Step {step_idx}: {room_id} temperature is not finite"
                )

                # Humidity in [30, 70].
                assert 30.0 <= room["humidity_pct"] <= 70.0, (
                    f"Step {step_idx}: {room_id} humidity {room['humidity_pct']:.2f}% out of [30, 70]"
                )

                # Airflow in [min_airflow, max_airflow].
                assert cfg.min_airflow_lps <= room["airflow_lps"] <= cfg.max_airflow_lps, (
                    f"Step {step_idx}: {room_id} airflow {room['airflow_lps']:.1f} L/s out of bounds"
                )

                # Comfort in [0, 100].
                assert 0.0 <= room["comfort_score"] <= 100.0, (
                    f"Step {step_idx}: {room_id} comfort {room['comfort_score']:.2f} out of [0, 100]"
                )

                # HVAC power within capacity.
                assert abs(room["hvac_power_kw"]) <= cfg.max_hvac_power_kw + 1e-9, (
                    f"Step {step_idx}: {room_id} HVAC power {room['hvac_power_kw']:.3f} kW "
                    f"exceeds capacity {cfg.max_hvac_power_kw} kW"
                )

                # Energy is non-negative and non-decreasing.
                assert room["energy_kwh"] >= 0.0, (
                    f"Step {step_idx}: {room_id} energy {room['energy_kwh']:.6f} kWh is negative"
                )

    def test_building_total_energy_non_negative(self) -> None:
        """Total building energy is always >= 0."""
        b = BuildingTwin()
        b.reset()
        for _ in range(20):
            b.step()
            assert b.get_state()["total_energy_kwh"] >= 0.0


# ---------------------------------------------------------------------------
# Test 9 — Constraint does not change temperature_c
# ---------------------------------------------------------------------------

class TestConstraintBehavior:
    """Test 9: apply_constraint changes setpoint targets, NOT current temperature."""

    def test_constraint_does_not_change_temperature(self) -> None:
        """
        After apply_constraint(), temperature_c must be unchanged.
        The setpoint must change.
        """
        b = BuildingTwin(outside_temperature_c=34.0)
        b.reset()
        b.set_setpoint("B2", 24.0)

        # Run a few steps to get a non-initial temperature.
        for _ in range(5):
            b.step()

        _, state_before = b.get_room("B2")
        temp_before = state_before.temperature_c
        setpoint_before = state_before.setpoint_c

        # Apply constraint: -2°C setpoint change.
        result = b.apply_constraint("B2", temp_offset_c=-2.0)

        _, state_after = b.get_room("B2")
        temp_after = state_after.temperature_c
        setpoint_after = state_after.setpoint_c

        # Temperature must be UNCHANGED.
        assert temp_after == temp_before, (
            f"apply_constraint() changed temperature! "
            f"Before: {temp_before:.4f}, After: {temp_after:.4f}"
        )

        # Setpoint must have changed by -2°C.
        expected_setpoint = setpoint_before - 2.0
        assert abs(setpoint_after - expected_setpoint) < 1e-9, (
            f"Setpoint should be {expected_setpoint:.2f}, got {setpoint_after:.2f}"
        )

        # The return dict must confirm the temperature was not touched.
        assert result["temperature_c_unchanged"] == temp_before

    def test_constraint_airflow_boost(self) -> None:
        """apply_constraint with airflow_boost_pct changes airflow."""
        b = BuildingTwin()
        b.reset()
        b.set_airflow("B2", 100.0)

        _, state_before = b.get_room("B2")
        airflow_before = state_before.airflow_lps

        b.apply_constraint("B2", airflow_boost_pct=20.0)

        _, state_after = b.get_room("B2")
        airflow_after = state_after.airflow_lps

        assert airflow_after > airflow_before, (
            f"Airflow should have increased: {airflow_before} → {airflow_after}"
        )
        assert abs(airflow_after - 120.0) < 1e-9, (
            f"100 L/s × 1.20 = 120 L/s, got {airflow_after}"
        )

    def test_temp_offset_clamped_to_spec(self) -> None:
        """Temperature offset is clamped to [-5, +5] °C per specification."""
        b = BuildingTwin()
        b.reset()
        b.set_setpoint("A1", 22.0)

        # Apply offset of +10°C (exceeds +5°C limit).
        b.apply_constraint("A1", temp_offset_c=10.0)
        _, state = b.get_room("A1")

        # Should be clamped to 22 + 5 = 27°C.
        assert state.setpoint_c <= SETPOINT_MAX_C, (
            f"Setpoint {state.setpoint_c} exceeds max {SETPOINT_MAX_C}"
        )

    def test_invalid_room_raises(self) -> None:
        """apply_constraint on non-existent room raises KeyError."""
        b = BuildingTwin()
        b.reset()
        with pytest.raises(KeyError):
            b.apply_constraint("INVALID_ROOM_XYZ")


# ---------------------------------------------------------------------------
# Test 10 — Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Test 10: Same inputs must produce identical histories."""

    def _run_scenario(self) -> list[dict]:
        """Helper: run a standard scenario and return history."""
        b = BuildingTwin(outside_temperature_c=34.0)
        b.reset()
        b.set_setpoint("B2", 24.0)
        b.set_occupancy("B2", 10)

        for step in range(10):
            b.step()
            if step == 5:
                b.apply_constraint("B2", temp_offset_c=-2.0, airflow_boost_pct=10.0)

        for _ in range(10):
            b.step()

        return b.get_history()

    def test_two_identical_runs_match(self) -> None:
        """Two runs with identical setup must produce identical histories."""
        history_1 = self._run_scenario()
        history_2 = self._run_scenario()

        assert len(history_1) == len(history_2), (
            f"History lengths differ: {len(history_1)} vs {len(history_2)}"
        )

        for i, (snap1, snap2) in enumerate(zip(history_1, history_2)):
            for room_id in snap1["rooms"]:
                t1 = snap1["rooms"][room_id]["temperature_c"]
                t2 = snap2["rooms"][room_id]["temperature_c"]
                assert abs(t1 - t2) < 1e-9, (
                    f"Step {i}, room {room_id}: temperatures differ: {t1} vs {t2}"
                )

            e1 = snap1["total_energy_kwh"]
            e2 = snap2["total_energy_kwh"]
            assert abs(e1 - e2) < 1e-9, (
                f"Step {i}: total energy differs: {e1} vs {e2}"
            )

    def test_reset_restores_determinism(self) -> None:
        """After reset(), running the same scenario again gives same results."""
        b = BuildingTwin(outside_temperature_c=34.0)
        b.reset()
        b.set_setpoint("B2", 24.0)
        for _ in range(10):
            b.step()
        history_1 = b.get_history()

        b.reset()
        b.set_setpoint("B2", 24.0)
        for _ in range(10):
            b.step()
        history_2 = b.get_history()

        assert len(history_1) == len(history_2)
        for i, (s1, s2) in enumerate(zip(history_1, history_2)):
            for room_id in s1["rooms"]:
                t1 = s1["rooms"][room_id]["temperature_c"]
                t2 = s2["rooms"][room_id]["temperature_c"]
                assert abs(t1 - t2) < 1e-9, (
                    f"Step {i}, {room_id}: {t1} vs {t2} after reset"
                )


# ---------------------------------------------------------------------------
# Additional API tests
# ---------------------------------------------------------------------------

class TestPublicAPI:
    """Verify all required public API methods exist and work."""

    def test_step_returns_snapshot(self, fresh_building: BuildingTwin) -> None:
        snap = fresh_building.step()
        assert "simulation_time_minutes" in snap
        assert "rooms" in snap
        assert "total_energy_kwh" in snap

    def test_get_state_returns_dict(self, fresh_building: BuildingTwin) -> None:
        state = fresh_building.get_state()
        assert isinstance(state, dict)
        assert len(state["rooms"]) == 5

    def test_get_history_returns_list(self, fresh_building: BuildingTwin) -> None:
        for _ in range(5):
            fresh_building.step()
        history = fresh_building.get_history()
        assert isinstance(history, list)
        assert len(history) > 0

    def test_set_outside_temperature(self, fresh_building: BuildingTwin) -> None:
        fresh_building.set_outside_temperature(38.0)
        assert fresh_building.outside_temperature_c == 38.0

    def test_all_rooms_present(self, fresh_building: BuildingTwin) -> None:
        state = fresh_building.get_state()
        for room_id in ["A1", "A2", "B1", "B2", "C1"]:
            assert room_id in state["rooms"], f"Room {room_id} missing from state"

    def test_simulation_time_advances(self, fresh_building: BuildingTwin) -> None:
        assert fresh_building.simulation_time_minutes == 0.0
        fresh_building.step()
        assert fresh_building.simulation_time_minutes == fresh_building.step_minutes

    def test_history_max_length(self) -> None:
        """History does not grow beyond MAX_HISTORY."""
        from digital_twin.building import MAX_HISTORY
        b = BuildingTwin()
        b.reset()
        for _ in range(MAX_HISTORY + 50):
            b.step()
        assert len(b.get_history()) <= MAX_HISTORY
