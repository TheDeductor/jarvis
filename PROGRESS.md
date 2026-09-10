# PROGRESS — JARVIS 3D build

Branch: `feature/3d-twin` · Plan: `MASTER_PROMPT_3D.md` + `docs/PHASES.md`
Rule: one phase per session. After each phase: tests → update this file → commit → **STOP**.

| Phase | Title | Status | Gate |
|---|---|---|---|
| P0 | Setup & recon | DONE | awaiting user approval for P1 |
| P1 | Scaffold + static 3D scene | NOT STARTED | — |
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
**GATE:** awaiting user approval for P1

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
