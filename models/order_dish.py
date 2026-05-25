from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class OrderDish(Base):
    __tablename__ = "order_dishes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    dish_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dishes.id", ondelete="CASCADE"), nullable=False
    )
    servings: Mapped[int] = mapped_column(Integer, default=1)

    order = relationship("Order", back_populates="dishes")
    dish = relationship("Dish")
