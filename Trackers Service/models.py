import enum
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Text, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class TrackingStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class OutboxStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"


class TrackingRecord(Base):
    __tablename__ = "tracking_records"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    promise_id: Mapped[str] = mapped_column(String, nullable=False)
    politician_id: Mapped[str] = mapped_column(String, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[TrackingStatus] = mapped_column(
        SAEnum(TrackingStatus),
        nullable=False,
        default=TrackingStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(
        SAEnum(OutboxStatus),
        default=OutboxStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )