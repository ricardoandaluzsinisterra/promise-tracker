from datetime import datetime, timezone
import enum
from sqlalchemy import String, Text, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class OutboxStatus(str, enum.Enum):
	PENDING = "PENDING"
	SENT = "SENT"


class Politician(Base):
	__tablename__ = "politicians"

	id: Mapped[str] = mapped_column(String, primary_key=True)
	name: Mapped[str] = mapped_column(String(255), nullable=False)
	role: Mapped[str] = mapped_column(String(255), nullable=False)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PoliticianPromise(Base):
	__tablename__ = "politician_promises"

	id: Mapped[str] = mapped_column(String, primary_key=True)
	politician_id: Mapped[str] = mapped_column(String, nullable=False)
	promise_id: Mapped[str] = mapped_column(String, nullable=False)
	tagged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class OutboxEvent(Base):
	__tablename__ = "outbox_events"

	id: Mapped[str] = mapped_column(String, primary_key=True)
	event_type: Mapped[str] = mapped_column(String(100), nullable=False)
	aggregate_id: Mapped[str] = mapped_column(String, nullable=False)
	payload: Mapped[str] = mapped_column(Text, nullable=False)
	status: Mapped[OutboxStatus] = mapped_column(SAEnum(OutboxStatus), default=OutboxStatus.PENDING)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
