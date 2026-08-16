"""
test_thermal_model.py
=====================
Tests for thermal_model.py — temperature and humidity equations.

Tests covered:
  Test 1  — Temperature changes after multiple steps
  Test 2  — Temperature does not jump by large amounts per step
  Test 3  — Cooling trend: temperature > setpoint decreases over time
  Test 4  — Heating trend: temperature < setpoint increases over time
  Test 6  — Outside temperature has an effect on trajectory
"""

from __future__ import annotations

import pytest

from digital_twin.models import RoomConfig
from digital_twin.thermal_model import (
    compute_hvac_power,
    compute_internal_heat,
    compute_next_humidity,
    compute_next_temperature,
    compute_humidity_target,
    clamp_airflow,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_config() -> RoomConfig:
    """Default room configuration for tests."""
    return RoomConfig(room_id="TEST")


# ---------------------------------------------------------------------------
# Test 1 — Temperature changes after multiple steps
# ---------------------------------------------------------------------------

class TestTemperatureChanges:
    """Test 1: Temperature is dynamic — it must change after steps."""

    def test_temperature_changes_when_cooling(self, default_config: RoomConfig) -> None:
        """After 10 steps with setpoint < current temp, temperature must change."""
        temp = 27.0  # °C — above setpoint
        setpoint = 22.0  # °C
        outside = 34.0  # °C

        initial_temp = temp
        for _ in range(10):
            temp = compute_next_temperature(
                temperature_c=temp,
                setpoint_c=setpoint,
                outside_temperature_c=outside,
                internal_heat_kw=0.5,
                config=default_config,
                step_minutes=5.0,
            )

        # Temperature must have changed (not static).
        assert temp != initial_temp, (
            f"Temperature did not change after 10 steps: remained {initial_temp}°C"
        )

    def test_temperature_changes_when_heating(self, default_config: RoomConfig) -> None:
        """After 10 steps with setpoint > current temp, temperature must change."""
        temp = 19.0  # °C — below setpoint
        setpoint = 22.0  # °C
        outside = 15.0  # °C — cold outside

        initial_temp = temp
        for _ in range(10):
            temp = compute_next_temperature(
                temperature_c=temp,
                setpoint_c=setpoint,
                outside_temperature_c=outside,
                internal_heat_kw=0.5,
                config=default_config,
                step_minutes=5.0,
            )

        assert temp != initial_temp, (
            f"Temperature did not change after 10 steps: remained {initial_temp}°C"
        )


# ---------------------------------------------------------------------------
# Test 2 — Temperature does not jump by more than threshold per step
# ---------------------------------------------------------------------------

class TestTemperatureStepSize:
    """
    Test 2: Per-step temperature change stays within a reasonable bound.

    Threshold: 2.0°C per 5-minute step.
    Justification: With thermal_lag=0.08 and a max HVAC error of ~10°C,
    the setpoint effect is at most 10 × 0.08 = 0.8°C.
    With outdoor_gain=0.02 and max outdoor difference of ~20°C,
    outside effect is at most 20 × 0.02 = 0.4°C.
    Internal heat: occupants × 0.1 kW × 0.05 = small.
    Total max change ≈ 1.2–1.5°C.  Threshold of 2.0°C provides headroom.
    """
    MAX_STEP_CHANGE_C: float = 2.0  # °C per step — justified threshold

    def test_step_size_bounded_cooling(self, default_config: RoomConfig) -> None:
        """Each step changes temperature by less than MAX_STEP_CHANGE_C."""
        temp = 30.0  # °C — hot start
        setpoint = 20.0  # °C — large error
        outside = 35.0  # °C

        for _ in range(20):
            next_temp = compute_next_temperature(
                temperature_c=temp,
                setpoint_c=setpoint,
                outside_temperature_c=outside,
                internal_heat_kw=2.0,
                config=default_config,
                step_minutes=5.0,
            )
            change = abs(next_temp - temp)
            assert change < self.MAX_STEP_CHANGE_C, (
                f"Temperature changed by {change:.3f}°C in one step "
                f"(max allowed: {self.MAX_STEP_CHANGE_C}°C). "
                f"Was: {temp:.2f}°C, Now: {next_temp:.2f}°C"
            )
            temp = next_temp

    def test_step_size_bounded_heating(self, default_config: RoomConfig) -> None:
        """Each step changes temperature by less than MAX_STEP_CHANGE_C."""
        temp = 15.0  # °C — cold start
        setpoint = 25.0  # °C — large error (heating)
        outside = 5.0   # °C — cold outside

        for _ in range(20):
            next_temp = compute_next_temperature(
                temperature_c=temp,
                setpoint_c=setpoint,
                outside_temperature_c=outside,
                internal_heat_kw=1.0,
                config=default_config,
                step_minutes=5.0,
            )
            change = abs(next_temp - temp)
            assert change < self.MAX_STEP_CHANGE_C, (
                f"Temperature changed by {change:.3f}°C in one step "
                f"(max: {self.MAX_STEP_CHANGE_C}°C)"
            )
            temp = next_temp


# ---------------------------------------------------------------------------
# Test 3 — Cooling trend
# ---------------------------------------------------------------------------

class TestCoolingTrend:
    """Test 3: When temperature > setpoint, it should generally trend downward."""

    def test_cooling_reduces_temperature(self, default_config: RoomConfig) -> None:
        """
        Over 20 steps with room warmer than setpoint, the trend must be downward.

        We use a cold outside temperature to avoid the outdoor heat gain
        overwhelming the HVAC cooling effect.
        """
        temp = 27.0    # °C — above setpoint
        setpoint = 22.0  # °C
        outside = 20.0   # °C — cooler outside (not fighting HVAC)

        temps = [temp]
        for _ in range(20):
            temp = compute_next_temperature(
                temperature_c=temp,
                setpoint_c=setpoint,
                outside_temperature_c=outside,
                internal_heat_kw=0.0,
                config=default_config,
                step_minutes=5.0,
            )
            temps.append(temp)

        # Final temperature must be lower than initial.
        assert temps[-1] < temps[0], (
            f"Cooling did not reduce temperature: {temps[0]:.2f} → {temps[-1]:.2f}°C"
        )
        # Final temperature must be closer to setpoint than initial.
        initial_error = abs(temps[0] - setpoint)
        final_error = abs(temps[-1] - setpoint)
        assert final_error < initial_error, (
            f"Cooling did not reduce setpoint error: {initial_error:.2f} → {final_error:.2f}°C"
        )


# ---------------------------------------------------------------------------
# Test 4 — Heating trend
# ---------------------------------------------------------------------------

class TestHeatingTrend:
    """Test 4: When temperature < setpoint, it should generally trend upward."""

    def test_heating_raises_temperature(self, default_config: RoomConfig) -> None:
        """
        Over 20 steps with room cooler than setpoint, the trend must be upward.

        We use a warm outside temperature to help the heating effect dominate.
        """
        temp = 19.0    # °C — below setpoint
        setpoint = 24.0  # °C
        outside = 20.0   # °C — mild outside

        temps = [temp]
        for _ in range(20):
            temp = compute_next_temperature(
                temperature_c=temp,
                setpoint_c=setpoint,
                outside_temperature_c=outside,
                internal_heat_kw=0.5,
                config=default_config,
                step_minutes=5.0,
            )
            temps.append(temp)

        # Final temperature must be higher than initial.
        assert temps[-1] > temps[0], (
            f"Heating did not raise temperature: {temps[0]:.2f} → {temps[-1]:.2f}°C"
        )
        initial_error = abs(temps[0] - setpoint)
        final_error = abs(temps[-1] - setpoint)
        assert final_error < initial_error, (
            f"Heating did not reduce setpoint error: {initial_error:.2f} → {final_error:.2f}°C"
        )


# ---------------------------------------------------------------------------
# Test 6 — Outside temperature has an effect
# ---------------------------------------------------------------------------

class TestOutsideTemperatureEffect:
    """Test 6: Different outside temperatures must produce different trajectories."""

    def test_outside_temp_affects_trajectory(self, default_config: RoomConfig) -> None:
        """
        Two identical runs with different outdoor temperatures must diverge.
        """
        initial_temp = 24.0
        setpoint = 22.0
        outside_low = 20.0   # °C — cooler outside
        outside_high = 38.0  # °C — hotter outside

        temp_low = initial_temp
        temp_high = initial_temp

        for _ in range(10):
            temp_low = compute_next_temperature(
                temperature_c=temp_low,
                setpoint_c=setpoint,
                outside_temperature_c=outside_low,
                internal_heat_kw=0.5,
                config=default_config,
                step_minutes=5.0,
            )
            temp_high = compute_next_temperature(
                temperature_c=temp_high,
                setpoint_c=setpoint,
                outside_temperature_c=outside_high,
                internal_heat_kw=0.5,
                config=default_config,
                step_minutes=5.0,
            )

        assert temp_high > temp_low, (
            f"Outside temperature had no effect: "
            f"low_outside={temp_low:.3f}°C, high_outside={temp_high:.3f}°C"
        )

    def test_hotter_outside_leads_to_higher_room_temp(self, default_config: RoomConfig) -> None:
        """Hot outside temperature makes room warmer than cold outside at same setpoint."""
        temp = 24.0
        setpoint = 22.0

        temp_hot_outside = temp
        temp_cold_outside = temp

        for _ in range(20):
            temp_hot_outside = compute_next_temperature(
                temperature_c=temp_hot_outside,
                setpoint_c=setpoint,
                outside_temperature_c=38.0,
                internal_heat_kw=0.5,
                config=default_config,
                step_minutes=5.0,
            )
            temp_cold_outside = compute_next_temperature(
                temperature_c=temp_cold_outside,
                setpoint_c=setpoint,
                outside_temperature_c=18.0,
                internal_heat_kw=0.5,
                config=default_config,
                step_minutes=5.0,
            )

        assert temp_hot_outside > temp_cold_outside, (
            f"Hotter outside should result in higher room temp. "
            f"hot={temp_hot_outside:.3f}, cold={temp_cold_outside:.3f}"
        )


# ---------------------------------------------------------------------------
# HVAC power tests
# ---------------------------------------------------------------------------

class TestHVACPower:
    """HVAC controller behavior tests."""

    def test_cooling_mode_negative_power(self) -> None:
        """When room is hot (temp > setpoint), HVAC power is negative (cooling)."""
        power = compute_hvac_power(
            temperature_c=27.0,
            setpoint_c=22.0,
            max_hvac_power_kw=5.0,
        )
        assert power < 0, f"Expected negative (cooling) power, got {power}"

    def test_heating_mode_positive_power(self) -> None:
        """When room is cold (temp < setpoint), HVAC power is positive (heating)."""
        power = compute_hvac_power(
            temperature_c=19.0,
            setpoint_c=24.0,
            max_hvac_power_kw=5.0,
        )
        assert power > 0, f"Expected positive (heating) power, got {power}"

    def test_hvac_power_within_capacity(self) -> None:
        """HVAC power magnitude never exceeds max_hvac_power_kw."""
        for temp_error in [-20.0, -10.0, -5.0, 0.0, 5.0, 10.0, 20.0]:
            temp = 22.0
            setpoint = 22.0 + temp_error
            power = compute_hvac_power(temp, setpoint, max_hvac_power_kw=5.0)
            assert abs(power) <= 5.0 + 1e-9, (
                f"HVAC power {power:.3f} kW exceeded capacity 5.0 kW"
            )

    def test_no_power_at_setpoint(self) -> None:
        """When temperature equals setpoint, HVAC power is zero."""
        power = compute_hvac_power(22.0, 22.0, max_hvac_power_kw=5.0)
        assert abs(power) < 1e-9, f"Expected 0 kW at setpoint, got {power}"


# ---------------------------------------------------------------------------
# Internal heat tests
# ---------------------------------------------------------------------------

class TestInternalHeat:
    """Occupancy heat generation tests."""

    def test_zero_occupancy_zero_heat(self) -> None:
        heat = compute_internal_heat(0, 0.1)
        assert heat == 0.0

    def test_heat_proportional_to_occupancy(self) -> None:
        heat_5 = compute_internal_heat(5, 0.1)
        heat_20 = compute_internal_heat(20, 0.1)
        # 20 occupants should generate 4x more heat than 5.
        assert abs(heat_20 / heat_5 - 4.0) < 1e-9, (
            f"Heat not proportional: {heat_5:.3f} vs {heat_20:.3f}"
        )


# ---------------------------------------------------------------------------
# Airflow clamp tests
# ---------------------------------------------------------------------------

class TestAirflowClamp:
    """Airflow must stay within configured bounds."""

    def test_airflow_min_clamp(self, default_config: RoomConfig) -> None:
        result = clamp_airflow(-100.0, default_config)
        assert result == default_config.min_airflow_lps

    def test_airflow_max_clamp(self, default_config: RoomConfig) -> None:
        result = clamp_airflow(9999.0, default_config)
        assert result == default_config.max_airflow_lps

    def test_airflow_valid_passes_through(self, default_config: RoomConfig) -> None:
        result = clamp_airflow(150.0, default_config)
        assert result == 150.0


# ---------------------------------------------------------------------------
# Humidity tests
# ---------------------------------------------------------------------------

class TestHumidityModel:
    """Humidity response tests."""

    def test_humidity_moves_toward_target(self) -> None:
        """Humidity should gradually approach the target over steps."""
        humidity = 50.0
        target = 65.0
        lag = 0.05

        for _ in range(20):
            humidity = compute_next_humidity(humidity, target, lag)

        assert humidity > 50.0, "Humidity did not increase toward target"
        assert humidity < 65.0, "Humidity overshot target (should lag)"

    def test_humidity_stays_bounded(self) -> None:
        """Humidity never goes below 30% or above 70%."""
        for extreme_target in [0.0, 100.0]:
            humidity = 50.0
            for _ in range(100):
                # compute_next_humidity(humidity_pct, effective_humidity_target, humidity_lag)
                humidity = compute_next_humidity(humidity, extreme_target, 0.1)
            assert 30.0 <= humidity <= 70.0, (
                f"Humidity {humidity:.2f}% out of bounds for target {extreme_target}%"
            )
