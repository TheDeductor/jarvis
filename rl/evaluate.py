"""
evaluate.py    Load a trained JARVIS policy and run a full evaluation episode.

Usage:
    python -m rl.evaluate --model rl/models/jarvis_20240817_123456_final.zip
    python -m rl.evaluate --model rl/models/my_run/best_model.zip --episodes 3

Output:
    Per-step table printed to console.
    Summary stats at the end.
    Optional CSV: rl/logs/eval_results.csv
"""
from __future__ import annotations

import argparse
import os
import sys
import csv
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from stable_baselines3 import PPO
from rl.env.building_env import BuildingEnv

LOGS_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)


def evaluate(model_path: str, n_episodes: int = 1, save_csv: bool = True) -> None:
    """
    Run the trained policy for n_episodes and report results.

    Parameters
    ----------
    model_path  : Path to saved .zip policy.
    n_episodes  : Number of full episodes (days) to evaluate.
    save_csv    : Whether to save per-step data to CSV.
    """
    print(f"\n Loading policy from: {model_path}")
    model = PPO.load(model_path)
    env   = BuildingEnv()

    all_episode_stats = []
    csv_rows = []

    for ep in range(n_episodes):
        obs, _ = env.reset()
        total_reward  = 0.0
        total_comfort = 0.0
        total_energy  = 0.0
        step_count    = 0

        print(f"\n{''*70}")
        print(f"  Episode {ep + 1}/{n_episodes}")
        print(f"{''*70}")
        print(f"  {'Step':>4}  {'Comfort':>8}  {'Power(kW)':>10}  {'Reward':>8}  Setpoints")
        print(f"{''*70}")

        while True:
            # Use deterministic=True for evaluation (no random exploration)
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)

            # Collect per-step stats from the env's twin state
            state = env.twin.get_state()
            rooms = state["rooms"]

            avg_comfort = sum(r["comfort_score"] for r in rooms.values()) / 4.0
            total_power = sum(
                abs(r["hvac_power_kw"]) + r["fan_power_kw"]
                for r in rooms.values()
            )
            setpoints = {rid: f"{r['setpoint_c']:.1f}" for rid, r in rooms.items()}

            total_reward  += reward
            total_comfort += avg_comfort
            total_energy  += total_power
            step_count    += 1

            # Print every 24 steps (~2 sim hours)
            if step_count % 24 == 0 or step_count == 1:
                sp_str = " | ".join(f"{k}:{v}" for k, v in setpoints.items())
                print(
                    f"  {step_count:>4}  "
                    f"{avg_comfort:>7.1f}%  "
                    f"{total_power:>9.2f}  "
                    f"{reward:>8.4f}  "
                    f"[{sp_str}]"
                )

            # CSV row
            if save_csv:
                row = {
                    "episode":   ep + 1,
                    "step":      step_count,
                    "reward":    round(reward, 4),
                    "avg_comfort": round(avg_comfort, 2),
                    "total_power_kw": round(total_power, 3),
                }
                for rid, r in rooms.items():
                    row[f"temp_{rid}"]    = round(r["temperature_c"], 2)
                    row[f"setpoint_{rid}"] = round(r["setpoint_c"], 1)
                csv_rows.append(row)

            if terminated or truncated:
                break

        # Episode summary
        ep_stats = {
            "episode":         ep + 1,
            "steps":           step_count,
            "total_reward":    round(total_reward, 3),
            "avg_comfort":     round(total_comfort / step_count, 1),
            "avg_power_kw":    round(total_energy / step_count, 2),
        }
        all_episode_stats.append(ep_stats)

    #  Final summary 
    print(f"\n{''*70}")
    print(f"  EVALUATION SUMMARY  ({n_episodes} episode(s))")
    print(f"{''*70}")
    print(f"  {'Episode':>7}  {'Steps':>6}  {'Reward':>10}  {'Comfort':>9}  {'Avg Power':>10}")
    print(f"{''*70}")
    for s in all_episode_stats:
        print(
            f"  {s['episode']:>7}  "
            f"{s['steps']:>6}  "
            f"{s['total_reward']:>10.3f}  "
            f"{s['avg_comfort']:>8.1f}%  "
            f"{s['avg_power_kw']:>9.2f} kW"
        )

    if all_episode_stats:
        mean_reward  = sum(s["total_reward"]  for s in all_episode_stats) / n_episodes
        mean_comfort = sum(s["avg_comfort"]   for s in all_episode_stats) / n_episodes
        mean_power   = sum(s["avg_power_kw"]  for s in all_episode_stats) / n_episodes
        print(f"{''*70}")
        print(f"  {'MEAN':>7}  {'':>6}  {mean_reward:>10.3f}  {mean_comfort:>8.1f}%  {mean_power:>9.2f} kW")

    #  Save CSV 
    if save_csv and csv_rows:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = os.path.join(LOGS_DIR, f"eval_{ts}.csv")
        fieldnames = list(csv_rows[0].keys())
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)
        print(f"\n   Results saved to: {csv_path}")

    env.close()
    print(f"{''*70}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a trained JARVIS policy")
    parser.add_argument("--model",    type=str, required=True,
                        help="Path to .zip policy file")
    parser.add_argument("--episodes", type=int, default=1,
                        help="Number of evaluation episodes (default: 1)")
    parser.add_argument("--no-csv",   action="store_true",
                        help="Skip saving CSV output")
    args = parser.parse_args()

    evaluate(
        model_path = args.model,
        n_episodes = args.episodes,
        save_csv   = not args.no_csv,
    )


if __name__ == "__main__":
    main()
