"""
test_scenarios.py
=================
End-to-end scenario tests for the Digital Twin simulation.

Tests covered:
  - Scenario A: Cooling trajectory
  - Scenario B: Heating trajectory
  - Scenario C: Outside temperature disturbance
  - Scenario D: Occupancy disturbance
  - Scenario E: Constraint (setpoint changes, temperature does not jump)
  - Scenario F: Airflow constraint
  - Baseline vs adaptive energy comparison
"""

from __future__ import annotations

import pytest

from digital_twin.building import BuildingTwin


# ---------------------------------------------------------------------------
# Scenario A — Cooling
# ---------------------------------------------------------------------------

class TestScenarioCooling:
    """Scenario A: Room starts hot, HVAC cools it toward setpoint."""

    def test_cooling_trajectory(self) -> None:
        """
        Start: B2 = 27°C, setpoint = 24°C, outside = 34°C.
        Run 20 steps.
        Final temperature must be lower than initial and closer to setpoint.
        """
        b = BuildingTwin(outside_temperature_c=34.0)
        b.reset()

        # Override B2 initial temperature.
        b._states["B2"].temperature_c = 27.0
        b.set_setpoint("B2", 24.0)

        initial_temp = b.get_room("B2")[1].temperature_c
        assert abs(initial_temp - 27.0) < 1e-9

        for _ in range(20):
            b.step()

        final_temp = b.get_room("B2")[1].temperature_c

        # Temperature must have decreased.
        assert final_temp < initial_temp, (
            f"Cooling: temperature should decrease. {initial_temp:.2f} → {final_temp:.2f}°C"
        )

        # Final temperature should be closer to setpoint than initial.
        initial_error = abs(initial_temp - 24.0)
        final_error = abs(final_temp - 24.0)
        assert final_error < initial_error, (
            f"Cooling: temperature should approach setpoint. "
            f"Initial error: {initial_error:.2f}°C, Final error: {final_error:.2f}°C"
        )

    def test_temperature_does_not_reach_setpoint_instantly(self) -> None:
        """After only 1 step, temperature must NOT equal setpoint."""
        b = BuildingTwin(outside_temperature_c=34.0)
        b.reset()
        b._states["B2"].temperature_c = 27.0
        b.set_setpoint("B2", 24.0)

        b.step()
        temp = b.get_room("B2")[1].temperature_c

        # Temperature must not have jumped to setpoint.
        assert abs(temp - 24.0) > 0.5, (
            f"Temperature jumped too close to setpoint in 1 step: {temp:.3f}°C "
            f"(setpoint: 24.0°C)"
        )


# ---------------------------------------------------------------------------
# Scenario B — Heating
# ---------------------------------------------------------------------------

class TestScenarioHeating:
    """Scenario B: Room starts cold, HVAC heats it toward setpoint."""

    def test_heating_trajectory(self) -> None:
        """
        Start: B2 = 19°C, setpoint = 22°C.
        Run 20 steps.
        Temperature must increase and approach setpoint.
        """
        b = BuildingTwin(outside_temperature_c=20.0)  # mild outside for heating test
        b.reset()
        b._states["B2"].temperature_c = 19.0
        b.set_setpoint("B2", 22.0)

        initial_temp = b.get_room("B2")[1].temperature_c

        for _ in range(20):
            b.step()

        final_temp = b.get_room("B2")[1].temperature_c

        assert final_temp > initial_temp, (
            f"Heating: temperature should increase. {initial_temp:.2f} → {final_temp:.2f}°C"
        )

        initial_error = abs(initial_temp - 22.0)
        final_error = abs(final_temp - 22.0)
        assert final_error < initial_error, (
            f"Heating: should approach setpoint. "
            f"Initial error: {initial_error:.2f}°C, Final error: {final_error:.2f}°C"
        )


# ---------------------------------------------------------------------------
# Scenario C — Outside temperature disturbance
# ---------------------------------------------------------------------------

