# PROGRESS — JARVIS 3D build

Branch: `feature/3d-twin` · Plan: `MASTER_PROMPT_3D.md` + `docs/PHASES.md`
Rule: one phase per session. After each phase: tests → update this file → commit → **STOP**.

| Phase | Title | Status | Gate |
|---|---|---|---|
| P0 | Setup & recon | DONE | approved → P1 executed |
| P1 | Scaffold + static 3D scene | DONE | approved → P2 executed |
| P2 | CO2 / IAQ backend | DONE | awaiting user approval for P3 |
| P3 | Furniture & people assets | DONE | awaiting user approval for P4 |
| P4 | Live data → visual wiring | NOT STARTED | — |
| P5 | Constraint lifecycle + physics deltas + reactions | NOT STARTED | — |
| P6 | Price overlay + TOU + parity charts + demo macros | NOT STARTED | — |
| P7 | Live weather (Open-Meteo, fail-safe) | NOT STARTED | — |
| P8 | NLP evaluation harness | NOT STARTED | — |
| P9 | Polish, rehearsal, freeze | NOT STARTED | — |

---

## Recon summary (read before coding — required by prompt §0)

Read in full: `backend/main.py`, `backend/simulation_manager.py`, `backend/digital_twin.py`,
`backend/thermal_model.py`, `backend/comfort_model.py`, `backend/energy_model.py`,
`backend/baseline.py`, `backend/nlp_engine.py`, `backend/models.py`, `frontend/src/App.tsx`,
`frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/utils/temperatureColor.ts`
(`BuildingMap.tsx` and `rl/agent.py` covered via read-only inspection).

**Architecture.** FastAPI app in `backend/main.py` holds a module-level singleton
`SimulationManager`. The manager owns a `BuildingTwin` and a parallel baseline twin, plus a
daemon thread (`_run_loop`) that steps the twin `speed` times per ~1s tick. All shared state is
guarded by a single `threading.Lock`. There is no database — everything is in-memory.

**Physics.** `BuildingTwin.step()` per-room order: neighbour temps (old values, explicit Euler)
→ 2R1C temperature update → fan power → humidity lag → air speed → PMV/PPD comfort → energy
accumulation; then advance clock → step baseline → snapshot to history (capped 300 points).
Room adjacency is a 2×2 grid: A↔B, A↔C, B↔D, C↔D. `_snapshot()` is the single place the room
JSON payload is built; `_snapshot_and_record()` mirrors it for history.

**Constraints (key for P2/P5/P6).** Constraints are currently a plain dict on the manager:
`active_constraints[room_id] = {action, urgency, setpoint_delta_c, expires_at}`. `get_state()`
injects the action name as an `active_constraint` string into the room payload and nulls expired
entries. Critically, the clamp that *applies* constraints lives inside
`if self.rl_mode == "auto"` in `_run_loop` — so today constraints only take effect in auto mode.

**RL.** `rl/agent.py` (`JarvisAgent`) is lazily imported on `set_rl_mode("auto", path)`;
`get_actions(state)` returns per-room `setpoint_c` / `airflow_lps`. It must stay in sync with
`BuildingEnv`'s 23-float observation encoding. Read-only in this build.

**NLP.** `nlp_engine.parse_complaint(complaint, state)` calls Groq
(`openai/gpt-oss-120b`), embeds a live room-context block built by `_build_room_context`, and
returns `{room_id, action, urgency, setpoint_delta_c, rationale, confidence}` with robust
fallbacks. `POST /api/chat/message` maps a non-`none` result into `set_nlp_constraint(...,
duration_mins=30.0)`. `_build_room_context` has a stale comment claiming PMV is unavailable —
PMV **is** present in `RoomStateResponse`.

**Frontend.** Single-page React 19 + Vite + Tailwind dashboard. No router, no state library.
`App.tsx` polls `/simulation/state` every 1s and `/simulation/history` every 2s via axios and
passes `state` down as props; all REST calls live in `api.ts`; types mirrored in `types.ts`.
`BuildingMap.tsx` renders an SVG 2×2 floor plan and receives `state`, `selectedRoom`,
`onSelect` — this is the component the 3D scene must replace behind a toggle.
`temperatureColor.temperatureToColor(tempC)` returns a CSS `hsl()` string (pure math, easy to
port to `THREE.Color`).

