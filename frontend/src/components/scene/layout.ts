// layout.ts — per-room furniture arrangement, in room-local metres.
//
//   A Conference | B Engineering
//   ----------------------------
//   C Server     | D Reception
//
// Room-local frame: origin at the room centre, x to the right (east), z toward the
// viewer (south). Room shells are 6 x 5 m. yaw 0 means the model faces +Z.
//
// Every placement is derived from the measured model footprints (see CREDITS/§P3
// notes), so clearances are real: e.g. the engineering desk is 1.17 x 0.69 m with
// its 0.78 m top at y = 0.768, and chair rows leave a 1.04 m centre aisle.

import { FURNITURE_SCALE, type FurnitureKind, type Placement, type Seat } from './models';
import type { RoomId } from '../../types';

const HALF_PI = Math.PI / 2;

// desk.glb = 0.734 x 0.384 x 0.392 units; these multipliers (on top of
// FURNITURE_SCALE) give a 1.17 x 0.77 x 0.69 m workstation.
const DESK_SCALE: [number, number, number] = [0.8, 1, 0.875];
const DESK_TOP_Y = 0.384 * FURNITURE_SCALE;

function rot(ry: number, dx: number, dz: number): { dx: number; dz: number } {
  const c = Math.cos(ry);
  const s = Math.sin(ry);
  return { dx: dx * c + dz * s, dz: -dx * s + dz * c };
}

// Offsets are expressed in a pod's own frame (user side = +Z) and rotated into the room.
function podLocal(x: number, z: number, ry: number) {
  return (dx: number, dz: number): Placement => {
    const o = rot(ry, dx, dz);
    return { x: x + o.dx, z: z + o.dz, ry };
  };
}

const SCREEN_DZ = -0.12;
const KEYBOARD_DZ = 0.16;
const MOUSE_DX = 0.34;
const SEAT_DZ = 0.72;

interface Workstation {
  desk: Placement;
  screen: Placement;
  keyboard: Placement;
  mouse: Placement;
  seat: Seat;
}

function workstation(x: number, z: number, ry: number): Workstation {
  const at = podLocal(x, z, ry);
  const seat = at(0, SEAT_DZ);
  return {
    desk: { ...at(0, 0), scale: DESK_SCALE },
    screen: { ...at(0, SCREEN_DZ), y: DESK_TOP_Y },
    keyboard: { ...at(0, KEYBOARD_DZ), y: DESK_TOP_Y },
    mouse: { ...at(MOUSE_DX, KEYBOARD_DZ), y: DESK_TOP_Y },
    seat: { x: seat.x, z: seat.z, ry: ry + Math.PI },
  };
}

// ── A — Conference: 2.30 x 1.21 m table, 8 chairs, 2 plants ──────────────────
const A_TABLE: Placement = { x: 0, z: 0, scale: [1.35, 1, 1.35] };

const A_SIDE_X = [-0.75, 0, 0.75];
const A_CHAIRS: Seat[] = [
  ...A_SIDE_X.map((x) => ({ x, z: -0.905, ry: 0 })),
  ...A_SIDE_X.map((x) => ({ x, z: 0.905, ry: Math.PI })),
  { x: -1.45, z: 0, ry: HALF_PI },
  { x: 1.45, z: 0, ry: -HALF_PI },
];

// ── B — Engineering: 8 desks in two facing rows of four, 1.04 m centre aisle ──
const B_DESK_X = [-2.1, -0.7, 0.7, 2.1];
const B_PODS: Workstation[] = [
  ...B_DESK_X.map((x) => workstation(x, -1.55, 0)),
  ...B_DESK_X.map((x) => workstation(x, 1.55, Math.PI)),
];

// ── C — Server / IT: 3 rack cabinets, one IT bench ───────────────────────────
const C_RACK_SCALE: [number, number, number] = [0.5, 1.25, 1];
const C_RACKS: Placement[] = [-0.9, 0, 0.9].map((x) => ({
  x,
  z: -1.95,
  scale: C_RACK_SCALE,
}));
const C_POD = workstation(-1.8, 1.35, 0);

// ── D — Reception: 3.23 m counter, lounge corner, rug ───────────────────────
const D_COUNTER: Placement = { x: 0, z: -1.2, ry: Math.PI, scale: [2.2, 1, 1.2] };

export interface RoomScene {
  furniture: { kind: FurnitureKind; placements: Placement[] }[];
  seats: Seat[];
  standing: Seat[];
}

export const ROOM_SCENE: Record<RoomId, RoomScene> = {
  A: {
    furniture: [
      { kind: 'tableCross', placements: [A_TABLE] },
      { kind: 'chairModernCushion', placements: A_CHAIRS.map((c) => ({ x: c.x, z: c.z, ry: c.ry })) },
      {
        kind: 'plantSmall1',
        placements: [
          { x: -2.6, z: -2.1 },
          { x: 2.6, z: 2.1 },
        ],
      },
    ],
    seats: A_CHAIRS,
    standing: [
      { x: -2.6, z: 0.2, ry: HALF_PI },
      { x: 2.6, z: 0.2, ry: -HALF_PI },
      { x: -2.5, z: -1.8, ry: HALF_PI },
      { x: 2.5, z: -1.8, ry: -HALF_PI },
      { x: -2.5, z: 1.8, ry: HALF_PI },
      { x: 2.5, z: 1.8, ry: -HALF_PI },
      { x: 0, z: 2.0, ry: Math.PI },
      { x: 0, z: -2.0, ry: 0 },
      { x: -1.6, z: -2.05, ry: 0 },
      { x: 1.6, z: -2.05, ry: 0 },
      { x: -1.6, z: 2.05, ry: Math.PI },
      { x: 1.6, z: 2.05, ry: Math.PI },
    ],
  },

  B: {
    furniture: [
      { kind: 'desk', placements: B_PODS.map((p) => p.desk) },
      { kind: 'computerScreen', placements: B_PODS.map((p) => p.screen) },
      { kind: 'computerKeyboard', placements: B_PODS.map((p) => p.keyboard) },
      { kind: 'computerMouse', placements: B_PODS.map((p) => p.mouse) },
      { kind: 'chairDesk', placements: B_PODS.map((p) => ({ x: p.seat.x, z: p.seat.z, ry: p.seat.ry })) },
      { kind: 'bookcaseOpenLow', placements: [{ x: -2.72, z: -0.05, ry: HALF_PI }] },
      { kind: 'trashcan', placements: [{ x: 2.72, z: -0.05 }] },
    ],
    seats: B_PODS.map((p) => p.seat),
    standing: [
      { x: -2.2, z: 0, ry: HALF_PI },
      { x: -1.3, z: 0, ry: HALF_PI },
      { x: 0, z: 0, ry: 0 },
      { x: 1.3, z: 0, ry: -HALF_PI },
      { x: 2.2, z: 0, ry: -HALF_PI },
      { x: -2.6, z: 2.2, ry: HALF_PI },
      { x: -1.3, z: 2.2, ry: Math.PI },
      { x: 0, z: 2.2, ry: Math.PI },
      { x: 1.3, z: 2.2, ry: Math.PI },
      { x: 2.6, z: 2.2, ry: -HALF_PI },
      { x: -2.6, z: -2.2, ry: HALF_PI },
      { x: 0, z: -2.2, ry: 0 },
      { x: 2.6, z: -2.2, ry: -HALF_PI },
    ],
  },

  C: {
    furniture: [
      { kind: 'bookcaseClosedWide', placements: C_RACKS },
      { kind: 'desk', placements: [C_POD.desk] },
      { kind: 'computerScreen', placements: [C_POD.screen] },
      { kind: 'computerKeyboard', placements: [C_POD.keyboard] },
      { kind: 'computerMouse', placements: [C_POD.mouse] },
      { kind: 'chairDesk', placements: [{ x: C_POD.seat.x, z: C_POD.seat.z, ry: C_POD.seat.ry }] },
      { kind: 'ceilingFan', placements: [{ x: 0, z: 0.3, y: 2.55 }] },
      { kind: 'trashcan', placements: [{ x: 2.5, z: 1.9 }] },
    ],
    seats: [C_POD.seat],
    standing: [
      { x: 2.2, z: 0.2, ry: -HALF_PI },
      { x: -2.4, z: 0.2, ry: HALF_PI },
      { x: 0, z: 0.6, ry: 0 },
      { x: 2.2, z: -0.6, ry: -HALF_PI },
      { x: 0.9, z: 0.3, ry: 0 },
      { x: 1.0, z: 1.9, ry: Math.PI },
      { x: 2.4, z: 2.2, ry: Math.PI },
      { x: -0.6, z: 2.2, ry: Math.PI },
      { x: 0, z: 2.2, ry: Math.PI },
      { x: 2.4, z: 1.0, ry: -HALF_PI },
    ],
  },

  D: {
    furniture: [
      { kind: 'desk', placements: [D_COUNTER] },
      { kind: 'chairDesk', placements: [{ x: 0, z: -2.05, ry: 0 }] },
      { kind: 'rugRound', placements: [{ x: 1.6, z: 1.5 }] },
      { kind: 'loungeSofa', placements: [{ x: 1.6, z: 0.65 }] },
      { kind: 'tableCoffee', placements: [{ x: 1.6, z: 1.55 }] },
      { kind: 'loungeChair', placements: [{ x: -0.15, z: 1.35, ry: HALF_PI }] },
      { kind: 'pottedPlant', placements: [{ x: 2.65, z: -1.9 }, { x: -2.65, z: 2.0 }] },
    ],
    seats: [{ x: 0, z: -2.05, ry: 0 }],
    standing: [
      { x: 0, z: 0.45, ry: 0 },
      { x: -1.3, z: 0.9, ry: 0 },
      { x: 0.3, z: 0.2, ry: 0 },
      { x: -1.3, z: 0.2, ry: 0 },
      { x: -2.4, z: 0.4, ry: HALF_PI },
      { x: 2.6, z: 2.3, ry: -HALF_PI },
      { x: -2.6, z: -0.6, ry: HALF_PI },
      { x: 1.2, z: 2.3, ry: Math.PI },
      { x: -2.6, z: 1.6, ry: HALF_PI },
      { x: 0.6, z: 2.3, ry: Math.PI },
      { x: 2.0, z: -0.4, ry: -HALF_PI },
      { x: -1.0, z: 2.3, ry: Math.PI },
    ],
  },
};
