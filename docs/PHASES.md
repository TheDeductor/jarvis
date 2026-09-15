# JARVIS 3D — Phase Plan (execution breakdown)

Companion to `MASTER_PROMPT_3D.md`. One phase per session. After each phase: run tests,
update `PROGRESS.md`, commit, then **STOP** and await an explicit "go phase N+1".

Branch: `feature/3d-twin` (never commit to `main`).

---

## Ground truth from the code (verified, not assumed)

| Fact | Where |
|---|---|
| Constraints today are a plain dict: `active_constraints[room_id]` = `{action, urgency, setpoint_delta_c, expires_at}` | `backend/simulation_manager.py:set_nlp_constraint` |
| The clamp block runs **only inside `if self.rl_mode == "auto"`** in `_run_loop` | `backend/simulation_manager.py:_run_loop` |
| `active_constraint` string is injected into room state in `get_state()`; expired ones are nulled there | `backend/simulation_manager.py:get_state` |
| Room states are `RoomConfig` (frozen) / `RoomState` (mutable) dataclasses; `_make_configs()` builds all 4 rooms uniformly | `backend/thermal_model.py`, `backend/digital_twin.py` |
| `_snapshot()` is the single place the JSON room payload is assembled; `_snapshot_and_record()` mirrors it for history | `backend/digital_twin.py` |
| Baseline twin already runs in parallel and records `baseline_energy_kwh` | `backend/digital_twin.py` |
| `nlp_engine.py` uses `os.getenv("GROQ_API_KEY", "")` — **no secret is hardcoded** | `backend/nlp_engine.py` |
| Frontend polls state 1s / history 2s in `App.tsx`; no websockets | `frontend/src/App.tsx` |
| `temperatureToColor(tempC)` returns a CSS `hsl()` string | `frontend/src/utils/temperatureColor.ts` |
| `requirements.txt` has **no pytest** → new dev dep needed | `backend/requirements.txt` |

### Critical design consequence (decide once, apply from P2)

The prompt says IAQ and price overlays ride "the existing clamp layer." That layer currently
executes **only in auto mode**. But the price-response demo (pre-cool → relax) and the IAQ rule
must be visible in manual/demo mode, otherwise "Force peak pricing now" does nothing.

**Decision:** extract the clamp application into one helper
`_apply_overlays(room_id, base_sp, base_af, sim_time)` that runs **every step in both modes**,
layered over (a) the RL agent's command in auto, or (b) the current manual setpoint/airflow in
manual. Deterministic overlay in the same architecture; adds no RL surface; leaves manual control
of the base value intact. Recorded in `PROGRESS.md` as an intentional deviation.

**Status:** awaiting your explicit blessing — flagged at P2. If you prefer overlays stay
auto-only, say so and the manual-mode demo macros will be dropped from P6.

---

## Gate protocol

- After each phase: run tests → update `PROGRESS.md` → commit → **STOP**.
- `PROGRESS.md` gets `GATE: awaiting user approval`.
- Next phase starts only on an explicit "go phase N+1". Never bundle two phases in one turn.

---

## P0 — Setup & recon (no code)

**Tasks**
1. `git checkout -b feature/3d-twin` (created).
2. Write `MASTER_PROMPT_3D.md` (verbatim master prompt).
3. Write `docs/PHASES.md` (this file).
4. Read the protected list and write a recon summary at the top of `PROGRESS.md`.
5. Confirm `.gitignore` allows `frontend/public/models/**` and keeps `.env` ignored.

**Acceptance:** branch exists; docs committed; recon summary present; no `backend/` or `rl/` edits.
**Commit:** `docs: add 3D build master prompt, phase plan, and progress log`

---

## P1 — Scaffold + static 3D scene

**Tasks**
- Add pinned deps to `frontend/package.json` (justify + pin in `PROGRESS.md`):
  `three`, `@react-three/fiber` (v9 line for React 19), `@react-three/drei`, `@types/three`.
  Verify React-19-compatible versions at implementation time.
