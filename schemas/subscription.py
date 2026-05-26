from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from models.subscription import SubscriptionStatus
from schemas.tariff import TariffRead


class DayOverride(BaseModel):
    date: str
    address: Optional[str] = None
    timeSlot: Optional[str] = None
    tariff: Optional[str] = None
    skipped: Optional[bool] = None
    comment: Optional[str] = None


class SubscriptionChange(BaseModel):
    id: str
    at: str
    field: str
    description: str


class SubscriptionBase(BaseModel):
    tariff_code: str
    start_date: date
    end_date: date
    total_price: float = 0
    notes: Optional[str] = None


class SubscriptionCreate(SubscriptionBase):
    pass


class SubscriptionUpdate(BaseModel):
    tariff_code: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    total_price: Optional[float] = None
    notes: Optional[str] = None
    status: Optional[SubscriptionStatus] = None


class SubscriptionRead(SubscriptionBase):
    id: int
    client_id: int
    status: SubscriptionStatus
    day_overrides: list[DayOverride] = []
    change_log: list[SubscriptionChange] = []
    tariff: Optional[TariffRead] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubscriptionStatusUpdate(BaseModel):
    status: SubscriptionStatus