**Deployment / config.** Backend Dockerized (`python:3.11-slim`, CPU-only torch) for
Koyeb/Render; frontend on Netlify (SPA fallback). `.env` is gitignored; `.env.example` documents
`GROQ_API_KEY` and `VITE_API_URL`. `nlp_engine` reads the key via `os.getenv("GROQ_API_KEY", "")`
— the earlier scan note claiming a hardcoded secret was **incorrect**; no secret is in the code.
`requirements.txt` = fastapi, uvicorn, pydantic, numpy, groq, stable-baselines3 — **no pytest**
(hence the new dev-dependency in P2).

**Corrected earlier assumptions.** (1) No hardcoded Groq key. (2) `.dockerignore` excludes `*.md`,
`.env`, and parts of `rl/`, but that is image-scope only and does not affect git. (3) A
`.pytest_cache/` exists at repo root, gitignored — pytest has been run here before.

---

## Phase 0 — Setup & recon

**Status:** DONE
**GATE:** approved — P1 executed in the next session.

**Files touched**
- `MASTER_PROMPT_3D.md` (NEW) — master prompt, verbatim.
- `docs/PHASES.md` (NEW) — P0–P9 execution breakdown with acceptance criteria.
- `PROGRESS.md` (NEW) — this file.

**Git**
- Branch `feature/3d-twin` created off `main`. `main` untouched.

**Decisions / deviations**
- Added a **P0** phase (branch + docs + recon) ahead of the prompt's P1 so the first code phase
  stays focused. Substance of prompt P1 unchanged.
- Storage layout chosen by user: `MASTER_PROMPT_3D.md` + `docs/PHASES.md` + `PROGRESS.md`.
- Gate mechanism chosen by user: hard stop after each phase, resume only on explicit "go phase N".

**Open item requiring your decision (flagged at P2)**
- The IAQ rule and price-response overlay must be visible in manual/demo mode or the P6 demo
  macros do nothing, but the existing clamp layer runs only when `rl_mode == "auto"`. Proposed:
  a single `_apply_overlays(...)` helper applied every step in **both** modes. This is a
  deliberate deviation from a literal reading of "same clamp layer". Confirm at P2 or the
  manual-mode macros get cut.
- **RESOLVED at P2 — approved by the user: overlays run in both modes** (see Phase 2 below).

**New dependencies:** none.

**Tests run + result:** n/a (docs-only phase).

**Acceptance criteria:**
- Branch exists → PASS (`git rev-parse --abbrev-ref HEAD` → `feature/3d-twin`)
- Three docs committed → PASS (this commit)
- Recon summary present → PASS (above)
- No `backend/` or `rl/` edits → PASS (git status shows docs only)

**Commit:** `docs: add 3D build master prompt, phase plan, and progress log`

---

## Phase 1 — Scaffold + static 3D scene

**Status:** DONE
**GATE:** awaiting user approval for P2

**Files touched**
- `frontend/package.json` — added the four pinned 3D deps; pinned `react`/`react-dom` to exact `19.2.8`.
- `frontend/package-lock.json` — regenerated.
- `frontend/src/components/BuildingScene3D.tsx` (NEW) — `<Canvas>`, four room volumes in the 2×2 grid
  (A|B top, C|D bottom), low outer walls, interior glass partitions, one ambient + one directional
  light, `OrbitControls`, drei `Grid` ground plane, per-room labels.
- `frontend/src/App.tsx` — `viewMode: '2d' | '3d'` state + segmented toggle above the building view;
  renders `BuildingMap` or `BuildingScene3D` with identical props.

**Dependencies added (§6 requires justification + pin)**

| Package | Pin | Justification |
|---|---|---|
| `three` | `0.185.1` | The 3D engine. Pinned to exactly match `@types/three` so runtime and types share a minor — `three@0.185.4` does not exist (only the types package goes to `.4`). |
| `@react-three/fiber` | `9.7.0` | React renderer for three. v9 is the React-19 line; peer range is `react >=19 <19.3`. |
| `@react-three/drei` | `10.7.8` | Supplies `OrbitControls`, `Html`, `Grid`, `useCursor`. Peer requires R3F ^9 and three >=0.159. |
| `@types/three` | `0.185.1` (dev) | Types for three, matched to the runtime minor. |

All four installed with `--save-exact` (no caret), per §6 "pin versions".

