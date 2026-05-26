from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from models.courier import CourierVehicle


class CourierBase(BaseModel):
    name: str
    phone: str
    vehicle: CourierVehicle = CourierVehicle.car
    is_active: bool = True
    notes: Optional[str] = None


class CourierCreate(CourierBase):
    pass


class CourierUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    vehicle: Optional[CourierVehicle] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class CourierRead(CourierBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
