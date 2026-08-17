// App.tsx  —  Main dashboard layout.
//
// POLLING: fetchState() is called every 1000ms while the app is mounted.
//          fetchHistory() is called every 2000ms.
//          All displayed values come from these API calls — no local physics.

import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { SimulationState, HistoryPoint, RoomId } from './types';
import { fetchState, fetchHistory } from './api';

import BuildingMap from './components/BuildingMap';
import SimulationControls from './components/SimulationControls';
import SelectedRoomPanel from './components/SelectedRoomPanel';
import SensorOverridePanel from './components/SensorOverridePanel';
import EnvironmentPanel from './components/EnvironmentPanel';
import TemperatureChart from './components/TemperatureChart';
import EnergyChart from './components/EnergyChart';
import ComfortChart from './components/ComfortChart';
import NLPChatPanel from './components/NLPChatPanel';

const POLL_INTERVAL_MS = 1000;
const HISTORY_INTERVAL_MS = 2000;

const DEFAULT_STATE: SimulationState = {
  simulation_time_minutes: 0,
  running: false,
  speed: 1,
  outside_temperature_c: 34.0,
  electricity_price_per_kwh: 8.5,
  rooms: {
    A: { room_id:'A', temperature_c:23, wall_temperature_c:23, humidity_pct:50, setpoint_c:22, airflow_lps:100, occupancy:8,  hvac_power_kw:0, fan_power_kw:0, total_power_kw:0, energy_kwh:0, comfort_score:95, pmv:0 },
    B: { room_id:'B', temperature_c:27, wall_temperature_c:27, humidity_pct:62, setpoint_c:24, airflow_lps:120, occupancy:12, hvac_power_kw:0, fan_power_kw:0, total_power_kw:0, energy_kwh:0, comfort_score:75, pmv:1 },
    C: { room_id:'C', temperature_c:22, wall_temperature_c:22, humidity_pct:48, setpoint_c:22, airflow_lps:90,  occupancy:4,  hvac_power_kw:0, fan_power_kw:0, total_power_kw:0, energy_kwh:0, comfort_score:95, pmv:0 },
    D: { room_id:'D', temperature_c:25, wall_temperature_c:25, humidity_pct:55, setpoint_c:23, airflow_lps:110, occupancy:10, hvac_power_kw:0, fan_power_kw:0, total_power_kw:0, energy_kwh:0, comfort_score:88, pmv:0.5 },
  },
  building: { total_energy_kwh:0, baseline_energy_kwh:0, current_power_kw:0, average_comfort:88, estimated_cost:0 },
  rl_mode: 'manual' as const,
  rl_model_path: null,
};