class TestScenarioOutsideDisturbance:
    """Scenario C: Changing outside temperature affects room behavior."""

    def test_outside_temp_change_affects_room(self) -> None:
        """
        Run 10 steps at outside=30°C, then 10 steps at outside=38°C.
        Energy usage should increase in the second phase (HVAC works harder).
        """
        b = BuildingTwin(outside_temperature_c=30.0)
        b.reset()
        b.set_setpoint("B2", 22.0)

        # Phase 1: outside = 30°C.
        for _ in range(10):
            b.step()
        energy_phase1 = b.get_room("B2")[1].energy_kwh

        # Phase 2: outside = 38°C.
        b.set_outside_temperature(38.0)
        for _ in range(10):
            b.step()
        energy_phase2 = b.get_room("B2")[1].energy_kwh

        # Energy should have increased more in the hotter phase.
        energy_increment_phase1 = energy_phase1
        energy_increment_phase2 = energy_phase2 - energy_phase1

        assert energy_increment_phase2 > energy_increment_phase1, (
            f"Hotter outside should require more HVAC energy. "
            f"Phase1={energy_increment_phase1:.4f} kWh, Phase2={energy_increment_phase2:.4f} kWh"
        )

    def test_two_outside_temps_diverge(self) -> None:
        """
        Buildings with outside=30°C vs 38°C must diverge in temperature.

        Strategy: set setpoint = current temp to neutralize HVAC effect,
        so only the outdoor_gain term differentiates the two runs.
        outdoor_gain=0.02 means 0.02 × (outside - 24) difference per step.
        For 30°C: 0.02 × 6 = +0.12°C/step.
        For 38°C: 0.02 × 14 = +0.28°C/step.
        After 30 steps the gap is 30 × 0.16 ≈ 4.8°C — clearly measurable.
        """
        initial_temp = 24.0  # both start at 24°C

        b_cool = BuildingTwin(outside_temperature_c=30.0)
        b_cool.reset()
        # Set setpoint = initial_temp so HVAC error = 0 → HVAC power = 0
        b_cool.set_setpoint("B2", initial_temp)

        b_hot = BuildingTwin(outside_temperature_c=38.0)
        b_hot.reset()
        b_hot.set_setpoint("B2", initial_temp)

        for _ in range(30):
            b_cool.step()
            b_hot.step()

        temp_cool = b_cool.get_room("B2")[1].temperature_c
        temp_hot = b_hot.get_room("B2")[1].temperature_c

        assert temp_hot > temp_cool, (
            f"Outside=38°C should give higher room temp than outside=30°C. "
            f"Cool={temp_cool:.4f}, Hot={temp_hot:.4f}"
        )


# ---------------------------------------------------------------------------
# Scenario D — Occupancy disturbance
# ---------------------------------------------------------------------------

class TestScenarioOccupancyDisturbance:
    """Scenario D: Sudden occupancy change affects temperature response."""

    def test_occupancy_spike_raises_temperature(self) -> None:
        """
        Start with occupancy=5, run 10 steps.
        Increase to occupancy=20, run 10 more steps.
        Temperature after spike must be higher than it would be without spike.
        """
        # Building with spike.
        b_spike = BuildingTwin(outside_temperature_c=30.0)
        b_spike.reset()
        b_spike.set_setpoint("B2", 22.0)
        b_spike.set_occupancy("B2", 5)

        for _ in range(10):
            b_spike.step()
        temp_before_spike = b_spike.get_room("B2")[1].temperature_c

        b_spike.set_occupancy("B2", 20)
        for _ in range(10):
            b_spike.step()
        temp_after_spike = b_spike.get_room("B2")[1].temperature_c

        # Building without spike (stays at 5 occupants).
        b_control = BuildingTwin(outside_temperature_c=30.0)
        b_control.reset()
        b_control.set_setpoint("B2", 22.0)
        b_control.set_occupancy("B2", 5)

        for _ in range(20):
            b_control.step()
        temp_control = b_control.get_room("B2")[1].temperature_c

        # Spiked occupancy should give higher temperature than control.
        assert temp_after_spike > temp_control, (
            f"Occupancy spike should raise temperature. "
            f"Spike={temp_after_spike:.3f}, Control={temp_control:.3f}"
        )

    def test_occupancy_affects_energy(self) -> None:
        """Higher occupancy means more heat, more HVAC work, more energy."""
        b_low = BuildingTwin(outside_temperature_c=34.0)
        b_low.reset()
        b_low.set_occupancy("B2", 2)

        b_high = BuildingTwin(outside_temperature_c=34.0)
        b_high.reset()
        b_high.set_occupancy("B2", 25)

        for _ in range(20):
            b_low.step()
            b_high.step()

        energy_low = b_low.get_room("B2")[1].energy_kwh
        energy_high = b_high.get_room("B2")[1].energy_kwh

        assert energy_high > energy_low, (
            f"Higher occupancy should use more energy. "
            f"Low={energy_low:.4f}, High={energy_high:.4f} kWh"
        )


# ---------------------------------------------------------------------------
# Scenario E — Complaint constraint
# ---------------------------------------------------------------------------

