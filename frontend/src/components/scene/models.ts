// models.ts — self-hosted asset registry for the 3D scene.
//
// Everything under frontend/public/models/ is vendored (no CDN, no hot-linking),
// so simulated mode has zero internet dependency. See CREDITS.md for licences.
//
// Scale note: the Kenney Furniture Kit is authored at roughly 0.5 m per unit
// (a desk is 0.384 units tall). FURNITURE_SCALE converts model units to metres.
// Model textures are embedded in the .glb, so no external texture fetch.

import type { RoomId } from '../../types';

export const MODEL_BASE = '/models/';
export const FURNITURE_SCALE = 2;

export type FurnitureKind =
  | 'tableCross'
  | 'chairModernCushion'
  | 'desk'
  | 'chairDesk'
  | 'computerScreen'
  | 'computerKeyboard'
  | 'computerMouse'
  | 'bookcaseOpenLow'
  | 'bookcaseClosedWide'
  | 'trashcan'
  | 'ceilingFan'
  | 'loungeSofa'
  | 'loungeChair'
  | 'tableCoffee'
  | 'pottedPlant'
  | 'plantSmall1'
  | 'rugRound';

export type AvatarKind = 'man' | 'woman' | 'matt' | 'sam';

export const FURNITURE_URL: Record<FurnitureKind, string> = {
  tableCross: `${MODEL_BASE}furniture/tableCross.glb`,
  chairModernCushion: `${MODEL_BASE}furniture/chairModernCushion.glb`,
  desk: `${MODEL_BASE}furniture/desk.glb`,
  chairDesk: `${MODEL_BASE}furniture/chairDesk.glb`,
  computerScreen: `${MODEL_BASE}furniture/computerScreen.glb`,
  computerKeyboard: `${MODEL_BASE}furniture/computerKeyboard.glb`,
  computerMouse: `${MODEL_BASE}furniture/computerMouse.glb`,
  bookcaseOpenLow: `${MODEL_BASE}furniture/bookcaseOpenLow.glb`,
  bookcaseClosedWide: `${MODEL_BASE}furniture/bookcaseClosedWide.glb`,
  trashcan: `${MODEL_BASE}furniture/trashcan.glb`,
  ceilingFan: `${MODEL_BASE}furniture/ceilingFan.glb`,
  loungeSofa: `${MODEL_BASE}furniture/loungeSofa.glb`,
  loungeChair: `${MODEL_BASE}furniture/loungeChair.glb`,
  tableCoffee: `${MODEL_BASE}furniture/tableCoffee.glb`,
  pottedPlant: `${MODEL_BASE}furniture/pottedPlant.glb`,
  plantSmall1: `${MODEL_BASE}furniture/plantSmall1.glb`,
  rugRound: `${MODEL_BASE}furniture/rugRound.glb`,
};

export const AVATAR_URL: Record<AvatarKind, string> = {
  man: `${MODEL_BASE}people/man.glb`,
  woman: `${MODEL_BASE}people/woman.glb`,
  matt: `${MODEL_BASE}people/matt.glb`,
  sam: `${MODEL_BASE}people/sam.glb`,
};

// Clip played per avatar. Stored as the plain clip name — the .glb files carry an
// exporter prefix ("HumanArmature|Man_Sitting", "Armature|SitIdle", "CharacterArmature|Idle"),
// so the lookup matches on suffix rather than equality.
export const AVATAR_CLIP: Record<AvatarKind, string> = {
  man: 'Man_Sitting',
  woman: 'SitIdle',
  matt: 'Idle',
  sam: 'Idle',
};

// Only `man` and `woman` ship a seated clip, so they take the seats; `matt` and `sam`
// only have Idle/Walk and are used for the overflow people standing in the room.
export const SEATED_AVATARS: AvatarKind[] = ['woman', 'man', 'woman', 'man'];
export const STANDING_AVATARS: AvatarKind[] = ['matt', 'sam'];

// Room code stays A/B/C/D; persona names are display-only (MASTER_PROMPT_3D §3.3).
export const PERSONA: Record<RoomId, string> = {
  A: 'Conference',
  B: 'Engineering',
  C: 'Server Room',
  D: 'Reception',
};

// yaw 0 == model faces +Z. Verified from the geometry: chair backrests and avatar
// toes both sit at -Z in every source model, so all assets share one convention.
export interface Placement {
  x: number;
  z: number;
  y?: number;
  ry?: number;
  scale?: number | [number, number, number];
}

export interface Seat {
  x: number;
  z: number;
  ry: number;
}
