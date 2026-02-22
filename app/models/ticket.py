import datetime
import uuid

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_guid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(50), nullable=True)
    birth_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    segment: Mapped[str] = mapped_column(String(50), nullable=False)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    house: Mapped[str | None] = mapped_column(String(50), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    ai_analysis: Mapped["AIAnalysis | None"] = relationship(
        back_populates="ticket", uselist=False
    )
    assignment: Mapped["Assignment | None"] = relationship(
        back_populates="ticket", uselist=False
    )


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    sentiment: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="RU")
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    ticket: Mapped["Ticket"] = relationship(back_populates="ai_analysis")
    assignment: Mapped["Assignment | None"] = relationship(
        back_populates="ai_analysis", uselist=False
    )


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    ai_analysis_id: Mapped[int] = mapped_column(
        ForeignKey("ai_analyses.id", ondelete="CASCADE"), nullable=False
    )
    manager_id: Mapped[int] = mapped_column(
        ForeignKey("managers.id", ondelete="CASCADE"), nullable=False
    )
    business_unit_id: Mapped[int] = mapped_column(
        ForeignKey("business_units.id", ondelete="CASCADE"), nullable=False
    )
    assigned_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    ticket: Mapped["Ticket"] = relationship(back_populates="assignment")
    ai_analysis: Mapped["AIAnalysis"] = relationship(back_populates="assignment")
    manager: Mapped["Manager"] = relationship(back_populates="assignments")  # noqa: F821
    business_unit: Mapped["BusinessUnit"] = relationship(back_populates="assignments")  # noqa: F821
