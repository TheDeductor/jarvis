"""
train.py  —  Phase 3: PPO Training Script for JARVIS HVAC Agent.

Usage:
    python -m rl.train                          # default 1M steps
    python -m rl.train --timesteps 500000       # quick test run
    python -m rl.train --envs 4 --timesteps 2000000  # parallel envs

Outputs:
    rl/models/jarvis_policy_<timestamp>.zip     # final saved policy
    rl/logs/                                    # TensorBoard logs
        tensorboard --logdir rl/logs/           # to visualize
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.callbacks import (
    CheckpointCallback,
    EvalCallback,
    CallbackList,
)
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv
from stable_baselines3.common.env_checker import check_env

from rl.env.building_env import BuildingEnv


# ── Directories ───────────────────────────────────────────────────────────────
MODELS_DIR = os.path.join(os.path.dirname(__file__), 'models')
LOGS_DIR   = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR,   exist_ok=True)


def validate_env() -> None:
    """Run SB3's built-in env checker. If this passes, training will work."""
    print("[*] Validating environment with SB3 check_env()...")
    env = BuildingEnv()
    check_env(env, warn=True)
    env.close()
    print("[OK] Environment validation passed.\n")


def train(
    total_timesteps: int = 1_000_000,
    n_envs: int = 4,
    run_name: str | None = None,
) -> str:
    """
    Train the JARVIS HVAC agent with PPO.

    Parameters
    ----------
    total_timesteps : Total number of environment steps to train for.
    n_envs          : Number of parallel environments (DummyVecEnv).
    run_name        : Identifier for this training run (default: timestamp).

    Returns
    -------
    str : Path to the saved final policy.
    """
    if run_name is None:
        run_name = datetime.now().strftime("jarvis_%Y%m%d_%H%M%S")

    print(f"[TRAIN] Starting training run: {run_name}")
    print(f"   Total timesteps : {total_timesteps:,}")
    print(f"   Parallel envs   : {n_envs}")
    print(f"   Models dir      : {MODELS_DIR}")

    # Check if TensorBoard is available
    try:
        import tensorboard  # noqa: F401
        tb_log = LOGS_DIR
        print(f"   TensorBoard     : tensorboard --logdir {LOGS_DIR}\n")
    except ImportError:
        tb_log = None
        print("   TensorBoard     : not installed (pip install tensorboard to enable)\n")

    # ── 1. Create vectorized training environments ────────────────────────────
    # DummyVecEnv runs envs sequentially in one process — safe on Windows.
    # Switch to SubprocVecEnv on Linux/Mac for true parallelism.
    vec_env = make_vec_env(BuildingEnv, n_envs=n_envs, vec_env_cls=DummyVecEnv)

    # ── 2. Separate eval environment ──────────────────────────────────────────
    eval_env = DummyVecEnv([lambda: BuildingEnv()])

    # ── 3. PPO Hyperparameters ────────────────────────────────────────────────
    # Tuned for continuous HVAC control:
    #   n_steps     — steps collected per env per update (larger = less noisy)
    #   batch_size  — PPO minibatch (must divide n_steps * n_envs)
    #   learning_rate — standard Adam LR
    #   ent_coef    — entropy bonus prevents greedy collapse (agent keeps exploring)
    #   gamma       — discount factor (0.99 = plans ~100 steps ahead)
    #   gae_lambda  — GAE smoothing for advantage estimates
    #   clip_range  — PPO trust-region clipping (standard 0.2)
    #   n_epochs    — how many passes over each collected batch
    model = PPO(
        policy         = "MlpPolicy",
        env            = vec_env,
        verbose        = 1,
        tensorboard_log= tb_log,

        # Core hyperparameters
        n_steps        = 2048,
        batch_size     = 256,
        learning_rate  = 3e-4,
        gamma          = 0.99,
        gae_lambda     = 0.95,
        clip_range     = 0.2,
        n_epochs       = 10,

        # Exploration vs exploitation
        ent_coef       = 0.01,

        # Network architecture: 2 hidden layers of 256 neurons each
        policy_kwargs  = dict(net_arch=[256, 256]),
    )

    # ── 4. Callbacks ──────────────────────────────────────────────────────────

    # Save a checkpoint every 50k steps
    checkpoint_cb = CheckpointCallback(
        save_freq   = 50_000 // n_envs,  # per-env steps
        save_path   = os.path.join(MODELS_DIR, run_name),
        name_prefix = "checkpoint",
        verbose     = 1,
    )

    # Evaluate on a separate env every 20k steps; save the best model
    eval_cb = EvalCallback(
        eval_env          = eval_env,
        best_model_save_path = os.path.join(MODELS_DIR, run_name),
        log_path          = LOGS_DIR,
        eval_freq         = 20_000 // n_envs,
        n_eval_episodes   = 3,
        deterministic     = True,
        verbose           = 1,
    )

    callbacks = CallbackList([checkpoint_cb, eval_cb])

    # ── 5. Train ──────────────────────────────────────────────────────────────
    start = time.time()
    model.learn(
        total_timesteps = total_timesteps,
        callback        = callbacks,
        tb_log_name     = run_name if tb_log else "",
        progress_bar    = True,
    )
    elapsed = time.time() - start

    # ── 6. Save final policy ──────────────────────────────────────────────────
    final_path = os.path.join(MODELS_DIR, f"{run_name}_final")
    model.save(final_path)

    print(f"\n[DONE] Training complete in {elapsed / 60:.1f} minutes.")
    print(f"   Final policy saved: {final_path}.zip")
    print(f"   Best policy saved : {os.path.join(MODELS_DIR, run_name, 'best_model.zip')}")

    vec_env.close()
    eval_env.close()
    return final_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Train JARVIS HVAC RL agent")
    parser.add_argument("--timesteps", type=int, default=1_000_000,
                        help="Total training timesteps (default: 1,000,000)")
    parser.add_argument("--envs",      type=int, default=4,
                        help="Number of parallel environments (default: 4)")
    parser.add_argument("--name",      type=str, default=None,
                        help="Run name identifier (default: timestamp)")
    parser.add_argument("--validate-only", action="store_true",
                        help="Only run env validation, skip training")
    args = parser.parse_args()

    validate_env()

    if not args.validate_only:
        train(
            total_timesteps = args.timesteps,
            n_envs          = args.envs,
            run_name        = args.name,
        )


if __name__ == "__main__":
    main()
