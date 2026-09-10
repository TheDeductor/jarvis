// BuildingScene3D.tsx  —  3D building view (react-three-fiber).
//
// Layout matches the physics adjacency and BuildingMap.tsx:
//
//   A Conference | B Engineering
//   ----------------------------
//   C Server     | D Reception
//
// P1 scope: geometry, lighting and orbit camera only. All room values are
// HARDCODED placeholders (PLACEHOLDER_TEMP_C) — P4 replaces them with the
// polled `state` prop. Props mirror BuildingMap so App.tsx can toggle views.

import { useMemo, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { Grid, Html, OrbitControls, useCursor } from '@react-three/drei';
import * as THREE from 'three';
import type { SimulationState, RoomId } from '../types';
import { temperatureToColor } from '../utils/temperatureColor';

interface Props {
  state: SimulationState;
  selectedRoom: RoomId;
  onSelect: (room: RoomId) => void;
}

// ── Scene units = metres. Room volumes are nominal, not architectural. ────────
const ROOM_W = 6.0;
const ROOM_D = 5.0;
const GAP = 0.2;
const SLAB_H = 0.12;
const LOW_WALL_H = 0.7;
const GLASS_H = 1.9;
const WALL_T = 0.16;
const BUILDING_W = ROOM_W * 2 + GAP;
const BUILDING_D = ROOM_D * 2 + GAP;

const LAYOUT: Record<RoomId, { col: 0 | 1; row: 0 | 1; persona: string }> = {
  A: { col: 0, row: 0, persona: 'Conference' },
  B: { col: 1, row: 0, persona: 'Engineering' },
  C: { col: 0, row: 1, persona: 'Server Room' },
  D: { col: 1, row: 1, persona: 'Reception' },
};

// P1 placeholders — P4 swaps these for state.rooms[roomId].temperature_c.
const PLACEHOLDER_TEMP_C: Record<RoomId, number> = { A: 22.4, B: 27.6, C: 21.3, D: 25.1 };

const colX = (col: number) => (col - 0.5) * (ROOM_W + GAP);
const rowZ = (row: number) => (row - 0.5) * (ROOM_D + GAP);

function RoomFloor({
  roomId,
  selected,
  onSelect,
}: {
  roomId: RoomId;
  selected: boolean;
  onSelect: (room: RoomId) => void;
}) {
  const [hovered, setHovered] = useState(false);
  useCursor(hovered);

  const { col, row, persona } = LAYOUT[roomId];
  const tempC = PLACEHOLDER_TEMP_C[roomId];

  // Same palette as the 2D map: the CSS hsl() string parses straight into THREE.Color.
  const tint = useMemo(
    () => new THREE.Color(temperatureToColor(tempC)).multiplyScalar(0.55),
    [tempC]
  );
  const outline = useMemo(
    () => new THREE.EdgesGeometry(new THREE.BoxGeometry(ROOM_W, SLAB_H, ROOM_D)),
    []
  );

  return (
    <group position={[colX(col), -SLAB_H / 2, rowZ(row)]}>
      <mesh
        receiveShadow
        onPointerOver={(e) => {
          e.stopPropagation();
          setHovered(true);
        }}
        onPointerOut={() => setHovered(false)}
        onClick={(e) => {
          e.stopPropagation();
          onSelect(roomId);
        }}
      >
        <boxGeometry args={[ROOM_W, SLAB_H, ROOM_D]} />
        <meshStandardMaterial
          color={tint}
          emissive={selected ? '#0ea5e9' : '#000000'}
          emissiveIntensity={selected ? 0.25 : 0}
          roughness={0.85}
          metalness={0.05}
        />
      </mesh>

      <lineSegments geometry={outline}>
        <lineBasicMaterial color={selected ? '#38bdf8' : hovered ? '#475569' : '#334155'} />
      </lineSegments>

      <Html
        center
        distanceFactor={16}
        position={[0, GLASS_H * 0.62, 0]}
        zIndexRange={[20, 0]}
        style={{ pointerEvents: 'none' }}
      >
        <div className="flex flex-col items-center gap-0.5 whitespace-nowrap rounded-md border border-white/10 bg-slate-950/70 px-2.5 py-1 backdrop-blur-sm">
          <span className="text-[11px] font-bold uppercase tracking-widest text-slate-200">
            Zone {roomId}
          </span>
          <span className="text-[10px] font-medium tracking-wide text-slate-400">{persona}</span>
          <span className="text-[10px] font-semibold text-slate-300">{tempC.toFixed(1)}°C</span>
        </div>
      </Html>
    </group>
  );
}

function LowWall({
  position,
  size,
}: {
  position: [number, number, number];
  size: [number, number, number];
}) {
  return (
    <mesh position={position} castShadow receiveShadow>
      <boxGeometry args={size} />
      <meshStandardMaterial color="#1e293b" roughness={0.9} metalness={0.05} />
    </mesh>
  );
}

function GlassPartition({
  position,
  size,
}: {
  position: [number, number, number];
  size: [number, number, number];
}) {
  return (
    <mesh position={position}>
      <boxGeometry args={size} />
      <meshStandardMaterial
        color="#7dd3fc"
        transparent
        opacity={0.12}
        roughness={0.05}
        metalness={0}
        side={THREE.DoubleSide}
        depthWrite={false}
      />
    </mesh>
  );
}

function Building({
  selectedRoom,
  onSelect,
}: {
  selectedRoom: RoomId;
  onSelect: (room: RoomId) => void;
}) {
  return (
    <group>
      {/* Plinth */}
      <mesh position={[0, -SLAB_H - 0.09, 0]} receiveShadow>
        <boxGeometry args={[BUILDING_W + 0.9, 0.18, BUILDING_D + 0.9]} />
        <meshStandardMaterial color="#0b1220" roughness={1} />
      </mesh>

      {/* Room floors (2x2 grid) */}
      {(['A', 'B', 'C', 'D'] as RoomId[]).map((rid) => (
        <RoomFloor
          key={rid}
          roomId={rid}
          selected={selectedRoom === rid}
          onSelect={onSelect}
        />
      ))}

      {/* Outer low walls — kept low so every room stays visible from the camera */}
      <LowWall position={[0, LOW_WALL_H / 2, -BUILDING_D / 2]} size={[BUILDING_W + WALL_T * 2, LOW_WALL_H, WALL_T]} />
      <LowWall position={[0, LOW_WALL_H / 2, BUILDING_D / 2]} size={[BUILDING_W + WALL_T * 2, LOW_WALL_H, WALL_T]} />
      <LowWall position={[-BUILDING_W / 2, LOW_WALL_H / 2, 0]} size={[WALL_T, LOW_WALL_H, BUILDING_D]} />
      <LowWall position={[BUILDING_W / 2, LOW_WALL_H / 2, 0]} size={[WALL_T, LOW_WALL_H, BUILDING_D]} />

      {/* Interior glass partitions on the grid lines */}
      <GlassPartition position={[0, GLASS_H / 2, 0]} size={[WALL_T, GLASS_H, BUILDING_D]} />
      <GlassPartition position={[0, GLASS_H / 2, 0]} size={[BUILDING_W, GLASS_H, WALL_T]} />
    </group>
  );
}

export default function BuildingScene3D({ selectedRoom, onSelect }: Props) {
  return (
    <div className="w-full aspect-[7/5] rounded-lg overflow-hidden border border-slate-700/50 bg-slate-950">
      <Canvas shadows dpr={[1, 2]} camera={{ position: [8.5, 7.5, 10.5], fov: 40 }}>
        <color attach="background" args={['#070c17']} />

        <ambientLight intensity={0.7} />
        <directionalLight
          position={[9, 13, 7]}
          intensity={1.7}
          castShadow
          shadow-mapSize={[1024, 1024]}
          shadow-camera-left={-11}
          shadow-camera-right={11}
          shadow-camera-top={10}
          shadow-camera-bottom={-10}
          shadow-camera-near={1}
          shadow-camera-far={40}
        />

        <Building selectedRoom={selectedRoom} onSelect={onSelect} />

        <Grid
          position={[0, -SLAB_H - 0.19, 0]}
          args={[60, 60]}
          cellSize={1}
          cellColor="#1e293b"
          sectionSize={5}
          sectionColor="#334155"
          fadeDistance={52}
          fadeStrength={1.5}
        />

        <OrbitControls
          target={[0, 0, 0]}
          enableDamping
          dampingFactor={0.08}
          enablePan={false}
          minDistance={8}
          maxDistance={32}
          maxPolarAngle={Math.PI / 2.3}
        />
      </Canvas>
    </div>
  );
}
