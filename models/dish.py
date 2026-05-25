import enum

from sqlalchemy import Boolean, Enum, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class MealType(str, enum.Enum):
    breakfast = "breakfast"
    snack = "snack"
    lunch = "lunch"
    salad = "salad"
    dinner = "dinner"


class Dish(Base):
    __tablename__ = "dishes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    meal_type: Mapped[MealType] = mapped_column(
        Enum(MealType), nullable=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=True)
    calories: Mapped[float] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    ingredients = relationship("DishIngredient", back_populates="dish")
