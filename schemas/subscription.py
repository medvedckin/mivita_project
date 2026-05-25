from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from models.subscription import SubscriptionPlan, SubscriptionStatus
from schemas.tariff import TariffRead


class SubscriptionBase(BaseModel):
    plan: SubscriptionPlan
    start_date: date
    end_date: Optional[date] = None
    price: float
    meals_per_day: int = 1
    days_of_week: str = "1,2,3,4,5"
    notes: Optional[str] = None


class SubscriptionCreate(SubscriptionBase):
    tariff_code: Optional[str] = None


class SubscriptionUpdate(BaseModel):
    tariff_code: Optional[str] = None
    plan: Optional[SubscriptionPlan] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    price: Optional[float] = None
    meals_per_day: Optional[int] = None
    days_of_week: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[SubscriptionStatus] = None


class SubscriptionRead(SubscriptionBase):
    id: int
    client_id: int
    tariff_code: Optional[str] = None
    status: SubscriptionStatus
    tariff: Optional[TariffRead] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubscriptionStatusUpdate(BaseModel):
    status: SubscriptionStatus