**Version constraints hit + resolutions (the P1 risk the plan flagged)**

1. `react`/`react-dom` were declared `^19.2.8`, which npm resolves to **19.3.0** — rejected by R3F
   9.7.0 (`peer react >=19 <19.3`). R3F 9.7.0 is the newest fibre on the registry; no 19.3-compatible
   release exists. → **Pinned `react` and `react-dom` to exact `19.2.8`**, which is the version already
   installed on disk, so the runtime behaviour is unchanged and 3D-dep-free pages are unaffected.
   `docs/PHASES.md` anticipated an R3F/React-19 pinning adjustment in P1. **Deliberate deviation from
   the `^` ranges used elsewhere in `package.json`.**
2. `three@0.185.4` does not exist (I initially mis-read the `@types/three` version list). →
   `three@0.185.1` + `@types/three@0.185.1`, an exact pair.
3. Verified after install: the whole tree dedupes to a single `three@0.185.1` and `react@19.2.8`, and
   `npm ls` reports no peer conflicts. `xr`/`stats-gl` pull their own nested `three@0.170.0` — vendored
   inside drei, not on our import path.

**Environment gotcha (this one cost me a build)**
This machine's shell has `NODE_ENV=production` and `npm config omit=dev`, so a bare `npm install`
**prunes every devDependency** — `vite`, `typescript`, `tailwindcss`, `oxlint` and all `@types/*`
disappeared, and `npm run build` then failed with `'tsc' is not recognized`. Fix:
`npm install --include=dev`. Worth knowing before P2 adds `backend/requirements-dev.txt`.

**Decisions / deviations**
- `viewMode` **defaults to `'2d'`**. The 3D scene still renders hardcoded placeholders, so making it the
  default would present invented temperatures as real readings. Flip the default to `'3d'` in P4 once
  the scene is wired to live state (DoD: "3D scene replaces 2D map, toggle keeps 2D fallback").
- `BuildingScene3D` takes **the same props as `BuildingMap`** (`state`, `selectedRoom`, `onSelect`) so
  the toggle is a drop-in swap and P4 is a data change, not an interface change. `state` is **typed but
  deliberately not read** in P1 — reading it is exactly P4's "live wiring". Per-room floors are tinted
  from `PLACEHOLDER_TEMP_C` through the existing `temperatureToColor()` util: a CSS `hsl()` string
  parses straight into `THREE.Color`, so P4 needs **no duplicated colour maths** — the 2D palette and
  the 3D tint stay one implementation.
- Click-to-select and the hover cursor are wired now rather than deferred to P9. Rationale: `BuildingMap`
  already answers clicks, and a 3D view that ignored them while the 2D view honoured them is a UX
  inconsistency, not a feature. P9 still owns polish + offline rehearsal.
- Room labels use drei `<Html>` (real DOM, app typography) instead of drei `<Text>`: troika's `<Text>`
  fetches a default font from a CDN, which would violate "zero internet dependency in simulated mode".
- No drei `Environment`/HDR preset, same reason. Lighting is exactly one `ambientLight` + one
  `directionalLight` (1024² shadow map), per §3.6, and there is no postprocessing.
- `frameloop` stays default (`always`) because `OrbitControls` damping needs continuous frames.
- Perf guards already in: `dpr={[1, 2]}`, `enablePan={false}`, bounded zoom/polar angle, `EdgesGeometry`
  outlines instead of extra meshes.

**Known item carried to P9 (not a P1 acceptance criterion)**
- `three` + `drei` grow the production bundle from ~0.5 MB to **1,565.96 kB (439.66 kB gzip)**; vite
  warns about the >500 kB chunk. Cleanest fix is `React.lazy`-ing `BuildingScene3D` so the 2D fallback
  never downloads three. Deliberately not done in P1.

**Tests run + result**
- `npm run build` (`tsc -b && vite build`) → **PASS** — 2981 modules transformed, no type errors.
- `npm run lint` (`oxlint`) → **0 errors, 6 warnings**, all pre-existing (unused `HvacBar`, unused
  `useRef` import, unused catch binding in `App.tsx`). `BuildingScene3D.tsx` produces **no** warnings.
- Backend: `py -3 -m uvicorn backend.main:app --port 8000` → `GET /api/simulation/state` returns **200**.
  Note there is **no venv in the repo** and `python` resolves to the Windows Store stub — use `py -3`
  (3.13.5), which has fastapi/uvicorn/numpy.
