// BuildingScene3D.tsx — 3D building view (react-three-fiber).
//
// Layout matches the physics adjacency and BuildingMap.tsx:
//
//   A Conference | B Engineering
//   ----------------------------
//   C Server     | D Reception
//
// P1 built the shell (slabs, low walls, glass partitions, orbit camera).
// P3 added the self-hosted assets: furniture placed per persona and occupant avatars,
// both from frontend/public/models/ (see CREDITS.md).
//
// P4 wires live backend state into every visual:
//
//   state.rooms[id].temperature_c        → floor/wall tint (temperatureToColor)
//   state.rooms[id].occupancy            → avatar count (unchanged from P3)
//   state.rooms[id].co2_ppm              → Co2Haze opacity
//   state.rooms[id].airflow_lps          → AirflowParticles speed + ceiling fan RPM
//   state.rooms[id].overall_comfort_score → comfort badge colour/label
//   state.rooms[id].active_constraint    → amber pulsing beacon ring + label text
//   state.rooms[id].hvac_power_kw        → shown in label
//
// IMPORTANT: No placeholder data remains in this file. PLACEHOLDER_TEMP_C has
// been deleted. Every visual derives from state.rooms[roomId] — the same object
// App.tsx polls from the backend every 1 second. Zero new polling loops added.

import { Suspense, memo, useCallback, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Grid, Html, OrbitControls, useCursor, useGLTF } from '@react-three/drei';
import * as THREE from 'three';
import type { SimulationState, RoomState, RoomId, ConstraintRecord } from '../types';
import { temperatureToColor } from '../utils/temperatureColor';
import {
  FURNITURE_URL,
  PERSONA,
  SEATED_AVATARS,
  STANDING_AVATARS,
  FURNITURE_SCALE,
} from './scene/models';
import { ROOM_SCENE } from './scene/layout';
import InstancedModel from './scene/InstancedModel';
import Avatars, { type AvatarSpec } from './scene/Avatars';
import Co2Haze from './scene/Co2Haze';
import AirflowParticles from './scene/AirflowParticles';

interface Props {
  state: SimulationState;
  selectedRoom: RoomId;
  onSelect: (room: RoomId) => void;
}

// ── Scene units = metres. Room volumes are nominal, not architectural. ─────────
const ROOM_W      = 6.0;
const ROOM_D      = 5.0;
const GAP         = 0.2;
const SLAB_H      = 0.12;
const LOW_WALL_H  = 0.7;
const GLASS_H     = 1.9;
const WALL_T      = 0.16;
const BUILDING_W  = ROOM_W * 2 + GAP;
const BUILDING_D  = ROOM_D * 2 + GAP;

// Fan placement in Room C (room-local metres) — matches P3 layout.ts value
const FAN_POSITION: [number, number, number] = [0, 2.55, 0.3];

const LAYOUT: Record<RoomId, { col: 0 | 1; row: 0 | 1 }> = {
  A: { col: 0, row: 0 },
  B: { col: 1, row: 0 },
  C: { col: 0, row: 1 },
  D: { col: 1, row: 1 },
};

const colX = (col: number) => (col - 0.5) * (ROOM_W + GAP);
const rowZ = (row: number) => (row - 0.5) * (ROOM_D + GAP);

// ── Ceiling fan with live rotation — Room C only ──────────────────────────────
//
// Removed from layout.ts furniture list so InstancedModel doesn't render it
// statically. FanMesh renders it here with airflow_lps-driven rotation.
// useGLTF caches by URL so the GLB is loaded only once.
function FanMesh({
  airflow_lps,
  position,
}: {
  airflow_lps: number;
  position: [number, number, number];
}) {
  const { scene } = useGLTF(FURNITURE_URL.ceilingFan);
  const groupRef  = useRef<THREE.Group>(null);
  // Mirror prop in ref — useFrame reads without re-render
  const afRef = useRef(airflow_lps);
  afRef.current = airflow_lps;

  // Clone once so this instance has its own rotation independent of the cached scene
  const cloned = useMemo(() => scene.clone(true), [scene]);

  useFrame((_, delta) => {
    if (!groupRef.current) return;
    // 0 → 0 rad/s at no airflow; 300 L/s → 6 rad/s (visually convincing)
    const speed = (Math.min(afRef.current, 300) / 300) * 6;
    groupRef.current.rotation.y += speed * delta;
  });

  return (
    <group ref={groupRef} position={position} scale={FURNITURE_SCALE}>
      <primitive object={cloned} />
    </group>
  );
}

// ── Pulsing beacon ring — full lifecycle status (P5) ────────────────────────
//
// amber ring  = active (constraint firing)
// orange ring = renewed (first renewal with 1.5× delta — urgency indicator)
// red ring    = escalated (two failures — requires human attention)
//
// When status is undefined/null the ring is hidden (resolved = no beacon).
// The ring always exists in the scene (visible toggled in useFrame) so the
// useFrame subscription is unconditional — no hook-in-conditional issues.
function ConstraintBeacon({
  constraint,
  status,
  renewals: _renewals = 0,
}: {
  constraint?: string | null;
  status?: string;
  renewals?: number;
}) {
  const meshRef       = useRef<THREE.Mesh>(null);
  const timeRef       = useRef(0);
  const constraintRef = useRef(constraint);
  const statusRef     = useRef(status);
  constraintRef.current = constraint;
  statusRef.current     = status;

  const ringColor = useMemo(() => {
    if (status === 'escalated') return '#ef4444';   // red
    if (status === 'renewed')   return '#f97316';   // orange
    return '#f59e0b';                               // amber (active)
  }, [status]);

  useFrame((_, delta) => {
    timeRef.current += delta;
    if (!meshRef.current) return;
    const active = !!constraintRef.current;
    meshRef.current.visible = active;
    if (active) {
      const mat = meshRef.current.material as THREE.MeshBasicMaterial;
      // Escalated = faster, more alarming pulse
      const freq = statusRef.current === 'escalated' ? 4.5 : 2.5;
      mat.opacity = 0.22 + Math.sin(timeRef.current * freq) * 0.16;
    }
  });

  return (
    <mesh
      ref={meshRef}
      rotation={[-Math.PI / 2, 0, 0]}
      position={[0, 0.02, 0]}
      visible={!!constraint}
    >
      <ringGeometry args={[2.65, 3.05, 48]} />
      <meshBasicMaterial
        color={ringColor}
        transparent
        opacity={0.28}
        depthWrite={false}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}


// ── Room furniture + occupant avatars ─────────────────────────────────────────
const RoomContents = memo(function RoomContents({
  roomId,
  occupancy,
}: {
  roomId: RoomId;
  occupancy: number;
}) {
  const scene = ROOM_SCENE[roomId];

  // Seats first, then overflow standing spots: the avatar count always equals
  // the room's live occupancy (up to the number of defined places). Seated
  // people use rigs with a sitting clip, standers use the idle-only rigs.
  const avatars = useMemo<AvatarSpec[]>(() => {
    const capacity = scene.seats.length + scene.standing.length;
    const total    = Math.max(0, Math.min(Math.round(occupancy), capacity));
    const seated   = Math.min(total, scene.seats.length);

    const specs: AvatarSpec[] = scene.seats.slice(0, seated).map((place, index) => ({
      kind: SEATED_AVATARS[index % SEATED_AVATARS.length],
      ...place,
    }));

    for (let index = 0; index < total - seated; index += 1) {
      specs.push({
        kind: STANDING_AVATARS[index % STANDING_AVATARS.length],
        ...scene.standing[index],
      });
    }

    return specs;
  }, [scene, occupancy]);

  return (
    <>
      {scene.furniture.map(({ kind, placements }) => (
        <InstancedModel key={kind} url={FURNITURE_URL[kind]} placements={placements} />
      ))}
      <Avatars specs={avatars} />
    </>
  );
});

// ── Room floor slab + per-room live visuals ───────────────────────────────────
function RoomFloor({
  roomId,
  room,
  selected,
  onSelect,
  constraintRecord,
  priceResponseActive = false,
  isPeak = false,
}: {
  roomId: RoomId;
  room: RoomState;
  selected: boolean;
  onSelect: (room: RoomId) => void;
  constraintRecord?: ConstraintRecord | null;
  priceResponseActive?: boolean;
  isPeak?: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  useCursor(hovered);

  const { col, row } = LAYOUT[roomId];

  // ── Temperature tint (live) ──────────────────────────────────────────────
  // Same palette as the 2D map: the CSS hsl() string parses straight into
  // THREE.Color. multiplyScalar(0.55) dims the floor so furniture reads over it.
  const tint = useMemo(
    () => new THREE.Color(temperatureToColor(room.temperature_c)).multiplyScalar(0.55),
    [room.temperature_c]
  );

  const outline = useMemo(
    () => new THREE.EdgesGeometry(new THREE.BoxGeometry(ROOM_W, SLAB_H, ROOM_D)),
    []
  );

  // ── Comfort badge ────────────────────────────────────────────────────────
  const comfortColor =
    room.overall_comfort_score >= 75 ? '#10b981' :
    room.overall_comfort_score >= 55 ? '#f59e0b' : '#ef4444';
  const comfortLabel =
    room.overall_comfort_score >= 75 ? 'GOOD' :
    room.overall_comfort_score >= 55 ? 'FAIR' : 'POOR';

  // ── Constraint label (underscore → space for readability) ────────────────
  const constraintText = room.active_constraint
    ? room.active_constraint.replace(/_/g, ' ')
    : null;

  return (
    <group position={[colX(col), -SLAB_H / 2, rowZ(row)]}>

      {/* Floor slab — colour driven by live temperature_c */}
      <mesh
        receiveShadow
        onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = 'pointer'; }}
        onPointerOut={() => { setHovered(false); document.body.style.cursor = 'auto'; }}
        onClick={(e) => { e.stopPropagation(); onSelect(roomId); }}
      >
        <boxGeometry args={[ROOM_W, SLAB_H, ROOM_D]} />
        <meshStandardMaterial
          color={tint}
          emissive={selected ? '#0284c7' : '#000000'}
          emissiveIntensity={selected ? 0.35 : 0}
          roughness={0.8}
          metalness={0.08}
        />
      </mesh>

      <lineSegments geometry={outline}>
        <lineBasicMaterial
          color={selected ? '#38bdf8' : hovered ? '#64748b' : '#334155'}
          linewidth={selected ? 2 : 1}
        />
      </lineSegments>

      {/* Selected room elevated frame */}
      {selected && (
        <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[ROOM_W * 0.46, ROOM_W * 0.48, 4]} />
          <meshBasicMaterial color="#38bdf8" transparent opacity={0.6} side={THREE.DoubleSide} />
        </mesh>
      )}

      {/* CO₂ haze — opacity driven by co2_ppm */}
      <Co2Haze co2_ppm={room.co2_ppm} />

      {/* Airflow particles — speed/opacity driven by airflow_lps */}
      <AirflowParticles airflow_lps={room.airflow_lps} />

      {/* Ceiling fan with live RPM for Room C */}
      {roomId === 'C' && (
        <FanMesh airflow_lps={room.airflow_lps} position={FAN_POSITION} />
      )}

      {/* Price response subtle vent glow (P6 MASTER_PROMPT_3D §3.4) */}
      {priceResponseActive && (
        <mesh position={[0, GLASS_H * 0.95, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.5, 0.8, 24]} />
          <meshBasicMaterial
            color={isPeak ? '#f59e0b' : '#38bdf8'}
            transparent
            opacity={0.35}
            depthWrite={false}
            side={THREE.DoubleSide}
          />
        </mesh>
      )}

      {/* Pulsing beacon ring — amber (active), orange (renewed), red (escalated) */}
      <ConstraintBeacon
        constraint={room.active_constraint}
        status={constraintRecord?.status}
        renewals={constraintRecord?.renewals ?? 0}
      />

      {/* Furniture + avatars (avatar count == room.occupancy exactly) */}
      <Suspense fallback={null}>
        <RoomContents roomId={roomId} occupancy={room.occupancy} />
      </Suspense>

      {/* ── Info label — all values from live backend state ─────────────────
           Clean, high-contrast industrial typography without emojis.
      */}
      <Html
        center
        distanceFactor={16}
        position={[0, GLASS_H * 0.62, 0]}
        zIndexRange={[20, 0]}
        style={{ pointerEvents: 'none' }}
      >
        <div className={`flex flex-col items-center gap-0.5 whitespace-nowrap rounded-lg border px-3 py-2 backdrop-blur-md transition-all shadow-md ${
          selected
            ? 'border-sky-400 bg-[#0c162c]/95 ring-2 ring-sky-500/40'
            : 'border-slate-700/70 bg-[#09101d]/90'
        }`}>
          {/* Zone + persona + selection badge */}
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-extrabold uppercase tracking-widest text-white">
              Zone {roomId}
            </span>
            {selected && (
              <span className="text-[8px] font-bold px-1 py-0.2 rounded bg-sky-500/30 text-sky-200 border border-sky-400/40">
                ACTIVE
              </span>
            )}
          </div>
          <span className="text-[10px] font-semibold tracking-wide text-slate-300">
            {PERSONA[roomId]}
          </span>

          {/* Live temperature */}
          <span className="text-[11px] font-bold text-white font-mono">
            {room.temperature_c.toFixed(1)}°C
          </span>

          {/* Comfort badge: green / amber / red */}
          <span
            className="text-[9px] font-bold uppercase tracking-wide"
            style={{ color: comfortColor }}
          >
            {comfortLabel} · {room.overall_comfort_score.toFixed(0)}
          </span>

          {/* IAQ telemetry */}
          <span className="text-[9px] text-slate-300 font-mono">
            CO₂ {room.co2_ppm.toFixed(0)} ppm · {room.airflow_lps.toFixed(0)} L/s
          </span>

          {/* Active constraint with lifecycle status */}
          {constraintText && (
            <span className="text-[9px] font-bold uppercase tracking-wide flex items-center gap-1" style={{
              color: constraintRecord?.status === 'escalated' ? '#f87171'
                   : constraintRecord?.status === 'renewed'   ? '#fb923c'
                   : '#fde047'
            }}>
              <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
              <span>{constraintText}</span>
              {constraintRecord && constraintRecord.renewals > 0 && (
                <span className="ml-0.5 text-[8px] opacity-80">(x{constraintRecord.renewals + 1})</span>
              )}
            </span>
          )}

          {/* Price response active indicator (P6) */}
          {priceResponseActive && (
            <span
              className={`text-[8px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${
                isPeak
                  ? 'bg-rose-500/25 text-rose-200 border-rose-500/40'
                  : 'bg-emerald-500/25 text-emerald-200 border-emerald-500/40'
              }`}
            >
              TOU {isPeak ? 'RELAX' : 'PRE-COOL'}
            </span>
          )}
        </div>
      </Html>
    </group>
  );
}

