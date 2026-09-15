// types.ts — TypeScript types matching the FastAPI response models.
// Updated for 2R1C model: wall_temperature_c (mass node) and pmv (Fanger).
// P5: Added ConstraintRecord lifecycle types.

export interface RoomState {
  room_id: string;
  active_constraint?: string;
  temperature_c: number;
  wall_temperature_c: number;  // 2R1C: structural mass temperature [°C]
  humidity_pct: number;
  humidity_target_pct: number;   // target RH% for dehumidifier control
  humidity_status: 'comfortable' | 'too_humid' | 'too_dry';  // comfort band
  dehumidifier_power_kw: number; // active dehumidification power draw [kW]
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
  current_price?: number;
  cost_today?: number;
  baseline_cost_today?: number;
  peak_kw_15min?: number;
  baseline_average_comfort?: number;
  price_response_active?: boolean;
  is_peak?: boolean;
  is_pre_peak?: boolean;
}

// ── P5 — Constraint lifecycle ─────────────────────────────────────────────────

/** Status progression: active → resolved | renewed → escalated */
export type ConstraintStatus = 'active' | 'resolved' | 'renewed' | 'escalated';

export interface ConstraintRecord {
  id: string;
  room: string;
  action: string;
  source: 'nlp' | 'iaq_rule' | string;
  urgency: string;
  status: ConstraintStatus;
  created_at: number;            // simulation minutes
  expires_at: number;
  resolved_at: number | null;
  resolution_mins: number | null;
  llm_raw_delta: number;
  applied_delta: number;         // physics-derived delta (§2.3)
  renewals: number;
}

export interface ConstraintStats {
  by_status: Record<string, number>;
  median_resolution_minutes: number | null;
  total: number;
}

export interface ConstraintList {
  constraints: ConstraintRecord[];
  stats: ConstraintStats;
}

// ── State + history ───────────────────────────────────────────────────────────

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
  constraints?: ConstraintRecord[];  // P5: active + recent lifecycle list
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
  cost?: number;
  baseline_cost?: number;
  peak_kw_15min?: number;
  baseline_average_comfort?: number;
  electricity_price?: number;
  is_peak?: boolean;
  is_pre_peak?: boolean;
}

// ── P6 — TOU Tariff interfaces ────────────────────────────────────────────────

export interface TariffSlot {
  from_h: number;
  to_h: number;
  price: number;
  is_peak?: boolean;
}

export interface TariffResponse {
  slots: TariffSlot[];
  current_price: number;
  is_peak: boolean;
  is_pre_peak: boolean;
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
