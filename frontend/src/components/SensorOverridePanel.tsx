// SensorOverridePanel.tsx  —  Manual hardware sensor override UI.

import React, { useState, useEffect } from 'react';
import type { RoomState, SimulationState } from '../types';
import { injectRoomSensorData, injectOutsideSensorData } from '../api';
import { Radio, RotateCcw, Sliders, Thermometer, ArrowUpRight } from 'lucide-react';

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
        ? 'border-amber-500/50 bg-amber-500/10'
        : 'border-slate-800 bg-[#080e1b]'
    }`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-slate-200">{label}</span>
        <button
          onClick={() => onToggle(!active, defaultValue)}
          className={`text-[10px] font-bold px-2 py-0.5 rounded-full border transition-all flex items-center gap-1 ${
            active
              ? 'border-amber-500/50 bg-amber-500/20 text-amber-300 hover:bg-amber-500/30'
              : 'border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700'
          }`}
        >
          {active ? <Radio size={10} /> : <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />}
          <span>{active ? 'Sensor Active' : 'Simulated'}</span>
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
              ? 'bg-[#0b1324] border-amber-500/50 text-amber-300 focus:outline-none focus:border-amber-400 font-bold'
              : 'bg-[#050912] border-slate-800 text-slate-400 cursor-not-allowed'
          }`}
        />
        <span className="text-xs text-slate-300 w-10 text-right font-medium">{unit}</span>
      </div>
      {!active && (
        <p className="text-[11px] text-slate-400 mt-1">
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
      setStatus(`Pushed: ${Object.keys(data).join(', ')}`);
      setTimeout(onRefresh, 100);
    } catch {
      setStatus('Failed to push data.');
    } finally {
      setSending(false);
      setTimeout(() => setStatus(null), 3000);
    }
  };

  return (
    <div className="bg-[#0c1424] border border-slate-800 rounded-xl p-4 space-y-3 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Thermometer size={14} className="text-sky-400" />
          <h3 className="text-xs font-bold uppercase tracking-widest text-slate-200">
            Outside Environment
          </h3>
        </div>
        <span className="text-[11px] text-slate-300 font-medium">Weather Station</span>
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
          className={`flex-1 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all flex items-center justify-center gap-1.5 ${
            tempActive
              ? 'bg-amber-500/20 border border-amber-500/40 text-amber-300 hover:bg-amber-500/30 active:scale-95'
              : 'bg-slate-800/40 border border-slate-700/30 text-slate-400 cursor-not-allowed'
          }`}
        >
          <ArrowUpRight size={13} />
          <span>{sending ? 'Pushing…' : 'Push to Twin'}</span>
        </button>
      </div>
      {status && (
        <p className={`text-xs text-center font-semibold ${status.startsWith('Pushed') ? 'text-emerald-400' : 'text-rose-400'}`}>
          {status}
        </p>
      )}
    </div>
  );
}

// Room sensor override section
export default function SensorOverridePanel({ room, state, onRefresh }: Props) {
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
      setStatus(`Pushed ${Object.keys(data).length} field(s): ${Object.keys(data).join(', ')}`);
      setTimeout(onRefresh, 100);
    } catch {
      setStatus('Failed to push. Is backend running?');
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
      <div className="bg-[#0c1424] border border-slate-800 rounded-xl p-4 space-y-3 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-1.5">
              <Sliders size={14} className="text-amber-400" />
              <h3 className="text-xs font-bold uppercase tracking-widest text-slate-200">
                Sensor Override — Zone {room.room_id}
              </h3>
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Replace simulated physics values with live sensor feeds
            </p>
          </div>
          {activeCount > 0 && (
            <button
              onClick={handleReset}
              className="text-[11px] font-semibold text-slate-300 hover:text-white border border-slate-700 rounded px-2.5 py-1 bg-slate-800 transition-all flex items-center gap-1"
            >
              <RotateCcw size={11} />
              <span>Reset All</span>
            </button>
          )}
        </div>

        {/* Active sensor count badge */}
        <div className="flex items-center gap-2">
          <div className={`flex items-center gap-1.5 text-[11px] font-bold px-2.5 py-1 rounded-full border ${
            activeCount > 0
              ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
              : 'border-slate-800 bg-slate-900 text-slate-300'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${activeCount > 0 ? 'bg-amber-400 animate-pulse' : 'bg-slate-400'}`} />
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
          className={`w-full py-2.5 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center justify-center gap-2 ${
            activeCount > 0
              ? 'bg-amber-500/20 border border-amber-500/40 text-amber-300 hover:bg-amber-500/30 active:scale-95'
              : 'bg-slate-800/40 border border-slate-800 text-slate-400 cursor-not-allowed'
          }`}
        >
          <ArrowUpRight size={14} />
          <span>{sending ? 'Pushing to Twin…' : `Push ${activeCount || 'No'} Sensor Override${activeCount !== 1 ? 's' : ''}`}</span>
        </button>

        {status && (
          <p className={`text-xs text-center font-semibold py-1 rounded ${
            status.startsWith('Pushed') ? 'text-emerald-400' : 'text-amber-400'
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
