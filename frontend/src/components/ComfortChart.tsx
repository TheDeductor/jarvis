import React from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ReferenceLine,
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

export default function ComfortChart({ history, roomId }: Props) {
  const data = history.map((pt) => ({
    time: minutesToLabel(pt.simulation_time_minutes),
    comfort: pt.rooms[roomId]?.comfort_score ?? null,
  }));

  return (
    <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5">
      <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-4">
        Zone {roomId} — Comfort Score
      </h3>
      {data.length < 2 ? (
        <p className="text-slate-500 text-sm text-center py-10 font-medium">
          Awaiting simulation data...
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={data} margin={{ top: 5, right: 10, left: -15, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
            <XAxis
              dataKey="time" tick={{ fill: '#64748b', fontSize: 10 }}
              axisLine={false} tickLine={false}
              interval={Math.max(1, Math.floor(data.length / 8))}
            />
            <YAxis 
              domain={[0, 100]} 
              tick={{ fill: '#64748b', fontSize: 10 }} 
              axisLine={false} tickLine={false}
            />
            <ReferenceLine y={85} stroke="#10b981" strokeDasharray="4 4" opacity={0.3} label={{ value:'Good', fill:'#10b981', fontSize:10, position: 'insideTopLeft' }} />
            <ReferenceLine y={65} stroke="#f59e0b" strokeDasharray="4 4" opacity={0.3} label={{ value:'Fair', fill:'#f59e0b', fontSize:10, position: 'insideTopLeft' }} />
            <Tooltip
              contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
              labelStyle={{ color: '#94a3b8', fontSize: 12, marginBottom: 4 }}
              itemStyle={{ color: '#f8fafc', fontSize: 13, fontWeight: 500 }}
            />
            <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8', paddingTop: 10 }} />
            <Line
              type="monotone"
              dataKey="comfort"
              name="Comfort Score (0–100)"
              stroke="#6366f1"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
