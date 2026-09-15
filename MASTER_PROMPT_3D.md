# JARVIS 3D — Final Build Prompt (Additive Extension)

You are extending JARVIS, an existing, working, end-to-end HVAC digital twin (FastAPI backend:
4-room grey-box physics, PPO RL controller, Groq NLP complaint parser; React+TS+Vite frontend).
This build is **ADDITIVE**: a real-time 3D scene plus small, well-scoped backend overlay features.
You are NOT rebuilding the backend, NOT retraining RL, NOT redesigning the NLP engine.

Work on the git branch `feature/3d-twin` (create it if missing). Never commit to `main`.
Track all progress in `PROGRESS.md` at repo root.

---

## 0. READ THESE FILES FIRST (you have full repo access — use it)

`backend/main.py`, `backend/simulation_manager.py`, `backend/digital_twin.py`,
`backend/thermal_model.py`, `backend/comfort_model.py`, `backend/energy_model.py`,
`backend/baseline.py`, `backend/nlp_engine.py`, `backend/models.py`,
`frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/types.ts`,
`frontend/src/components/BuildingMap.tsx`, `frontend/src/utils/temperatureColor.ts`,
`rl/agent.py` (READ-ONLY).

Summarize what you found in `PROGRESS.md` before coding.

---

## 1. PROTECTED — do not touch without stopping and asking first

- `rl/` — training pipeline, PPO hyperparameters, saved `.zip` policies (read-only).
- `backend/nlp_engine.py` — **EXCEPTION:** you may edit ONLY the system-prompt string constants
  to improve parsing accuracy; log every such edit in `PROGRESS.md` with eval-harness scores
  before/after. No structural changes.
- Core equations in `thermal_model.py` / `comfort_model.py` (2R1C physics, Fanger PMV/PPD).
  You may **ADD** new functions; never modify existing math.
- `digital_twin/` standalone package and `digital_twin/tests/`.
- Existing REST contracts: additive optional fields only; never remove/rename.
- No changes to RL observation/action spaces. No PPO retraining.
  All new control behavior is deterministic overlays in the constraint/clamp layer — the same
  architecture the existing NLP constraints already use.

---

## 2. BACKEND ADDITIONS (in this order)

### 2.1 CO2 / IAQ model (new field + functions)

Per-room `co2_ppm` state. Mass balance per 5-min step, per room:
`V` = nominal volume m³ (A:80, B:150, C:60, D:100 — documented assumption);
`G` = 0.005 L/s CO2 per occupant; supply airflow treated as fresh air (documented simplification);
outdoor = 420 ppm; init 450; clamp [400, 3000].

```
dC/dt [ppm/s] = (Gocc*1e6 + airflow_lps*(420 - C)) / (V*1000)
```

New function `iaq_score(co2_ppm)` in `comfort_model.py`: 100 at <=800, 0 at >=2000, linear between.

New per-room field `overall_comfort_score = 0.7*comfort_score + 0.3*iaq_score`
plus `co2_ppm` and `iaq_score` in the room state response (additive fields).

IAQ rule in `simulation_manager.py`: if room `co2 > 1000 ppm` AND no active constraint on that
room, trigger the EXISTING `increase_airflow` constraint mechanism (same clamp/expiry code path
as NLP complaints), tagged `source="iaq_rule"`, target co2 < 900. Do not build a parallel mechanism.

### 2.2 Constraint lifecycle manager (close the feedback loop)

Upgrade constraints to objects with: `id, room, action, source ("nlp"|"iaq_rule")`, `created_at`,
`expires_at`, `applied_delta`, `llm_raw_delta`, `status`.

Keep the existing `active_constraint` string field for compatibility; add `constraints` list
(active + last 50 resolved) to the state response.

On expiry: verify outcome (thermal constraints: room PMV within [-0.5, 0.5]; airflow/IAQ: co2 < 950).
If satisfied -> release early when satisfied before expiry, log `status="resolved"`, resolution time.
If not -> renew ONCE with 1.5x delta and send a chat notification; second failure ->
`status="escalated"`, flagged in UI.

New endpoints: `GET /api/constraints` (list + stats: counts by status, median resolution minutes);
`POST /api/constraints/{id}/react {helpful: bool}`.

### 2.3 Physics-derived constraint deltas (applied at the clamp site)

In `simulation_manager.py` where constraints clamp setpoints: for thermal actions, compute the
applied delta from live comfort state instead of the LLM's raw number:

