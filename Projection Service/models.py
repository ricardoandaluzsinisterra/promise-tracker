import enum
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class PromiseSummaryStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class PromiseSummary(Base):
    __tablename__ = "promise_summaries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    promise_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    politician_id: Mapped[str] = mapped_column(String, nullable=False)
    politician_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[PromiseSummaryStatus] = mapped_column(
        SAEnum(PromiseSummaryStatus),
        nullable=False,
        default=PromiseSummaryStatus.PENDING,
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )