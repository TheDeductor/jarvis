"""
test_phase5b_nlp_rl.py  —  Phase 5B: NLP + RL Integration Validation
======================================================================

Verifies the BuildingEnv NLP reward-shaping logic WITHOUT requiring a
trained model.  All tests run against the raw environment reward/observation
functions using hand-crafted actions.

Test matrix
-----------
T1 : No complaint → NLP shaping = 0.0
T2 : "Make it warmer" → align bonus when agent raises setpoint
T3 : "Make it warmer" → oppose penalty when agent lowers setpoint
T4 : "Make it cooler" → align bonus when agent lowers setpoint
T5 : "Make it cooler" → oppose penalty when agent raises setpoint
T6 : High urgency > medium > low (same direction action)
T7 : target_delta proportional scaling (large delta > small delta)
T8 : Airflow constraint — increase_airflow align/oppose
T9 : Observation shape == 40
T10: Constraint signals in obs correctly reflect active constraint
T11: No constraint → obs NLP slots are neutral
T12: Constraint cleared on episode reset
T13: NLP does NOT hard-override action (action applied regardless)
T14: Safety — total reward stays reasonable during NLP + energy conflict
T15: IAQ comfort not blindly overridden (comfort reward still present)

Run with:
    python -m pytest rl/tests/test_phase5b_nlp_rl.py -v
  or:
    python rl/tests/test_phase5b_nlp_rl.py
"""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

import numpy as np

from rl.env.building_env import (
    BuildingEnv,
    _NLP_ALIGN_BONUS,
    _NLP_OPPOSE_PENALTY,
    _NLP_URGENCY_SCALE,
)

# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_env() -> BuildingEnv:
    return BuildingEnv(step_minutes=5.0)


def _zero_action(room: int, sp_sign: float = 0.0, af_sign: float = 0.0) -> np.ndarray:
    """8-element action with controlled room component. sp_sign/af_sign in [-1,1]."""
    a = np.zeros(8, dtype=np.float32)
    a[room * 2]     = sp_sign
    a[room * 2 + 1] = af_sign
    return a


def _nlp_shaping_only(env: BuildingEnv, room_id: str, room_idx: int, action: np.ndarray) -> float:
    return env._nlp_reward_shaping(room_id, room_idx, action)


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_t1_no_complaint_no_shaping():
    env = _make_env(); env.reset()
    shaping = _nlp_shaping_only(env, "A", 0, _zero_action(0, sp_sign=0.8))
    assert shaping == 0.0, f"Expected 0.0, got {shaping}"
    print("T1 PASS: no complaint → shaping = 0.0")


def test_t2_warmer_align_bonus():
    env = _make_env(); env.reset()
    env.set_nlp_constraint("A", "increase_temp", urgency="medium", target_delta=1.0)
    shaping = _nlp_shaping_only(env, "A", 0, _zero_action(0, sp_sign=+0.5))
    assert shaping > 0, f"Expected positive bonus, got {shaping}"
    print(f"T2 PASS: 'warmer' align bonus = {shaping:.4f}")


def test_t3_warmer_oppose_penalty():
    env = _make_env(); env.reset()
    env.set_nlp_constraint("A", "increase_temp", urgency="medium", target_delta=1.0)
    shaping = _nlp_shaping_only(env, "A", 0, _zero_action(0, sp_sign=-0.5))
    assert shaping < 0, f"Expected negative penalty, got {shaping}"
    print(f"T3 PASS: 'warmer' oppose penalty = {shaping:.4f}")


def test_t4_cooler_align_bonus():
    env = _make_env(); env.reset()
    env.set_nlp_constraint("B", "decrease_temp", urgency="medium", target_delta=1.0)
    shaping = _nlp_shaping_only(env, "B", 1, _zero_action(1, sp_sign=-0.5))
    assert shaping > 0, f"Expected positive bonus, got {shaping}"
    print(f"T4 PASS: 'cooler' align bonus = {shaping:.4f}")


def test_t5_cooler_oppose_penalty():
    env = _make_env(); env.reset()
    env.set_nlp_constraint("B", "decrease_temp", urgency="medium", target_delta=1.0)
    shaping = _nlp_shaping_only(env, "B", 1, _zero_action(1, sp_sign=+0.5))
    assert shaping < 0, f"Expected negative penalty, got {shaping}"
    print(f"T5 PASS: 'cooler' oppose penalty = {shaping:.4f}")


def test_t6_urgency_ordering():
    env = _make_env(); env.reset()
    action = _zero_action(0, sp_sign=+0.5)
    results = {}
    for urg in ("high", "medium", "low"):
        env.set_nlp_constraint("A", "increase_temp", urgency=urg, target_delta=1.0)
        results[urg] = _nlp_shaping_only(env, "A", 0, action)
    assert results["high"] > results["medium"] > results["low"], f"Order wrong: {results}"
    print(f"T6 PASS: high={results['high']:.4f} > medium={results['medium']:.4f} > low={results['low']:.4f}")


def test_t7_target_delta_scaling():
    env = _make_env(); env.reset()
    action = _zero_action(0, sp_sign=+0.5)
    env.set_nlp_constraint("A", "increase_temp", urgency="medium", target_delta=0.5)
    small = _nlp_shaping_only(env, "A", 0, action)
    env.set_nlp_constraint("A", "increase_temp", urgency="medium", target_delta=4.0)
    large = _nlp_shaping_only(env, "A", 0, action)
    assert large > small, f"large={large:.4f} should > small={small:.4f}"
    print(f"T7 PASS: target_delta 4.0 → {large:.4f} > 0.5 → {small:.4f}")


