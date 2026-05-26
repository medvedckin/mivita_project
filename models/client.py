import enum
from datetime import datetime

from sqlalchemy import DateTime, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Messenger(str, enum.Enum):
    telegram = "telegram"
    whatsapp = "whatsapp"
    instagram = "instagram"


class PaymentMethod(str, enum.Enum):
    cash = "cash"
    transfer = "transfer"


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str] = mapped_column(String(100), nullable=True)
    messenger: Mapped[Messenger] = mapped_column(
        String(20), default=Messenger.telegram.value, nullable=False
    )
    messenger_handle: Mapped[str] = mapped_column(String(100), nullable=True)
    payment_method: Mapped[PaymentMethod] = mapped_column(
        String(20), default=PaymentMethod.transfer.value, nullable=False
    )
    tariff_code: Mapped[str] = mapped_column(String(10), nullable=True)
    allergens: Mapped[list] = mapped_column(JSON, default=list)
    allergens_text: Mapped[str] = mapped_column(Text, nullable=True)
    excluded_ingredients: Mapped[list] = mapped_column(JSON, default=list)
    schedule: Mapped[list] = mapped_column(JSON, default=list)
    internal_notes: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    subscriptions = relationship("Subscription", back_populates="client")
