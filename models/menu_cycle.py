from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class MenuCycle(Base):
    """Single-row table that anchors the 21-day cycle to a calendar date."""

    __tablename__ = "menu_cycles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)

    days = relationship(
        "MenuCycleDay",
        back_populates="cycle",
        cascade="all, delete-orphan",
        order_by="MenuCycleDay.day_index",
    )


class MenuCycleDay(Base):
    __tablename__ = "menu_cycle_days"
    __table_args__ = (UniqueConstraint("cycle_id", "day_index", name="uq_cycle_day_index"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    cycle_id: Mapped[int] = mapped_column(Integer, ForeignKey("menu_cycles.id", ondelete="CASCADE"), nullable=False)
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..21
    # {"breakfast": dish_id, "snack1": dish_id, "lunch": ...}
    meals: Mapped[dict] = mapped_column(JSON, default=dict)

    cycle = relationship("MenuCycle", back_populates="days")
