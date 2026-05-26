import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class OrderStatus(str, enum.Enum):
    draft = "draft"
    confirmed = "confirmed"
    in_kitchen = "in_kitchen"
    delivered = "delivered"
    cancelled = "cancelled"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False
    )
    subscription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscriptions.id"), nullable=True
    )
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    tariff_code: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), default=OrderStatus.draft, nullable=False
    )
    meals: Mapped[list] = mapped_column(JSON, default=list)
    delivery_slot: Mapped[dict] = mapped_column(JSON, default=dict)
    allergens: Mapped[list] = mapped_column(JSON, default=list)
    excluded_ingredients: Mapped[list] = mapped_column(JSON, default=list)
    payment_method: Mapped[str] = mapped_column(String(20), default="transfer")
    price_total: Mapped[float] = mapped_column(Float, default=0)
    is_priority: Mapped[bool] = mapped_column(Boolean, default=False)
    comment: Mapped[str] = mapped_column(Text, nullable=True)
    locked_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    client = relationship("Client")
    dishes = relationship("OrderDish", back_populates="order", cascade="all, delete-orphan")
