// DemoMacros.tsx — Scripted demo triggers and TOU tariff editor (MASTER_PROMPT_3D §3.5, §P6).
// Runs over existing backend REST endpoints.

import React, { useState, useEffect } from 'react';
import { Zap, Wind, Flame, RotateCcw, ChevronRight, ChevronDown, CheckCircle, ShieldCheck } from 'lucide-react';
import {
  setOccupancy,
  setAirflow,
  setOutsideTemperature,
  setElectricityPrice,
  resetSimulation,
  forcePeak,
  fetchTariff,
  setTariff,
} from '../api';
import type { SimulationState, TariffSlot } from '../types';

interface Props {
  state: SimulationState;
  onRefresh: () => void;
}

export default function DemoMacros({ state, onRefresh }: Props) {
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [feedbackMsg, setFeedbackMsg] = useState<string | null>(null);
  const [slots, setSlots] = useState<TariffSlot[]>([]);
  const [showTariffEditor, setShowTariffEditor] = useState(false);

  useEffect(() => {
    fetchTariff()
      .then((data) => setSlots(data.slots))
      .catch((e) => console.warn('Failed to fetch tariff schedule:', e));
  }, []);

  const runMacro = async (name: string, fn: () => Promise<void>, msg: string) => {
    setLoadingAction(name);
    try {
      await fn();
      setFeedbackMsg(msg);
      setTimeout(() => setFeedbackMsg(null), 3500);
      onRefresh();
    } catch (err: any) {
      setFeedbackMsg(`Error: ${err?.message || 'Failed to trigger macro'}`);
      setTimeout(() => setFeedbackMsg(null), 4000);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleStuffyRoomB = () =>
    runMacro(
      'stuffy',
      async () => {
        await setOccupancy('B', 14);
        await setAirflow('B', 60);
      },
      'Macro executed: Room B occupancy → 14, airflow → 60 L/s. Watch CO2 climb & IAQ rule engage!'
    );

  const handleHeatWave = () =>
    runMacro(
      'heatwave',
      async () => {
        await setOutsideTemperature(38.0);
      },
      'Macro executed: Outside temp → 38.0°C. Heavy thermal load simulated!'
    );

  const handleForcePeak = () =>
    runMacro(
      'peak',
      async () => {
        await forcePeak();
      },
      'Macro executed: Peak tariff ₹9.0/kWh forced. Pre-cool / Peak-relax overlay engaged with ±0.7 PMV guard!'
    );

  const handleReset = () =>
    runMacro(
      'reset',
      async () => {
        await resetSimulation();
      },
      'System reset to nominal initial conditions.'
    );

  const handleSaveTariff = async () => {
    try {
      const res = await setTariff(slots);
      setSlots(res.slots);
      setFeedbackMsg('TOU tariff schedule updated successfully.');
      setTimeout(() => setFeedbackMsg(null), 3000);
      onRefresh();
    } catch (e: any) {
      setFeedbackMsg(`Failed to save tariff: ${e.message}`);
    }
  };

  const isPeak = state.building?.is_peak ?? false;
  const isPrePeak = state.building?.is_pre_peak ?? false;
  const priceResponseActive = state.building?.price_response_active ?? false;
  const currentPrice = state.building?.current_price ?? state.electricity_price_per_kwh;

  return (
    <div className="bg-[#0c1424] border border-slate-800 rounded-xl p-5 space-y-4 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap size={16} className="text-amber-400" />
          <h3 className="text-xs font-bold uppercase tracking-widest text-slate-200">
            Demo Macros & TOU Controls
          </h3>
        </div>
        {/* Live pricing pill */}
        <span
          className={`text-[11px] font-bold px-3 py-1 rounded-full border flex items-center gap-1.5 ${
            isPeak
              ? 'bg-rose-500/15 text-rose-300 border-rose-500/40 animate-pulse'
              : isPrePeak
              ? 'bg-amber-500/15 text-amber-300 border-amber-500/40'
              : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40'
          }`}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-current" />
          {isPeak ? 'Peak Window (₹9/kWh)' : isPrePeak ? 'Pre-Peak Window' : 'Normal / Off-Peak'}
        </span>
      </div>

      {feedbackMsg && (
        <div className="bg-sky-950/80 border border-sky-800/80 rounded-lg p-2.5 text-xs text-sky-200 font-medium flex items-center gap-2 animate-fadeIn">
          <CheckCircle size={14} className="text-sky-400 shrink-0" />
          <span>{feedbackMsg}</span>
        </div>
      )}

      {/* Scripted demo macro buttons */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
        <button
          onClick={handleForcePeak}
          disabled={loadingAction !== null}
          className="flex flex-col items-center justify-center p-3 rounded-lg border border-rose-500/40 bg-rose-500/10 hover:bg-rose-500/20 active:scale-95 transition-all text-left group"
        >
          <Zap size={20} className="text-rose-400 mb-1.5 group-hover:scale-110 transition-transform" />
          <span className="text-xs font-bold text-rose-200 text-center">Force Peak Price</span>
          <span className="text-[11px] text-slate-300 text-center mt-0.5 font-medium">₹9.0/kWh overlay</span>
        </button>

        <button
          onClick={handleStuffyRoomB}
          disabled={loadingAction !== null}
          className="flex flex-col items-center justify-center p-3 rounded-lg border border-amber-500/40 bg-amber-500/10 hover:bg-amber-500/20 active:scale-95 transition-all text-left group"
        >
          <Wind size={20} className="text-amber-400 mb-1.5 group-hover:scale-110 transition-transform" />
          <span className="text-xs font-bold text-amber-200 text-center">Stuffy Room B</span>
          <span className="text-[11px] text-slate-300 text-center mt-0.5 font-medium">14 occ, 60 L/s</span>
        </button>

        <button
          onClick={handleHeatWave}
          disabled={loadingAction !== null}
          className="flex flex-col items-center justify-center p-3 rounded-lg border border-orange-500/40 bg-orange-500/10 hover:bg-orange-500/20 active:scale-95 transition-all text-left group"
        >
          <Flame size={20} className="text-orange-400 mb-1.5 group-hover:scale-110 transition-transform" />
          <span className="text-xs font-bold text-orange-200 text-center">Heat Wave</span>
          <span className="text-[11px] text-slate-300 text-center mt-0.5 font-medium">38.0°C Outside</span>
        </button>

        <button
          onClick={handleReset}
          disabled={loadingAction !== null}
          className="flex flex-col items-center justify-center p-3 rounded-lg border border-slate-700 bg-slate-800/80 hover:bg-slate-700 active:scale-95 transition-all text-left group"
        >
          <RotateCcw size={20} className="text-slate-300 mb-1.5 group-hover:scale-110 transition-transform" />
          <span className="text-xs font-bold text-white text-center">Reset Defaults</span>
          <span className="text-[11px] text-slate-300 text-center mt-0.5 font-medium">Nominal state</span>
        </button>
      </div>

      {/* Comfort Guard & Price Response status card */}
      <div className="bg-[#080e1b] border border-slate-800 rounded-lg p-3 text-xs space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck size={15} className="text-sky-400" />
            <span className="font-semibold text-slate-200">Comfort Guard Status:</span>
            <span className="text-sky-300 font-mono font-bold">|PMV| ≤ 0.7</span>
          </div>
          <span
            className={`font-bold px-2 py-0.5 rounded text-[10px] ${
              priceResponseActive
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                : 'bg-slate-800 text-slate-300 border border-slate-700'
            }`}
          >
            {priceResponseActive
              ? isPeak
                ? 'Relax Active (+1.5°C)'
                : 'Pre-Cool Active (-1.0°C)'
              : 'Standby'}
          </span>
        </div>
        <p className="text-[11px] text-slate-300 leading-relaxed">
          The price overlay adjusts setpoints dynamically during TOU windows, strictly clamped
          by a physics comfort guard. PMV is guaranteed to stay within ±0.7 Fanger limits.
        </p>
      </div>

      {/* TOU Tariff Schedule summary + expander */}
      <div className="pt-1">
        <div className="flex items-center justify-between">
          <button
            onClick={() => setShowTariffEditor(!showTariffEditor)}
            className="text-xs text-sky-400 hover:text-sky-300 font-semibold flex items-center gap-1.5 transition-colors"
          >
            {showTariffEditor ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <span>TOU Tariff Schedule & Rates (₹{currentPrice.toFixed(2)}/kWh active)</span>
          </button>
        </div>

        {showTariffEditor && (
          <div className="mt-3 bg-[#080e1b] border border-slate-800 rounded-lg p-3 space-y-3">
            <div className="grid grid-cols-4 gap-2 text-center text-xs font-semibold text-slate-300 pb-1 border-b border-slate-800">
              <span>Time Slot</span>
              <span>Rate (₹/kWh)</span>
              <span>Category</span>
              <span>Action</span>
            </div>
            {slots.map((slot, idx) => (
              <div key={idx} className="grid grid-cols-4 gap-2 items-center text-xs text-slate-200">
                <span className="font-mono text-center text-slate-300">
                  {String(slot.from_h).padStart(2, '0')}:00 – {String(slot.to_h).padStart(2, '0')}:00
                </span>
                <input
                  type="number"
                  step="0.5"
                  min="1"
                  max="50"
                  value={slot.price}
                  onChange={(e) => {
                    const next = [...slots];
                    next[idx] = { ...slot, price: parseFloat(e.target.value) || 0 };
                    setSlots(next);
                  }}
                  className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-center font-mono text-white text-xs"
                />
                <span className="text-center font-medium">
                  {slot.is_peak ? (
                    <span className="text-rose-300 font-bold">Peak</span>
                  ) : slot.price <= 4.0 ? (
                    <span className="text-emerald-300 font-bold">Off-Peak</span>
                  ) : (
                    <span className="text-slate-300 font-medium">Shoulder</span>
                  )}
                </span>
                <div className="flex justify-center">
                  <button
                    onClick={() => {
                      setElectricityPrice(slot.price).then(onRefresh);
                    }}
                    className="text-[10px] px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-sky-300 font-semibold border border-slate-700 transition-colors"
                  >
                    Test Rate
                  </button>
                </div>
              </div>
            ))}
            <div className="flex justify-end pt-2">
              <button
                onClick={handleSaveTariff}
                className="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs font-bold shadow-sm transition-colors"
              >
                Apply Tariff Schedule
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
