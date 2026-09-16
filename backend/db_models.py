from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone
from .database import Base

class RoomStateHistory(Base):
    __tablename__ = "room_state_history"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    room_id = Column(String, index=True)
    temperature = Column(Float)
    humidity = Column(Float)
    occupants = Column(Integer)
    cooling_power = Column(Float)
    heating_power = Column(Float)
    thermal_comfort_pmv = Column(Float)

class SystemStateHistory(Base):
    __tablename__ = "system_state_history"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    outdoor_temperature = Column(Float)
    energy_price = Column(Float)
    total_building_power = Column(Float)

class NLPFeedbackEvent(Base):
    __tablename__ = "nlp_feedback_events"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    room_id = Column(String, index=True)
    raw_text = Column(String)
    parsed_intent = Column(String)
    applied_constraint = Column(Float)

class RLActionLog(Base):
    __tablename__ = "rl_action_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    room_id = Column(String, index=True)
    action_command = Column(String)
    reward_received = Column(Float)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String)
    assigned_room = Column(String, nullable=True)

class OccupantFeedback(Base):
    __tablename__ = "occupant_feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    room_id = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    requested_temp = Column(Float)
    actual_temp = Column(Float)
    humidity = Column(Float)
    hvac_power = Column(Float)
    is_comfortable = Column(Boolean)
    comfort_rating = Column(Integer)
    reuse_preference = Column(Boolean)
