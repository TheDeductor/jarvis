"""
test_comfort_model.py
=====================
Tests for comfort_model.py — simplified comfort scoring.

Tests covered:
  - Comfort at ideal conditions = 100
  - Comfort bounded [0, 100] for all inputs
  - Comfort decreases with temperature deviation
  - Comfort decreases with humidity deviation
"""

from __future__ import annotations

import pytest

from digital_twin.comfort_model import (
    IDEAL_HUMIDITY_PCT,
    IDEAL_TEMPERATURE_C,
    comfort_label,
    compute_comfort_score,
)


# ---------------------------------------------------------------------------
# Ideal conditions
# ---------------------------------------------------------------------------

class TestIdealConditions:
    """At ideal temperature and humidity, comfort must be 100."""

    def test_perfect_comfort_at_ideal(self) -> None:
        score = compute_comfort_score(IDEAL_TEMPERATURE_C, IDEAL_HUMIDITY_PCT)
        assert abs(score - 100.0) < 1e-9, (
            f"Expected 100 at ideal conditions, got {score}"
        )

    def test_comfort_near_ideal_is_high(self) -> None:
        """Small deviations should give high but not perfect comfort."""
        score = compute_comfort_score(22.5, 51.0)
        assert score > 90.0, f"Near-ideal comfort should be >90, got {score}"


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

class TestComfortBounds:
    """Comfort score is always within [0, 100]."""

    def test_extreme_high_temperature(self) -> None:
        # 50°C is 28°C above ideal. Temp penalty = 28 × 5 = 140, capped at 60.
        # Humidity is at ideal (50%), so humidity penalty = 0.
        # Score = 100 - 60 - 0 = 40.
        # To get score=0, we need both penalties at max simultaneously.
        score = compute_comfort_score(50.0, 50.0)
        assert 0.0 <= score <= 100.0, f"Score out of bounds: {score}"
        assert score == 40.0, (
            f"50°C, 50% humidity: expected 40 (temp penalty maxed, humidity ideal), got {score}"
        )
        # Test true worst case: extreme temp AND extreme humidity → score = 0.
        score_worst = compute_comfort_score(50.0, 100.0)
        assert score_worst == 0.0, f"Extreme temp+humidity should give 0, got {score_worst}"

    def test_extreme_low_temperature(self) -> None:
        score = compute_comfort_score(-10.0, 50.0)
        assert 0.0 <= score <= 100.0

    def test_extreme_high_humidity(self) -> None:
        score = compute_comfort_score(22.0, 100.0)
        assert 0.0 <= score <= 100.0

    def test_extreme_low_humidity(self) -> None:
        score = compute_comfort_score(22.0, 0.0)
        assert 0.0 <= score <= 100.0

    @pytest.mark.parametrize("temp,humidity", [
        (22.0, 50.0),   # ideal
        (27.0, 60.0),   # warm, humid
        (19.0, 40.0),   # cold, dry
        (35.0, 70.0),   # hot, very humid
        (15.0, 30.0),   # cold, dry
        (60.0, 70.0),   # extreme
        (-10.0, 30.0),  # extreme
    ])
    def test_always_in_range(self, temp: float, humidity: float) -> None:
        score = compute_comfort_score(temp, humidity)
        assert 0.0 <= score <= 100.0, (
            f"Score {score} out of [0, 100] for temp={temp}, humidity={humidity}"
        )


# ---------------------------------------------------------------------------
# Monotonicity
# ---------------------------------------------------------------------------

class TestComfortMonotonicity:
    """Comfort decreases as deviation from ideal increases."""

    def test_comfort_decreases_with_temp_deviation(self) -> None:
        """Higher temperature deviation → lower comfort."""
        score_ideal = compute_comfort_score(22.0, 50.0)
        score_1deg = compute_comfort_score(23.0, 50.0)
        score_3deg = compute_comfort_score(25.0, 50.0)

        assert score_ideal > score_1deg, "1°C deviation should lower comfort"
        assert score_1deg > score_3deg, "3°C deviation should lower comfort more"

    def test_comfort_decreases_with_humidity_deviation(self) -> None:
        """Higher humidity deviation → lower comfort."""
        score_ideal = compute_comfort_score(22.0, 50.0)
        score_5pct = compute_comfort_score(22.0, 55.0)
        score_15pct = compute_comfort_score(22.0, 65.0)

        assert score_ideal > score_5pct
        assert score_5pct > score_15pct

    def test_symmetric_temperature_penalty(self) -> None:
        """Deviation above and below ideal should give the same penalty."""
        score_above = compute_comfort_score(22.0 + 3.0, 50.0)
        score_below = compute_comfort_score(22.0 - 3.0, 50.0)
        assert abs(score_above - score_below) < 1e-9, (
            f"Temperature penalty is not symmetric: {score_above} vs {score_below}"
        )


# ---------------------------------------------------------------------------
# Comfort labels
# ---------------------------------------------------------------------------

class TestComfortLabel:
    def test_label_excellent(self) -> None:
        assert comfort_label(90.0) == "Excellent"

    def test_label_good(self) -> None:
        assert comfort_label(75.0) == "Good"

    def test_label_moderate(self) -> None:
        assert comfort_label(60.0) == "Moderate"

    def test_label_poor(self) -> None:
        assert comfort_label(40.0) == "Poor"

    def test_label_very_poor(self) -> None:
        assert comfort_label(10.0) == "Very Poor"
