// api.ts — All backend communication.  No physics logic lives here.

import axios from 'axios';
import type { HistoryPoint, SimulationState } from './types';

const BASE_URL = 'http://localhost:8000/api';

const api = axios.create({ baseURL: BASE_URL, timeout: 5000 });

// ── Simulation state ──────────────────────────────────────────────────────────

export async function fetchState(): Promise<SimulationState> {
  const res = await api.get<SimulationState>('/simulation/state');
  return res.data;
}

export async function fetchHistory(): Promise<HistoryPoint[]> {
  const res = await api.get<{ history: HistoryPoint[] }>('/simulation/history');
  return res.data.history;
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

// ── Environment ───────────────────────────────────────────────────────────────

export async function setOutsideTemperature(temperature_c: number) {
  await api.post('/environment/outside-temperature', { temperature_c });
}

export async function setElectricityPrice(price_per_kwh: number) {
  await api.post('/environment/electricity-price', { price_per_kwh });
}
