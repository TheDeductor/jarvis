import React from 'react';
import type { SimulationState } from '../types';
import { Zap } from 'lucide-react';

interface Props {
  state: SimulationState;
}

function minutesToTime(minutes: number): string {
  // Simulation starts at 08:00
  const totalMin = (480 + minutes) % 1440;
  const h = Math.floor(totalMin / 60);
  const m = Math.floor(totalMin % 60);
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
}

function Stat({ label, value, highlight }: { label: string; value: string; highlight?: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-slate-800">
      <span className="text-slate-300 text-xs font-semibold">{label}</span>
      <span className={`text-sm font-semibold font-mono ${highlight ?? 'text-slate-100'}`}>{value}</span>
    </div>
  );
}

export default function EnvironmentPanel({ state }: Props) {
  const { building } = state;
  const energyDiff = building.total_energy_kwh - building.baseline_energy_kwh;
  const diffColor = energyDiff <= 0 ? 'text-emerald-400' : 'text-amber-400';
  const diffStr = (energyDiff >= 0 ? '+' : '') + energyDiff.toFixed(3);

  const costToday = building.cost_today ?? building.estimated_cost;
  const baselineCost = building.baseline_cost_today ?? 0;
  const costSavings = baselineCost - costToday;
  const costSavingsColor = costSavings >= 0 ? 'text-emerald-400' : 'text-amber-400';

  const baseComfort = building.baseline_average_comfort ?? 0;
  const comfortParityDiff = building.average_comfort - baseComfort;

  const isPeak = building.is_peak ?? false;
  const isPrePeak = building.is_pre_peak ?? false;
  const priceResponseActive = building.price_response_active ?? false;
  const currentPrice = building.current_price ?? state.electricity_price_per_kwh;

  return (
    <div className="bg-[#0c1424] border border-slate-800 rounded-xl p-5 space-y-4 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-bold uppercase tracking-widest text-slate-200">
          System Overview & Metrics
        </h2>
        {priceResponseActive && (
          <span className="text-[10px] font-bold px-2.5 py-1 rounded-md bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1">
            <Zap size={12} />
            <span>Price Response</span>
          </span>
        )}
      </div>

      <div className="space-y-0.5">
        <Stat label="Simulation Time" value={minutesToTime(state.simulation_time_minutes)} />
        <Stat label="Outdoor Temperature" value={`${state.outside_temperature_c.toFixed(1)} °C`} />
        <Stat
          label="Active Electricity Rate"
          value={`₹${currentPrice.toFixed(2)}/kWh ${isPeak ? '(PEAK)' : isPrePeak ? '(PRE-PEAK)' : ''}`}
          highlight={isPeak ? 'text-rose-300 font-bold' : isPrePeak ? 'text-amber-300 font-bold' : undefined}
        />
      </div>

      <div className="h-px bg-slate-800" />

      <div className="space-y-0.5">
        <Stat
          label="Global Comfort Score"
          value={`${building.average_comfort.toFixed(1)}/100 (Base: ${baseComfort > 0 ? baseComfort.toFixed(1) : '—'})`}
          highlight={comfortParityDiff >= 0 ? 'text-emerald-400' : 'text-slate-100'}
        />
        <Stat label="Current HVAC Power" value={`${building.current_power_kw.toFixed(2)} kW`} />
        {building.peak_kw_15min !== undefined && building.peak_kw_15min > 0 && (
          <Stat label="Peak 15-min Demand" value={`${building.peak_kw_15min.toFixed(2)} kW`} highlight="text-amber-400" />
        )}
        <Stat label="Total Building Energy" value={`${building.total_energy_kwh.toFixed(3)} kWh`} />
        <Stat label="Baseline Target Energy" value={`${building.baseline_energy_kwh.toFixed(3)} kWh`} />
        <div className="flex items-center justify-between py-2 border-b border-slate-800">
          <span className="text-slate-300 text-xs font-semibold">Energy Variance</span>
          <span className={`text-sm font-bold font-mono ${diffColor}`}>{diffStr} kWh</span>
        </div>
        <Stat label="Adaptive Energy Cost" value={`₹${costToday.toFixed(2)}`} highlight="text-sky-300 font-bold" />
        {baselineCost > 0 && (
          <Stat label="Baseline Estimated Cost" value={`₹${baselineCost.toFixed(2)}`} />
        )}
        {baselineCost > 0 && (
          <div className="flex items-center justify-between py-2 border-b border-slate-800">
            <span className="text-slate-300 text-xs font-semibold">Net Tariff Savings</span>
            <span className={`text-sm font-bold font-mono ${costSavingsColor}`}>
              {costSavings >= 0 ? '−' : '+'}₹{Math.abs(costSavings).toFixed(2)}
            </span>
          </div>
        )}
      </div>

      <p className="text-xs text-slate-300 italic pt-1">
        Telemetry fed continuously from physics engine.
      </p>
    </div>
  );
}
