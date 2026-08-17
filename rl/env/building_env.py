import gymnasium as gym
from gymnasium import spaces
import numpy as np
import math
import sys
import os

# Add JARVIS root to path so we can import backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from backend.digital_twin import BuildingTwin

class BuildingEnv(gym.Env):
    """
    Gymnasium wrapper for the JARVIS BuildingTwin.
    Allows RL agents (like PPO) to interact with the HVAC digital twin.
    """
    
    def __init__(self, step_minutes: float = 5.0):
        super().__init__()
        
        self.step_minutes = step_minutes
        self.twin = BuildingTwin(step_minutes=self.step_minutes)
        self.room_ids = ["A", "B", "C", "D"]
        
        # ── ACTION SPACE ──
        # For each room (A, B, C, D), we output 2 continuous values in [-1, 1]:
        # 1. Setpoint Delta: mapped to [-2.0, +2.0] °C
        # 2. Airflow Delta:  mapped to [-20.0, +20.0] L/s
        # Total 8 actions.
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(8,), dtype=np.float32)
        
        # ── OBSERVATION SPACE ──
        # Per room (4 rooms * 5 variables = 20 values):
        # [temperature_c, humidity_pct, setpoint_c, occupancy, hvac_power_kw]
        # Global (3 values):
        # [outside_temperature_c, time_sin, time_cos]
        # Total = 23 values. All normalized to [-1, 1].
        self.observation_space = spaces.Box(low=-1.0, high=1.0, shape=(23,), dtype=np.float32)
        
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
        
        # Reset the underlying physics twin
        self.twin.reset()
        
        # Optionally randomize starting states here (Domain Randomization)
        # e.g., randomize outside_temp or initial room temperatures
        
        state = self.twin.get_state()
        obs = self._get_obs(state)
        
        info = {}
        return obs, info
        
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
            # [temperature, humidity, setpoint, occupancy, hvac_power]
            obs.append(norm(r["temperature_c"], 10.0, 40.0))
            obs.append(norm(r["humidity_pct"], 0.0, 100.0))
            obs.append(norm(r["setpoint_c"], 16.0, 30.0))
            obs.append(norm(r["occupancy"], 0, 50))
            # hvac_power is signed (-10 for cooling, +10 for heating)
            obs.append(norm(r["hvac_power_kw"], -10.0, 10.0))
            
        # Global stats
        obs.append(norm(state["outside_temperature_c"], -10.0, 50.0))
        
        # Time of day (cyclical)
        time_mins = state["simulation_time_minutes"]
        time_hours = (time_mins / 60.0) % 24.0
        time_rads = (time_hours / 24.0) * 2 * math.pi
        obs.append(math.sin(time_rads))  # already in [-1, 1]
        obs.append(math.cos(time_rads))  # already in [-1, 1]
        
        return np.array(obs, dtype=np.float32)

    def _get_reward(self, state: dict, current_action: np.ndarray = None) -> float:
        """
        Multi-objective reward: Maximize comfort, minimize energy, with reward shaping.
        """
        rooms = state["rooms"]
        
        total_comfort = 0.0
        total_power = 0.0
        
        # Reward shaping accumulators
        setpoint_penalty = 0.0
        oscillation_penalty = 0.0
        vacancy_bonus = 0.0
        
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
        
        return float(reward)
