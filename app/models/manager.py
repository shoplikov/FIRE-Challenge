from sqlalchemy import ARRAY, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Manager(Base):
    __tablename__ = "managers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[str] = mapped_column(String(100), nullable=False)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    business_unit_id: Mapped[int] = mapped_column(ForeignKey("business_units.id"), nullable=False)
    current_load: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    business_unit: Mapped["BusinessUnit"] = relationship(back_populates="managers")  # noqa: F821
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="manager")  # noqa: F821
