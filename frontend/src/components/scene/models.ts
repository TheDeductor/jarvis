// models.ts — self-hosted asset registry for the 3D scene.
//
// Everything under frontend/public/models/ is vendored (no CDN, no hot-linking),
// so simulated mode has zero internet dependency. See CREDITS.md for licences.
//
// Scale note: the Kenney Furniture Kit is authored at roughly 0.5 m per unit
// (a desk is 0.384 units tall). FURNITURE_SCALE converts model units to metres.
// Model textures are embedded in the .glb, so no external texture fetch.
//
// P3-fix / P4: matt.glb and sam.glb carried hard-hats and handheld props that
// read as weapons in the rendered scene. They are replaced by using the already-
// present man.glb and woman.glb as standing avatars too, with their Idle clips
// instead of the sitting clips. useGLTF caches by URL, so the files are loaded
// only once regardless of how many AvatarKind entries point to them.

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

// 'man_idle' / 'woman_idle' point to the same .glb files as 'man' / 'woman'.
// They are separate kinds so the clip lookup can select 'Idle' for standing
// avatars while 'man'/'woman' keep their sitting clips for seated positions.
// No new asset downloads — both GLBs are already on disk from P3.
export type AvatarKind = 'man' | 'woman' | 'man_idle' | 'woman_idle';

export const FURNITURE_URL: Record<FurnitureKind, string> = {
  tableCross:         `${MODEL_BASE}furniture/tableCross.glb`,
  chairModernCushion: `${MODEL_BASE}furniture/chairModernCushion.glb`,
  desk:               `${MODEL_BASE}furniture/desk.glb`,
  chairDesk:          `${MODEL_BASE}furniture/chairDesk.glb`,
  computerScreen:     `${MODEL_BASE}furniture/computerScreen.glb`,
  computerKeyboard:   `${MODEL_BASE}furniture/computerKeyboard.glb`,
  computerMouse:      `${MODEL_BASE}furniture/computerMouse.glb`,
  bookcaseOpenLow:    `${MODEL_BASE}furniture/bookcaseOpenLow.glb`,
  bookcaseClosedWide: `${MODEL_BASE}furniture/bookcaseClosedWide.glb`,
  trashcan:           `${MODEL_BASE}furniture/trashcan.glb`,
  ceilingFan:         `${MODEL_BASE}furniture/ceilingFan.glb`,
  loungeSofa:         `${MODEL_BASE}furniture/loungeSofa.glb`,
  loungeChair:        `${MODEL_BASE}furniture/loungeChair.glb`,
  tableCoffee:        `${MODEL_BASE}furniture/tableCoffee.glb`,
  pottedPlant:        `${MODEL_BASE}furniture/pottedPlant.glb`,
  plantSmall1:        `${MODEL_BASE}furniture/plantSmall1.glb`,
  rugRound:           `${MODEL_BASE}furniture/rugRound.glb`,
};

export const AVATAR_URL: Record<AvatarKind, string> = {
  man:        `${MODEL_BASE}people/man.glb`,
  woman:      `${MODEL_BASE}people/woman.glb`,
  man_idle:   `${MODEL_BASE}people/man.glb`,    // same file — standing use
  woman_idle: `${MODEL_BASE}people/woman.glb`,  // same file — standing use
};

// Clip played per avatar. Stored as the plain clip name — the .glb files carry
// an exporter prefix ("HumanArmature|Man_Sitting", "Armature|SitIdle",
// "HumanArmature|Idle", "Armature|Idle"), so the lookup matches on suffix.
// man_idle/woman_idle use 'Idle' so they play the standing idle animation
// rather than the sitting pose, making them look like office employees walking
// around the room rather than hovering in mid-air.
export const AVATAR_CLIP: Record<AvatarKind, string> = {
  man:        'Man_Sitting',
  woman:      'SitIdle',
  man_idle:   'Idle',   // matches HumanArmature|Idle (suffix lookup)
  woman_idle: 'Idle',   // matches Armature|Idle (suffix lookup)
};

// Seated people use the sitting-clip rigs; standing overflow uses the idle
// rigs. Both sets are plain office employees — no hard hats, no props.
export const SEATED_AVATARS:   AvatarKind[] = ['woman', 'man', 'woman', 'man'];
export const STANDING_AVATARS: AvatarKind[] = ['man_idle', 'woman_idle'];

// Room code stays A/B/C/D; persona names are display-only (MASTER_PROMPT_3D §3.3).
export const PERSONA: Record<RoomId, string> = {
  A: 'Conference',
  B: 'Engineering',
  C: 'Server Room',
  D: 'Reception',
};

// yaw 0 == model faces +Z. Verified from the geometry: chair backrests and avatar
// toes both sit at −Z in every source model, so all assets share one convention.
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