- Frontend dev server: `npm run dev` on :3000 returns **200**; `GET /src/components/BuildingScene3D.tsx`
  returns a 23.7 kB transformed module with drei resolved and no Vite error overlay.
- Protected files: **no `backend/` or `rl/` edits** — `git status` shows only `frontend/` changes.
  `docs/`, `MASTER_PROMPT_3D.md` untouched.

**Acceptance criteria**
- `npm run dev` toggles 2D/3D → **PASS on code + build**; ⚠️ **browser render NOT verified by the agent.**
  `agent-browser` is not installed on this machine and the user opted to verify manually. Open
  http://localhost:3000 and click **3D Twin**. Residual risk: a React-19/R3F runtime error or a blank
  canvas — neither is catchable by `tsc`/vite, and both are the exact class of failure P1 exists to
  flush out. Everything else (server, module graph, production build) is green.
- `npm run build` (tsc) passes → **PASS**
- Deps pinned + justified → **PASS** (table above)

**Commit:** `feat(fe): add 2D/3D view toggle and static 3D building scene`

---

## Phase 2 — CO2 / IAQ backend

**Status:** DONE
**GATE:** awaiting user approval for P3

**Resolved before coding**
- Overlay scope (the item P0/P1 flagged): user approved **overlays run in both modes** via
  `_apply_overlays()`. Logged below as the intentional deviation from a literal reading of
  "same clamp layer".

**Files touched**
- `backend/thermal_model.py` (ADD only) — `RoomConfig.nominal_volume_m3` (default 100),
  `RoomState.co2_ppm / iaq_score / overall_comfort_score`, `compute_next_co2(...)`,
  `airflow_to_hold_co2(...)`, CO2 constants (`CO2_GENERATION_LPS_PER_OCCUPANT`, `CO2_OUTDOOR_PPM`,
  `CO2_INITIAL_PPM`, `CO2_MIN_PPM`, `CO2_MAX_PPM`). New functions appended in a new
  "CO2 / IAQ model" section — no existing math touched.
- `backend/comfort_model.py` (ADD only) — `iaq_score(co2_ppm)` (100 at ≤800 ppm, 0 at ≥2000,
  linear between), `overall_comfort_score(comfort, iaq) = 0.7·comfort + 0.3·iaq`,
  `IAQ_CO2_GOOD_PPM` / `IAQ_CO2_BAD_PPM`.
- `backend/digital_twin.py` — `ROOM_VOLUMES_M3 {A:80, B:150, C:60, D:100}` consumed by
  `_make_configs()`; `_make_states()` initialises CO2 450 + IAQ/overall; `step()` computes CO2
  after humidity (new sub-step 3e) and stores IAQ + overall with the rest of the atomic update;
  `_snapshot()` emits the three fields; `_snapshot_and_record()` adds `co2_ppm` to history.
- `backend/models.py` — `RoomStateResponse` gains the three additive fields.
- `backend/simulation_manager.py` — constraint dict gains `source`; `_step_once()` extracted from
  `_run_loop`; `_apply_overlays(room_id, base_sp, base_af, sim_time)`; `_apply_iaq_rule()`;
  `_set_constraint` / `_expire_constraints` / `_sync_base_targets`; manual-mode base targets
  (`_base_setpoints`, `_base_airflow`, `_overlay_active`); `reset()` clears constraints and
  re-syncs bases; `get_state()` reuses `_expire_constraints`.
- `backend/requirements-dev.txt` (NEW), `backend/tests/__init__.py` (NEW),
  `backend/tests/test_iaq.py` (NEW, 22 tests).
- `frontend/src/types.ts` — mirrors the three fields on `RoomState` + `co2_ppm` on `HistoryPoint`.
- `frontend/src/App.tsx` — the four `DEFAULT_STATE` placeholder literals gain the three fields
  (without this `tsc -b` fails with 4 × TS2739).

**Dependencies added (§6 requires justification + pin)**

