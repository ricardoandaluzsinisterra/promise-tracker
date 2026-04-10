import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from database import Base
import enum

class PromiseStatus(str, enum.Enum):
    PENDING    = "pending"     # saga in progress, not yet confirmed
    ACTIVE     = "active"      # saga completed successfully
    RETRACTING = "retracting"  # retraction saga in progress
    RETRACTED  = "retracted"   # retraction saga completed
    FAILED     = "failed"      # saga failed, compensation fired

class OutboxStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT    = "SENT"

class Promise(Base):
    __tablename__ = "promises"

    id:          Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title:       Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    politician_id: Mapped[str] = mapped_column(String, nullable=False)
    status:      Mapped[PromiseStatus] = mapped_column(SAEnum(PromiseStatus), default=PromiseStatus.PENDING) #Pending will always be the initial state
    created_at:  Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at:  Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id:           Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type:   Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String, nullable=False)  # the promise_id
    payload:      Mapped[str] = mapped_column(Text, nullable=False)     # JSON string
    status:       Mapped[OutboxStatus] = mapped_column(SAEnum(OutboxStatus), default=OutboxStatus.PENDING)
    created_at:   Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))