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

# Hardcoded for the hackathon as requested
_client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

MODEL = "openai/gpt-oss-120b"

# ──────────────────────────────────────────────
# Prompt helpers
# ──────────────────────────────────────────────

_SYSTEM_TEMPLATE = """\
You are an AI Building Management System (BMS) assistant embedded in a 4-room office building \
digital twin simulator. Your job is to interpret occupant comfort complaints in natural language \
and translate them into structured HVAC control actions.

CURRENT BUILDING STATE (real-time):
{room_context}

AVAILABLE ROOMS: A, B, C, D
SETPOINT BOUNDS: 16°C minimum, 30°C maximum

ACTIONS YOU CAN TAKE:
- increase_temp   → raise the room setpoint (occupant feels cold/freezing/chilly)
- decrease_temp   → lower the room setpoint (occupant feels hot/warm/stuffy/sweating)
- increase_airflow → increase supply airflow L/s (occupant feels stuffy/stale/poor air quality)
- decrease_airflow → decrease supply airflow L/s (occupant feels drafty/too much wind/blowing)
- set_setpoint    → set an explicit target temperature mentioned in the complaint
- none            → complaint noted but no actionable HVAC change needed

URGENCY RULES:
- high   → extreme words: "freezing", "burning", "unbearable", "emergency", "cannot work"
- medium → moderate words: "too hot", "a bit cold", "uncomfortable", "warm"
- low    → mild words: "slightly", "a little", "maybe", "could be better"

DELTA RULES:
- For increase_temp / decrease_temp: use 1.0–4.0°C delta based on urgency
  - high urgency → 3.0–4.0°C  |  medium → 1.5–2.5°C  |  low → 1.0°C
- For set_setpoint: setpoint_delta_c is the ABSOLUTE target temperature
- For airflow actions: setpoint_delta_c = airflow change in L/s (positive value)
- For none: setpoint_delta_c = 0.0

RESPONSE FORMAT (return ONLY valid JSON, no markdown, no commentary):
{{
  "room_id": "B",
  "action": "decrease_temp",
  "urgency": "high",
  "setpoint_delta_c": 3.0,
  "rationale": "Occupant in Room B reports extreme heat. Lowering setpoint by 3°C from 24°C to 21°C.",
  "confidence": 0.95
}}

If no specific room is mentioned, infer from context or set room_id to null (applies to all rooms).
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
        # Since PMV is not in RoomStateResponse yet, we'll estimate or omit it. 
        # Using comfort score directly to provide context:
        lines.append(
            f"  Room {rid}: air={r.get('temperature_c', 0):.1f}°C, "
            f"setpoint={r.get('setpoint_c', 0):.1f}°C, "
            f"humidity={r.get('humidity_pct', 0):.0f}%, "
            f"airflow={r.get('airflow_lps', 0):.0f} L/s, "
            f"occupants={r.get('occupancy', 0)}"
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
        response = _client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=1,
            max_completion_tokens=1024,
            top_p=1,
            reasoning_effort="medium",
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
