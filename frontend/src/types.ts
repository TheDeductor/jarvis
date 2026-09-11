// types.ts — TypeScript types matching the FastAPI response models.
// Updated for 2R1C model: wall_temperature_c (mass node) and pmv (Fanger).

export interface RoomState {
  room_id: string;
  active_constraint?: string;
  temperature_c: number;
  wall_temperature_c: number;  // 2R1C: structural mass temperature [°C]
  humidity_pct: number;
  setpoint_c: number;
  airflow_lps: number;
  occupancy: number;
  hvac_power_kw: number;
  fan_power_kw: number;
  total_power_kw: number;
  energy_kwh: number;
  comfort_score: number;
  pmv: number;                 // Fanger PMV: -3 (cold) to +3 (hot)
  co2_ppm: number;             // indoor CO2 concentration [ppm]
  iaq_score: number;           // 0-100 IAQ sub-score (CO2-based)
  overall_comfort_score: number; // 0-100 blend: 0.7*comfort + 0.3*IAQ
}

export interface BuildingSummary {
  total_energy_kwh: number;
  baseline_energy_kwh: number;
  current_power_kw: number;
  average_comfort: number;
  estimated_cost: number;
}

export interface SimulationState {
  simulation_time_minutes: number;
  running: boolean;
  speed: number;
  outside_temperature_c: number;
  electricity_price_per_kwh: number;
  rl_mode: 'manual' | 'auto';
  rl_model_path: string | null;
  rooms: Record<string, RoomState>;
  building: BuildingSummary;
}

export interface HistoryPoint {
  simulation_time_minutes: number;
  rooms: Record<string, {
    temperature_c: number;
    wall_temperature_c: number;
    setpoint_c: number;
    comfort_score: number;
    pmv: number;
    energy_kwh: number;
    hvac_power_kw: number;
    humidity_pct: number;
    co2_ppm: number;
  }>;
  total_energy_kwh: number;
  baseline_energy_kwh: number;
}

export type RoomId = 'A' | 'B' | 'C' | 'D';
export type SpeedOption = 1 | 5 | 20;

export interface FeedbackConstraint {
  room_id: string | null;
  action: string;
  urgency: string;
  setpoint_delta_c: number;
  rationale: string;
  confidence: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  timestamp: Date;
  constraint?: FeedbackConstraint;
  action_taken?: string;
  error?: boolean;
}
