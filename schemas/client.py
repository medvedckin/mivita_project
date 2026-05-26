from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from models.client import Messenger, PaymentMethod


class DeliverySlot(BaseModel):
    weekday: str
    address: str
    timeSlot: str
    comment: Optional[str] = None


class ClientBase(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    messenger: Messenger = Messenger.telegram
    messenger_handle: Optional[str] = None
    payment_method: PaymentMethod = PaymentMethod.transfer
    tariff_code: Optional[str] = None
    allergens: list[str] = []
    allergens_text: Optional[str] = None
    excluded_ingredients: list[str] = []
    schedule: list[DeliverySlot] = []
    internal_notes: Optional[str] = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    messenger: Optional[Messenger] = None
    messenger_handle: Optional[str] = None
    payment_method: Optional[PaymentMethod] = None
    tariff_code: Optional[str] = None
    allergens: Optional[list[str]] = None
    allergens_text: Optional[str] = None
    excluded_ingredients: Optional[list[str]] = None
    schedule: Optional[list[DeliverySlot]] = None
    internal_notes: Optional[str] = None


class ClientRead(ClientBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
