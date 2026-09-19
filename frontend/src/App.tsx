// App.tsx  —  Main dashboard layout.
//
// POLLING: fetchState() is called every 1000ms while the app is mounted.
//          fetchHistory() is called every 2000ms.
//          All displayed values come from these API calls — no local physics.

import React, { useState, useEffect, useCallback } from 'react';

import type { SimulationState, HistoryPoint, RoomId } from './types';
import { fetchState, fetchHistory } from './api';
import { BarChart3, Sliders, Zap } from 'lucide-react';

import BuildingMap from './components/BuildingMap';
import BuildingScene3D from './components/BuildingScene3D';
import SimulationControls from './components/SimulationControls';
import SelectedRoomPanel from './components/SelectedRoomPanel';
import SensorOverridePanel from './components/SensorOverridePanel';
import EnvironmentPanel from './components/EnvironmentPanel';
import TemperatureChart from './components/TemperatureChart';
import EnergyChart from './components/EnergyChart';
import ComfortChart from './components/ComfortChart';
import NLPChatPanel from './components/NLPChatPanel';
import DemoMacros from './components/DemoMacros';
import LoginScreen from './components/LoginScreen';
import OccupantView from './components/OccupantView';

const POLL_INTERVAL_MS = 1000;
const HISTORY_INTERVAL_MS = 2000;