- New `frontend/src/components/BuildingScene3D.tsx`: `<Canvas>`, low walls + glass partitions,
  4 room volumes in 2×2 grid (A|B top, C|D bottom), `<OrbitControls>`, one ambient + one
  directional light, hardcoded placeholder values.
- `App.tsx`: add `viewMode: '2d' | '3d'` + header toggle; render `BuildingMap` or
  `BuildingScene3D` with the **same** `state` prop. `BuildingMap` stays the fallback.

**Acceptance:** `npm run dev` toggles 2D/3D; `npm run build` (tsc) passes.
**Watch:** R3F/React 19 version compatibility — pin and verify immediately.
**Commit:** `feat(fe): add 2D/3D view toggle and static 3D building scene`

---

## P2 — CO2 / IAQ backend

New functions/fields only — never modify existing physics.

- `backend/thermal_model.py` (ADD only)
  - `RoomConfig`: add `nominal_volume_m3: float = 100.0`.
  - `RoomState`: add `co2_ppm: float = 450.0`.
  - `compute_next_co2(co2_ppm, occupancy, airflow_lps, volume_m3, dt_minutes, co2_outdoor=420)`
    implementing `dC/dt[ppm/s] = (Gocc*1e6 + airflow_lps*(420 - C)) / (V*1000)`,
    `Gocc = 0.005 L/s/occupant`, integrate over `dt_minutes*60`, clamp `[400, 3000]`.
- `backend/comfort_model.py` (ADD only)
  - `iaq_score(co2_ppm)`: 100 at ≤800, 0 at ≥2000, linear between.
  - `overall_comfort_score(comfort_score, iaq) = 0.7*comfort + 0.3*iaq`.
- `backend/digital_twin.py`
  - `_make_configs()`: per-room volumes **A:80, B:150, C:60, D:100**.
  - `_make_states()`: init `co2_ppm = 450`.
  - `step()`: update CO2 per room (after humidity); compute `iaq_score` + `overall_comfort_score`.
  - `_snapshot()`: emit `co2_ppm`, `iaq_score`, `overall_comfort_score`.
  - `_snapshot_and_record()`: add `co2_ppm` to history points.
- `backend/models.py`: `RoomStateResponse` gains the three fields (additive).
- `backend/simulation_manager.py`
  - `set_nlp_constraint(...)` gains optional `source: str = "nlp"`.
  - IAQ rule after each `twin.step()`: `co2_ppm > 1000` and no active constraint → existing
    `increase_airflow` path, `source="iaq_rule"`, target co2 < 900. No parallel mechanism.
  - `_apply_overlays(...)` runs in **both** modes (see decision above).
- `backend/requirements-dev.txt` (NEW): `pytest`, `httpx` — pinned, justified.
- `backend/tests/test_iaq.py` (NEW): CO2 rise/decay, `iaq_score` bounds/monotonicity,
  per-room volume, rule triggers at >1000 and does **not** re-trigger with an active constraint.
- `frontend/src/types.ts`: mirror the three new fields.

**Acceptance:** pytest green; live JSON shows Room B `co2_ppm` climbing at 12 occupants and the
rule firing (`active_constraint` = INCREASE_AIRFLOW, source `iaq_rule`).
**Commit:** `feat(be): add CO2/IAQ state, iaq_score, and IAQ-driven airflow rule`

---

## P3 — Furniture & people assets

- Download Kenney Furniture Kit (CC0) + Quaternius low-poly people (CC0/CC-BY); self-host under
  `frontend/public/models/` (glTF/GLB). Never hotlink.
- `CREDITS.md` (asset, author, license, source URL).
- Personas: A Conference (large table + 8 chairs); B Engineering (6–8 desks + monitors + chairs);
  C Server/IT (2–3 racks, minimal); D Reception (desk + lounge/sofa). Labels "Conference",
  "Engineering", "Server Room", "Reception" — display only; IDs stay A/B/C/D.
