"""
main.py  —  FastAPI application for the 4-room Digital Twin.

Endpoints:
  GET  /api/health
  GET  /api/simulation/state
  GET  /api/simulation/history
  POST /api/simulation/start
  POST /api/simulation/pause
  POST /api/simulation/reset
  POST /api/simulation/speed
  POST /api/rooms/{room_id}/setpoint
  POST /api/rooms/{room_id}/occupancy
  POST /api/rooms/{room_id}/airflow
  POST /api/environment/outside-temperature
  POST /api/environment/electricity-price
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    AirflowRequest,
    ElectricityPriceRequest,
    MessageResponse,
    OccupancyRequest,
    OutsideSensorDataRequest,
    OutsideTemperatureRequest,
    ROOM_IDS,
    RLModeRequest,
    ChatMessageRequest,
    SensorDataRequest,
    SetpointRequest,
    SimulationSpeedRequest,
)
from .simulation_manager import SimulationManager
from .nlp_engine import parse_complaint

# ──────────────────────────────────────────────
# Global simulation manager (singleton)
# ──────────────────────────────────────────────

manager = SimulationManager(
    step_minutes=5.0,
    tick_interval_seconds=1.0,
    outside_temperature_c=34.0,
    electricity_price_per_kwh=8.5,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing special — manager is already initialised
    yield
    # Shutdown: stop background thread
    manager.pause()


# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────

app = FastAPI(
    title="Digital Twin Building Simulator",
    description=(
        "4-room simplified grey-box thermal digital twin simulation. "
        "NOT physically calibrated. NOT EnergyPlus. NOT ASHRAE PMV."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # For development. Restrict in production.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────

def _validate_room(room_id: str) -> None:
    if room_id.upper() not in ROOM_IDS:
        raise HTTPException(
            status_code=404,
            detail=f"Room '{room_id}' not found. Valid rooms: {sorted(ROOM_IDS)}"
        )


# ──────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────

@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "simulation": "digital-twin-v0.2"}


# ──────────────────────────────────────────────
# Simulation state & history
# ──────────────────────────────────────────────

@app.get("/api/simulation/state", tags=["simulation"])
def get_state():
    """Return current simulation state (polled by frontend every ~1 s)."""
    return manager.get_state()


@app.get("/api/simulation/history", tags=["simulation"])
def get_history():
    """Return full recorded history for charts."""
    return {"history": manager.get_history()}


# ──────────────────────────────────────────────
# Simulation control
# ──────────────────────────────────────────────

@app.post("/api/simulation/start", response_model=MessageResponse, tags=["simulation"])
def start_simulation():
    manager.start()
    return MessageResponse(message="Simulation started.")


@app.post("/api/simulation/pause", response_model=MessageResponse, tags=["simulation"])
def pause_simulation():
    manager.pause()
    return MessageResponse(message="Simulation paused.")


@app.post("/api/simulation/reset", response_model=MessageResponse, tags=["simulation"])
def reset_simulation():
    manager.reset()
    return MessageResponse(message="Simulation reset to initial conditions.")


@app.post("/api/simulation/speed", response_model=MessageResponse, tags=["simulation"])
def set_speed(body: SimulationSpeedRequest):
    manager.set_speed(body.speed)
    return MessageResponse(message=f"Speed set to {body.speed}×.")


# ──────────────────────────────────────────────
# Room controls
# ──────────────────────────────────────────────

@app.post("/api/rooms/{room_id}/setpoint", response_model=MessageResponse, tags=["rooms"])
def set_setpoint(
    room_id: str = Path(..., description="Room ID: A, B, C, or D"),
    body: SetpointRequest = ...,
):
    _validate_room(room_id.upper())
    manager.set_setpoint(room_id.upper(), body.setpoint_c)
    return MessageResponse(message=f"Room {room_id.upper()} setpoint → {body.setpoint_c}°C.")


@app.post("/api/rooms/{room_id}/occupancy", response_model=MessageResponse, tags=["rooms"])
def set_occupancy(
    room_id: str = Path(..., description="Room ID: A, B, C, or D"),
    body: OccupancyRequest = ...,
):
    _validate_room(room_id.upper())
    manager.set_occupancy(room_id.upper(), body.occupancy)
    return MessageResponse(message=f"Room {room_id.upper()} occupancy → {body.occupancy}.")


@app.post("/api/rooms/{room_id}/airflow", response_model=MessageResponse, tags=["rooms"])
def set_airflow(
    room_id: str = Path(..., description="Room ID: A, B, C, or D"),
    body: AirflowRequest = ...,
):
    _validate_room(room_id.upper())
    manager.set_airflow(room_id.upper(), body.airflow_lps)
    return MessageResponse(message=f"Room {room_id.upper()} airflow → {body.airflow_lps} L/s.")


@app.post("/api/rooms/{room_id}/sensor-data", response_model=MessageResponse, tags=["hardware"])
def inject_sensor_data(
    room_id: str = Path(..., description="Room ID: A, B, C, or D"),
    body: SensorDataRequest = ...,
):
    """
    Hardware sensor override for a room.

    Push real sensor readings here to anchor the digital twin to reality.
    Only fields you provide are overwritten — omit fields you don't have sensors for.

    Expected call frequency: every 1–60 seconds from your hardware bridge.

    Future integration:
      Replace manual calls with an MQTT/Modbus/BACnet bridge that reads
      physical sensors and calls this endpoint automatically.
    """
    _validate_room(room_id.upper())
    updated = manager.inject_sensor_data(
        room_id.upper(),
        body.model_dump(exclude_none=True),
    )
    fields = ", ".join(updated.keys()) or "none"
    return MessageResponse(message=f"Room {room_id.upper()} sensor override applied. Fields updated: {fields}.")


# ──────────────────────────────────────────────
# Environment
# ──────────────────────────────────────────────

@app.post("/api/environment/outside-temperature", response_model=MessageResponse, tags=["environment"])
def set_outside_temperature(body: OutsideTemperatureRequest):
    manager.set_outside_temperature(body.temperature_c)
    return MessageResponse(message=f"Outside temperature → {body.temperature_c}°C.")


@app.post("/api/environment/electricity-price", response_model=MessageResponse, tags=["environment"])
def set_electricity_price(body: ElectricityPriceRequest):
    manager.set_electricity_price(body.price_per_kwh)
    return MessageResponse(message=f"Electricity price → ₹{body.price_per_kwh}/kWh.")


@app.post("/api/environment/sensor-data", response_model=MessageResponse, tags=["hardware"])
def inject_outside_sensor_data(body: OutsideSensorDataRequest):
    """
    Hardware sensor override for outdoor environment.

    Push real weather station readings here.
    When temperature_c is provided, diurnal/stochastic weather generation
    is automatically disabled and the real sensor value is used instead.

    Future integration:
      Wire to an outdoor weather station via MQTT or a REST weather API
      (e.g., OpenWeatherMap) to keep the twin synced with real conditions.
    """
    updated = manager.inject_outside_sensor_data(body.model_dump(exclude_none=True))
    fields = ", ".join(updated.keys()) or "none"
    return MessageResponse(message=f"Outside environment sensor override applied. Fields updated: {fields}.")


# ──────────────────────────────────────────────
# RL Auto Mode
# ──────────────────────────────────────────────

@app.post("/api/rl/mode", response_model=MessageResponse, tags=["rl"])
def set_rl_mode(body: RLModeRequest):
    """
    Switch the simulation between Manual and Auto (RL agent) control.

    Manual mode: user controls setpoints and airflow via the UI.
    Auto mode:   a trained PPO policy controls all rooms autonomously.
                 The policy runs once per simulation step (every 5 sim-minutes).

    Body:
      mode        : "manual" | "auto"
      model_path  : path to .zip policy (required for "auto").
                    Example: "rl/models/test_run/best_model.zip"
    """
    try:
        manager.set_rl_mode(body.mode, body.model_path)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    msg = (
        f"RL mode set to AUTO. Policy loaded: {body.model_path}"
        if body.mode == "auto"
        else "RL mode set to MANUAL. User controls active."
    )
    return MessageResponse(message=msg)


@app.get("/api/rl/status", tags=["rl"])
def get_rl_status():
    """Return current RL mode and loaded model path."""
    state = manager.get_state()
    return {
        "rl_mode":       state.get("rl_mode", "manual"),
        "rl_model_path": state.get("rl_model_path"),
    }

# ──────────────────────────────────────────────
# NLP Chatbot
# ──────────────────────────────────────────────

@app.post("/api/chat/message", tags=["chat"])
def chat_message(body: ChatMessageRequest):
    """
    Receives a natural language complaint, parses it using an LLM,
    and applies a temporary constraint to the simulation if valid.
    """
    state = manager.get_state()
    constraint = parse_complaint(body.message, state)
    
    room_id = constraint.get("room_id")
    action = constraint.get("action")
    
    if action != "none" and room_id:
        manager.set_nlp_constraint(
            room_id=room_id,
            action=action,
            urgency=constraint.get("urgency", "medium"),
            setpoint_delta_c=constraint.get("setpoint_delta_c", 0.0),
            duration_mins=30.0
        )
        
    return {
        "action_taken": f"Constraint applied to Room {room_id}: {action}" if action != "none" and room_id else "No action taken.",
        "constraint": constraint
    }