// ── Static geometry helpers ───────────────────────────────────────────────────
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

// ── Building — four rooms in the 2×2 grid ─────────────────────────────────────
function Building({
  rooms,
  constraints,
  selectedRoom,
  onSelect,
  priceResponseActive = false,
  isPeak = false,
}: {
  rooms: Record<string, RoomState>;
  constraints?: ConstraintRecord[];
  selectedRoom: RoomId;
  onSelect: (room: RoomId) => void;
  priceResponseActive?: boolean;
  isPeak?: boolean;
}) {
  // Build a quick room→record map from the active constraints in the list
  const constraintByRoom = useMemo(() => {
    const map: Record<string, ConstraintRecord> = {};
    if (constraints) {
      for (const cr of constraints) {
        // Active records take priority (list is active-first from backend)
        if (cr.status === 'active' || cr.status === 'renewed') {
          map[cr.room] = cr;
        }
      }
    }
    return map;
  }, [constraints]);

  return (
    <group>
      {/* Plinth */}
      <mesh position={[0, -SLAB_H - 0.09, 0]} receiveShadow>
        <boxGeometry args={[BUILDING_W + 0.9, 0.18, BUILDING_D + 0.9]} />
        <meshStandardMaterial color="#0b1220" roughness={1} />
      </mesh>

      {/* Room floors (2×2 grid) — each receives its full RoomState */}
      {(['A', 'B', 'C', 'D'] as RoomId[]).map((roomId) => {
        const room = rooms[roomId];
        if (!room) return null;
        return (
          <RoomFloor
            key={roomId}
            roomId={roomId}
            room={room}
            selected={selectedRoom === roomId}
            onSelect={onSelect}
            constraintRecord={constraintByRoom[roomId] ?? null}
            priceResponseActive={priceResponseActive}
            isPeak={isPeak}
          />
        );
      })}


      {/* Outer low walls — kept low so every room is visible from the camera */}
      <LowWall
        position={[0, LOW_WALL_H / 2, -BUILDING_D / 2]}
        size={[BUILDING_W + WALL_T * 2, LOW_WALL_H, WALL_T]}
      />
      <LowWall
        position={[0, LOW_WALL_H / 2, BUILDING_D / 2]}
        size={[BUILDING_W + WALL_T * 2, LOW_WALL_H, WALL_T]}
      />
      <LowWall
        position={[-BUILDING_W / 2, LOW_WALL_H / 2, 0]}
        size={[WALL_T, LOW_WALL_H, BUILDING_D]}
      />
      <LowWall
        position={[BUILDING_W / 2, LOW_WALL_H / 2, 0]}
        size={[WALL_T, LOW_WALL_H, BUILDING_D]}
      />

      {/* Interior glass partitions on the grid lines */}
      <GlassPartition
        position={[0, GLASS_H / 2, 0]}
        size={[WALL_T, GLASS_H, BUILDING_D]}
      />
      <GlassPartition
        position={[0, GLASS_H / 2, 0]}
        size={[BUILDING_W, GLASS_H, WALL_T]}
      />
    </group>
  );
}