- Perf: `useGLTF` + instancing; no postprocessing; one ambient + one directional light.

**Acceptance:** personas recognizable; frame time measured on a mid laptop (60fps target).
**Commit:** `feat(fe): add self-hosted furniture and people assets, place per-room personas`

---

## P4 — Live data → visual wiring (**risk: perf**)

- Temperature tint: port `temperatureColor` math to `THREE.Color`.
- Occupancy: exactly `occupancy` avatars at desks.
- Airflow: vent fan rotation mapped over 50–300 L/s.
- `overall_comfort_score` floating indicator: green ≥75, amber ≥55, red <55.
- CO2/IAQ: semi-transparent haze volume, opacity rising with ppm.
- `active_constraint`: amber beacon. `hvac_power_kw`: vent glow intensity.
- Price response (after P6): vent badge/glow.

**Verify manually:** avatars == `occupancy` for all rooms; 60fps. Do not trust self-report.
**Commit:** `feat(fe): wire live twin state into 3D scene visuals`

---

## P5 — Constraint lifecycle + physics-derived deltas + reactions

- Constraint objects: `id, room, action, source, created_at, expires_at, applied_delta,
  llm_raw_delta, status`.
- Keep `active_constraint` string; add `constraints` list (active + last 50 resolved) + stats
  (counts by status, median resolution minutes) to the state response.
- Expiry verification: thermal → PMV within `[-0.5, 0.5]`; airflow/IAQ → `co2_ppm < 950`.
  Satisfied early → release, `status="resolved"`, log resolution time. Not satisfied → renew
  **once** with 1.5× delta + chat notification; second failure → `escalated`, flagged in UI.
- `GET /api/constraints`; `POST /api/constraints/{id}/react {helpful: bool}`.
- Physics-derived delta: `applied_delta = sign * clip((|PMV| * 0.7) / 0.3, 0.5, 2.5)`; severity
  → expiry only (high 45 / medium 30 / low 20 sim-minutes). Log `llm_raw_delta` + `applied_delta`.
- Models: `ConstraintResponse`, `ConstraintListResponse`, `ConstraintReactRequest`; mirror in `types.ts`.
- Tests: resolution-success, renew, escalate-on-second-failure.

**Acceptance:** complaint → resolution tracked end-to-end; renew + escalate paths tested.
**Commit:** `feat(be): constraint lifecycle manager with physics-derived deltas and reactions`

---

## P6 — Price overlay + TOU + parity charts + demo macros (**risk: guard math**)

- TOU defaults `00-06=4, 06-14=6, 14-20=9, 20-24=6` INR/kWh; `POST /api/environment/tariff
  {slots:[{from_h,to_h,price}]}`.
- Building state: `current_price`, `cost_today`, `baseline_cost_today`, `peak_kw_15min`,
  `baseline_average_comfort`.
- Overlay (`source="price_response"`, persistent while condition holds, excluded from complaint stats):
  pre-peak −1.0 °C; peak +1.5 °C while occupied; **comfort guard ±0.7 PMV** reducing bias until within.
- Frontend: "Price response active" badge + shaded peak window; charts for cost vs baseline cost,
  peak marker, comfort parity.
- Demo macros (existing endpoints only): "Stuffy Room B" (occupancy 14, airflow 60),
  "Heat wave" (outside 38), "Force peak pricing now"; price/TOU editor; weather toggle (P7).

**Verify manually:** force peak → pre-cool then relax; PMV never beyond ±0.7; cost savings vs
baseline at comfort parity.
**Commit:** `feat(be,fe): TOU price-response overlay with comfort guard, parity charts, demo macros`

---

## P7 — Live weather (Open-Meteo, fail-safe)

