"""
agent.py  —  JarvisAgent: loads a trained policy and serves actions to the backend.

This is the bridge between the trained RL policy (a .zip file) and the live
simulation_manager / real hardware in Auto Mode.

The obs/action encoding here MUST be identical to building_env.py.
If you change building_env._get_obs() or the action decoding there,
update this file to match.

Usage from backend (Phase 5):
    from rl.agent import JarvisAgent
    agent = JarvisAgent("rl/models/jarvis_final.zip")
    actions = agent.get_actions(manager.get_state())
    # actions = {"A": {"setpoint_delta": 0.5, "airflow_delta": -10.0}, ...}
"""
from __future__ import annotations

import math
import os
import sys
from typing import Any, Dict

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from stable_baselines3 import PPO


ROOM_IDS = ["A", "B", "C", "D"]


class JarvisAgent:
    """
    Wraps a trained PPO policy for live deployment.

    Thread safety:
        predict() is stateless — safe to call from multiple threads.
        It holds no mutable state between calls.
    """

    def __init__(self, model_path: str) -> None:
        """
        Load a saved PPO policy.

        Parameters
        ----------
        model_path : Absolute or relative path to a .zip policy file.
                     Example: "rl/models/jarvis_20240817_final.zip"
        """
        if not os.path.exists(model_path) and not os.path.exists(model_path + ".zip"):
            raise FileNotFoundError(
                f"Policy not found: {model_path}\n"
                f"Train a policy first: python -m rl.train"
            )
        self.model = PPO.load(model_path)
        self.model_path = model_path
        print(f"[JarvisAgent] Loaded policy: {model_path}")

    def get_actions(self, state: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        """
        Given the current twin/building state, return HVAC actions for all rooms.

        Parameters
        ----------
        state : Dict returned by BuildingTwin.get_state() or
                SimulationManager.get_state() (same schema).

        Returns
        -------
        Dict mapping room_id → {"setpoint_delta": float, "airflow_delta": float}

        Example
        -------
        {
            "A": {"setpoint_delta": -0.5, "airflow_delta":  10.0},
            "B": {"setpoint_delta":  0.0, "airflow_delta": -20.0},
            "C": {"setpoint_delta":  1.0, "airflow_delta":   0.0},
            "D": {"setpoint_delta": -1.5, "airflow_delta":  15.0},
        }
        """
        obs = self._build_obs(state)
        # deterministic=True: no exploration noise during deployment
        raw_actions, _ = self.model.predict(obs, deterministic=True)
        return self._decode_actions(raw_actions, state)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_obs(self, state: Dict[str, Any]) -> np.ndarray:
        """
        Build the 23-float observation vector from a raw twin state dict.
        Must exactly match BuildingEnv._get_obs().
        """
        def norm(val: float, lo: float, hi: float) -> float:
            clipped = max(lo, min(hi, float(val)))
            return 2.0 * ((clipped - lo) / (hi - lo)) - 1.0

        obs: list[float] = []
        rooms = state["rooms"]

        for room_id in ROOM_IDS:
            r = rooms[room_id]
            obs.append(norm(r["temperature_c"],  10.0, 40.0))
            obs.append(norm(r["humidity_pct"],    0.0, 100.0))
            obs.append(norm(r["setpoint_c"],     16.0, 30.0))
            obs.append(norm(r["occupancy"],       0,   50))
            obs.append(norm(r["hvac_power_kw"], -10.0, 10.0))

        obs.append(norm(state["outside_temperature_c"], -10.0, 50.0))

        time_mins  = state["simulation_time_minutes"]
        time_hours = (time_mins / 60.0) % 24.0
        time_rads  = (time_hours / 24.0) * 2 * math.pi
        obs.append(math.sin(time_rads))
        obs.append(math.cos(time_rads))

        return np.array(obs, dtype=np.float32)

    def _decode_actions(
        self,
        raw: np.ndarray,
        state: Dict[str, Any],
    ) -> Dict[str, Dict[str, float]]:
        """
        Decode raw [-1, 1] network output to physical HVAC deltas.
        Applies the same clamping as BuildingEnv.step().

        Also clamps absolute setpoint to [16, 30] and airflow to [50, 300]
        so the backend API validators never reject the command.
        """
        rooms = state["rooms"]
        result: dict = {}

        for i, room_id in enumerate(ROOM_IDS):
            setpoint_delta = float(raw[i * 2])     * 2.0    # [-1,1] → [-2,+2] °C
            airflow_delta  = float(raw[i * 2 + 1]) * 20.0   # [-1,1] → [-20,+20] L/s

            current_sp = rooms[room_id]["setpoint_c"]
            current_af = rooms[room_id]["airflow_lps"]

            new_sp = current_sp + setpoint_delta
            new_af = current_af + airflow_delta

            # Clamp to API-accepted physical limits
            new_sp = max(16.0, min(30.0, new_sp))
            new_af = max(50.0, min(300.0, new_af))

            result[room_id] = {
                "setpoint_c":    round(new_sp, 2),
                "airflow_lps":   round(new_af, 1),
                "setpoint_delta": round(setpoint_delta, 3),
                "airflow_delta":  round(airflow_delta, 1),
            }

        return result


# ── Quick smoke-test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Smoke-test JarvisAgent")
    parser.add_argument("--model", type=str, required=True,
                        help="Path to a trained .zip policy")
    args = parser.parse_args()

    # Import BuildingTwin here only for the smoke test
    from backend.digital_twin import BuildingTwin

    twin  = BuildingTwin()
    agent = JarvisAgent(args.model)
    state = twin.get_state()

    print("\n[Smoke Test] Running 5 steps with trained policy...")
    for step in range(5):
        actions = agent.get_actions(state)
        for room_id, cmd in actions.items():
            twin.set_setpoint(room_id, cmd["setpoint_c"])
            twin.set_airflow(room_id, cmd["airflow_lps"])
        twin.step()
        state = twin.get_state()
        rooms = state["rooms"]
        print(f"  Step {step+1}: " + " | ".join(
            f"Room {r}: {rooms[r]['temperature_c']:.1f}°C @ {rooms[r]['setpoint_c']:.1f}°C sp"
            for r in ROOM_IDS
        ))

    print("\n✅ Smoke test passed.")