export default function App() {
  const [state, setState] = useState<SimulationState>(DEFAULT_STATE);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [selectedRoom, setSelectedRoom] = useState<RoomId>('B');
  const [backendError, setBackendError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [activeTab, setActiveTab] = useState<'telemetry' | 'sensors'>('telemetry');

  const refreshState = useCallback(async () => {
    try {
      const s = await fetchState();
      setState(s);
      setBackendError(null);
      setConnected(true);
    } catch (e: any) {
      setBackendError('Cannot connect to backend. Is FastAPI running on port 8000?');
      setConnected(false);
    }
  }, []);

  const refreshHistory = useCallback(async () => {
    try {
      const h = await fetchHistory();
      setHistory(h);
    } catch { /* silent */ }
  }, []);

  // State poll
  useEffect(() => {
    refreshState();
    const id = setInterval(refreshState, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refreshState]);

  // History poll (less frequent)
  useEffect(() => {
    refreshHistory();
    const id = setInterval(refreshHistory, HISTORY_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refreshHistory]);

  const selectedRoomData = state.rooms[selectedRoom];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans selection:bg-blue-500/30">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/50 px-6 py-4 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-4">
          <div className="w-1.5 h-8 bg-blue-500 rounded-full" />
          <div>
            <h1 className="text-lg font-bold text-slate-100 tracking-tight">
              Digital Twin Simulation Engine
            </h1>
            <p className="text-xs text-slate-500 font-medium">
              Zone Control & Analytics Dashboard
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className={`text-xs font-bold px-3 py-1 rounded-md border tracking-wide uppercase ${
            connected
              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-500'
              : 'border-red-500/30 bg-red-500/10 text-red-500'
          }`}>
            {connected ? (state.running ? 'System Live' : 'System Ready') : 'System Offline'}
          </span>
          <span className="text-xs text-slate-500 font-medium">
            {state.running ? `T-Scale: ${state.speed}×` : 'T-Scale: —'}
          </span>
        </div>
      </header>

      {/* Error banner */}
      {backendError && (
        <div className="bg-red-950/50 border-b border-red-900/50 px-6 py-2.5 text-red-400 text-sm font-medium flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" /> {backendError}
        </div>
      )}

      <main className="max-w-screen-2xl mx-auto px-6 py-6 space-y-6">
        {/* Top: building map + controls */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
          {/* Left: map + environment */}
          <div className="space-y-4">
            <BuildingMap
              state={state}
              selectedRoom={selectedRoom}
              onSelect={setSelectedRoom}
            />
            <EnvironmentPanel state={state} />
            <NLPChatPanel onRefresh={refreshState} />
          </div>

          {/* Right: controls + selected room */}
          <div className="space-y-4">
            <SimulationControls
              running={state.running}
              speed={state.speed}
              outsideTemp={state.outside_temperature_c}
              electricityPrice={state.electricity_price_per_kwh}
              rlMode={state.rl_mode || 'manual'}
              onRefresh={refreshState}
            />
            {selectedRoomData && (
              <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl overflow-hidden">
                {/* Tab bar */}
                <div className="flex border-b border-white/5">
                  <button
                    onClick={() => setActiveTab('telemetry')}
                    className={`flex-1 py-2.5 text-xs font-bold uppercase tracking-widest transition-all ${
                      activeTab === 'telemetry'
                        ? 'text-sky-400 border-b-2 border-sky-400 bg-sky-500/5'
                        : 'text-slate-500 hover:text-slate-300'
                    }`}
                  >
                    📊 Room Detail
                  </button>
                  <button
                    onClick={() => setActiveTab('sensors')}
                    className={`flex-1 py-2.5 text-xs font-bold uppercase tracking-widest transition-all ${
                      activeTab === 'sensors'
                        ? 'text-amber-400 border-b-2 border-amber-400 bg-amber-500/5'
                        : 'text-slate-500 hover:text-slate-300'
                    }`}
                  >
                    ⚡ Sensors
                  </button>
                </div>
                {/* Tab content */}
                <div className="p-1">
                  {activeTab === 'telemetry' ? (
                    <SelectedRoomPanel room={selectedRoomData} onRefresh={refreshState} />
                  ) : (
                    <SensorOverridePanel room={selectedRoomData} state={state} onRefresh={refreshState} />
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <TemperatureChart history={history} roomId={selectedRoom} />
          <EnergyChart history={history} />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <ComfortChart history={history} roomId={selectedRoom} />

          {/* Quick stats for all 4 rooms */}
          <div className="bg-slate-800/60 border border-white/10 rounded-xl p-4">
            <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3">
              All Rooms — Current State
            </h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 text-xs border-b border-white/10 pb-1">
                  <th className="py-1 font-medium">Room</th>
                  <th className="py-1 font-medium">Temp</th>
                  <th className="py-1 font-medium">Setpt</th>
                  <th className="py-1 font-medium">RH%</th>
                  <th className="py-1 font-medium">HVAC</th>
                  <th className="py-1 font-medium">Cmft</th>
                </tr>
              </thead>
              <tbody>
                {(['A','B','C','D'] as RoomId[]).map((rid) => {
                  const r = state.rooms[rid];
                  if (!r) return null;
                  const comfortColor =
                    r.comfort_score >= 85 ? 'text-emerald-400' :
                    r.comfort_score >= 65 ? 'text-amber-400' : 'text-red-400';
                  return (
                    <tr
                      key={rid}
                      onClick={() => setSelectedRoom(rid)}
                      className={`cursor-pointer border-b border-white/5 hover:bg-white/5 transition-colors ${selectedRoom === rid ? 'bg-sky-500/10' : ''}`}
                    >
                      <td className="py-1.5 font-bold text-sky-400">{rid}</td>
                      <td className="py-1.5">{r.temperature_c.toFixed(1)}°</td>
                      <td className="py-1.5 text-slate-400">{r.setpoint_c.toFixed(1)}°</td>
                      <td className="py-1.5">{r.humidity_pct.toFixed(0)}%</td>
                      <td className="py-1.5">{r.hvac_power_kw.toFixed(1)} kW</td>
                      <td className={`py-1.5 font-medium ${comfortColor}`}>{r.comfort_score.toFixed(0)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </main>

      <footer className="text-center text-slate-600 text-xs py-4 border-t border-white/5">
        Digital Twin Simulation · Grey-box 1R1C model · NOT physically calibrated ·
        NOT EnergyPlus · NOT CFD · Virtual sensor data only
      </footer>
    </div>
  );
}
