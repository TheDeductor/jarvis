import gymnasium as gym
from gymnasium import spaces
import numpy as np
import math
import sys
import os

# Add JARVIS root to path so we can import backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from backend.digital_twin import BuildingTwin

# ── Phase 5: NLP Constraint → Reward coupling ────────────────────────────────
# Maps active NLP constraint actions to the required DIRECTION of setpoint/airflow
# change in the RL action space.  When the agent’s action OPPOSES this direction,
# a penalty is applied per step.  When it ALIGNS, a bonus is given, encouraging
# organic policy adaptation rather than a hard supervisory override.
#
# sign convention: +1 = agent should INCREASE the quantity, -1 = DECREASE.
_NLP_SETPOINT_DIRECTION: dict[str, float] = {
    "increase_temp":  +1.0,   # occupant feels cold   → raise setpoint
    "decrease_temp":  -1.0,   # occupant feels hot    → lower setpoint
}
_NLP_AIRFLOW_DIRECTION: dict[str, float] = {
    "increase_airflow": +1.0,  # stuffy / high CO2    → more airflow
    "decrease_airflow": -1.0,  # drafty / too windy   → less airflow
}
# Urgency → numeric encoding (for observation vector) and scale
_NLP_URGENCY_ENCODE: dict[str, float] = {"high": 1.0, "medium": 0.5, "low": 0.0}
_NLP_URGENCY_SCALE:  dict[str, float] = {"high": 1.5, "medium": 1.0, "low": 0.5}
# Reward shaping magnitudes (tunable hyperparameters)
_NLP_OPPOSE_PENALTY: float = -0.15   # per-step penalty for opposing an active constraint
_NLP_ALIGN_BONUS:    float =  0.08   # per-step bonus   for aligning  with an active constraint
# ─────────────────────────────────────────────────────────────────────────────


