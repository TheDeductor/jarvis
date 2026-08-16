"""
test_energy_model.py
====================
Tests for energy_model.py — kW → kWh integration.

Tests covered:
  Test 7  — Energy = power × time (unit correctness)
  Test 8  — Energy is always non-negative
"""

from __future__ import annotations

import pytest

from digital_twin.energy_model import (
    compute_cost,
    compute_energy_increment,
    compute_total_energy,
)


# ---------------------------------------------------------------------------
# Test 7 — Energy accumulates as power × time
# ---------------------------------------------------------------------------

class TestEnergyAccumulation:
    """Test 7: Energy integration must satisfy E = P × t."""

    def test_energy_equals_power_times_time(self) -> None:
        """
        For constant power P kW over N steps of step_minutes each:
          total_energy_kwh = P × (N × step_minutes / 60)

        This verifies the kW → kWh conversion is correct.
        """
        power_kw = 3.0           # kW (constant)
        step_minutes = 5.0       # minutes
        n_steps = 12             # 12 steps × 5 min = 60 min = 1 hour

        expected_energy_kwh = power_kw * (n_steps * step_minutes / 60.0)  # = 3.0 kWh

        accumulated = 0.0
        for _ in range(n_steps):
            accumulated += compute_energy_increment(power_kw, step_minutes)

        assert abs(accumulated - expected_energy_kwh) < 1e-9, (
            f"Energy mismatch: expected {expected_energy_kwh:.6f} kWh, "
            f"got {accumulated:.6f} kWh"
        )

    def test_energy_half_hour(self) -> None:
        """2 kW for 30 minutes = 1.0 kWh."""
        power_kw = 2.0
        step_minutes = 5.0
        n_steps = 6  # 6 × 5 min = 30 min = 0.5 hours

        expected = power_kw * 0.5  # 1.0 kWh
        accumulated = sum(compute_energy_increment(power_kw, step_minutes) for _ in range(n_steps))

        assert abs(accumulated - expected) < 1e-9, (
            f"Expected {expected} kWh, got {accumulated} kWh"
        )

    def test_energy_unit_sanity(self) -> None:
        """1 kW for 60 minutes = 1.0 kWh exactly."""
        power_kw = 1.0
        step_minutes = 60.0  # 1 step of 60 minutes

        energy = compute_energy_increment(power_kw, step_minutes)
        assert abs(energy - 1.0) < 1e-9, f"1 kW × 60 min should be 1 kWh, got {energy}"

    def test_step_minutes_zero_raises(self) -> None:
        """step_minutes = 0 should raise ValueError (division by zero / no time)."""
        with pytest.raises(ValueError, match="step_minutes must be positive"):
            compute_energy_increment(3.0, 0.0)

    def test_step_minutes_negative_raises(self) -> None:
        """step_minutes < 0 should raise ValueError."""
        with pytest.raises(ValueError):
            compute_energy_increment(3.0, -5.0)


# ---------------------------------------------------------------------------
# Test 8 — Energy is always non-negative
# ---------------------------------------------------------------------------

class TestEnergyNonNegative:
    """Test 8 (partial): Energy must always be non-negative."""

    def test_cooling_power_gives_positive_energy(self) -> None:
        """Cooling HVAC power (negative sign) still produces positive energy."""
        # hvac_power_kw = -3.5 kW (cooling)
        energy = compute_energy_increment(-3.5, 5.0)
        assert energy > 0, f"Energy should be positive even for cooling, got {energy}"

    def test_zero_power_zero_energy(self) -> None:
        """Zero HVAC power → zero energy increment."""
        energy = compute_energy_increment(0.0, 5.0)
        assert energy == 0.0

    def test_heating_power_positive_energy(self) -> None:
        """Heating HVAC power (positive sign) produces positive energy."""
        energy = compute_energy_increment(4.0, 5.0)
        assert energy > 0

    def test_energy_always_finite(self) -> None:
        """Energy increments should be finite for normal inputs."""
        for power in [-5.0, -2.5, 0.0, 2.5, 5.0]:
            energy = compute_energy_increment(power, 5.0)
            assert energy >= 0
            assert energy < float("inf")


# ---------------------------------------------------------------------------
# Building total energy tests
# ---------------------------------------------------------------------------

class TestTotalEnergy:
    """Total building energy is the sum of all room energies."""

    def test_total_is_sum(self) -> None:
        room_energies = [1.5, 2.3, 0.8, 1.1, 0.7]
        expected = sum(room_energies)
        result = compute_total_energy(room_energies)
        assert abs(result - expected) < 1e-9

    def test_empty_list_is_zero(self) -> None:
        assert compute_total_energy([]) == 0.0


# ---------------------------------------------------------------------------
# Electricity cost tests
# ---------------------------------------------------------------------------

class TestElectricityCost:
    """Cost = energy × price, units: kWh × currency/kWh = currency."""

    def test_cost_calculation(self) -> None:
        energy_kwh = 10.0
        price = 0.12
        expected = 1.2
        result = compute_cost(energy_kwh, price)
        assert abs(result - expected) < 1e-9

    def test_zero_energy_zero_cost(self) -> None:
        assert compute_cost(0.0, 0.12) == 0.0

    def test_cost_proportional_to_energy(self) -> None:
        price = 0.15
        cost_10 = compute_cost(10.0, price)
        cost_20 = compute_cost(20.0, price)
        assert abs(cost_20 / cost_10 - 2.0) < 1e-9