def test_t8_airflow_align_and_oppose():
    env = _make_env(); env.reset()
    env.set_nlp_constraint("C", "increase_airflow", urgency="medium", target_delta=30.0)
    align   = _nlp_shaping_only(env, "C", 2, _zero_action(2, af_sign=+0.8))
    oppose  = _nlp_shaping_only(env, "C", 2, _zero_action(2, af_sign=-0.8))
    assert align > 0 and oppose < 0, f"align={align:.4f}, oppose={oppose:.4f}"
    print(f"T8 PASS: airflow align={align:.4f}, oppose={oppose:.4f}")


def test_t9_obs_shape():
    env = _make_env()
    obs, _ = env.reset()
    assert obs.shape == (40,), f"Expected (40,), got {obs.shape}"
    print(f"T9 PASS: obs.shape = {obs.shape}")


def test_t10_obs_constraint_signals():
    env = _make_env(); env.reset()
    env.set_nlp_constraint("A", "increase_temp", urgency="high", target_delta=2.0)
    state = env.twin.get_state()
    obs = env._get_obs(state)
    # Room A slots 5-8 (9 vars per room, nlp signals at offsets 5,6,7,8)
    assert obs[5] == 1.0,  f"nlp_active should be 1.0, got {obs[5]}"
    assert obs[6] == 1.0,  f"constraint_dir should be +1.0, got {obs[6]}"
    assert obs[7] == 1.0,  f"urgency_encoded for 'high' should be 1.0, got {obs[7]}"
    expected_td = round((2.0 / 5.0) * 2.0 - 1.0, 4)
    assert abs(obs[8] - expected_td) < 1e-4, f"target_delta obs: expected {expected_td}, got {obs[8]}"
    print(f"T10 PASS: obs NLP signals correct (active=1.0, dir=1.0, urg=1.0, tdelta={obs[8]:.3f})")


def test_t11_obs_no_constraint_neutral():
    env = _make_env(); env.reset()
    obs = env._get_obs(env.twin.get_state())
    assert obs[5] == -1.0, f"Expected -1.0, got {obs[5]}"
    assert obs[6] ==  0.0, f"Expected  0.0, got {obs[6]}"
    print("T11 PASS: no constraint → obs NLP slots are neutral")


def test_t12_constraint_cleared_on_reset():
    env = _make_env(); env.reset()
    env.set_nlp_constraint("A", "increase_temp", urgency="high", target_delta=3.0)
    assert env._nlp_constraints["A"] is not None
    env.reset()
    assert env._nlp_constraints["A"] is None, "Constraint should be cleared after reset"
    print("T12 PASS: constraint cleared on episode reset")


def test_t13_no_hard_override():
    env = _make_env(); env.reset()
    env.set_nlp_constraint("A", "increase_temp", urgency="high", target_delta=2.0)
    sp_before = env.twin.get_state()["rooms"]["A"]["setpoint_c"]
    action = _zero_action(0, sp_sign=-1.0)   # agent OPPOSES
    env.step(action)
    sp_after = env.twin.get_state()["rooms"]["A"]["setpoint_c"]
    assert sp_after < sp_before, f"Action should still apply. Before={sp_before:.2f}, After={sp_after:.2f}"
    print(f"T13 PASS: NLP does not hard-override. Setpoint {sp_before:.2f}→{sp_after:.2f} despite 'increase_temp'")


def test_t14_reward_reasonable_range():
    env = _make_env(); env.reset()
    env.set_nlp_constraint("A", "increase_temp", urgency="high", target_delta=4.0)
    _, reward, _, _, _ = env.step(_zero_action(0, sp_sign=-1.0))
    assert -5.0 < reward < 5.0, f"Reward {reward:.4f} out of expected [-5, 5] range"
    print(f"T14 PASS: reward={reward:.4f} within reasonable bounds")


def test_t15_comfort_reward_preserved():
    env = _make_env(); env.reset()
    neutral = np.zeros(8, dtype=np.float32)
    _, reward_no_nlp, _, _, _ = env.step(neutral)

    env.reset()
    env.set_nlp_constraint("A", "increase_temp", urgency="high", target_delta=4.0)
    _, reward_with_nlp, _, _, _ = env.step(neutral)  # dead-band → nlp shaping=0

    diff = abs(reward_no_nlp - reward_with_nlp)
    assert diff < 0.01, (
        f"Comfort reward should dominate (diff={diff:.4f}). "
        f"no_nlp={reward_no_nlp:.4f}, with_nlp={reward_with_nlp:.4f}"
    )
    print(f"T15 PASS: comfort preserved (no_nlp={reward_no_nlp:.4f} ≈ with_nlp={reward_with_nlp:.4f})")


# ─── Main runner ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_t1_no_complaint_no_shaping,
        test_t2_warmer_align_bonus,
        test_t3_warmer_oppose_penalty,
        test_t4_cooler_align_bonus,
        test_t5_cooler_oppose_penalty,
        test_t6_urgency_ordering,
        test_t7_target_delta_scaling,
        test_t8_airflow_align_and_oppose,
        test_t9_obs_shape,
        test_t10_obs_constraint_signals,
        test_t11_obs_no_constraint_neutral,
        test_t12_constraint_cleared_on_reset,
        test_t13_no_hard_override,
        test_t14_reward_reasonable_range,
        test_t15_comfort_reward_preserved,
    ]

    passed = failed = 0
    print("\n" + "=" * 60)
    print("  Phase 5B — NLP + RL Integration Validation Suite")
    print("=" * 60 + "\n")
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL [{t.__name__}]: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"  Results: {passed}/{passed+failed} passed, {failed} failed")
    print("=" * 60)
    if failed:
        sys.exit(1)
