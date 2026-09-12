"""
nlp_engine.py  —  Groq LLM parsing layer for the Digital Twin NLP Feedback system.

Converts natural-language user complaints into structured HVAC constraint actions
using the Llama model via the Groq API.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict

from groq import Groq

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def _get_client() -> Groq:
    return Groq(api_key=os.getenv("GROQ_API_KEY", ""))

_client = _get_client()

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# ──────────────────────────────────────────────
# Prompt helpers
# ──────────────────────────────────────────────

_SYSTEM_TEMPLATE = """\
You are an AI Building Management System (BMS) assistant embedded in a 4-room office building \
digital twin simulator. Your job is to interpret occupant comfort complaints in natural language \
and translate them into structured HVAC control actions.

CURRENT BUILDING STATE (real-time):
{room_context}

AVAILABLE ROOMS & ALIASES:
- Room A: "Conference Room", "big meeting room", "boardroom", "presentation room", "main conference"
- Room B: "Engineering", "open office", "where the devs sit", "dev pit", "developers", "engineering area"
- Room C: "Server Room", "IT closet", "data center", "server racks", "tech room"
- Room D: "Reception", "front desk", "lobby", "waiting area", "entrance", "front lobby"

SETPOINT BOUNDS: 16°C minimum, 30°C maximum

ACTIONS YOU CAN TAKE:
- increase_temp    → raise the room setpoint (occupant feels cold/freezing/chilly/teeth chattering)
- decrease_temp    → lower the room setpoint (occupant feels hot/warm/sweltering/boiling/sweating/sauna)
- increase_airflow → increase supply airflow L/s (occupant feels stuffy/stale air/suffocating/poor air quality/high CO2)
- decrease_airflow → decrease supply airflow L/s (occupant feels drafty/too much wind/blowing papers/hurricane)
- set_setpoint     → set an explicit target temperature mentioned in the complaint/request (e.g. "set to 22°C", "set room a to 19 c")
- set_occupancy    → set or update room occupancy / headcount / people / pax (e.g. "set occupancy in room a to 15", "10 people in conference room", "room is empty" → 0)
- set_airflow      → set an explicit supply airflow in L/s (e.g. "set airflow in room a to 180", "set airflow to 200 L/s")
- none             → non-actionable or out-of-scope complaint

CRITICAL OUT-OF-SCOPE REJECTION RULE (TARGET 100% REJECTION):
You ONLY manage thermal comfort, temperature, airflow, and ventilation.
If the complaint is about ANY non-HVAC topic, including but not limited to:
- Furniture (e.g., broken/wobbly chair, desk, table)
- Noise / acoustics (e.g., loud talking, laughter, noisy calls)
- Lighting / visuals (e.g., monitor glare, bright sun, flickering light bulb, blinds)
- Refreshments / pantry (e.g., coffee machine empty, snacks, lunch, catering)
- IT / networking / peripherals (e.g., Wi-Fi dropping, mouse battery, stuck keyboard key, printer jam)
- Housekeeping / cleaning (e.g., spilled soda on carpet, trash, messy desks)
YOU MUST IMMEDIATELY RETURN:
  "room_id": null,
  "action": "none",
  "urgency": "low",
  "setpoint_delta_c": 0.0,
  "rationale": "Out of scope: complaint pertains to facilities/IT/furniture/noise, not HVAC or thermal comfort.",
  "confidence": 0.99
Do NOT take any HVAC action for out-of-scope issues.

URGENCY RULES:
- high   → extreme words: "freezing", "burning", "boiling", "sweltering", "unbearable", "emergency", "cannot work", "scorching", "icebox"
- medium → moderate words: "too hot", "a bit cold", "uncomfortable", "warm", "stuffy", "drafty"
- low    → mild words: "slightly", "a little", "maybe", "could be better", "tiny bit"

DELTA RULES:
- For increase_temp / decrease_temp: use 1.0–4.0°C delta based on urgency
  - high urgency → 3.0–4.0°C  |  medium → 1.5–2.5°C  |  low → 1.0°C
