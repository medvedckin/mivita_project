import enum

from sqlalchemy import Boolean, Enum, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class MealSlot(str, enum.Enum):
    breakfast = "breakfast"
    snack1 = "snack1"
    lunch = "lunch"
    snack2 = "snack2"
    dinner = "dinner"


class Dish(Base):
    __tablename__ = "dishes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    slot: Mapped[MealSlot] = mapped_column(
        Enum(MealSlot), default=MealSlot.lunch, nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=True)
    kcal_by_tariff: Mapped[dict] = mapped_column(JSON, default=dict)
    allergens: Mapped[list] = mapped_column(JSON, default=list)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    cook_time_min: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    ingredients = relationship("DishIngredient", back_populates="dish", cascade="all, delete-orphan")
