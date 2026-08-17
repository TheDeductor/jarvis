// SensorOverridePanel.tsx  —  Manual hardware sensor override UI.
//
// Design intent:
//   Each field shows the current simulated value as the default.
//   User can edit any field and click "Push to Twin" to send real values.
//   Fields left at their defaults are NOT sent — only edited fields are pushed.
//   A "Simulated" badge shows when a field is in default mode.
//   A "Sensor Active" badge shows when a real value is overriding that field.
//
// Future: replace manual input with a hardware bridge that calls the same API
// automatically (MQTT, Modbus, BACnet, etc.).

import React, { useState, useEffect } from 'react';
import type { RoomState, SimulationState } from '../types';
import { injectRoomSensorData, injectOutsideSensorData } from '../api';

interface Props {
  room: RoomState;
  state: SimulationState;
  onRefresh: () => void;
}

// A single sensor field row with enable/disable toggle
function SensorField({
  label, unit, defaultValue, step, min, max,
  active, value,
  onToggle, onChange,
}: {
  label: string; unit: string;
  defaultValue: number; step: number; min: number; max: number;
  active: boolean; value: string;
  onToggle: (active: boolean, defaultVal: number) => void;
  onChange: (v: string) => void;
}) {
  return (
    <div className={`rounded-lg border transition-all duration-200 p-3 ${
      active
        ? 'border-amber-500/40 bg-amber-500/5'
        : 'border-white/5 bg-slate-900/30'
    }`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-slate-300">{label}</span>
        <button
          onClick={() => onToggle(!active, defaultValue)}
          className={`text-[10px] font-bold px-2 py-0.5 rounded-full border transition-all ${
            active
              ? 'border-amber-500/50 bg-amber-500/20 text-amber-400 hover:bg-amber-500/30'
              : 'border-slate-600 bg-slate-700/50 text-slate-400 hover:bg-slate-700'
          }`}
        >
          {active ? '⚡ Sensor Active' : '● Simulated'}
        </button>
      </div>
      <div className="flex items-center gap-2">
        <input
          type="number"
          disabled={!active}
          value={value}
          step={step}
          min={min}
          max={max}
          onChange={(e) => onChange(e.target.value)}
          className={`flex-1 text-center rounded-lg px-2 py-1.5 text-sm font-mono border transition-all ${
            active
              ? 'bg-slate-800 border-amber-500/40 text-amber-300 focus:outline-none focus:border-amber-400'
              : 'bg-slate-900/50 border-slate-700/50 text-slate-500 cursor-not-allowed'
          }`}
        />
        <span className="text-xs text-slate-500 w-10 text-right">{unit}</span>
      </div>
      {!active && (
        <p className="text-[10px] text-slate-600 mt-1">
          Simulated: {defaultValue.toFixed(step < 1 ? 2 : 0)} {unit}
        </p>
      )}
    </div>
  );
}

// Outside environment override section
function OutsideSensorSection({
  state, onRefresh,
}: {
  state: SimulationState;
  onRefresh: () => void;
}) {
  const [tempActive, setTempActive] = useState(false);
  const [tempVal, setTempVal]       = useState('');
  const [status, setStatus]         = useState<string | null>(null);
  const [sending, setSending]       = useState(false);

  const handlePush = async () => {
    if (!tempActive) { setStatus('No fields overridden.'); return; }
    setSending(true);
    try {
      const data: Record<string, number> = {};
      if (tempActive) data.temperature_c = parseFloat(tempVal);
      await injectOutsideSensorData(data);
      setStatus(`✓ Pushed: ${Object.keys(data).join(', ')}`);
      setTimeout(onRefresh, 100);
    } catch {
      setStatus('✗ Failed to push data.');
    } finally {
      setSending(false);
      setTimeout(() => setStatus(null), 3000);
    }
  };

  return (
    <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400">
          🌡️ Outside Environment
        </h3>
        <span className="text-[10px] text-slate-600">Weather Station</span>
      </div>

      <SensorField
        label="Outside Temperature"
        unit="°C" step={0.1} min={-10} max={55}
        defaultValue={state.outside_temperature_c}
        active={tempActive}
        value={tempActive ? tempVal : state.outside_temperature_c.toFixed(1)}
        onToggle={(on, def) => { setTempActive(on); if (on) setTempVal(def.toFixed(1)); }}
        onChange={setTempVal}
      />

      <div className="flex items-center gap-2 pt-1">
        <button
          onClick={handlePush}
          disabled={sending || !tempActive}
          className={`flex-1 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all ${
            tempActive
              ? 'bg-amber-500/20 border border-amber-500/40 text-amber-400 hover:bg-amber-500/30'
              : 'bg-slate-700/30 border border-slate-700/30 text-slate-600 cursor-not-allowed'
          }`}
        >
          {sending ? 'Pushing…' : 'Push to Twin'}
        </button>
      </div>
      {status && (
        <p className={`text-xs text-center font-medium ${status.startsWith('✓') ? 'text-emerald-400' : 'text-red-400'}`}>
          {status}
        </p>
      )}
    </div>
  );
}

// Room sensor override section
export default function SensorOverridePanel({ room, state, onRefresh }: Props) {
  // Track which fields are active (overriding simulation) + their draft values
  type FieldKey = 'temperature_c' | 'wall_temperature_c' | 'humidity_pct' | 'occupancy' | 'airflow_lps' | 'hvac_power_kw';

  const FIELDS: {
    key: FieldKey; label: string; unit: string;
    step: number; min: number; max: number;
    getDefault: (r: RoomState) => number;
  }[] = [
    { key: 'temperature_c',      label: 'Air Temperature',   unit: '°C',  step: 0.1, min: -10, max: 60,  getDefault: r => r.temperature_c },
    { key: 'wall_temperature_c', label: 'Wall Temperature',  unit: '°C',  step: 0.1, min: -10, max: 60,  getDefault: r => r.wall_temperature_c },
    { key: 'humidity_pct',       label: 'Humidity',          unit: '%',   step: 1,   min: 0,   max: 100, getDefault: r => r.humidity_pct },
    { key: 'occupancy',          label: 'Occupancy',         unit: 'pax', step: 1,   min: 0,   max: 500, getDefault: r => r.occupancy },
    { key: 'airflow_lps',        label: 'Airflow',           unit: 'L/s', step: 5,   min: 0,   max: 1000,getDefault: r => r.airflow_lps },
    { key: 'hvac_power_kw',      label: 'HVAC Power (meter)',unit: 'kW',  step: 0.1, min: -100,max: 100, getDefault: r => r.hvac_power_kw },
  ];

  const [active, setActive]   = useState<Record<FieldKey, boolean>>({
    temperature_c: false, wall_temperature_c: false, humidity_pct: false,
    occupancy: false, airflow_lps: false, hvac_power_kw: false,
  });
  const [values, setValues]   = useState<Record<FieldKey, string>>({
    temperature_c: '', wall_temperature_c: '', humidity_pct: '',
    occupancy: '', airflow_lps: '', hvac_power_kw: '',
  });
  const [status, setStatus]   = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  // When room changes, update inactive fields' display defaults
  useEffect(() => {
    setValues(prev => {
      const next = { ...prev };
      FIELDS.forEach(f => {
        if (!active[f.key]) next[f.key] = f.getDefault(room).toFixed(f.step < 1 ? 2 : 0);
      });
      return next;
    });
  }, [room, active]);

  const toggleField = (key: FieldKey, on: boolean, def: number, step: number) => {
    setActive(prev => ({ ...prev, [key]: on }));
    if (on) setValues(prev => ({ ...prev, [key]: def.toFixed(step < 1 ? 2 : 0) }));
  };

  const activeCount = Object.values(active).filter(Boolean).length;

  const handlePush = async () => {
    if (activeCount === 0) { setStatus('Enable at least one field.'); return; }
    setSending(true);
    try {
      const data: Record<string, number> = {};
      FIELDS.forEach(f => {
        if (active[f.key]) {
          const v = parseFloat(values[f.key]);
          if (!isNaN(v)) data[f.key] = v;
        }
      });
      await injectRoomSensorData(room.room_id, data as any);
      setStatus(`✓ Pushed ${Object.keys(data).length} field(s): ${Object.keys(data).join(', ')}`);
      setTimeout(onRefresh, 100);
    } catch {
      setStatus('✗ Failed. Is backend running?');
    } finally {
      setSending(false);
      setTimeout(() => setStatus(null), 4000);
    }
  };

  const handleReset = () => {
    setActive({ temperature_c: false, wall_temperature_c: false, humidity_pct: false,
                occupancy: false, airflow_lps: false, hvac_power_kw: false });
    setStatus(null);
  };

  return (
    <div className="space-y-4">
      {/* Room sensor panel */}
      <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400">
              ⚡ Sensor Override — Zone {room.room_id}
            </h3>
            <p className="text-[10px] text-slate-600 mt-0.5">
              Toggle fields to replace simulated values with real sensor data
            </p>
          </div>
          {activeCount > 0 && (
            <button
              onClick={handleReset}
              className="text-[10px] text-slate-500 hover:text-slate-300 border border-slate-600 rounded px-2 py-1 transition-all"
            >
              Reset All
            </button>
          )}
        </div>

        {/* Active sensor count badge */}
        <div className="flex items-center gap-2">
          <div className={`flex items-center gap-1.5 text-[10px] font-bold px-2 py-1 rounded-full border ${
            activeCount > 0
              ? 'border-amber-500/40 bg-amber-500/10 text-amber-400'
              : 'border-slate-700 bg-slate-800 text-slate-500'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${activeCount > 0 ? 'bg-amber-400 animate-pulse' : 'bg-slate-600'}`} />
            {activeCount > 0 ? `${activeCount} sensor(s) active` : 'All simulated'}
          </div>
        </div>

        {/* Sensor fields grid */}
        <div className="grid grid-cols-1 gap-2">
          {FIELDS.map(f => (
            <SensorField
              key={f.key}
              label={f.label} unit={f.unit}
              step={f.step} min={f.min} max={f.max}
              defaultValue={f.getDefault(room)}
              active={active[f.key]}
              value={values[f.key]}
              onToggle={(on, def) => toggleField(f.key, on, def, f.step)}
              onChange={(v) => setValues(prev => ({ ...prev, [f.key]: v }))}
            />
          ))}
        </div>

        {/* Push button */}
        <button
          onClick={handlePush}
          disabled={sending || activeCount === 0}
          className={`w-full py-2.5 rounded-lg text-xs font-bold uppercase tracking-widest transition-all ${
            activeCount > 0
              ? 'bg-amber-500/20 border border-amber-500/40 text-amber-400 hover:bg-amber-500/30 active:scale-95'
              : 'bg-slate-700/30 border border-slate-700/30 text-slate-600 cursor-not-allowed'
          }`}
        >
          {sending ? '⟳ Pushing to Twin…' : `Push ${activeCount || 'No'} Sensor Override${activeCount !== 1 ? 's' : ''}`}
        </button>

        {status && (
          <p className={`text-xs text-center font-medium py-1 rounded ${
            status.startsWith('✓') ? 'text-emerald-400' : 'text-amber-400'
          }`}>
            {status}
          </p>
        )}
      </div>

      {/* Outside environment sensor section */}
      <OutsideSensorSection state={state} onRefresh={onRefresh} />
    </div>
  );
}
