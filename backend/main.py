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
    OutsideTemperatureRequest,
    ROOM_IDS,
    SetpointRequest,
    SimulationSpeedRequest,
)
from .simulation_manager import SimulationManager

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
