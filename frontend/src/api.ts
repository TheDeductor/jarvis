// api.ts — All backend communication.  No physics logic lives here.

import axios from 'axios';
import type { HistoryPoint, SimulationState, TariffResponse, TariffSlot, OccupantFeedbackCreate, OccupantFeedbackResponse } from './types';

const BASE_URL = (import.meta.env.VITE_API_URL as string) || 'http://localhost:8001/api';

const api = axios.create({ baseURL: BASE_URL, timeout: 5000 });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Simulation state ──────────────────────────────────────────────────────────

export async function fetchState(): Promise<SimulationState> {
  const res = await api.get<SimulationState>('/simulation/state');
  return res.data;
}

export async function fetchHistory(): Promise<HistoryPoint[]> {
  const res = await api.get<{ history: HistoryPoint[] }>('/simulation/history');
  return res.data.history;
}

export async function login(username: string, password: string) {
  const formData = new URLSearchParams();
  formData.append('username', username);
  formData.append('password', password);
  const res = await api.post('/auth/token', formData, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded'
    }
  });
  return res.data;
}

// ── Simulation control ────────────────────────────────────────────────────────

export async function startSimulation() {
  await api.post('/simulation/start');
}

export async function pauseSimulation() {
  await api.post('/simulation/pause');
}

export async function resetSimulation() {
  await api.post('/simulation/reset');
}

export async function setSpeed(speed: 1 | 5 | 20) {
  await api.post('/simulation/speed', { speed });
}

// ── Room controls ─────────────────────────────────────────────────────────────

export async function setSetpoint(roomId: string, setpoint_c: number) {
  await api.post(`/rooms/${roomId}/setpoint`, { setpoint_c });
}

export async function setOccupancy(roomId: string, occupancy: number) {
  await api.post(`/rooms/${roomId}/occupancy`, { occupancy });
}

export async function setAirflow(roomId: string, airflow_lps: number) {
  await api.post(`/rooms/${roomId}/airflow`, { airflow_lps });
}

export async function setHumiditySetpoint(roomId: string, humidity_target_pct: number) {
  await api.post(`/rooms/${roomId}/humidity-setpoint`, { humidity_target_pct });
}

// ── Environment ───────────────────────────────────────────────────────────────

export async function setOutsideTemperature(temperature_c: number) {
  await api.post('/environment/outside-temperature', { temperature_c });
}

export async function setElectricityPrice(price_per_kwh: number) {
  await api.post('/environment/electricity-price', { price_per_kwh });
}

// ── Hardware sensor overrides ──────────────────────────────────────────────────

export interface RoomSensorData {
  temperature_c?:      number;
  wall_temperature_c?: number;
  humidity_pct?:       number;
  occupancy?:          number;
  airflow_lps?:        number;
  hvac_power_kw?:      number;
}

export interface OutsideSensorData {
  temperature_c?: number;
  humidity_pct?:  number;
}

export async function injectRoomSensorData(roomId: string, data: RoomSensorData) {
  // Strip undefined keys so backend sees only fields we're actually sending
  const payload = Object.fromEntries(
    Object.entries(data).filter(([, v]) => v !== undefined && v !== null)
  );
  await api.post(`/rooms/${roomId}/sensor-data`, payload);
}

export async function injectOutsideSensorData(data: OutsideSensorData) {
  const payload = Object.fromEntries(
    Object.entries(data).filter(([, v]) => v !== undefined && v !== null)
  );
  await api.post('/environment/sensor-data', payload);
}

// ── RL Auto Mode ───────────────────────────────────────────────────────────────

export async function setRlMode(mode: 'manual' | 'auto', modelPath?: string) {
  await api.post('/rl/mode', { mode, model_path: modelPath ?? null });
}

// ── NLP Chat ───────────────────────────────────────────────────────────────────

export async function submitFeedback(complaint: string): Promise<any> {
  const res = await api.post('/chat/message', { message: complaint });
  return res.data;
}

// ── P6 — Tariff & Force Peak ──────────────────────────────────────────────────

export async function fetchTariff(): Promise<TariffResponse> {
  const res = await api.get<TariffResponse>('/environment/tariff');
  return res.data;
}

export async function setTariff(slots: TariffSlot[]): Promise<TariffResponse> {
  const res = await api.post<TariffResponse>('/environment/tariff', { slots });
  return res.data;
}

export async function forcePeak(): Promise<void> {
  await api.post('/environment/force-peak');
}

export async function submitOccupantFeedback(data: OccupantFeedbackCreate): Promise<OccupantFeedbackResponse> {
  const res = await api.post<OccupantFeedbackResponse>('/occupant-feedback', data);
  return res.data;
}

