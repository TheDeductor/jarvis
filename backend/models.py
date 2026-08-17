"""
models.py  —  Pydantic request / response models for the Digital Twin API.

All validation logic lives here.
The FastAPI layer remains thin by delegating to these models.
"""
from __future__ import annotations

from typing import Dict, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────
# Constants (simulation bounds — NOT physical)
# ──────────────────────────────────────────────
ROOM_IDS = {"A", "B", "C", "D"}
SETPOINT_MIN, SETPOINT_MAX = 16.0, 30.0
OCCUPANCY_MIN, OCCUPANCY_MAX = 0, 100
AIRFLOW_MIN_LPS, AIRFLOW_MAX_LPS = 50.0, 300.0
OUTSIDE_TEMP_MIN, OUTSIDE_TEMP_MAX = -10.0, 55.0
SPEED_OPTIONS: set[int] = {1, 5, 20}


# ──────────────────────────────────────────────
# Request bodies
# ──────────────────────────────────────────────

class SetpointRequest(BaseModel):
    setpoint_c: float = Field(..., ge=SETPOINT_MIN, le=SETPOINT_MAX,
                              description="Target HVAC setpoint [°C]")


class OccupancyRequest(BaseModel):
    occupancy: int = Field(..., ge=OCCUPANCY_MIN, le=OCCUPANCY_MAX,
                           description="Number of occupants [persons]")


class AirflowRequest(BaseModel):
    airflow_lps: float = Field(..., ge=AIRFLOW_MIN_LPS, le=AIRFLOW_MAX_LPS,
                               description="Supply airflow [L/s]")


class SensorDataRequest(BaseModel):
    """
    Hardware sensor override for a single room.

    All fields are Optional — send only the sensors you physically have.
    On the next simulation step(), the twin will use these real values
    instead of its simulated estimates for the fields you provide.

    Future integration note:
      Replace manual POST calls with a hardware bridge (MQTT, Modbus, BACnet)
      that reads real sensors and calls this endpoint automatically.
    """
    temperature_c:      Optional[float] = Field(None, ge=-10.0, le=60.0,
                                               description="Room air temperature from sensor [°C]")
    wall_temperature_c: Optional[float] = Field(None, ge=-10.0, le=60.0,
                                               description="Wall/mass surface temperature [°C]")
    humidity_pct:       Optional[float] = Field(None, ge=0.0, le=100.0,
                                               description="Relative humidity from sensor [%]")
    occupancy:          Optional[int]   = Field(None, ge=0, le=500,
                                               description="Occupancy count from sensor [persons]")
    airflow_lps:        Optional[float] = Field(None, ge=0.0, le=1000.0,
                                               description="Duct airflow from meter [L/s]")
    hvac_power_kw:      Optional[float] = Field(None, ge=-100.0, le=100.0,
                                               description="Actual HVAC power from energy meter [kW] (signed)")


class OutsideSensorDataRequest(BaseModel):
    """
    Hardware sensor override for outdoor/environment conditions.
    """
    temperature_c: Optional[float] = Field(None, ge=OUTSIDE_TEMP_MIN, le=OUTSIDE_TEMP_MAX,
                                          description="Outdoor temperature from weather station [°C]")
    humidity_pct:  Optional[float] = Field(None, ge=0.0, le=100.0,
                                          description="Outdoor relative humidity [%]")


class OutsideTemperatureRequest(BaseModel):
    temperature_c: float = Field(..., ge=OUTSIDE_TEMP_MIN, le=OUTSIDE_TEMP_MAX,
                                 description="Outdoor air temperature [°C]")


class ElectricityPriceRequest(BaseModel):
    price_per_kwh: float = Field(..., ge=0.0,
                                 description="Electricity tariff [currency/kWh]")


class SimulationSpeedRequest(BaseModel):
    speed: int = Field(..., description="Simulation speed multiplier: 1, 5, or 20")

    @field_validator("speed")
    @classmethod
    def speed_must_be_valid(cls, v: int) -> int:
        if v not in SPEED_OPTIONS:
            raise ValueError(f"speed must be one of {SPEED_OPTIONS}")
        return v


class RLModeRequest(BaseModel):
    mode: Literal["manual", "auto"] = Field(
        ..., description="'auto' = RL agent controls HVAC, 'manual' = user controls"
    )
    model_path: Optional[str] = Field(
        None,
        description="Path to .zip policy file. Required when switching to 'auto'."
    )

class ChatMessageRequest(BaseModel):
    message: str = Field(..., description="The user's complaint text")



# ──────────────────────────────────────────────
# Response models
# ──────────────────────────────────────────────

class RoomStateResponse(BaseModel):
    room_id: str
    temperature_c: float
    wall_temperature_c: float     # 2R1C mass node temperature [°C]
    humidity_pct: float
    setpoint_c: float
    airflow_lps: float
    occupancy: int
    hvac_power_kw: float          # compressor/heating power [kW]
    active_constraint: Optional[str] = None
    fan_power_kw: float           # fan power [kW]
    total_power_kw: float         # hvac + fan [kW]
    energy_kwh: float             # accumulated [kWh]
    comfort_score: float          # 0–100  (100 − PPD)
    pmv: float                    # Fanger PMV [-3, +3]


class BuildingSummaryResponse(BaseModel):
    total_energy_kwh: float
    baseline_energy_kwh: float
    current_power_kw: float
    average_comfort: float
    estimated_cost: float


class SimulationStateResponse(BaseModel):
    simulation_time_minutes: float
    running: bool
    speed: int
    outside_temperature_c: float
    electricity_price_per_kwh: float
    rl_mode: str                          # "manual" | "auto"
    rl_model_path: Optional[str]          # path of loaded policy, or None
    rooms: Dict[str, RoomStateResponse]
    building: BuildingSummaryResponse


class HistoryPointResponse(BaseModel):
    simulation_time_minutes: float
    rooms: Dict[str, Dict[str, float]]   # room_id → {metric: value}
    total_energy_kwh: float
    baseline_energy_kwh: float


class HistoryResponse(BaseModel):
    history: list[HistoryPointResponse]


class MessageResponse(BaseModel):
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    detail: str
    success: bool = False