| Package | Pin | Justification |
|---|---|---|
| `pytest` | `8.3.3` (dev) | Test runner for the backend suite (P2 now, P5 lifecycle tests later). Matches the version already on this machine's `py -3`, so the pinned range is verified green here. |
| `httpx` | `0.27.0` (dev) | Required by `fastapi.testclient.TestClient` for the API smoke test. Held at 0.27.x deliberately: starlette 0.38.6 (fastapi 0.115.0) is incompatible with httpx ≥ 0.28, which removed the `app=` shortcut `TestClient` uses. |

**Decisions / deviations**
- **Overlays in both modes (approved deviation).** Constraints used to clamp only inside
  `if self.rl_mode == "auto"`. Now `_apply_overlays(...)` runs every step in both modes. Manual
  mode keeps a per-room *base target* (`_base_setpoints` / `_base_airflow`, refreshed on user set
  and on auto→manual switch): the overlay is applied on top, and on expiry the base is written
  back — otherwise the overlaid setpoint/airflow would silently become the new manual value.
- `_step_once()` extracted from `_run_loop` so one step (expire → overlays → physics → rules) is
  callable deterministically. The tests drive it directly — no thread, no wall-clock timing.
- **IAQ delta is physics-derived, not a magic bump:** `airflow_to_hold_co2(occupancy, 900)` is the
  steady-state airflow that holds the room at target, so the constraint delta is
  `max(30 L/s, required − current)`. Same philosophy as P5's "physics decides magnitude".
- IAQ constraint tagged `urgency="high"`, `duration_mins=30` (mirrors the existing NLP default);
  P5 will map severity → expiry uniformly across sources.
- `reset()` now clears constraints and re-syncs base targets — before, a reset left stale
  constraints in place.
- Known 1-step nuance (P5 will absorb it): `get_state()` nulls an expired constraint at poll time,
  but the base target is written back on the *next* `_step_once`, so one state payload shows the
  expired constraint cleared while airflow/setpoint still hold the overlaid value.
- The three new dataclass fields were **appended** (not inserted) so any positional
  `RoomConfig(...)` / `RoomState(...)` construction stays valid.

**Tests run + result**
- `py -3 -m pytest backend/tests -q` → **22 passed** in 2.58 s. Coverage: CO2 rise with occupants /
  decay with ventilation / steady state vs `airflow_to_hold_co2` / numerical clamps; `iaq_score`
  bounds, midpoint and monotonicity; overall blend; per-room volumes; twin snapshot + history
  fields; IAQ rule trigger above 1000 ppm, no re-trigger while active, NLP constraint blocks the
  rule, airflow restored to base on expiry; `TestClient` smoke test of `/api/simulation/state`.
- `npm run build` (`tsc -b && vite build`) → **PASS** (2981 modules; 1,566.17 kB / 439.69 kB gzip).
- `npm run lint` (`oxlint`) → **0 errors, 6 warnings** — same pre-existing set as P1, none from P2
  files.
- Live API (uvicorn on **:8001**, `speed=1`, `curl`/`Invoke-RestMethod`): default scenario at
  12 occupants — B CO2 851 → 902 ppm, plateau ~920, **no rule trigger**; stuffy scenario
  (14 occ, 60 L/s) — B crosses 1000 ppm → `active_constraint = INCREASE_AIRFLOW`, airflow
  **60 → 145.8 L/s**, CO2 1070 → 921 ppm across the 30-min window; on expiry airflow restores to
  60 and the rule re-fires when the room drifts above 1000 again.
- Dev server: `npm run dev` on :3000 returns 200 and serves the updated `App.tsx` module.
- Protected files: no `rl/` edits, no structural `nlp_engine.py` edits, no changes to existing
  equations, `digital_twin/` untouched.

**Environment note (recurring, costs time)**
- Port **8000** is held by a leftover `python.exe` (PID 30616) from the P1 session — it is running
  the *pre-P2* code and must be restarted before manual verification, or the API will not show the
  new fields. The agent deliberately did not kill a process it did not start.

**Acceptance criteria**
- pytest green → **PASS**
- state JSON shows `co2_ppm` climbing in Room B at 12 occupants and the rule firing
  (`active_constraint = INCREASE_AIRFLOW`) → **PASS** (live log above)
- TS types mirror every new Pydantic field → **PASS** (`tsc -b`)

**Commit:** `feat(be): add CO2/IAQ state, iaq_score, and IAQ-driven airflow rule`

---

## Phase 3 — Furniture & people assets

**Status:** DONE
**GATE:** awaiting user approval for P4

