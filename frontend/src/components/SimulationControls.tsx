import React, { useState, useEffect } from 'react';
import type { SpeedOption } from '../types';
import { Play, Pause, RotateCcw, Bot, User } from 'lucide-react';
import {
  startSimulation, pauseSimulation, resetSimulation,
  setSpeed, setOutsideTemperature, setElectricityPrice,
  setRlMode,
} from '../api';

const DEFAULT_MODEL_PATH = 'rl/models/test_run/best_model.zip';

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
    <div className="bg-[#0c1424] border border-slate-800 rounded-xl p-5 space-y-5 shadow-sm">
      <h2 className="text-xs font-bold uppercase tracking-widest text-slate-200">
        Engine Control
      </h2>

      {/* Start / Pause / Reset */}
      <div className="flex gap-2">
        <button
          disabled={busy}
          onClick={() => act(running ? pauseSimulation : startSimulation)}
          className={`flex-1 py-2.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-all flex items-center justify-center gap-2 border shadow-sm active:scale-95
            ${running
              ? 'bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border-amber-500/40'
              : 'bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border-emerald-500/40'}`}
        >
          {running ? <><Pause size={15} /> Pause</> : <><Play size={15} /> Start</>}
        </button>
        <button
          disabled={busy}
          onClick={() => act(resetSimulation)}
          className="px-4 py-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-white text-xs font-bold uppercase tracking-wider transition-all border border-slate-700 flex items-center justify-center gap-1.5 active:scale-95 shadow-sm"
        >
          <RotateCcw size={15} /> Reset
        </button>
      </div>

      {/* ── RL Auto Mode Toggle ───────────────────────────────────────── */}
      <div>
        <p className="text-xs font-semibold text-slate-200 mb-2">HVAC Control Mode</p>
        <div className="flex gap-2">
          <button
            disabled={rlBusy || (isAuto === false && busy)}
            onClick={() => handleRlToggle('manual')}
            className={`flex-1 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all flex items-center justify-center gap-1.5 border shadow-sm ${
              !isAuto
                ? 'bg-blue-600 border-blue-500 text-white'
                : 'bg-slate-800/80 border-slate-700 text-slate-300 hover:text-white hover:bg-slate-700'
            }`}
          >
            <User size={13} /> Manual
          </button>
          <button
            disabled={rlBusy}
            onClick={() => handleRlToggle('auto')}
            className={`flex-1 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all flex items-center justify-center gap-1.5 border shadow-sm ${
              isAuto
                ? 'bg-amber-500 border-amber-400 text-slate-950 font-extrabold'
                : 'bg-slate-800/80 border-slate-700 text-slate-300 hover:text-white hover:bg-slate-700'
            }`}
          >
            <Bot size={13} /> {rlBusy ? 'Loading…' : 'Auto AI'}
          </button>
        </div>

        {/* Active indicator */}
        {isAuto && (
          <div className="mt-2 flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-500/15 border border-amber-500/30">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
            <span className="text-[10px] font-bold text-amber-300 uppercase tracking-widest">
              RL Agent Active — controlling all rooms
            </span>
          </div>
        )}
        {rlError && (
          <p className="mt-1 text-xs text-rose-300 font-semibold">{rlError}</p>
        )}
      </div>

      {/* Speed */}
      <div>
        <p className="text-xs font-semibold text-slate-200 mb-2">Simulated Time Speed</p>
        <div className="flex gap-2">
          {speedBtns.map((s) => (
            <button
              key={s}
              disabled={busy}
              onClick={() => act(() => setSpeed(s))}
              className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition-all border shadow-sm
                ${speed === s
                  ? 'bg-blue-600 border-blue-500 text-white'
                  : 'bg-slate-800 border-slate-700 text-slate-200 hover:bg-slate-700 hover:text-white'}`}
            >
              {s}×
            </button>
          ))}
        </div>
      </div>

      {/* Outside Temperature */}
      <div>
        <p className="text-xs font-semibold text-slate-200 mb-2">Outdoor Baseline Temperature</p>
        <div className="flex gap-2">
          <input
            type="number"
            value={outsideInput}
            onChange={(e) => setOutsideInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleOutsideTemp()}
            onBlur={handleOutsideTemp}
            step={0.5}
            className="flex-1 bg-[#080e1b] border border-slate-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 rounded-lg px-3 py-1.5 text-white font-mono text-sm outline-none transition-all font-bold"
          />
          <span className="self-center text-slate-300 font-bold text-sm w-6">°C</span>
        </div>
      </div>

      {/* Electricity Price */}
      <div>
        <p className="text-xs font-semibold text-slate-200 mb-2">Electricity Rate</p>
        <div className="flex gap-2">
          <span className="self-center text-slate-300 font-bold text-sm w-4">₹</span>
          <input
            type="number"
            value={priceInput}
            onChange={(e) => setPriceInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handlePrice()}
            onBlur={handlePrice}
            step={0.5}
            min={0}
            className="flex-1 bg-[#080e1b] border border-slate-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 rounded-lg px-3 py-1.5 text-white font-mono text-sm outline-none transition-all font-bold"
          />
        </div>
      </div>

      {/* Status indicator */}
      <div className="flex items-center gap-2 pt-2 border-t border-slate-800">
        <span className={`w-2 h-2 rounded-full ${running ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'}`} />
        <span className="text-xs text-slate-300 font-bold tracking-wider">
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
