"""
test_api.py  —  Smoke test for the Digital Twin API endpoints.

Run AFTER starting the backend:
  py -m uvicorn backend.main:app --port 8000 --reload

Then:
  py test_api.py
"""
import json
import time
import sys
import urllib.request
import urllib.error

BASE = "http://localhost:8000/api"


def get(path: str) -> dict:
    r = urllib.request.urlopen(f"{BASE}{path}", timeout=5)
    return json.loads(r.read())


def post(path: str, data: dict = None) -> dict:
    body = json.dumps(data or {}).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    r = urllib.request.urlopen(req, timeout=5)
    return json.loads(r.read())


results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, note: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    results.append((name, cond, note))
    print(f"  [{status}] {name}" + (f"  ({note})" if note else ""))
    if not cond:
        print(f"         *** FAILED ***")


def run() -> None:
    print("\n" + "=" * 60)
    print("  DIGITAL TWIN API SMOKE TEST")
    print("=" * 60)

    # ── Health ───────────────────────────────────────────────────
    print("\n[Health]")
    h = get("/health")
    check("Health endpoint", "status" in h and h["status"] == "ok")

    # ── Initial state ─────────────────────────────────────────────
    print("\n[Initial state]")
    s = get("/simulation/state")
    check("4 rooms present", set(s["rooms"].keys()) == {"A", "B", "C", "D"},
          str(list(s["rooms"].keys())))
    check("Not running initially", not s["running"])
    check("Speed = 1 initially", s["speed"] == 1)
    check("Energy = 0 initially",
          s["building"]["total_energy_kwh"] == 0.0,
          f"{s['building']['total_energy_kwh']}")

    # ── Start ─────────────────────────────────────────────────────
    print("\n[Start / dynamics]")
    post("/simulation/start")
    time.sleep(2)
    s1 = get("/simulation/state")
    check("Running after start", s1["running"])
    check("Time advancing", s1["simulation_time_minutes"] > 0,
          f"{s1['simulation_time_minutes']:.1f} min")
    check("Energy accumulating", s1["building"]["total_energy_kwh"] > 0,
          f"{s1['building']['total_energy_kwh']:.4f} kWh")
    check("B temperature changed",
          s1["rooms"]["B"]["temperature_c"] != 27.0,
          f"{s1['rooms']['B']['temperature_c']:.3f}°C")
    check("HVAC power non-zero",
          abs(s1["rooms"]["B"]["hvac_power_kw"]) > 0,
          f"{s1['rooms']['B']['hvac_power_kw']:.2f} kW")
    check("Baseline energy != 0 and != adaptive",
          s1["building"]["baseline_energy_kwh"] > 0,
          f"baseline={s1['building']['baseline_energy_kwh']:.4f}")

    # ── Critical test: setpoint change does NOT jump temp ─────────
    print("\n[Setpoint — no instant jump]")
    temp_before = s1["rooms"]["B"]["temperature_c"]
    post("/rooms/B/setpoint", {"setpoint_c": 22.0})
    s2 = get("/simulation/state")
    temp_after = s2["rooms"]["B"]["temperature_c"]
    jump = abs(temp_after - temp_before)
    check("Setpoint changes without temp jump",
          jump < 0.5,
          f"before={temp_before:.3f}  after={temp_after:.3f}  Δ={jump:.4f}")
    check("Setpoint recorded",
          abs(s2["rooms"]["B"]["setpoint_c"] - 22.0) < 0.01,
          f"setpoint={s2['rooms']['B']['setpoint_c']}")

    # ── Occupancy ─────────────────────────────────────────────────
    print("\n[Occupancy]")
    post("/rooms/A/occupancy", {"occupancy": 30})
    s3 = get("/simulation/state")
    check("Occupancy set", s3["rooms"]["A"]["occupancy"] == 30)

    # ── Airflow ───────────────────────────────────────────────────
    print("\n[Airflow]")
    post("/rooms/B/airflow", {"airflow_lps": 200.0})
    s4 = get("/simulation/state")
    check("Airflow set", abs(s4["rooms"]["B"]["airflow_lps"] - 200.0) < 0.1,
          f"{s4['rooms']['B']['airflow_lps']:.1f}")
    check("Fan power > 0", s4["rooms"]["B"]["fan_power_kw"] > 0,
          f"{s4['rooms']['B']['fan_power_kw']:.4f} kW")

    # ── Outside temperature ───────────────────────────────────────
    print("\n[Outside temperature]")
    post("/environment/outside-temperature", {"temperature_c": 38.0})
    s5 = get("/simulation/state")
    check("Outside temp set", abs(s5["outside_temperature_c"] - 38.0) < 0.01,
          f"{s5['outside_temperature_c']:.1f}")

    # ── Speed ─────────────────────────────────────────────────────
    print("\n[Speed]")
    post("/simulation/speed", {"speed": 5})
    s6 = get("/simulation/state")
    check("Speed = 5", s6["speed"] == 5)

    # ── Pause ─────────────────────────────────────────────────────
    print("\n[Pause]")
    post("/simulation/pause")
    t_at_pause = get("/simulation/state")["simulation_time_minutes"]
    time.sleep(1.5)
    t_after_wait = get("/simulation/state")["simulation_time_minutes"]
    check("Simulation stopped after pause",
          t_after_wait == t_at_pause,
          f"t_pause={t_at_pause:.1f}  t_after={t_after_wait:.1f}")

    # ── Reset ─────────────────────────────────────────────────────
    print("\n[Reset]")
    post("/simulation/reset")
    sr = get("/simulation/state")
    check("Time reset to 0", sr["simulation_time_minutes"] == 0.0,
          f"{sr['simulation_time_minutes']:.1f}")
    check("Energy reset to 0",
          sr["building"]["total_energy_kwh"] == 0.0,
          f"{sr['building']['total_energy_kwh']:.6f}")
    check("Room A temp reset",
          abs(sr["rooms"]["A"]["temperature_c"] - 23.0) < 0.01,
          f"{sr['rooms']['A']['temperature_c']:.3f}")

    # ── History ───────────────────────────────────────────────────
    print("\n[History]")
    hist = get("/simulation/history")["history"]
    check("History is a list", isinstance(hist, list))
    check("History non-empty", len(hist) > 0, f"{len(hist)} entries")

    # ── Validation errors ─────────────────────────────────────────
    print("\n[Input validation]")
    try:
        post("/rooms/B/setpoint", {"setpoint_c": 99.0})
        check("Invalid setpoint rejected", False, "Should have raised")
    except urllib.error.HTTPError as e:
        check("Invalid setpoint rejected", e.code == 422, f"HTTP {e.code}")

    try:
        post("/rooms/INVALID/setpoint", {"setpoint_c": 22.0})
        check("Invalid room rejected", False, "Should have raised")
    except urllib.error.HTTPError as e:
        check("Invalid room rejected", e.code == 404, f"HTTP {e.code}")

    # ── Summary ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"  RESULT: {passed} passed / {failed} failed")
    print("=" * 60 + "\n")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run()