- For set_setpoint: setpoint_delta_c is the ABSOLUTE target temperature mentioned (in °C, e.g. 19.0)
- For set_occupancy: setpoint_delta_c is the ABSOLUTE number of occupants (e.g. 15.0, or 0.0 if empty)
- For set_airflow: setpoint_delta_c is the ABSOLUTE target airflow in L/s (e.g. 180.0)
- For increase_airflow / decrease_airflow: setpoint_delta_c = airflow change in L/s (positive value: 20-50 L/s)
- For none: setpoint_delta_c = 0.0

MULTILINGUAL & SARCASM:
- Handle common sarcastic complaints (e.g., "arctic expedition" / "penguins" = freezing cold → increase_temp; "sauna" = boiling hot → decrease_temp; "hurricane" = extreme draft → decrease_airflow).
- Accurately parse non-English complaints (e.g., Spanish, French, Hindi/Hinglish) into the target actions.

RESPONSE FORMAT (return ONLY valid JSON, no markdown, no commentary):
{{
  "room_id": "B",
  "action": "decrease_temp",
  "urgency": "high",
  "setpoint_delta_c": 3.0,
  "rationale": "Occupant in Room B reports extreme heat. Lowering setpoint by 3°C from 24°C to 21°C.",
  "confidence": 0.95
}}

If no specific room is mentioned and cannot be inferred, set room_id to null.
If complaint is ambiguous or non-actionable, use action "none".
"""

_USER_TEMPLATE = "Occupant complaint: {complaint}"


def _build_room_context(state: Dict[str, Any]) -> str:
    """Format current room states into a human-readable block for the system prompt."""
    lines = []
    rooms = state.get("rooms", {})
    for rid in ["A", "B", "C", "D"]:
        r = rooms.get(rid)
        if not r:
            continue
        pmv_str = f", PMV={r.get('pmv', 0):.2f}" if "pmv" in r else ""
        co2_str = f", CO2={r.get('co2_ppm', 450):.0f}ppm" if "co2_ppm" in r else ""
        lines.append(
            f"  Room {rid}: air={r.get('temperature_c', 0):.1f}°C, "
            f"setpoint={r.get('setpoint_c', 0):.1f}°C, "
            f"humidity={r.get('humidity_pct', 0):.0f}%, "
            f"airflow={r.get('airflow_lps', 0):.0f} L/s, "
            f"occupants={r.get('occupancy', 0)}{co2_str}{pmv_str}"
        )
    outside = state.get("outside_temperature_c", 34.0)
    lines.append(f"  Outside: {outside:.1f}°C")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def parse_complaint(complaint: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call Groq with the complaint + current building state and return a
    validated constraint dictionary.

    Returns a dict with keys:
        room_id, action, urgency, setpoint_delta_c, rationale, confidence
    """
    room_context = _build_room_context(state)
    system_prompt = _SYSTEM_TEMPLATE.format(room_context=room_context)
    user_message = _USER_TEMPLATE.format(complaint=complaint)

    try:
        client = _get_client()
        active_model = os.getenv("GROQ_MODEL", MODEL)
        response = client.chat.completions.create(
            model=active_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
            max_tokens=1024,
            top_p=1,
            stream=False,
            stop=None,
        )
    except Exception as groq_err:
        # API key invalid, quota exceeded, network error, etc.
        return {
            "room_id": None,
            "action": "none",
            "urgency": "low",
            "setpoint_delta_c": 0.0,
            "rationale": f"AI backend error: {groq_err}",
            "confidence": 0.0,
        }

    raw = response.choices[0].message.content or ""

    # Strip markdown code fences if model wraps in ```json ... ```
    raw = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extract first JSON object from response
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            # Complete fallback if LLM returns garbage
            data = {
                "room_id": None,
                "action": "none",
                "urgency": "low",
                "setpoint_delta_c": 0.0,
                "rationale": "Could not parse complaint. No action taken.",
                "confidence": 0.0,
            }

    # Normalise and clamp values
    data["room_id"] = (data.get("room_id") or "").upper() or None
    if data["room_id"] not in {"A", "B", "C", "D"}:
        data["room_id"] = None
    data["action"] = data.get("action", "none")
    data["urgency"] = data.get("urgency", "medium")
    data["setpoint_delta_c"] = float(data.get("setpoint_delta_c", 0.0))
    data["rationale"] = str(data.get("rationale", ""))
    data["confidence"] = float(data.get("confidence", 0.5))

    return data
