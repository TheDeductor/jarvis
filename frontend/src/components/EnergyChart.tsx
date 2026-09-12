// EnergyChart.tsx  —  Adaptive energy & cost vs baseline over simulation time (P6).
// Both values come from backend — baseline is independently simulated.

import React, { useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceArea,
} from 'recharts';
import type { HistoryPoint } from '../types';

interface Props {
  history: HistoryPoint[];
}

function minutesToLabel(minutes: number): string {
  const totalMin = (480 + minutes) % 1440;
  const h = Math.floor(totalMin / 60);
  const m = Math.floor(totalMin % 60);
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
}

export default function EnergyChart({ history }: Props) {
  const [metric, setMetric] = useState<'cost' | 'energy'>('cost');

  const data = history.map((pt) => ({
    time: minutesToLabel(pt.simulation_time_minutes),
    adaptiveEnergy: Number(pt.total_energy_kwh.toFixed(3)),
    baselineEnergy: Number(pt.baseline_energy_kwh.toFixed(3)),
    adaptiveCost: Number((pt.cost ?? (pt.total_energy_kwh * 6.0)).toFixed(2)),
    baselineCost: Number((pt.baseline_cost ?? (pt.baseline_energy_kwh * 6.0)).toFixed(2)),
    isPeak: Boolean(pt.is_peak),
  }));

  const latest = history[history.length - 1];
  const adaptiveCost = latest?.cost ?? (latest ? latest.total_energy_kwh * 6.0 : 0);
  const baselineCost = latest?.baseline_cost ?? (latest ? latest.baseline_energy_kwh * 6.0 : 0);
  const costSavings = baselineCost - adaptiveCost;
  const savingsPct = baselineCost > 0 ? (costSavings / baselineCost) * 100 : 0;
  const peakKw = latest?.peak_kw_15min ?? 0;

  // Find continuous peak segments for chart shading
  const peakSegments: { start: string; end: string }[] = [];
  let currentStart: string | null = null;
  data.forEach((d, i) => {
    if (d.isPeak && !currentStart) {
      currentStart = d.time;
    } else if (!d.isPeak && currentStart) {
      peakSegments.push({ start: currentStart, end: data[i - 1].time });
      currentStart = null;
    }
  });
  if (currentStart && data.length > 0) {
    peakSegments.push({ start: currentStart, end: data[data.length - 1].time });
  }

  return (
    <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400">
            {metric === 'cost' ? 'Tariff Cost Parity (₹)' : 'Cumulative Energy (kWh)'} — Adaptive vs Baseline
          </h3>
          <div className="flex items-center gap-3 mt-1 text-[11px] text-slate-400">
            {metric === 'cost' && costSavings > 0 && (
              <span className="text-emerald-400 font-semibold">
                Savings: ₹{costSavings.toFixed(2)} ({savingsPct.toFixed(1)}%)
              </span>
            )}
            {peakKw > 0 && (
              <span className="text-amber-400 font-medium">
                Rolling 15-min Peak: {peakKw.toFixed(2)} kW
              </span>
            )}
          </div>
        </div>

        {/* View toggle */}
        <div className="flex items-center gap-1 rounded-lg border border-slate-700/60 bg-slate-900/60 p-0.5">
          <button
            onClick={() => setMetric('cost')}
            className={`rounded-md px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider transition-colors ${
              metric === 'cost'
                ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            💰 Cost (₹)
          </button>
          <button
            onClick={() => setMetric('energy')}
            className={`rounded-md px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider transition-colors ${
              metric === 'energy'
                ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            ⚡ Energy (kWh)
          </button>
        </div>
      </div>

      {data.length < 2 ? (
        <p className="text-slate-500 text-sm text-center py-10 font-medium">
          Awaiting simulation data...
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={210}>
          <LineChart data={data} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />

            {/* Shaded peak windows */}
            {peakSegments.map((seg, idx) => (
              <ReferenceArea
                key={idx}
                x1={seg.start}
                x2={seg.end}
                fill="#f43f5e"
                fillOpacity={0.08}
                stroke="#f43f5e"
                strokeOpacity={0.2}
              />
            ))}

            <XAxis
              dataKey="time"
              tick={{ fill: '#64748b', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              interval={Math.max(1, Math.floor(data.length / 8))}
            />
            <YAxis
              tick={{ fill: '#64748b', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              unit={metric === 'cost' ? ' ₹' : ' kWh'}
            />
            <Tooltip
              contentStyle={{
                background: '#0f172a',
                border: '1px solid #334155',
                borderRadius: 8,
                boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
              }}
              labelStyle={{ color: '#94a3b8', fontSize: 12, marginBottom: 4 }}
              itemStyle={{ color: '#f8fafc', fontSize: 13, fontWeight: 500 }}
            />
            <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8', paddingTop: 6 }} />

            {metric === 'cost' ? (
              <>
                <Line
                  type="monotone"
                  dataKey="adaptiveCost"
                  name="Adaptive Cost (₹)"
                  stroke="#38bdf8"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="baselineCost"
                  name="Baseline Cost (₹)"
                  stroke="#f87171"
                  strokeWidth={2}
                  strokeDasharray="5 3"
                  dot={false}
                  isAnimationActive={false}
                />
              </>
            ) : (
              <>
                <Line
                  type="monotone"
                  dataKey="adaptiveEnergy"
                  name="Adaptive Energy (kWh)"
                  stroke="#22d3ee"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="baselineEnergy"
                  name="Baseline Energy (kWh)"
                  stroke="#f87171"
                  strokeWidth={2}
                  strokeDasharray="5 3"
                  dot={false}
                  isAnimationActive={false}
                />
              </>
            )}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
