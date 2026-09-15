# Credits — third-party 3D assets

All models used by the 3D twin (`frontend/src/components/BuildingScene3D.tsx`) are self-hosted
under `frontend/public/models/`. Nothing is hot-linked at runtime — the app works offline.

---

## Furniture — Kenney Furniture Kit

- **Author:** Kenney (https://kenney.nl)
- **Source:** https://kenney.nl/assets/furniture-kit
- **License:** CC0 1.0 Universal (Public Domain Dedication) — https://creativecommons.org/publicdomain/zero/1.0/
- **Files:** `frontend/public/models/furniture/*.glb` (17 models, extracted from the kit)

| Model | Used as |
|---|---|
| `tableCross.glb` | Conference table (Room A) |
| `chairModernCushion.glb` | Conference + lounge seating |
| `desk.glb` | Desk / workstation (Rooms B, C) and reception counter (Room D) |
| `chairDesk.glb` | Desk chair (Rooms B, C, D) |
| `computerScreen.glb`, `computerKeyboard.glb`, `computerMouse.glb` | Workstation kit (Room B) |
| `bookcaseOpenLow.glb` | Low shelf (Room B) |
| `bookcaseClosedWide.glb` | Rack cabinet (Room C) |
| `trashcan.glb` | Bin (Rooms B, C) |
| `loungeSofa.glb`, `loungeChair.glb`, `tableCoffee.glb` | Reception lounge (Room D) |
| `pottedPlant.glb`, `plantSmall1.glb` | Planting (Rooms A, D) |
| `rugRound.glb` | Reception rug (Room D) |
| `ceilingFan.glb` | Ceiling fan (Room C) |

Attribution is not required by CC0; it is recorded here as good practice.

---

## People — Quaternius low-poly characters

- **Author:** Quaternius (https://quaternius.com)
- **Source:** Poly Pizza — https://poly.pizza/u/Quaternius
- **License:** CC0 1.0 Universal (Public Domain Dedication) — each Poly Pizza model page lists
  "Public Domain (CC0)"; Quaternius publishes his library under CC0.
- **Files:** `frontend/public/models/people/*.glb` (4 rigged characters, 10–20 animation clips each)

| Model | Source page | Clips used |
|---|---|---|
| `man.glb` | https://poly.pizza/m/HMnuH5geEG | `Man_Sitting` |
| `woman.glb` | https://poly.pizza/m/9kF7eTDbhO | `SitIdle` |
| `matt.glb` | https://poly.pizza/m/66kQ4dBBC7 | `Idle` |
| `sam.glb` | https://poly.pizza/m/UcLErL2W37 | `Idle` |

These are rigged/skinned meshes, so they are rendered via skeleton-aware clones rather than
`InstancedMesh` (see `PROGRESS.md`, Phase 3, for the reasoning and the perf note).

---

## Not used

No HDR environment, no CDN font, no postprocessing pass — all were rejected to keep the scene
free of network dependencies (`MASTER_PROMPT_3D.md` §3.6, Definition of Done: "zero internet
dependency in simulated mode").
