# PROGRESS — JARVIS 3D build

Branch: `feature/3d-twin` · Plan: `MASTER_PROMPT_3D.md` + `docs/PHASES.md`
Rule: one phase per session. After each phase: tests → update this file → commit → **STOP**.

| Phase | Title | Status | Gate |
|---|---|---|---|
| P0 | Setup & recon | DONE | approved → P1 executed |
| P1 | Scaffold + static 3D scene | DONE | awaiting user approval for P2 |
| P2 | CO2 / IAQ backend | NOT STARTED | — |
| P3 | Furniture & people assets | NOT STARTED | — |
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
