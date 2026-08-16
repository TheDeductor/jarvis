// SelectedRoomPanel.tsx  —  Detail view + interactive controls for selected room.

import React, { useState, useEffect } from 'react';
import type { RoomState } from '../types';
import { setSetpoint, setOccupancy, setAirflow } from '../api';

interface Props {
  room: RoomState;
  onRefresh: () => void;
}

function ControlRow({
  label, value, unit, step, min, max,
  onSet,
}: {
  label: string; value: number; unit: string;
  step: number; min: number; max: number;
  onSet: (v: number) => Promise<void>;
}) {
  const [draft, setDraft] = useState(value.toString());
  useEffect(() => setDraft(value.toFixed(step < 1 ? 1 : 0)), [value]);

  const clamp = (v: number) => Math.min(max, Math.max(min, v));
  const commit = (v: number) => onSet(clamp(v));

  return (
    <div className="flex items-center gap-3 py-2 border-b border-white/5">
      <span className="text-slate-400 text-sm w-28">{label}</span>
      <button
        onClick={() => commit(clamp(parseFloat(draft) - step))}
        className="w-7 h-7 rounded-lg bg-slate-700 hover:bg-slate-600 text-white flex items-center justify-center text-lg font-bold transition-all"
      >
        −
      </button>
      <input
        type="number"
        value={draft}
        step={step}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => { const v = parseFloat(draft); if (!isNaN(v)) commit(v); }}
        onKeyDown={(e) => { if (e.key === 'Enter') { const v = parseFloat(draft); if (!isNaN(v)) commit(v); } }}
        className="w-20 text-center bg-slate-700 border border-slate-600 rounded-lg px-2 py-1 text-white text-sm"
      />
      <button
        onClick={() => commit(clamp(parseFloat(draft) + step))}
        className="w-7 h-7 rounded-lg bg-slate-700 hover:bg-slate-600 text-white flex items-center justify-center text-lg font-bold transition-all"
      >
        +
      </button>
      <span className="text-slate-500 text-xs">{unit}</span>
    </div>
  );
}

function Metric({ label, value, unit, highlight }: {
  label: string; value: string; unit?: string; highlight?: boolean;
}) {
  return (
    <div className="bg-slate-700/50 rounded-lg p-3">
      <p className="text-xs text-slate-400">{label}</p>
      <p className={`text-lg font-bold ${highlight ? 'text-emerald-400' : 'text-white'}`}>
        {value}
        {unit && <span className="text-xs text-slate-400 ml-1 font-normal">{unit}</span>}
      </p>
    </div>
  );
}

export default function SelectedRoomPanel({ room, onRefresh }: Props) {
  const act = async (fn: () => Promise<void>) => {
    try { await fn(); setTimeout(onRefresh, 100); }
    catch (e) { console.error(e); }
  };

  const hvacPct = Math.round((Math.abs(room.hvac_power_kw) / 10.0) * 100);
  const isCooling = room.hvac_power_kw < 0;
  const comfortColor =
    room.comfort_score >= 85 ? 'text-emerald-400' :
    room.comfort_score >= 65 ? 'text-amber-400' : 'text-red-400';

  return (
    <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5 space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-slate-300 tracking-widest uppercase">
          Zone {room.room_id}
        </h2>
        <span className="text-xs text-slate-500 font-medium tracking-wide">Live Telemetry</span>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Metric label="Air Temp" value={room.temperature_c.toFixed(2)} unit="°C" />
        <Metric label="Wall Temp" value={room.wall_temperature_c.toFixed(2)} unit="°C" />
        <Metric label="Setpoint" value={room.setpoint_c.toFixed(1)} unit="°C" />
        <Metric label="Humidity" value={room.humidity_pct.toFixed(1)} unit="%" />
        <Metric label="HVAC Power" value={room.hvac_power_kw.toFixed(2)} unit="kW" />
        <Metric label="Fan Power" value={room.fan_power_kw.toFixed(3)} unit="kW" />
        <Metric label="Energy" value={room.energy_kwh.toFixed(3)} unit="kWh" />
        <Metric label="Airflow" value={room.airflow_lps.toFixed(0)} unit="L/s" />
        <Metric label="Occupancy" value={room.occupancy.toString()} unit="pax" />
        <div className="bg-slate-900/40 border border-slate-700/50 rounded-lg p-3">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">PMV Index</p>
          <p className={`text-lg font-bold ${
            Math.abs(room.pmv) <= 0.5 ? 'text-emerald-400' :
            Math.abs(room.pmv) <= 1.5 ? 'text-amber-500' : 'text-red-400'
          }`}>
            {room.pmv > 0 ? '+' : ''}{room.pmv.toFixed(2)}
            <span className="text-xs text-slate-500 ml-1.5 font-medium">
              {room.pmv <= -2 ? 'Cold' : room.pmv <= -0.5 ? 'Cool' : room.pmv <= 0.5 ? 'Neutral' : room.pmv <= 1.5 ? 'Warm' : 'Hot'}
            </span>
          </p>
        </div>
        <div className="bg-slate-900/40 border border-slate-700/50 rounded-lg p-3">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Comfort</p>
          <p className={`text-lg font-bold ${comfortColor}`}>
            {room.comfort_score.toFixed(0)}
            <span className="text-xs text-slate-500 ml-1.5 font-medium">/100</span>
          </p>
        </div>
      </div>

      {/* HVAC visual bar */}
      <div>
        <div className="flex justify-between text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
          <span>{isCooling ? 'Cooling Mode' : 'Heating Mode'}</span>
          <span>{hvacPct}% Output</span>
        </div>
        <div className="h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-500 ${isCooling ? 'bg-blue-500' : 'bg-amber-500'}`}
            style={{ width: `${hvacPct}%` }}
          />
        </div>
      </div>

      {/* Controls */}
      <div className="pt-2">
        <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3">Overrides</p>
        <ControlRow
          label="Setpoint"
          value={room.setpoint_c}
          unit="°C" step={0.5} min={16} max={30}
          onSet={(v) => act(() => setSetpoint(room.room_id, v))}
        />
        <ControlRow
          label="Occupancy"
          value={room.occupancy}
          unit="pax" step={1} min={0} max={100}
          onSet={(v) => act(() => setOccupancy(room.room_id, v))}
        />
        <ControlRow
          label="Airflow"
          value={room.airflow_lps}
          unit="L/s" step={10} min={50} max={300}
          onSet={(v) => act(() => setAirflow(room.room_id, v))}
        />
      </div>
    </div>
  );
}
