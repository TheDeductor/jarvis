// TemperatureChart.tsx  —  Room temperature + setpoint over simulation time.
// Values sourced exclusively from backend history — no fake data.

import React from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import type { HistoryPoint, RoomId } from '../types';

interface Props {
  history: HistoryPoint[];
  roomId: RoomId;
}

function minutesToLabel(minutes: number): string {
  const totalMin = (480 + minutes) % 1440;
  const h = Math.floor(totalMin / 60);
  const m = Math.floor(totalMin % 60);
  return `${h.toString().padStart(2,'0')}:${m.toString().padStart(2,'0')}`;
}

export default function TemperatureChart({ history, roomId }: Props) {
  const data = history.map((pt) => ({
    time: minutesToLabel(pt.simulation_time_minutes),
    temperature: pt.rooms[roomId]?.temperature_c ?? null,
    setpoint: pt.rooms[roomId]?.setpoint_c ?? null,
  }));

  return (
    <div className="bg-[#0c1424] border border-slate-800 rounded-xl p-5 shadow-sm">
      <h3 className="text-xs font-bold uppercase tracking-widest text-slate-200 mb-4">
        Zone {roomId} — Temperature Telemetry
      </h3>
      {data.length < 2 ? (
        <p className="text-slate-300 text-sm text-center py-12 font-medium">
          Awaiting simulation data...
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={data} margin={{ top: 5, right: 10, left: -15, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis
              dataKey="time" tick={{ fill: '#94a3b8', fontSize: 10, fontWeight: 500 }}
              axisLine={false} tickLine={false}
              interval={Math.max(1, Math.floor(data.length / 8))}
            />
            <YAxis
              domain={['auto', 'auto']}
              tick={{ fill: '#94a3b8', fontSize: 10, fontWeight: 500 }}
              axisLine={false} tickLine={false}
              unit="°"
            />
            <Tooltip
              contentStyle={{ background: '#0a101d', border: '1px solid #1e293b', borderRadius: 8, boxShadow: '0 8px 16px -2px rgb(0 0 0 / 0.5)' }}
              labelStyle={{ color: '#cbd5e1', fontSize: 12, marginBottom: 4, fontWeight: 600 }}
              itemStyle={{ color: '#ffffff', fontSize: 13, fontWeight: 600 }}
            />
            <Legend wrapperStyle={{ fontSize: 11, color: '#cbd5e1', paddingTop: 10 }} />
            <Line
              type="monotone"
              dataKey="temperature"
              name="Temperature (°C)"
              stroke="#38bdf8"
              strokeWidth={2.5}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="setpoint"
              name="Setpoint (°C)"
              stroke="#fb923c"
              strokeWidth={2}
              strokeDasharray="6 3"
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
