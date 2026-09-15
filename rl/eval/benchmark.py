"""
benchmark.py  —  Phase 6: RL vs Rule-Based Baseline Evaluation
===============================================================

Runs 30 simulated days (8 640 steps at 5 min each) for BOTH:
  1. RL Controller  — a trained PPO policy (JarvisAgent)
  2. Rule-Based     — ASHRAE-style fixed schedule (get_baseline_setpoint)

Outputs a side-by-side comparison report covering:
  • Total energy consumption  (kWh)
  • Discomfort minutes        (steps where ANY room comfort_score < COMFORT_THRESHOLD)
  • IAQ violation minutes     (steps where ANY room CO2 > IAQ_THRESHOLD_PPM)
  • Estimated cost            (INR, using TOU electricity price)
  • Per-room breakdown        (energy, discomfort)
  • Energy saved vs baseline  (%)
  • Discomfort reduced vs baseline (%)

Usage
-----
  # With a trained model:
  python -m rl.eval.benchmark --model rl/models/jarvis_final.zip

  # Dry-run with random policy (no model needed, for testing):
  python -m rl.eval.benchmark --random

  # Save JSON report:
  python -m rl.eval.benchmark --model rl/models/jarvis_final.zip --json report.json

REST endpoint hint (for backend/main.py — Phase 6B)
------------------------------------------------------
  GET  /api/benchmark?days=30
      → Runs this script in-process and returns the JSON report.
      → Endpoint implementation: see benchmark_endpoint() docstring at bottom.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

# ── project root on path ──────────────────────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from backend.digital_twin import BuildingTwin
from backend.baseline import get_baseline_setpoint

# ── Constants ─────────────────────────────────────────────────────────────────

STEP_MINUTES:        float = 5.0
DAYS:                int   = 30
STEPS_PER_DAY:       int   = int(24 * 60 / STEP_MINUTES)   # 288
TOTAL_STEPS:         int   = DAYS * STEPS_PER_DAY            # 8 640
ROOM_IDS:            list  = ["A", "B", "C", "D"]

# Thresholds for counting "discomfort" and "IAQ violation" minutes
COMFORT_THRESHOLD:   float = 70.0    # comfort_score below this → uncomfortable
IAQ_THRESHOLD_PPM:   float = 1000.0  # CO2 above this → IAQ violation
ELECTRICITY_PRICE:   float = 8.5     # INR/kWh (matches simulation default)


# ── Data containers ───────────────────────────────────────────────────────────

@dataclass
class RoomMetrics:
    room_id:             str
    energy_kwh:          float = 0.0
    discomfort_minutes:  float = 0.0
    iaq_violation_minutes: float = 0.0
    avg_comfort_score:   float = 0.0
    avg_co2_ppm:         float = 0.0
    _comfort_samples:    List[float] = field(default_factory=list, repr=False)
    _co2_samples:        List[float] = field(default_factory=list, repr=False)

    def record_step(self, state_room: dict) -> None:
        comfort = state_room.get("comfort_score", 100.0)
        co2     = state_room.get("co2_ppm", 400.0)
        energy  = state_room.get("energy_kwh", 0.0)

        self._comfort_samples.append(comfort)
        self._co2_samples.append(co2)

        if comfort < COMFORT_THRESHOLD:
            self.discomfort_minutes += STEP_MINUTES
        if co2 > IAQ_THRESHOLD_PPM:
            self.iaq_violation_minutes += STEP_MINUTES

    def finalise(self, twin: BuildingTwin) -> None:
        """Pull accumulated energy from twin after run."""
        _, room = twin.get_room(self.room_id)
        self.energy_kwh = round(room.energy_kwh, 4)
        if self._comfort_samples:
            self.avg_comfort_score = round(sum(self._comfort_samples) / len(self._comfort_samples), 2)
        if self._co2_samples:
            self.avg_co2_ppm = round(sum(self._co2_samples) / len(self._co2_samples), 1)


@dataclass
class RunReport:
    label:                  str
    total_energy_kwh:       float = 0.0
    total_discomfort_mins:  float = 0.0
    total_iaq_violation_mins: float = 0.0
    estimated_cost_inr:     float = 0.0
    avg_comfort_score:      float = 0.0
    rooms:                  Dict[str, Any] = field(default_factory=dict)
    elapsed_wall_seconds:   float = 0.0
    steps_run:              int   = 0


# ── Runner helpers ────────────────────────────────────────────────────────────

def _run_baseline(days: int = DAYS) -> RunReport:
    """
    Rule-based controller: ASHRAE-style fixed schedule setpoints, max airflow.
    Mirrors what BuildingTwin._create_baseline_twin() already does internally,
    but runs standalone so we capture full per-room metrics.
    """
    total_steps = days * STEPS_PER_DAY
    twin = BuildingTwin(
        step_minutes=STEP_MINUTES,
        use_diurnal_weather=True,
        use_stochastic_weather=False,
        use_occupancy_schedule=True,
        electricity_price_per_kwh=ELECTRICITY_PRICE,
    )
    room_metrics = {rid: RoomMetrics(room_id=rid) for rid in ROOM_IDS}
    t0 = time.monotonic()

    for step in range(total_steps):
        sim_time = twin.simulation_time_minutes
        # Apply fixed ASHRAE schedule setpoints to all rooms
        sp = get_baseline_setpoint(sim_time)
        for rid in ROOM_IDS:
            twin.set_setpoint(rid, sp)
            # Baseline keeps airflow at a comfortable constant 150 L/s
            twin.set_airflow(rid, 150.0)

        state = twin.step()
        for rid in ROOM_IDS:
            room_metrics[rid].record_step(state["rooms"][rid])

    elapsed = time.monotonic() - t0
    for rm in room_metrics.values():
        rm.finalise(twin)

    report = _build_report("Rule-Based Baseline", room_metrics, twin, elapsed, total_steps)
    return report


def _run_rl(model_path: str, days: int = DAYS, random_policy: bool = False) -> RunReport:
    """
    RL controller: loads a trained PPO policy and uses it at every step.
    Falls back to a random policy when random_policy=True (for dry-run tests).
    """
    total_steps = days * STEPS_PER_DAY
    twin = BuildingTwin(
        step_minutes=STEP_MINUTES,
        use_diurnal_weather=True,
        use_stochastic_weather=False,
        use_occupancy_schedule=True,
        electricity_price_per_kwh=ELECTRICITY_PRICE,
    )
    room_metrics = {rid: RoomMetrics(room_id=rid) for rid in ROOM_IDS}

    if random_policy:
        import numpy as np
        agent = None
    else:
        from rl.agent import JarvisAgent
        agent = JarvisAgent(model_path)

    t0 = time.monotonic()

    for step in range(total_steps):
        state = twin.get_state()

        if agent is not None:
            actions = agent.get_actions(state)
            for rid, cmd in actions.items():
                twin.set_setpoint(rid, cmd["setpoint_c"])
                twin.set_airflow(rid, cmd["airflow_lps"])
        else:
            # Random policy for dry-run
            import numpy as np
            for rid in ROOM_IDS:
                sp  = float(np.random.uniform(20.0, 26.0))
                af  = float(np.random.uniform(80.0, 200.0))
                twin.set_setpoint(rid, sp)
                twin.set_airflow(rid, af)

        state = twin.step()
        for rid in ROOM_IDS:
            room_metrics[rid].record_step(state["rooms"][rid])

    elapsed = time.monotonic() - t0
    for rm in room_metrics.values():
        rm.finalise(twin)

    label = "Random Policy (dry-run)" if random_policy else "RL Controller (PPO)"
    report = _build_report(label, room_metrics, twin, elapsed, total_steps)
    return report


def _build_report(
    label: str,
    room_metrics: Dict[str, RoomMetrics],
    twin: BuildingTwin,
    elapsed: float,
    steps: int,
) -> RunReport:
    report = RunReport(label=label, elapsed_wall_seconds=round(elapsed, 2), steps_run=steps)
    for rid, rm in room_metrics.items():
        report.total_energy_kwh      += rm.energy_kwh
        report.total_discomfort_mins += rm.discomfort_minutes
        report.total_iaq_violation_mins += rm.iaq_violation_minutes
        report.rooms[rid] = {
            "energy_kwh":             round(rm.energy_kwh, 4),
            "discomfort_minutes":     round(rm.discomfort_minutes, 1),
            "iaq_violation_minutes":  round(rm.iaq_violation_minutes, 1),
            "avg_comfort_score":      rm.avg_comfort_score,
            "avg_co2_ppm":            rm.avg_co2_ppm,
        }
    report.total_energy_kwh       = round(report.total_energy_kwh, 4)
    report.total_discomfort_mins  = round(report.total_discomfort_mins, 1)
    report.total_iaq_violation_mins = round(report.total_iaq_violation_mins, 1)
    report.estimated_cost_inr     = round(report.total_energy_kwh * ELECTRICITY_PRICE, 2)
    all_comfort = [rm.avg_comfort_score for rm in room_metrics.values() if rm.avg_comfort_score]
    report.avg_comfort_score      = round(sum(all_comfort) / len(all_comfort), 2) if all_comfort else 0.0
    return report


# ── Comparison printer ────────────────────────────────────────────────────────

def _compare_and_print(rl: RunReport, baseline: RunReport) -> dict:
    def pct_change(new, old):
        if old == 0:
            return 0.0
        return round((old - new) / old * 100, 2)

    energy_saved_pct      = pct_change(rl.total_energy_kwh,      baseline.total_energy_kwh)
    discomfort_saved_pct  = pct_change(rl.total_discomfort_mins,  baseline.total_discomfort_mins)
    iaq_saved_pct         = pct_change(rl.total_iaq_violation_mins, baseline.total_iaq_violation_mins)
    cost_saved_inr        = round(baseline.estimated_cost_inr - rl.estimated_cost_inr, 2)

    sep = "=" * 70
    print(f"\n{sep}")
    print(f"  JARVIS Phase 6 — RL vs Baseline Benchmark ({DAYS}-Day Simulation)")
    print(sep)
    print(f"  {'Metric':<35} {'Baseline':>12}  {'RL Agent':>12}  {'Delta':>10}")
    print(f"  {'-'*35} {'-'*12}  {'-'*12}  {'-'*10}")

    rows = [
        ("Total energy (kWh)",        baseline.total_energy_kwh,      rl.total_energy_kwh,      f"{energy_saved_pct:+.1f}%"),
        ("Estimated cost (INR)",       baseline.estimated_cost_inr,    rl.estimated_cost_inr,    f"saved {cost_saved_inr:.2f}"),
        ("Discomfort minutes",         baseline.total_discomfort_mins, rl.total_discomfort_mins, f"{discomfort_saved_pct:+.1f}%"),
        ("IAQ violation minutes",      baseline.total_iaq_violation_mins, rl.total_iaq_violation_mins, f"{iaq_saved_pct:+.1f}%"),
        ("Avg comfort score [0–100]",  baseline.avg_comfort_score,     rl.avg_comfort_score,     f"{rl.avg_comfort_score - baseline.avg_comfort_score:+.2f}"),
    ]
    for name, bval, rval, delta in rows:
        print(f"  {name:<35} {bval:>12.2f}  {rval:>12.2f}  {delta:>10}")

    print(f"\n  {sep}")
    print(f"  Per-Room Breakdown (RL vs Baseline):")
    print(f"  {'Room':<8} {'RL Energy':>10} {'BL Energy':>10} {'RL Discomf':>12} {'BL Discomf':>12}")
    print(f"  {'-'*8} {'-'*10}  {'-'*10}  {'-'*12}  {'-'*12}")
    for rid in ROOM_IDS:
        rl_r  = rl.rooms.get(rid, {})
        bl_r  = baseline.rooms.get(rid, {})
        print(
            f"  {rid:<8}"
            f" {rl_r.get('energy_kwh', 0):>10.4f}"
            f" {bl_r.get('energy_kwh', 0):>10.4f}"
            f" {rl_r.get('discomfort_minutes', 0):>12.1f}"
            f" {bl_r.get('discomfort_minutes', 0):>12.1f}"
        )

    print(f"\n  Wall-clock: RL={rl.elapsed_wall_seconds}s  Baseline={baseline.elapsed_wall_seconds}s")
    print(f"{sep}\n")

    return {
        "days_simulated":         DAYS,
        "steps_per_run":          TOTAL_STEPS,
        "comfort_threshold":      COMFORT_THRESHOLD,
        "iaq_threshold_ppm":      IAQ_THRESHOLD_PPM,
        "energy_saved_pct":       energy_saved_pct,
        "discomfort_reduced_pct": discomfort_saved_pct,
        "iaq_violation_reduced_pct": iaq_saved_pct,
        "cost_saved_inr":         cost_saved_inr,
        "rl":                     asdict(rl),
        "baseline":               asdict(baseline),
    }


# ── Public API (for FastAPI endpoint) ─────────────────────────────────────────

def run_benchmark(
    model_path: Optional[str] = None,
    days: int = DAYS,
    random_policy: bool = False,
) -> dict:
    """
    Run the full RL-vs-baseline benchmark and return a JSON-serialisable dict.

    This function is the entry-point for the REST endpoint.

    REST Endpoint hint (backend/main.py)
    =====================================
    @app.get("/api/benchmark")
    async def get_benchmark(
        days: int = Query(default=30, ge=1, le=90),
        model: str = Query(default="rl/models/jarvis_final.zip"),
    ):
        \"\"\"Phase 6: Run RL vs baseline benchmark and return comparative report.\"\"\"
        import asyncio
        from rl.eval.benchmark import run_benchmark
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: run_benchmark(model_path=model, days=days)
        )
        return result
    """
    print(f"[Benchmark] Running baseline controller ({days} days, {days*STEPS_PER_DAY} steps)…")
    baseline_report = _run_baseline(days=days)

    print(f"[Benchmark] Running RL controller ({days} days, {days*STEPS_PER_DAY} steps)…")
    rl_report = _run_rl(model_path=model_path or "", days=days, random_policy=random_policy)

    return _compare_and_print(rl_report, baseline_report)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 6: RL vs Baseline Benchmark")
    parser.add_argument("--model",  type=str, default=None,
                        help="Path to trained .zip policy file")
    parser.add_argument("--random", action="store_true",
                        help="Use random policy (dry-run, no model required)")
    parser.add_argument("--days",   type=int, default=DAYS,
                        help=f"Number of simulated days to run (default {DAYS})")
    parser.add_argument("--json",   type=str, default=None,
                        help="Optional path to save JSON report")
    args = parser.parse_args()

    if not args.random and args.model is None:
        parser.error("Provide --model <path> or --random for dry-run")

    result = run_benchmark(
        model_path=args.model,
        days=args.days,
        random_policy=args.random,
    )

    if args.json:
        with open(args.json, "w") as f:
            json.dump(result, f, indent=2)
        print(f"[Benchmark] JSON report saved → {args.json}")