class TestScenarioConstraint:
    """Scenario E: apply_constraint changes setpoint and trajectory, not instant temperature."""

    def test_constraint_trajectory_change(self) -> None:
        """
        Apply temp_offset=-2.
        setpoint changes immediately.
        temperature does NOT jump instantly.
        But the trajectory over next steps is pulled toward the new setpoint.
        """
        b = BuildingTwin(outside_temperature_c=34.0)
        b.reset()
        b._states["B2"].temperature_c = 27.0
        b.set_setpoint("B2", 24.0)

        # Run 5 steps without constraint.
        for _ in range(5):
            b.step()

        # Record temp and setpoint before constraint.
        temp_before_constraint = b.get_room("B2")[1].temperature_c
        setpoint_before = b.get_room("B2")[1].setpoint_c

        # Apply constraint.
        b.apply_constraint("B2", temp_offset_c=-2.0)

        # Verify: temperature did NOT change.
        temp_after_constraint = b.get_room("B2")[1].temperature_c
        setpoint_after = b.get_room("B2")[1].setpoint_c

        assert temp_after_constraint == temp_before_constraint, (
            f"Temperature must not change immediately: "
            f"before={temp_before_constraint:.4f}, after={temp_after_constraint:.4f}"
        )
        assert abs(setpoint_after - (setpoint_before - 2.0)) < 1e-9, (
            f"Setpoint should decrease by 2: {setpoint_before:.2f} → {setpoint_after:.2f}"
        )

        # Run 15 more steps — trajectory should now pull toward the lower setpoint.
        for _ in range(15):
            b.step()

        temp_final = b.get_room("B2")[1].temperature_c

        # Final temperature should be lower than it was before the constraint was applied,
        # because the setpoint was lowered.
        assert temp_final < temp_before_constraint, (
            f"After lowering setpoint, temperature should drop further: "
            f"before_constraint={temp_before_constraint:.3f}, final={temp_final:.3f}"
        )


# ---------------------------------------------------------------------------
# Scenario F — Airflow constraint
# ---------------------------------------------------------------------------

class TestScenarioAirflowConstraint:
    """Scenario F: Increasing airflow changes airflow state and affects humidity/energy."""

    def test_airflow_increases(self) -> None:
        """Applying +20% airflow boost should increase airflow."""
        b = BuildingTwin()
        b.reset()
        b.set_airflow("B2", 100.0)

        airflow_before = b.get_room("B2")[1].airflow_lps
        b.apply_constraint("B2", airflow_boost_pct=20.0)
        airflow_after = b.get_room("B2")[1].airflow_lps

        assert airflow_after > airflow_before, (
            f"Airflow should increase: {airflow_before} → {airflow_after}"
        )
        assert abs(airflow_after - 120.0) < 1e-9, (
            f"100 × 1.20 = 120 L/s, got {airflow_after}"
        )

    def test_airflow_stays_bounded(self) -> None:
        """Even with +50% boost from max airflow, stays at max."""
        b = BuildingTwin()
        b.reset()
        b.set_airflow("B2", 300.0)  # already at max

        b.apply_constraint("B2", airflow_boost_pct=50.0)
        airflow_after = b.get_room("B2")[1].airflow_lps

        assert airflow_after <= 300.0, f"Airflow exceeded max: {airflow_after}"

    def test_airflow_affects_humidity_over_time(self) -> None:
        """Higher airflow should reduce humidity over time (ventilation effect)."""
        b_low_flow = BuildingTwin(outside_temperature_c=30.0)
        b_low_flow.reset()
        b_low_flow.set_airflow("B2", 60.0)
        b_low_flow.set_occupancy("B2", 15)

        b_high_flow = BuildingTwin(outside_temperature_c=30.0)
        b_high_flow.reset()
        b_high_flow.set_airflow("B2", 250.0)
        b_high_flow.set_occupancy("B2", 15)

        for _ in range(30):
            b_low_flow.step()
            b_high_flow.step()

        humidity_low_flow = b_low_flow.get_room("B2")[1].humidity_pct
        humidity_high_flow = b_high_flow.get_room("B2")[1].humidity_pct

        assert humidity_high_flow < humidity_low_flow, (
            f"Higher airflow should lower humidity. "
            f"Low flow: {humidity_low_flow:.2f}%, High flow: {humidity_high_flow:.2f}%"
        )


# ---------------------------------------------------------------------------
# Baseline comparison
# ---------------------------------------------------------------------------

class TestBaselineComparison:
    """Verify baseline simulation runs independently on a separate instance."""

    def test_baseline_runs_without_error(self) -> None:
        """run_baseline() should complete without exception."""
        b = BuildingTwin(outside_temperature_c=34.0)
        b.reset()
        baseline_hist = b.run_baseline(n_steps=20)
        assert len(baseline_hist) > 0

    def test_baseline_accumulates_energy(self) -> None:
        """Baseline simulation should accumulate positive energy."""
        b = BuildingTwin(outside_temperature_c=34.0)
        b.reset()
        baseline_hist = b.run_baseline(n_steps=20)

        final_energy = baseline_hist[-1]["total_energy_kwh"]
        assert final_energy > 0.0, f"Baseline energy should be > 0, got {final_energy}"

    def test_baseline_does_not_affect_main_simulation(self) -> None:
        """run_baseline() must not modify the main simulation state."""
        b = BuildingTwin(outside_temperature_c=34.0)
        b.reset()
        b.set_setpoint("B2", 24.0)

        for _ in range(10):
            b.step()

        temp_before = b.get_room("B2")[1].temperature_c
        time_before = b.simulation_time_minutes

        b.run_baseline(n_steps=20)

        temp_after = b.get_room("B2")[1].temperature_c
        time_after = b.simulation_time_minutes

        assert temp_after == temp_before, "run_baseline() modified main temperature"
        assert time_after == time_before, "run_baseline() modified simulation time"