- `POST /api/environment/weather {source, latitude, longitude}` + env var; `weather_source`
  `"simulated"|"live"`, default `simulated`.
- Fetch every 10 min, no key.
- **Architecture:** fetch on a **separate daemon thread** updating a cached temperature; the sim
  tick only reads the cache. No HTTP inside the tick loop.
- Any failure → fall back to diurnal+stochastic for that tick, log, never break/block the loop.
- `types.ts` mirror.

**Acceptance:** wifi off → sim continues on simulated weather, no errors.
**Commit:** `feat(be,fe): live Open-Meteo weather with fail-safe fallback`

---

## P8 — NLP evaluation harness

- `tools/nlp_eval.py` + `docs/nlp_eval_cases.json`: ~45 labeled cases — hot/cold/stuffy/drafty;
  room synonyms; no-room ambiguity; out-of-scope; sarcasm; 2–3 non-English.
- Imports `nlp_engine.parse_complaint` with a fixed mocked context, calls Groq live
  (`GROQ_API_KEY` via `.env`), writes `docs/nlp_eval_report.md`: intent accuracy, room accuracy,
  out-of-scope rejection (target 100%), failures table.
- If OOS < 100%: tune **only prompt string constants** in `nlp_engine.py`, re-run, log before/after.
  *(Optional: the room-context builder has a stale comment claiming PMV isn't available — it is;
  adding PMV/CO2 to context may help.)*

**Acceptance:** report exists with numbers; OOS rejection 100% (or tuned + logged).
**Commit:** `feat(tools): NLP evaluation harness with labeled cases and report`

---

## P9 — Polish, rehearsal, freeze

- Click-to-select in 3D reusing `selectedRoom`.
- Offline rehearsal: `weather = simulated`, no internet; full DoD walk-through.
- Final `PROGRESS.md` pass; **FREEZE**.

**Commit:** `chore: polish 3D scene, offline rehearsal, freeze for demo`

---

## Definition of Done (mapped)

- 3D replaces 2D via toggle, 2D kept as fallback, same polled state. (P1, P4, P9)
- Avatars match `occupancy` exactly. (P4)
- Visible loop: complaint/demo → constraint → fan spins faster → haze recedes → comfort recovers
  → resolution logged → "Did that help?" records. (P2, P4, P5)
- Price story: peak → pre-cool → guarded relax → cost chart savings at comfort parity. (P6)
- `docs/nlp_eval_report.md` exists with numbers. (P8)
- Zero internet dependency in simulated mode. (P7)
- Nothing on the protected list structurally modified. (all)

---

## Protected-file compliance checklist (every phase)

- `rl/**` — read-only; no obs/action-space changes; no retraining.
- `backend/nlp_engine.py` — only prompt-string constants, logged with eval before/after.
- `thermal_model.py` / `comfort_model.py` — ADD functions/fields only; never alter existing math.
- `digital_twin/` standalone package + tests — untouched.
- Existing REST contracts — additive optional fields only; nothing removed or renamed.

---

## Verification

```powershell
# Backend
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
pytest backend/tests -q
uvicorn backend.main:app --reload          # http://localhost:8000

# Frontend
cd frontend; npm install; npm run dev       # http://localhost:3000

# NLP harness (P8)
python tools/nlp_eval.py                     # needs GROQ_API_KEY in .env
```

Manual checks at the risky phases:
- **P4:** avatars count == `occupancy` per room; sustained ~60fps.
- **P6:** after "Force peak pricing now", pre-cool then relax, PMV never exceeds ±0.7;
  cost chart shows savings vs baseline at comfort parity.

---

## Risks / open items

- **P4 perf** and **P6 guard math** are the two most likely failure points — verify personally.
- R3F/React 19 version pinning may need adjustment in P1.
- Overlay-in-both-modes is an intentional deviation (the clamp layer is auto-only today).
  Flag if you'd rather overlays stay auto-only — that would break the manual-mode demo macros.