**Files touched**
- `frontend/public/models/furniture/*.glb` (NEW, 17 files, 195 KB) — extracted from the Kenney kit.
- `frontend/public/models/people/*.glb` (NEW, 4 files, 3.2 MB) — Quaternius rigs, as published.
- `frontend/src/components/scene/models.ts` (NEW) — asset registry: URLs, `FURNITURE_SCALE`,
  avatar→clip map, seated/standing avatar assignment, persona labels, `Placement` / `Seat` types.
- `frontend/src/components/scene/layout.ts` (NEW) — all 71 placements + 12 seat and 47 overflow
  standing spots, in room-local metres.
- `frontend/src/components/scene/InstancedModel.tsx` (NEW) — per-primitive `InstancedMesh` renderer.
- `frontend/src/components/scene/Avatars.tsx` (NEW) — skinned clones + one `useFrame` for all mixers.
- `frontend/src/components/BuildingScene3D.tsx` — renders `RoomContents` (furniture + avatars) per
  room inside its own `<Suspense>`; adds an opt-in FPS readout.
- `CREDITS.md` (NEW, repo root) — per-file attribution and licences.

**Dependencies added:** none. Phase 3 is asset-and-code only, so §6 needs no new justification
entry. `three/examples/jsm/utils/SkeletonUtils.js` (bundled with the already-pinned `three`) supplies
the skeleton-aware clone; no `stats.js`/`three-stdlib` import was added for the FPS readout — it is
~15 lines of `useFrame` and a ref, writing to a DOM node so the sample never re-renders the scene.

**Asset sourcing (this was the slow part of the phase)**
- Kenney kit: `kenney.nl/media/pages/assets/furniture-kit/440e0608a4-1677580847/kenney_furniture-kit.zip`
  (CC0, includes the licence text). 17 of the 140 models were extracted, not the whole kit.
- Quaternius people: his own site now routes packs through itch.io/Patreon and ships FBX/OBJ/Blend
  (no glTF), and `api.poly.pizza` returns 401 without an account, so the models were taken from the
  **public model pages** on poly.pizza (`/m/<id>`), which expose a direct `static.poly.pizza/*.glb`.
  Both are listed as sanctioned sources in the spec; licences are recorded in `CREDITS.md`.

**Discoveries that shaped the code (all measured, not assumed)**
- Kenney models are authored at **~0.5 m per unit** (a desk is 0.384 units tall) → `FURNITURE_SCALE = 2`.
- Kenney models put the **origin on a footprint corner**, not the centre. `InstancedModel` therefore
  measures each model's bounds once and re-centres X/Z with the base at `y = 0`, so a placement reads
  as "put this here, standing on the floor" instead of carrying 17 hand-copied offsets.
- All assets face **+Z**: chair backrests and avatar toe bones both sit at −Z, and rotations are
  derived from that.
- The people are **rigged/skinned** (1-6 `SkinnedMesh` per model, 10-20 clips), so they cannot use
  `InstancedMesh`. They are `SkeletonUtils.clone()`d with one `AnimationMixer` each, all advanced from
  a single `useFrame`. Instancing is applied where the spec asks for it — the static furniture.
