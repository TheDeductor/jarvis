import React, { useState, useEffect } from 'react';
import type { SpeedOption } from '../types';
import { Play, Pause, RotateCcw, Bot, User } from 'lucide-react';
import {
  startSimulation, pauseSimulation, resetSimulation,
  setSpeed, setOutsideTemperature, setElectricityPrice,
  setRlMode,
} from '../api';

// Default policy path — points to best model from the test_run training
const DEFAULT_MODEL_PATH = 'rl/models/test_run/best_model.zip';

// In cloud deployments the model zip isn't shipped — detect via env var.
// Set VITE_RL_ENABLED=true in your hosting platform only if you upload the model.
const RL_ENABLED = import.meta.env.VITE_RL_ENABLED === 'true';

interface Props {
  running: boolean;
  speed: number;
  outsideTemp: number;
  electricityPrice: number;
  rlMode: 'manual' | 'auto';
  onRefresh: () => void;
}

export default function SimulationControls({
  running, speed, outsideTemp, electricityPrice, rlMode, onRefresh,
}: Props) {
  const [outsideInput, setOutsideInput] = useState(outsideTemp.toFixed(1));
  const [priceInput, setPriceInput] = useState(electricityPrice.toFixed(2));
  const [busy, setBusy] = useState(false);
  const [rlBusy, setRlBusy] = useState(false);
  const [rlError, setRlError] = useState<string | null>(null);

  useEffect(() => { setOutsideInput(outsideTemp.toFixed(1)); }, [outsideTemp]);
  useEffect(() => { setPriceInput(electricityPrice.toFixed(2)); }, [electricityPrice]);

  const act = async (fn: () => Promise<void>) => {
    setBusy(true);
    try { await fn(); await onRefresh(); }
    catch (e) { console.error(e); }
    finally { setBusy(false); }
  };

  const handleOutsideTemp = async () => {
    const v = parseFloat(outsideInput);
    if (!isNaN(v) && v >= -10 && v <= 55) await act(() => setOutsideTemperature(v));
  };

  const handlePrice = async () => {
    const v = parseFloat(priceInput);
    if (!isNaN(v) && v >= 0) await act(() => setElectricityPrice(v));
  };

  const handleRlToggle = async (targetMode: 'manual' | 'auto') => {
    if (targetMode === rlMode) return;
    setRlBusy(true);
    setRlError(null);
    try {
      if (targetMode === 'auto') {
        await setRlMode('auto', DEFAULT_MODEL_PATH);
      } else {
        await setRlMode('manual');
      }
      await onRefresh();
    } catch (e: any) {
      const msg = e?.response?.data?.detail ?? e?.message ?? 'Failed to switch RL mode';
      setRlError(msg);
    } finally {
      setRlBusy(false);
    }
  };

  const speedBtns: SpeedOption[] = [1, 5, 20];
  const isAuto = rlMode === 'auto';

  return (
    <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5 space-y-5">
      <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">
        Engine Control
      </h2>

      {/* Start / Pause / Reset */}
      <div className="flex gap-2">
        <button
          disabled={busy}
          onClick={() => act(running ? pauseSimulation : startSimulation)}
          className={`flex-1 py-2.5 rounded-lg text-sm font-semibold transition-all flex items-center justify-center gap-2
            ${running
              ? 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-500 border border-amber-500/30'
              : 'bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'}`}
        >
          {running ? <><Pause size={16} /> Pause</> : <><Play size={16} /> Start</>}
        </button>
        <button
          disabled={busy}
          onClick={() => act(resetSimulation)}
          className="px-4 py-2.5 rounded-lg bg-slate-700/50 hover:bg-slate-600/50 text-slate-300 text-sm font-semibold transition-all border border-slate-600/50 flex items-center justify-center gap-2"
        >
          <RotateCcw size={16} /> Reset
        </button>
      </div>

      {/* ── RL Auto Mode Toggle ───────────────────────────────────────── */}
      <div>
        <p className="text-xs font-medium text-slate-400 mb-2">HVAC Control Mode</p>
        <div className="flex gap-2">
          <button
            disabled={rlBusy || isAuto === false && busy}
            onClick={() => handleRlToggle('manual')}
            className={`flex-1 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all flex items-center justify-center gap-1.5 border ${
              !isAuto
                ? 'bg-sky-500/20 border-sky-500/40 text-sky-400'
                : 'bg-slate-800/50 border-slate-700 text-slate-500 hover:text-slate-300 hover:border-slate-600'
            }`}
          >
            <User size={13} /> Manual
          </button>
          <button
            disabled={rlBusy || !RL_ENABLED}
            title={RL_ENABLED ? 'Switch to RL auto control' : 'RL model not deployed — run locally to use Auto AI'}
            onClick={() => handleRlToggle('auto')}
            className={`flex-1 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all flex items-center justify-center gap-1.5 border ${
              isAuto
                ? 'bg-amber-500/20 border-amber-500/40 text-amber-400'
                : RL_ENABLED
                ? 'bg-slate-800/50 border-slate-700 text-slate-500 hover:text-slate-300 hover:border-slate-600'
                : 'bg-slate-800/30 border-slate-800 text-slate-700 cursor-not-allowed'
            }`}
          >
            <Bot size={13} /> {rlBusy ? 'Loading…' : RL_ENABLED ? 'Auto AI' : 'Auto AI 🔒'}
          </button>
        </div>

        {/* Active indicator */}
        {isAuto && (
          <div className="mt-2 flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
            <span className="text-[10px] font-semibold text-amber-400 uppercase tracking-widest">
              RL Agent Active — controlling all rooms
            </span>
          </div>
        )}
        {rlError && (
          <p className="mt-1 text-[10px] text-red-400 font-medium">{rlError}</p>
        )}
      </div>

      {/* Speed */}
      <div>
        <p className="text-xs font-medium text-slate-400 mb-2">Simulated Time Speed</p>
        <div className="flex gap-2">
          {speedBtns.map((s) => (
            <button
              key={s}
              disabled={busy}
              onClick={() => act(() => setSpeed(s))}
              className={`flex-1 py-1.5 rounded-md text-sm font-semibold transition-all border
                ${speed === s
                  ? 'bg-blue-500/20 border-blue-500/50 text-blue-400'
                  : 'bg-slate-800/50 border-slate-700 text-slate-400 hover:bg-slate-700/50 hover:text-slate-200'}`}
            >
              {s}×
            </button>
          ))}
        </div>
      </div>

      {/* Outside Temperature */}
      <div>
        <p className="text-xs font-medium text-slate-400 mb-2">Outdoor Baseline Temperature</p>
        <div className="flex gap-2">
          <input
            type="number"
            value={outsideInput}
            onChange={(e) => setOutsideInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleOutsideTemp()}
            onBlur={handleOutsideTemp}
            step={0.5}
            className="flex-1 bg-slate-900/50 border border-slate-700 focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 rounded-md px-3 py-1.5 text-slate-200 text-sm outline-none transition-all"
          />
          <span className="self-center text-slate-500 text-sm w-6">°C</span>
        </div>
      </div>

      {/* Electricity Price */}
      <div>
        <p className="text-xs font-medium text-slate-400 mb-2">Electricity Rate</p>
        <div className="flex gap-2">
          <span className="self-center text-slate-500 text-sm w-4">₹</span>
          <input
            type="number"
            value={priceInput}
            onChange={(e) => setPriceInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handlePrice()}
            onBlur={handlePrice}
            step={0.5}
            min={0}
            className="flex-1 bg-slate-900/50 border border-slate-700 focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 rounded-md px-3 py-1.5 text-slate-200 text-sm outline-none transition-all"
          />
        </div>
      </div>

      {/* Status indicator */}
      <div className="flex items-center gap-2 pt-2">
        <span className={`w-2 h-2 rounded-full ${running ? 'bg-emerald-500 animate-pulse' : 'bg-slate-600'}`} />
        <span className="text-xs text-slate-400 font-medium tracking-wide">
          {running
            ? isAuto
              ? `AI AGENT RUNNING AT ${speed}×`
              : `ENGINE RUNNING AT ${speed}×`
            : 'ENGINE IDLE'}
        </span>
      </div>
    </div>
  );
}