const DEFAULT_STATE: SimulationState = {
  simulation_time_minutes: 0,
  running: false,
  speed: 1,
  outside_temperature_c: 34.0,
  electricity_price_per_kwh: 8.5,
  rooms: {
    A: { room_id:'A', temperature_c:23, wall_temperature_c:23, humidity_pct:50, humidity_target_pct:50, humidity_status:'comfortable', dehumidifier_power_kw:0, setpoint_c:22, airflow_lps:100, occupancy:8,  hvac_power_kw:0, fan_power_kw:0, total_power_kw:0, energy_kwh:0, comfort_score:95, pmv:0,   co2_ppm:450, iaq_score:100, overall_comfort_score:96.5 },
    B: { room_id:'B', temperature_c:27, wall_temperature_c:27, humidity_pct:62, humidity_target_pct:50, humidity_status:'comfortable', dehumidifier_power_kw:0, setpoint_c:24, airflow_lps:120, occupancy:12, hvac_power_kw:0, fan_power_kw:0, total_power_kw:0, energy_kwh:0, comfort_score:75, pmv:1,   co2_ppm:450, iaq_score:100, overall_comfort_score:82.5 },
    C: { room_id:'C', temperature_c:22, wall_temperature_c:22, humidity_pct:48, humidity_target_pct:50, humidity_status:'comfortable', dehumidifier_power_kw:0, setpoint_c:22, airflow_lps:90,  occupancy:4,  hvac_power_kw:0, fan_power_kw:0, total_power_kw:0, energy_kwh:0, comfort_score:95, pmv:0,   co2_ppm:450, iaq_score:100, overall_comfort_score:96.5 },
    D: { room_id:'D', temperature_c:25, wall_temperature_c:25, humidity_pct:55, humidity_target_pct:50, humidity_status:'comfortable', dehumidifier_power_kw:0, setpoint_c:23, airflow_lps:110, occupancy:10, hvac_power_kw:0, fan_power_kw:0, total_power_kw:0, energy_kwh:0, comfort_score:88, pmv:0.5, co2_ppm:450, iaq_score:100, overall_comfort_score:91.6 },
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
  // Start in 2D if the stored token is the demo token (avoids a flash of 3D on first paint)
  const storedToken = localStorage.getItem('access_token');
  const [viewMode, setViewMode] = useState<'2d' | '3d'>(storedToken === 'demo' ? '2d' : '3d');

  
  const [authToken, setAuthToken] = useState<string | null>(localStorage.getItem('access_token'));
  const [userRole, setUserRole] = useState<string | null>(localStorage.getItem('user_role'));
  const [userRoom, setUserRoom] = useState<string | null>(localStorage.getItem('user_room'));

  const handleLogin = (token: string, role: string, room: string | null) => {
    localStorage.setItem('access_token', token);
    localStorage.setItem('user_role', role);
    if (room) localStorage.setItem('user_room', room);
    setAuthToken(token);
    setUserRole(role);
    setUserRoom(room);
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user_role');
    localStorage.removeItem('user_room');
    setAuthToken(null);
    setUserRole(null);
    setUserRoom(null);
  };

  const enterDemo = () => {
    setAuthToken('demo');
    setUserRole('admin');
    setUserRoom(null);
  };

  // Force demo mode if no auth token is present, since we bypassed login
  const isDemoMode = authToken === 'demo' || !authToken;

  // In demo mode stay on safe 2D view — no GLTF loading that could crash
  useEffect(() => { if (isDemoMode) setViewMode('2d'); }, [isDemoMode]);

  const refreshState = useCallback(async () => {
    if (isDemoMode) return;
    try {
      const s = await fetchState();
      // Guard against Netlify SPA returning index.html as a 200 OK string
      if (!s || typeof s !== 'object' || !('rooms' in s)) throw new Error('Invalid API response');
      setState(s as SimulationState);
      setBackendError(null);
      setConnected(true);
    } catch (e: any) {
      setBackendError('Cannot connect to backend. Is FastAPI running on port 8000?');
      setConnected(false);
    }
  }, [isDemoMode]);

  const refreshHistory = useCallback(async () => {
    if (isDemoMode) return;
    try {
      const h = await fetchHistory();
      if (!Array.isArray(h)) throw new Error('Invalid API response');
      setHistory(h);
    } catch { /* silent */ }
  }, [isDemoMode]);

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

  // Request Geolocation and send to backend
  useEffect(() => {
    if (isDemoMode) return;
    const apiBase = (import.meta.env.VITE_API_URL as string) || 'http://127.0.0.1:8001/api';
    if ("geolocation" in navigator) {
      navigator.geolocation.getCurrentPosition(async (position) => {
        try {
          await fetch(`${apiBase}/simulation/weather-location`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              lat: position.coords.latitude,
              lon: position.coords.longitude
            })
          });
          console.log("Geolocation sent to backend for live weather updates.");
        } catch (e) {
          console.error("Failed to send geolocation to backend", e);
        }
      }, (error) => {
        console.warn("Geolocation permission denied or error:", error.message);
      });
    }
  }, [isDemoMode]);

  const selectedRoomData = state.rooms[selectedRoom];

  // Temporarily bypass login screen so Netlify is always visible
  // if (!authToken) {
  //   return <LoginScreen onLogin={handleLogin} onDemo={enterDemo} />;
  // }

  if (userRole === 'Occupant' && userRoom) {
    return (
      <div className="min-h-screen bg-[#070d18] text-slate-100 font-sans selection:bg-blue-500/30 flex flex-col">
        <header className="border-b border-slate-800 bg-[#0c1424]/90 backdrop-blur-md px-6 py-4 flex items-center justify-between shadow-sm sticky top-0 z-40">
          <div className="flex items-center gap-4">
            <div className="w-1.5 h-8 bg-blue-500 rounded-full shadow-sm shadow-blue-500/50" />
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight">
                Digital Twin Simulation Engine
              </h1>
              <p className="text-xs text-slate-300 font-medium">
                Occupant Portal
              </p>
            </div>
          </div>
          <button 
            onClick={handleLogout}
            className="text-xs font-bold px-3 py-1 rounded-md border tracking-wide uppercase border-slate-500/40 bg-slate-500/15 text-slate-300 hover:bg-slate-500/30 transition-colors"
          >
            Logout
          </button>
        </header>
        <OccupantView state={state} userRoom={userRoom} onRefresh={refreshState} />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#070d18] text-slate-100 font-sans selection:bg-blue-500/30">
      {/* Header */}
      <header className="border-b border-slate-800 bg-[#0c1424]/90 backdrop-blur-md px-6 py-4 flex items-center justify-between shadow-sm sticky top-0 z-40">
        <div className="flex items-center gap-4">
          <div className="w-1.5 h-8 bg-blue-500 rounded-full shadow-sm shadow-blue-500/50" />
          <div>
            <h1 className="text-lg font-bold text-white tracking-tight">
              Digital Twin Simulation Engine
            </h1>
            <p className="text-xs text-slate-300 font-medium">
              Zone Control & Analytics Dashboard
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {state.building?.price_response_active && (
            <span className="text-xs font-bold px-3 py-1 rounded-md border tracking-wide uppercase border-amber-500/40 bg-amber-500/15 text-amber-300 flex items-center gap-1.5 animate-pulse">
              <Zap size={13} className="text-amber-300" />
              Price Response Active
            </span>
          )}
          <span className={`text-xs font-bold px-3 py-1 rounded-md border tracking-wide uppercase flex items-center gap-1.5 ${
            connected
              ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300'
              : 'border-rose-500/40 bg-rose-500/15 text-rose-300'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${connected ? (state.running ? 'bg-emerald-400 animate-ping' : 'bg-emerald-400') : 'bg-rose-400'}`} />
            {connected ? (state.running ? 'System Live' : 'System Ready') : 'System Offline'}
          </span>
          <span className="text-xs text-slate-300 font-medium px-2 py-1 rounded bg-slate-800/60 border border-slate-700/50">
            {state.running ? `T-Scale: ${state.speed}×` : 'T-Scale: —'}
          </span>
          <button 
            onClick={handleLogout}
            className="text-xs font-bold px-3 py-1 rounded-md border tracking-wide uppercase border-slate-500/40 bg-slate-500/15 text-slate-300 hover:bg-slate-500/30 transition-colors"
          >
            Logout
          </button>
        </div>
      </header>

      {/* Demo mode banner */}
      {isDemoMode && (
        <div className="bg-amber-950/80 border-b border-amber-900/60 px-6 py-2 text-amber-200 text-xs font-semibold flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
          Demo Mode — showing static data. Connect a backend for live simulation.
        </div>
      )}

      {/* Error banner */}
      {backendError && !isDemoMode && (
        <div className="bg-rose-950/80 border-b border-rose-900/60 px-6 py-2.5 text-rose-200 text-sm font-medium flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" /> {backendError}
        </div>
      )}

      <main className="max-w-screen-2xl mx-auto px-6 py-6 space-y-6">
        {/* Top: building map + controls */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_290px] gap-5">
          {/* Left: building view + environment */}
          <div className="space-y-5">
            <div>
              <div className="flex items-center justify-between px-1 pb-2">
                <span className="text-xs font-bold uppercase tracking-widest text-slate-300">
                  Building View
                </span>
                <div className="flex items-center gap-1 rounded-lg border border-slate-700/70 bg-[#0d1627] p-1 shadow-inner">
                  {(['2d', '3d'] as const).map((mode) => (
                    <button
                      key={mode}
                      onClick={() => setViewMode(mode)}
                      className={`rounded-md px-3.5 py-1 text-[11px] font-bold uppercase tracking-widest transition-all ${
                        viewMode === mode
                          ? 'bg-blue-600 text-white shadow-sm'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      {mode === '2d' ? '2D Map' : '3D Twin'}
                    </button>
                  ))}
                </div>
              </div>
              {viewMode === '2d' ? (
                <BuildingMap
                  state={state}
                  selectedRoom={selectedRoom}
                  onSelect={setSelectedRoom}
                />
              ) : (
                <BuildingScene3D
                  state={state}
                  selectedRoom={selectedRoom}
                  onSelect={setSelectedRoom}
                />
              )}
            </div>
            <DemoMacros state={state} onRefresh={refreshState} isDemoMode={isDemoMode} />
            <EnvironmentPanel state={state} />
            <NLPChatPanel onRefresh={refreshState} />
          </div>

          {/* Right: controls + selected room */}
          <div className="space-y-5">
            <SimulationControls
              running={state.running}
              speed={state.speed}
              outsideTemp={state.outside_temperature_c}
              electricityPrice={state.electricity_price_per_kwh}
              rlMode={state.rl_mode || 'manual'}
              onRefresh={refreshState}
            />
            {selectedRoomData && (
              <div className="bg-[#0c1424] border border-slate-800 rounded-xl overflow-hidden shadow-sm">
                {/* Tab bar */}
                <div className="flex border-b border-slate-800 bg-[#09101d]">
                  <button
                    onClick={() => setActiveTab('telemetry')}
                    className={`flex-1 py-2.5 text-xs font-bold uppercase tracking-widest transition-all flex items-center justify-center gap-2 ${
                      activeTab === 'telemetry'
                        ? 'text-sky-300 border-b-2 border-sky-400 bg-sky-500/10'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    <BarChart3 size={14} />
                    <span>Room Detail</span>
                  </button>
                  <button
                    onClick={() => setActiveTab('sensors')}
                    className={`flex-1 py-2.5 text-xs font-bold uppercase tracking-widest transition-all flex items-center justify-center gap-2 ${
                      activeTab === 'sensors'
                        ? 'text-amber-300 border-b-2 border-amber-400 bg-amber-500/10'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    <Sliders size={14} />
                    <span>Sensors</span>
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
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <TemperatureChart history={history} roomId={selectedRoom} />
          <EnergyChart history={history} />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <ComfortChart history={history} roomId={selectedRoom} />

          {/* Quick stats for all 4 rooms */}
          <div className="bg-[#0c1424] border border-slate-800 rounded-xl p-5 shadow-sm">
            <h3 className="text-xs font-bold uppercase tracking-widest text-slate-300 mb-3">
              All Rooms — Current State
            </h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-400 text-xs border-b border-slate-800 pb-1">
                  <th className="py-2 font-semibold">Room</th>
                  <th className="py-2 font-semibold">Temp</th>
                  <th className="py-2 font-semibold">Setpt</th>
                  <th className="py-2 font-semibold">RH%</th>
                  <th className="py-2 font-semibold">HVAC</th>
                  <th className="py-2 font-semibold">Cmft</th>
                </tr>
              </thead>
              <tbody>
                {(['A','B','C','D'] as RoomId[]).map((rid) => {
                  const r = state.rooms[rid];
                  if (!r) return null;
                  const comfortColor =
                    r.comfort_score >= 85 ? 'text-emerald-400' :
                    r.comfort_score >= 65 ? 'text-amber-400' : 'text-rose-400';
                  return (
                    <tr
                      key={rid}
                      onClick={() => setSelectedRoom(rid)}
                      className={`cursor-pointer border-b border-slate-800/60 hover:bg-slate-800/40 transition-colors ${selectedRoom === rid ? 'bg-sky-500/15' : ''}`}
                    >
                      <td className="py-2 font-bold text-sky-400">{rid}</td>
                      <td className="py-2 font-medium text-slate-200">{r.temperature_c.toFixed(1)}°</td>
                      <td className="py-2 text-slate-400">{r.setpoint_c.toFixed(1)}°</td>
                      <td className="py-2 text-slate-300">{r.humidity_pct.toFixed(0)}%</td>
                      <td className="py-2 text-slate-300">{r.hvac_power_kw.toFixed(1)} kW</td>
                      <td className={`py-2 font-bold ${comfortColor}`}>{r.comfort_score.toFixed(0)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </main>

      <footer className="text-center text-slate-400 text-xs py-5 border-t border-slate-800/80">
        Digital Twin Simulation · Grey-box 1R1C model · Physics-guarded TOU optimization · Virtual sensor telemetry
      </footer>
    </div>
  );
}
