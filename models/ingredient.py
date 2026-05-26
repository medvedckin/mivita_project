from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=True)
    supplier: Mapped[str] = mapped_column(String(150), nullable=True)
    price_per_unit: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