```
applied_delta = sign * clip((|PMV| * 0.7) / 0.3, 0.5, 2.5)
```

sign from action direction. Severity maps ONLY to expiry (high 45 / medium 30 / low 20 sim-minutes).
Log both `llm_raw_delta` and `applied_delta`.
Rationale for docs: the LLM understands language; physics decides magnitude.

### 2.4 Price-response overlay (reuses the clamp layer, no RL changes)

TOU tariff: default slots `00-06=4, 06-14=6, 14-20=9 (peak), 20-24=6` (INR/kWh).
New endpoint `POST /api/environment/tariff {slots:[{from_h,to_h,price}]}`.
Building state gains: `current_price`, `cost_today`, `baseline_cost_today`,
`peak_kw_15min` (rolling 15-min max power), `baseline_average_comfort`.

Overlay logic (in the same clamp code path, tagged `source="price_response"`, persistent while
condition holds, NOT counted in complaint stats):
- 60 min before peak window: setpoint bias `-1.0 C` (pre-cool).
- During peak while room occupied: setpoint relax `+1.5 C`.
- **COMFORT GUARD:** never let the overlay push any room's PMV beyond +/-0.7; reduce the bias
  until within guard. This guard is the feature's selling point: price savings bounded by an
  explicit comfort constraint.

Frontend: badge "Price response active" + shaded peak window on charts.

### 2.5 Live weather (Open-Meteo, fail-safe)

Background fetch every 10 min:
`https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true`
(no key needed).

Setting `weather_source: "simulated"|"live"` (env var + endpoint
`POST /api/environment/weather {source, latitude, longitude}`). Default `simulated`.
On ANY fetch failure: silently fall back to the existing diurnal+stochastic model for that tick
and log. A failed HTTP call must NEVER break the simulation loop or block a tick.

### 2.6 NLP evaluation harness (standalone, in `tools/`)

`tools/nlp_eval.py` + `docs/nlp_eval_cases.json`: ~45 labeled complaints — hot/cold/stuffy/drafty;
room synonyms ("the big meeting room"=A, "where the devs sit"=B, "server/IT"=C,
"reception/front"=D); no-room ambiguity; OUT-OF-SCOPE cases ("too noisy", "glare on my screen",
"chair is broken"); sarcasm; 2-3 non-English.

Harness imports the existing `nlp_engine` parse function with a fixed mocked building context,
calls Groq live (needs `GROQ_API_KEY`), and prints + writes `docs/nlp_eval_report.md`:
intent accuracy, room accuracy, out-of-scope rejection rate (target 100%), table of failures.

If out-of-scope rejection < 100%, you may tune the system-prompt string in `nlp_engine.py`
per section 1's exception, then re-run and log before/after.

---

## 3. FRONTEND — 3D SCENE

### 3.1 Component

`frontend/src/components/BuildingScene3D.tsx` with `@react-three/fiber` + `@react-three/drei`.
Add a 2D/3D view toggle in `App.tsx` that switches between `BuildingMap.tsx` and
`BuildingScene3D` (keep `BuildingMap` working — it is the fallback). Consume the SAME
already-polled state via props; no second loop.

### 3.2 Layout

Four room volumes in the existing 2x2 grid (A|B top, C|D bottom — matches physics adjacency).
Low walls + glass partitions so all rooms are visible from the default camera. `OrbitControls`;
default isometric-ish angle that looks correct untouched.

### 3.3 Furniture & people — match `baseline.py` personas

A (Conference): large table + 8 chairs. B (Engineering open-plan): 6-8 desks with monitors + chairs.
C (Server/IT): 2-3 rack-style boxes, minimal. D (Reception): reception desk + lounge chairs/sofa.
Label rooms with persona names in the 3D scene and UI: A "Conference", B "Engineering",
C "Server Room", D "Reception" (display only — room IDs in code stay A/B/C/D).

Assets: Kenney Furniture Kit (CC0, kenney.nl / poly.pizza) and Quaternius low-poly people
(CC0/CC-BY, poly.pizza / quaternius.com). Self-host ALL models under `frontend/public/models/` —
never hotlink. Add `CREDITS.md`.

### 3.4 Data -> visual mapping (same-polled state)

