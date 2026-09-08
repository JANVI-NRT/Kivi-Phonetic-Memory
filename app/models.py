from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    spoken_form: Mapped[str] = mapped_column(String(255), nullable=False)

    preferred_form: Mapped[str] = mapped_column(String(255), nullable=False)

    context: Mapped[str | None] = mapped_column(Text, nullable=True)

    language: Mapped[str | None] = mapped_column(String(20), nullable=True)

    confidence: Mapped[float] = mapped_column(
        Float,
        default=0.5,
        nullable=False,
    )

    evidence_count: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    memory_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    observed_form: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    evidence_type: Mapped[str] = mapped_column(
        String(20),
        default="positive",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

class MemoryCandidate(Base):
    __tablename__ = "memory_candidates"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    observed_form: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    possible_preferred_form: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    context: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    language: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        server_default="0.0",
        nullable=False,
    )

    importance: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        server_default="0.0",
        nullable=False,
    )

    risk_level: Mapped[str] = mapped_column(
        String(20),
        default="medium",
        server_default="medium",
        nullable=False,
    )

    evidence_count: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    evidence_type: Mapped[str] = mapped_column(
        String(50),
        default="asr_formatted_substitution",
        nullable=False,
    )

    evidence_source: Mapped[str] = mapped_column(
        String(50),
        default="observation",
        server_default="observation",
        nullable=False,
    )

    status: Mapped[str] = mapped_column(String(20), default="candidate", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
