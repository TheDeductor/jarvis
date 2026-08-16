import React from 'react';
import type { SimulationState } from '../types';

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

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-slate-700/30">
      <span className="text-slate-400 text-xs font-medium">{label}</span>
      <span className="text-slate-200 text-sm font-semibold">{value}</span>
    </div>
  );
}

export default function EnvironmentPanel({ state }: Props) {
  const { building } = state;
  const energyDiff = building.total_energy_kwh - building.baseline_energy_kwh;
  const diffColor = energyDiff <= 0 ? 'text-emerald-400' : 'text-amber-500';
  const diffStr = (energyDiff >= 0 ? '+' : '') + energyDiff.toFixed(3);

  return (
    <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5 space-y-4">
      <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">
        System Overview
      </h2>

      <div className="space-y-1">
        <Stat label="Sim Time"     value={minutesToTime(state.simulation_time_minutes)} />
        <Stat label="Outside Temp" value={`${state.outside_temperature_c.toFixed(1)} °C`} />
        <Stat label="Energy Rate"  value={`₹${state.electricity_price_per_kwh.toFixed(2)}/kWh`} />
      </div>

      <div className="h-px bg-slate-700/50" />

      <div className="space-y-1">
        <Stat label="Global Comfort" value={`${building.average_comfort.toFixed(1)}/100`} />
        <Stat label="HVAC Load"      value={`${building.current_power_kw.toFixed(2)} kW`} />
        <Stat label="Total Energy"   value={`${building.total_energy_kwh.toFixed(3)} kWh`} />
        <Stat label="Baseline Target"value={`${building.baseline_energy_kwh.toFixed(3)} kWh`} />
        <div className="flex items-center justify-between py-1.5 border-b border-slate-700/30">
          <span className="text-slate-400 text-xs font-medium">Energy Variance</span>
          <span className={`text-sm font-bold ${diffColor}`}>{diffStr} kWh</span>
        </div>
        <Stat label="Est. OpEx"      value={`₹${building.estimated_cost.toFixed(2)}`} />
      </div>

      <p className="text-xs text-slate-500 italic mt-2">
        Data fed from digital twin core simulation.
      </p>
    </div>
  );
}
