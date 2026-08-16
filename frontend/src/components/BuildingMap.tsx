// BuildingMap.tsx  —  SVG 2×2 floor plan with live state.
//
// Layout:
//   A | B
//   -----
//   C | D
//
// Each room cell shows: name, temperature, humidity, HVAC%, occupancy.
// Clicking selects a room.
// Room background color is derived from temperature (not hardcoded).
// Heat-transfer arrows shown when |ΔT| > 1°C between adjacent rooms.

import React from 'react';
import type { SimulationState, RoomId } from '../types';
import { temperatureToColor, contrastColor } from '../utils/temperatureColor';

interface Props {
  state: SimulationState;
  selectedRoom: RoomId;
  onSelect: (room: RoomId) => void;
}

const ROOM_POSITIONS: Record<string, { row: number; col: number }> = {
  A: { row: 0, col: 0 },
  B: { row: 0, col: 1 },
  C: { row: 1, col: 0 },
  D: { row: 1, col: 1 },
};

// Adjacent pairs with their heat-flow arrow positions (in SVG coords within the map)
const ADJACENCY_ARROWS = [
  { from: 'A', to: 'B', axis: 'h', pos: 'top' },    // horizontal top
  { from: 'C', to: 'D', axis: 'h', pos: 'bot' },    // horizontal bottom
  { from: 'A', to: 'C', axis: 'v', pos: 'left' },   // vertical left
  { from: 'B', to: 'D', axis: 'v', pos: 'right' },  // vertical right
];

const W = 560; const H = 400;
const COL_W = W / 2; const ROW_H = H / 2;
const PAD = 10;

function HvacBar({ power, maxPower }: { power: number; maxPower: number }) {
  const pct = Math.min(1, Math.abs(power) / maxPower);
  const bars = 10;
  const filled = Math.round(pct * bars);
  return (
    <div className="flex gap-px mt-1">
      {Array.from({ length: bars }).map((_, i) => (
        <div
          key={i}
          className={`h-1.5 w-3 rounded-sm ${i < filled ? 'bg-cyan-400' : 'bg-white/20'}`}
        />
      ))}
    </div>
  );
}

export default function BuildingMap({ state, selectedRoom, onSelect }: Props) {
  const rooms = state.rooms;

  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full rounded-lg border border-slate-700/50"
        style={{ background: '#0f172a' }} // slate-900
      >
        <defs>
          <marker id="arrow-flow" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="#94a3b8" />
          </marker>
        </defs>

        {/* Grid lines */}
        <line x1={COL_W} y1={0} x2={COL_W} y2={H} stroke="#ffffff10" strokeWidth={1} />
        <line x1={0} y1={ROW_H} x2={W} y2={ROW_H} stroke="#ffffff10" strokeWidth={1} />

        {/* Heat-transfer arrows between rooms */}
        {ADJACENCY_ARROWS.map(({ from, to, axis, pos }) => {
          const rFrom = rooms[from];
          const rTo   = rooms[to];
          if (!rFrom || !rTo) return null;
          const deltaT = rTo.temperature_c - rFrom.temperature_c;
          if (Math.abs(deltaT) < 1.0) return null;  // negligible difference

          // Arrow from hot to cold room
          const flowDir = deltaT > 0 ? 1 : -1; // +1 = from→to, -1 = to→from
          const intensity = Math.min(Math.abs(deltaT) / 8, 1); // opacity

          let x1, y1, x2, y2;
          if (axis === 'h') {
            y1 = y2 = pos === 'top' ? ROW_H / 2 : ROW_H + ROW_H / 2;
            if (flowDir > 0) { x1 = COL_W - 25; x2 = COL_W + 25; }
            else { x1 = COL_W + 25; x2 = COL_W - 25; }
          } else {
            x1 = x2 = pos === 'left' ? COL_W / 2 : COL_W + COL_W / 2;
            if (flowDir > 0) { y1 = ROW_H - 25; y2 = ROW_H + 25; }
            else { y1 = ROW_H + 25; y2 = ROW_H - 25; }
          }

          return (
            <line
              key={`transfer-${from}-${to}`}
              x1={x1} y1={y1} x2={x2} y2={y2}
              stroke="#94a3b8"
              strokeWidth={1 + intensity * 2}
              strokeDasharray="4 2"
              opacity={0.3 + intensity * 0.7}
              markerEnd="url(#arrow-flow)"
            />
          );
        })}

        {/* Rooms */}
        {(['A', 'B', 'C', 'D'] as RoomId[]).map((rid) => {
          const r = rooms[rid];
          if (!r) return null;
          const { row, col } = ROOM_POSITIONS[rid];
          const x = col * COL_W + PAD;
          const y = row * ROW_H + PAD;
          const rw = COL_W - PAD * 2;
          const rh = ROW_H - PAD * 2;
          const isSelected = selectedRoom === rid;
          
          // Formal aesthetics: subtle tinted backgrounds instead of bright colors
          const bgColor = temperatureToColor(r.temperature_c);
          const fgColor = '#f8fafc'; // always slate-50 for formal dark mode text
          
          const hvacPct = Math.round((Math.abs(r.hvac_power_kw) / 5.0) * 100);
          const isCooling = r.hvac_power_kw < 0;
          const hvacColor = isCooling ? '#38bdf8' : '#fb923c';

          return (
            <g key={rid} onClick={() => onSelect(rid)} style={{ cursor: 'pointer' }} className="transition-all">
              {/* Room background */}
              <rect
                x={x} y={y} width={rw} height={rh}
                rx={6}
                fill={bgColor}
                fillOpacity={0.15}
                stroke={isSelected ? '#38bdf8' : '#334155'}
                strokeWidth={isSelected ? 2 : 1}
              />

              {/* Room label (top left) */}
              <text x={x + 16} y={y + 28} fill="#94a3b8" fontSize={13} fontWeight="600" fontFamily="Inter, sans-serif" letterSpacing="1">
                ZONE {rid}
              </text>

              {/* Center Temperature */}
              <text x={x + rw / 2} y={y + rh / 2 + 8} textAnchor="middle" fill={fgColor} fontSize={40} fontWeight="700" fontFamily="Inter, sans-serif">
                {r.temperature_c.toFixed(1)}°
              </text>
              <text x={x + rw / 2} y={y + rh / 2 + 28} textAnchor="middle" fill="#94a3b8" fontSize={12} fontFamily="Inter, sans-serif">
                SP: {r.setpoint_c.toFixed(1)}°C
              </text>

              {/* Bottom stats row */}
              <text x={x + 16} y={y + rh - 16} fill="#94a3b8" fontSize={11} fontFamily="Inter, sans-serif">
                RH: {r.humidity_pct.toFixed(0)}%
              </text>
              <text x={x + rw / 2} y={y + rh - 16} textAnchor="middle" fill="#94a3b8" fontSize={11} fontFamily="Inter, sans-serif">
                Occ: {r.occupancy}
              </text>
              <text x={x + rw - 16} y={y + rh - 16} textAnchor="end" fill={hvacPct > 0 ? hvacColor : '#94a3b8'} fontSize={11} fontFamily="Inter, sans-serif" fontWeight={hvacPct > 0 ? '600' : '400'}>
                {hvacPct > 0 ? (isCooling ? 'CLG ' : 'HTG ') : 'IDLE '}{hvacPct}%
              </text>

              {/* Selection indicator */}
              {isSelected && (
                <rect x={x} y={y} width={rw} height={rh} rx={6} fill="none" stroke="#38bdf8" strokeWidth={2} opacity={0.6} className="pointer-events-none" />
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