- The four rigs are published at **wildly different unit scales** (bone spans 0.90, 0.91, 4.23, 5.16).
  Rather than hardcode four magic numbers, the bone span is measured at load and scaled to 1.5 m
  (a ~1.75 m adult's ankle→head-joint span), which is self-correcting if an asset is ever swapped.
- The people clips are exported **with a prefix** (`HumanArmature|Man_Sitting`, `Armature|SitIdle`,
  `CharacterArmature|Idle`), so the clip lookup matches on suffix.
- Only `man`/`woman` ship a seated clip → they take the seats; `matt`/`sam` are idle-only → they take
  the overflow standing spots.

**Bugs found by verification before any browser was involved**
1. **Desk scale double-converted** — `DESK_SCALE` contained `FURNITURE_SCALE` *and* `scaleOf()`
   multiplied by it again, making every desk 2.35 m wide and 1.54 m tall. Caught by the collision
   check (`desk overlaps desk` in room B). Now `[0.8, 1, 0.875]` → 1.17 × 0.77 × 0.69 m.
2. **Reception chair clipped the counter** — the counter is deeper (0.94 m) than a desk, so the chair
   overlapped it by 8 cm. Counter moved to z = −1.2; chair clearance is now 6.6 cm.
3. **People standing inside furniture** — the B overflow spots at x = ±2.6 sat inside the bookcase and
   bin, and one D spot sat inside the lounge chair. Spots moved; 0 problems remain.
4. **Wrong animation** — the clip lookup missed the prefixed names and silently fell through to
   `animations[0]`, so every `man` avatar would have stood in the conference room **clapping**. The
   fallback is what made it silent; the lookup now matches on suffix and the verifier asserts the
   resolved clip name.

**Verification (headless, reproducible — no browser needed)**
- Compiled `layout.ts` + `models.ts` with `tsc --ignoreConfig`, then ran a Node harness that imports
  the real modules, loads the real `.glb` files through the real `GLTFLoader`, and replays the
  component's normalisation maths for **every** placement:
  - **17/17** furniture models load; **71/71** placements have finite, non-degenerate bounds, base
    within 2 cm of the floor and the footprint centred on the requested point.
  - **0** wall breaches, **0** furniture overlaps, **0** people inside furniture (71 placements,
    12 seats, 47 overflow spots across 4 rooms).
  - **4/4** avatars load, have bones + `SkinnedMesh`, resolve the intended clip, and auto-scale to
    1.50 m bone span (raw scales 0.355 / 0.291 / 1.661 / 1.653).
  - Sizes spot-checked against hand maths: desk 1.175 × 0.769 × 0.687 m, conference table
    2.301 × 0.695 × 1.208 m, counter 3.232 × 0.769 × 0.942 m, rack 0.800 × 1.975 × 0.500 m.
- `npm run build` (`tsc -b && vite build`) → **PASS** (2986 modules; 1,648.00 kB / 464.17 kB gzip).
- `npm run lint` (`oxlint`) → **0 errors, 6 warnings** — the same pre-existing set as P1/P2; no new
  file contributes a warning.
- Dev server: all **21/21** model URLs return 200 with byte-exact content.
- `dist/` contains all 21 models, so the production build is self-contained (no runtime fetch).

**Perf budget (measured statically, since the frame rate itself needs your eyes)**
- Furniture is 52 draw calls for 71 placements — one `InstancedMesh` per primitive per model per room
  (e.g. 8 engineering desks + 8 monitors = a handful of calls, not 40+). 4,614 triangles in the
  instanced furniture.
- Avatars are the expensive half (skinned): `man` carries 6 primitives, `woman` 1, `matt`/`sam` 2.
  At the default occupancies (A8/B12/C4/D10) that is ~34 avatars.
- An **FPS button** sits above the canvas (top-right): it samples frames once a second and writes
  straight to a DOM node, so measuring costs nothing and never re-renders the scene.

**Deliberate scope note**
- Room occupancy **now drives the avatar count** (seated first, then standing spots), because P3's
  stated risk is the instanced/perf pipeline and it cannot be judged at 0 avatars. P4 keeps the rest
  of the live wiring: temperature tint, comfort indicator, CO2 haze, fan rotation, power glow,
  constraint beacon. Avatars do not cast shadows — that would double the skinned cost for little gain.

**Not verified by the agent (needs your eyes — same category as P1's blank-canvas risk)**
- Browser render: `tsc`/vite cannot catch a R3F runtime error or a blank canvas.
- **Avatar facing.** Derived from toe-bone geometry (+Z, same as the chairs) but never seen. If
  seated people face away from their desks, the fix is a single term in `Avatars.tsx`.
- Whether seated avatars sit *in* the chairs convincingly — the sit clips are authored poses and the
  seat height is a separate number; the offset is in the `Avatars.tsx` `<group>` if it needs a nudge.

**Acceptance criteria**
- Furniture downloaded + self-hosted + placed per persona → **PASS** (17 models, 71 placements,
  0 collisions; A Conference / B Engineering / C Server / D Reception all distinct).
- People assets self-hosted, per-persona → **PASS** on load/rig/clip/scale; placement is per seat.
- `useGLTF` + instancing → **PASS**. No postprocessing; lighting is still one ambient + one directional.
- Perf measured on a mid laptop → **YOUR CHECK** (FPS button); static budget above says 52 furniture
  + ~34 skinned avatars.

**Commit:** `feat(fe): add self-hosted furniture and people assets, place per-room personas`
