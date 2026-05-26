from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from models.route import RouteStatus
from schemas.client import ClientRead
from schemas.courier import CourierRead
from schemas.order import OrderRead


class RoutePointBase(BaseModel):
    order_id: int
    client_id: int
    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    sort_order: int = 0
    estimated_arrival: Optional[str] = None


class RoutePointRead(RoutePointBase):
    id: int
    route_id: int
    created_at: datetime
    order: Optional[OrderRead] = None
    client: Optional[ClientRead] = None

    class Config:
        from_attributes = True


class RouteBase(BaseModel):
    date: date
    courier_id: Optional[int] = None
    status: RouteStatus = RouteStatus.pending


class RouteCreate(BaseModel):
    date: date
    courier_id: Optional[int] = None


class RouteRead(BaseModel):
    id: int
    date: date
    courier_id: Optional[int] = None
    status: RouteStatus
    total_distance: Optional[float] = None
    total_duration: Optional[float] = None
    optimized_polyline: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    courier: Optional[CourierRead] = None
    points: list[RoutePointRead] = []

    class Config:
        from_attributes = True


class RouteStatusUpdate(BaseModel):
    status: RouteStatus


class RouteAssignCourier(BaseModel):
    courier_id: Optional[int] = None