// ── FPS sampler — writes to a DOM ref, never re-renders the scene ─────────────
function FrameSampler({ report }: { report: (fps: number) => void }) {
  const frames  = useRef(0);
  const elapsed = useRef(0);

  useFrame((_, delta) => {
    frames.current  += 1;
    elapsed.current += delta;
    if (elapsed.current >= 1) {
      report(Math.round(frames.current / elapsed.current));
      frames.current  = 0;
      elapsed.current = 0;
    }
  });

  return null;
}

// ── Root component ────────────────────────────────────────────────────────────
export default function BuildingScene3D({ state, selectedRoom, onSelect }: Props) {
  const [showPerf, setShowPerf] = useState(false);
  const fpsLabel = useRef<HTMLSpanElement>(null);

  const report = useCallback((fps: number) => {
    if (fpsLabel.current) fpsLabel.current.textContent = `${fps} fps`;
  }, []);

  return (
    <div className="relative w-full aspect-[7/5] rounded-lg overflow-hidden border border-slate-700/50 bg-slate-950">
      <div className="absolute right-3 top-3 z-10 flex items-center gap-2">
        {showPerf && (
          <span
            ref={fpsLabel}
            className="rounded-md border border-white/10 bg-slate-950/80 px-2 py-1 text-[11px] font-semibold tabular-nums text-emerald-300"
          >
            — fps
          </span>
        )}
        <button
          type="button"
          onClick={() => setShowPerf((on) => !on)}
          className={`rounded-md border px-2 py-1 text-[11px] font-semibold transition-colors ${
            showPerf
              ? 'border-emerald-400/40 bg-emerald-500/15 text-emerald-300'
              : 'border-white/10 bg-slate-950/80 text-slate-400 hover:text-slate-200'
          }`}
        >
          FPS
        </button>
      </div>

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

        {/* Pass full rooms + P5 constraints list + P6 price response status */}
        <Building
          rooms={state.rooms}
          constraints={state.constraints}
          selectedRoom={selectedRoom}
          onSelect={onSelect}
          priceResponseActive={state.building?.price_response_active ?? false}
          isPeak={state.building?.is_peak ?? false}
        />

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

        {showPerf && <FrameSampler report={report} />}
      </Canvas>
    </div>
  );
}
