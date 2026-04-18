from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String
from db.database import Base


class Provider(Base):
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True)
    phone_number = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    business_type = Column(String, nullable=False)
    location_type = Column(String, nullable=False)
    auto_book = Column(Boolean, default=False)
    buffer_mins = Column(Integer, default=15)
    working_hours = Column(JSON, nullable=False)
    business_config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False)
    name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, nullable=False)
    address = Column(String, nullable=True)
    status = Column(String, nullable=False)
    membership_type = Column(String, nullable=True)
    sessions_per_week = Column(Integer, nullable=True)
    preferred_days = Column(JSON, nullable=True)
    preferred_time = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    scheduled_at = Column(DateTime, nullable=False)
    duration_mins = Column(Integer, default=60)
    location = Column(String, nullable=True)
    status = Column(String, nullable=False)
    is_recurring = Column(Boolean, default=False)
    recurrence_type = Column(String, nullable=True)
    travel_time_before_mins = Column(Integer, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SessionArchive(Base):
    __tablename__ = "sessions_archive"

    id = Column(Integer, primary_key=True)
    original_session_id = Column(Integer, nullable=False)
    provider_id = Column(Integer, nullable=False)
    client_id = Column(Integer, nullable=False)
    scheduled_at = Column(DateTime, nullable=False)
    duration_mins = Column(Integer)
    location = Column(String, nullable=True)
    status = Column(String, nullable=False)
    is_recurring = Column(Boolean)
    recurrence_type = Column(String, nullable=True)
    archived_at = Column(DateTime, default=datetime.utcnow)
    archive_reason = Column(String, nullable=False)


class ConversationState(Base):
    __tablename__ = "conversation_state"

    id = Column(Integer, primary_key=True)
    phone_number = Column(String, unique=True, nullable=False)
    role = Column(String, nullable=False)
    context = Column(JSON, default=dict)
    last_donna_message = Column(String, nullable=True)
    client_id = Column(Integer, nullable=True)
    session_id = Column(Integer, nullable=True)
    turn_count = Column(Integer, default=0)
    handoff_active = Column(Boolean, default=False)
    handoff_target_phone = Column(String, nullable=True)
    last_message_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