class BuildingEnv(gym.Env):
    """
    Gymnasium wrapper for the JARVIS BuildingTwin.
    Allows RL agents (like PPO) to interact with the HVAC digital twin.

    Phase 5 – NLP+RL Deep Integration
    ----------------------------------
    Active NLP constraints (parsed from occupant complaints) are injected into
    the reward function at every step via `_nlp_reward_shaping()`.  This means:
      • The agent is penalised when it moves the setpoint/airflow AGAINST the
        direction requested by the NLP constraint (e.g. cooling a room that an
        occupant reported as too cold).
      • The agent earns a small bonus when it acts IN alignment with the constraint.
      • Constraint information is visible in the observation (nlp_active flag per
        room — added in Phase 4), so the policy can learn to condition on it.
    """
    
    def __init__(self, step_minutes: float = 5.0):
        super().__init__()
        
        self.step_minutes = step_minutes
        self.twin = BuildingTwin(step_minutes=self.step_minutes)
        self.room_ids = ["A", "B", "C", "D"]

        # ── Phase 5: in-episode NLP constraint tracking ───────────────────────
        # Stores the CURRENT active constraint per room.  The environment owner
        # (training script or SimulationManager) can inject constraints at any
        # step via set_nlp_constraint().  The reward function reads this dict.
        # Schema per room:
        #   {
        #     "action":       str,   # e.g. "increase_temp"
        #     "urgency":      str,   # "high" | "medium" | "low"
        #     "target_delta": float, # magnitude requested by NLP (e.g. 2.0 °C)
        #     "active":       bool,  # True while constraint is enforced
        #   } | None
        self._nlp_constraints: dict[str, dict | None] = {
            rid: None for rid in ["A", "B", "C", "D"]
        }
        
        # ── ACTION SPACE ──
        # For each room (A, B, C, D), we output 2 continuous values in [-1, 1]:
        # 1. Setpoint Delta: mapped to [-2.0, +2.0] °C
        # 2. Airflow Delta:  mapped to [-20.0, +20.0] L/s
        # Total 8 actions.
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(8,), dtype=np.float32)
        
        # ── OBSERVATION SPACE ──
        # Per room (4 rooms * 9 variables = 36 values):
        #   [temperature_c, humidity_pct, setpoint_c, occupancy, hvac_power_kw,
        #    nlp_active, constraint_direction, urgency_encoded, target_delta]
        # Global (4 values):
        #   [outside_temperature_c, electricity_price, time_sin, time_cos]
        # Total = 40 values. All normalized to [-1, 1].
        self.observation_space = spaces.Box(low=-1.0, high=1.0, shape=(40,), dtype=np.float32)
        
        # Max limits for reward calculation and normalization
        self.max_hvac_total = 10.0 * 4  # 10kW per room max
        
        # Tracking simulation time for max episodes (1 day = 24 hours * 60 / 5 = 288 steps)
        self.current_step = 0
        self.max_steps = 288
        
        # Track previous actions to penalize oscillations
        # Array of 4 floats, storing the previous setpoint_delta for each room
        self.prev_setpoint_deltas = np.zeros(4, dtype=np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.current_step = 0
        self.prev_setpoint_deltas = np.zeros(4, dtype=np.float32)
        # Clear NLP constraints on episode reset
        self._nlp_constraints = {rid: None for rid in self.room_ids}
        
        # Reset the underlying physics twin
        self.twin.reset()
        
        # Optionally randomize starting states here (Domain Randomization)
        # e.g., randomize outside_temp or initial room temperatures
        
        state = self.twin.get_state()
        obs = self._get_obs(state)
        
        info = {}
        return obs, info

    def set_nlp_constraint(
        self,
        room_id: str,
        action: str,
        urgency: str = "medium",
        target_delta: float = 0.0,
    ) -> None:
        """
        Phase 5 — Inject an active NLP constraint into the reward + observation.

        Call this from SimulationManager whenever the NLP engine parses a new
        occupant complaint.  The constraint persists until explicitly cleared
        (action="none") or episode reset.

        Parameters
        ----------
        room_id : str
            One of "A", "B", "C", "D".
        action : str
            NLP-parsed action string, e.g. "increase_temp", "decrease_airflow".
            Pass "none" to clear the constraint for this room.
        urgency : str
            "high" | "medium" | "low".  Scales penalty/bonus magnitude.
        target_delta : float
            Magnitude requested by NLP (e.g. 2.0 for a 2°C warming request).
            Used for proportional penalty scaling.
        """
        if room_id not in self._nlp_constraints:
            return
        if action == "none":
            self._nlp_constraints[room_id] = None
        else:
            self._nlp_constraints[room_id] = {
                "action":       action,
                "urgency":      urgency,
                "target_delta": float(target_delta),
                "active":       True,
            }
        
    def step(self, action: np.ndarray):
        """
        Apply actions, step physics engine, return observation and reward.
        """
        # 1. Decode actions and apply to twin
        # Action array: [A_setp, A_flow, B_setp, B_flow, C_setp, C_flow, D_setp, D_flow]
        state = self.twin.get_state()
        rooms = state["rooms"]
        
        for i, room_id in enumerate(self.room_ids):
            setpoint_delta_norm = action[i * 2]
            airflow_delta_norm = action[i * 2 + 1]
            
            # Map [-1, 1] to physical changes
            real_setpoint_delta = setpoint_delta_norm * 2.0  # max ±2°C change per 5 min
            real_airflow_delta = airflow_delta_norm * 20.0   # max ±20 L/s change per 5 min
            
            current_setpoint = rooms[room_id]["setpoint_c"]
            current_airflow = rooms[room_id]["airflow_lps"]
            
            new_setpoint = current_setpoint + real_setpoint_delta
            new_airflow = current_airflow + real_airflow_delta
            
            # Apply to twin
            self.twin.set_setpoint(room_id, new_setpoint)
            self.twin.set_airflow(room_id, new_airflow)
            
        # 2. Advance physics by one step
        self.twin.step()
        self.current_step += 1
        
        # 3. Get new state and calculate reward
        new_state = self.twin.get_state()
        obs = self._get_obs(new_state)
        
        # Pass current action for oscillation tracking/penalties
        reward = self._get_reward(new_state, action)
        
        # 4. Check if done (end of episode)
        terminated = False
        truncated = self.current_step >= self.max_steps
        
        # 5. Save action for next step's oscillation check
        for i in range(4):
            self.prev_setpoint_deltas[i] = action[i * 2]
            
        info = {}
        return obs, reward, terminated, truncated, info

    def _get_obs(self, state: dict) -> np.ndarray:
        """
        Extract variables from state and normalize to [-1, 1].

        Per-room signals (9 per room = 36 total):
          [temperature_c, humidity_pct, setpoint_c, occupancy, hvac_power_kw,
           nlp_active, constraint_direction, urgency_encoded, target_delta]
        Global (4):
          [outside_temperature_c, electricity_price, time_sin, time_cos]
        Total = 40.
        """
        obs = []
        
        # Normalization helpers
        def norm(val, min_val, max_val):
            # map [min, max] to [-1, 1]
            clipped = max(min_val, min(max_val, val))
            return 2.0 * ((clipped - min_val) / (max_val - min_val)) - 1.0
            
        rooms = state["rooms"]
        for room_id in self.room_ids:
            r = rooms[room_id]
            # 1-5: physics state
            obs.append(norm(r["temperature_c"], 10.0, 40.0))
            obs.append(norm(r["humidity_pct"], 0.0, 100.0))
            obs.append(norm(r["setpoint_c"], 16.0, 30.0))
            obs.append(norm(r["occupancy"], 0, 50))
            obs.append(norm(r["hvac_power_kw"], -10.0, 10.0))

            # 6-9: NLP constraint signals (Phase 5)
            c = self._nlp_constraints.get(room_id)
            if c and c.get("active", False):
                act = c["action"]
                # constraint_active: +1 if active, -1 if not
                obs.append(1.0)
                # constraint_direction: +1 raise, -1 lower, 0 airflow/other (encoded as 0.0)
                if act in _NLP_SETPOINT_DIRECTION:
                    obs.append(_NLP_SETPOINT_DIRECTION[act])          # already in [-1, 1]
                elif act in _NLP_AIRFLOW_DIRECTION:
                    obs.append(_NLP_AIRFLOW_DIRECTION[act])
                else:
                    obs.append(0.0)
                # urgency_encoded: high=1.0, medium=0.5 (mapped from 0-1 → already in [-1,1] via norm)
                obs.append(_NLP_URGENCY_ENCODE.get(c.get("urgency", "medium"), 0.5) * 2.0 - 1.0)
                # target_delta: NLP requested magnitude, normalized to [-1,1] over [0, 5°C max]
                obs.append(norm(c.get("target_delta", 0.0), 0.0, 5.0))
            else:
                # no active constraint — emit neutral values
                obs.extend([-1.0, 0.0, -1.0, -1.0])
            
        # Global stats
        obs.append(norm(state["outside_temperature_c"], -10.0, 50.0))
        # Handle different keys for electricity price between BuildingTwin and SimulationManager
        price = state.get("electricity_price_per_kwh", state.get("current_price", 8.5))
        obs.append(norm(price, 0.0, 20.0))
        
        # Time of day (cyclical)
        time_mins = state["simulation_time_minutes"]
        time_hours = (time_mins / 60.0) % 24.0
        time_rads = (time_hours / 24.0) * 2 * math.pi
        obs.append(math.sin(time_rads))  # already in [-1, 1]
        obs.append(math.cos(time_rads))  # already in [-1, 1]
        
        return np.array(obs, dtype=np.float32)

    def _nlp_reward_shaping(self, room_id: str, room_index: int, current_action: np.ndarray) -> float:
        """
        Phase 5 — NLP constraint → per-room reward shaping.

        For thermal constraints: reads the setpoint action component.
        For airflow constraints: reads the airflow action component.
        Scales by urgency AND by target_delta (larger requested change = stronger signal).
        Safety guard: does NOT override IAQ / comfort clamps; just shifts the reward signal.
        """
        constraint = self._nlp_constraints.get(room_id)
        if constraint is None or not constraint.get("active", False) or current_action is None:
            return 0.0

        action       = constraint["action"]
        urgency      = constraint.get("urgency", "medium")
        target_delta = max(0.0, constraint.get("target_delta", 1.0))

        urgency_scale = _NLP_URGENCY_SCALE.get(urgency, 1.0)
        # Proportional boost when target_delta is large: cap at 2× base
        delta_scale   = min(1.0 + target_delta / 4.0, 2.0)
        total_scale   = urgency_scale * delta_scale

        def _evaluate(agent_delta: float, required_sign: float) -> float:
            if abs(agent_delta) < 0.05:
                return 0.0   # dead-band: ignore tiny twitches
            if (agent_delta * required_sign) > 0:
                return _NLP_ALIGN_BONUS   * total_scale
            else:
                return _NLP_OPPOSE_PENALTY * total_scale

        if action in _NLP_SETPOINT_DIRECTION:
            return _evaluate(float(current_action[room_index * 2]),
                             _NLP_SETPOINT_DIRECTION[action])
        elif action in _NLP_AIRFLOW_DIRECTION:
            return _evaluate(float(current_action[room_index * 2 + 1]),
                             _NLP_AIRFLOW_DIRECTION[action])
        return 0.0

    def _get_reward(self, state: dict, current_action: np.ndarray = None) -> float:
        """
        Multi-objective reward: Maximize comfort, minimize energy, with reward shaping.

        Phase 5 additions
        -----------------
        NLP constraint shaping is added per room via _nlp_reward_shaping().
        When an NLP constraint is active for a room:
          • The agent is penalised for acting AGAINST the constraint direction.
          • The agent earns a bonus for acting WITH the constraint direction.
        This forces the RL policy to organically adapt to occupant feedback
        without requiring a hard supervisory override of the action.
        """
        rooms = state["rooms"]
        
        total_comfort = 0.0
        total_power = 0.0
        
        # Reward shaping accumulators
        setpoint_penalty = 0.0
        oscillation_penalty = 0.0
        vacancy_bonus = 0.0
        nlp_shaping = 0.0  # Phase 5: NLP constraint reward signal
        
        for i, room_id in enumerate(self.room_ids):
            r = rooms[room_id]
            comfort = r["comfort_score"]
            power = abs(r["hvac_power_kw"]) + r["fan_power_kw"]
            
            total_comfort += comfort
            total_power += power
            
            # --- 1. Setpoint Penalty ---
            # Discourage extreme setpoints (outside 18-27°C)
            sp = r["setpoint_c"]
            if sp < 18.0:
                setpoint_penalty -= (18.0 - sp) * 0.05
            elif sp > 27.0:
                setpoint_penalty -= (sp - 27.0) * 0.05
                
            # --- 2. Oscillation Penalty ---
            # Punish if the agent reverses direction of the setpoint immediately
            if current_action is not None:
                current_delta = current_action[i * 2]
                prev_delta = self.prev_setpoint_deltas[i]
                
                # If signs are strictly opposite and the changes are significant
                if (current_delta * prev_delta) < 0 and abs(current_delta) > 0.1 and abs(prev_delta) > 0.1:
                    oscillation_penalty -= 0.02
                    
            # --- 3. Vacancy Bonus ---
            # If room is empty, we don't care about comfort, we only want to save energy.
            if r["occupancy"] == 0:
                # If power is near zero, reward the agent
                if power < 0.5:
                    vacancy_bonus += 0.05
                # Furthermore, penalize high power in empty rooms more strictly
                # (We just subtract a bit extra proportional to power)
                energy_waste = power / 10.0
                vacancy_bonus -= energy_waste * 0.05

            # --- 4. Phase 5: NLP constraint alignment shaping (per room) ---
            nlp_shaping += self._nlp_reward_shaping(room_id, i, current_action)
            
        # Average comfort score [0, 100] mapped to [0, 1]
        avg_comfort = (total_comfort / 4.0) / 100.0
        
        # Power penalty mapped to [0, -1]
        max_power = 40.0
        energy_penalty = -min(total_power / max_power, 1.0)
        
        # --- Multi-objective balancing (Lambda tuning) ---
        lambda_comfort = 0.75
        lambda_energy  = 0.25
        
        # Base reward
        reward = (lambda_comfort * avg_comfort) + (lambda_energy * energy_penalty)
        
        # Add shaping terms
        reward += setpoint_penalty
        reward += oscillation_penalty
        reward += vacancy_bonus
        reward += nlp_shaping  # Phase 5: NLP-driven reward shaping
        
        return float(reward)
