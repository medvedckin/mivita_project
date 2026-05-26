from sqlalchemy import Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class DishIngredient(Base):
    __tablename__ = "dish_ingredients"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    dish_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dishes.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    unit: Mapped[str] = mapped_column(String(20), nullable=True)
    # Per-tariff grams: {"1500": 100, "1800": 120, "2000": 140, "2500": 160}.
    amounts: Mapped[dict] = mapped_column(JSON, default=dict)

    dish = relationship("Dish", back_populates="ingredients")
    ingredient = relationship("Ingredient")
