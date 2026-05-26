from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class TelegramCourier(Base):
    __tablename__ = "telegram_couriers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    courier_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("couriers.id"), unique=True, nullable=False
    )
    telegram_chat_id: Mapped[int] = mapped_column(
        Integer, unique=True, nullable=False, index=True
    )
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