| Field | Visual |
|---|---|
| `temperature_c` | floor/wall tint — port `temperatureColor.ts` logic to `THREE.Color` |
| `occupancy` | people avatar count spawned at desks (must match the number exactly) |
| `airflow_lps` | vent fan mesh rotation speed (map 50-300 L/s range) |
| `overall_comfort_score` | floating per-room indicator: green >=75, amber >=55, red <55 |
| `co2_ppm` / `iaq_score` | in-room haze: semi-transparent volume, opacity rises with ppm |
| `active_constraint` | amber beacon/glow on the room |
| `hvac_power_kw` | vent glow intensity |
| price_response active | subtle badge/glow on vents + chart shading |

### 3.5 Demo controls (frontend macros over EXISTING endpoints only)

Next to the scene: electricity price / TOU editor; weather source toggle + lat/lon; and scripted
demo buttons: "Stuffy Room B" (occupancy 14, airflow 60), "Heat wave" (outside temp 38),
"Force peak pricing now". These call existing REST endpoints — zero new backend surface.

### 3.6 Performance

Instancing for repeated furniture; `useGLTF`; one ambient + one directional light; no postprocessing.
Target 60fps on a mid laptop — test on day 1-2, not the night before.

---

## 4. BUILD PHASES (one per session; run, test, commit after each)

- **P1:** branch + `PROGRESS.md` + deps (three, `@react-three/fiber`, `@react-three/drei`) +
  static dummy 3D scene behind the toggle with hardcoded data. ACCEPT: app runs, toggle switches 2D/3D.
- **P2:** CO2/IAQ backend (2.1) + pytest for the CO2 dynamics, `iaq_score`, and the `iaq_rule` trigger.
  ACCEPT: tests green; state JSON shows `co2_ppm` climbing in Room B at 12 occupants and the rule firing.
- **P3:** furniture assets downloaded + placed per persona; perf verified.
- **P4:** live wiring — temperature tint, occupancy avatars, comfort indicator, CO2 haze, fan rotation,
  constraint beacon. ACCEPT: counts visibly match API numbers; 60fps.
- **P5:** constraint lifecycle + physics-derived deltas + reaction buttons + `/api/constraints`.
  ACCEPT: complaint -> resolution tracked; renew/escalate paths tested.
- **P6:** price overlay + TOU endpoint + cost/peak/parity fields + dashboard charts (cost vs baseline
  cost, peak marker, comfort parity) + demo macro buttons. ACCEPT: "Force peak pricing" shows pre-cool
  then relax, comfort guard holds PMV within +/-0.7.
- **P7:** live weather + toggle + fail-safe. ACCEPT: wifi off -> sim continues on simulated weather, no errors.
- **P8:** NLP eval harness + report. ACCEPT: report file exists; out-of-scope rejection 100%
  (or prompt tuned + logged to reach it).
- **P9:** polish, click-to-select reusing `selectedRoom`, offline rehearsal (weather= simulated,
  no internet), then FREEZE — no new features.

---

## 5. DEFINITION OF DONE

- 3D scene replaces 2D map (toggle keeps 2D fallback), driven by the same polled state; occupant
  avatars match occupancy exactly.
- End-to-end visible loop: "it's stuffy in Room B" (or the demo button) -> constraint -> fan visibly
  spins faster -> haze recedes -> comfort recovers -> resolution logged -> "Did that help?" button records it.
- Price story: peak pricing -> pre-cool -> comfort-guarded relax -> cost chart shows savings vs
  baseline at comfort parity.
- `docs/nlp_eval_report.md` exists with accuracy numbers.
- Zero internet dependency in simulated mode. Nothing in the protected list was structurally modified.

---

## 6. WORKING RULES

- One phase per session. Never silently refactor protected files.
- After each phase: run backend tests + both dev servers, verify manually, update `PROGRESS.md`
  (files touched, decisions, deviations), commit.
- New dependencies require a logged justification; pin versions.
- TS types must mirror every new Pydantic field.
- If anything seems to require touching protected code, STOP and ask.
- No secrets in code; `GROQ_API_KEY` via `.env`.

## How to drive it

One phase per session: "Read MASTER_PROMPT_3D.md and PROGRESS.md, then execute Phase N only."

After every phase you verify and commit. The two most likely failure points to watch: P4 (Three.js
perf) and P6 (the comfort guard math) — test those yourself, don't trust the agent's self-report.

Run `tools/nlp_eval.py` yourself and screenshot the report — that plus the comfort-parity chart are
your receipts against the "AI-generated, unproven" judge critique.

Report back when P2 or P6 gives you trouble and we'll debug the spec.
