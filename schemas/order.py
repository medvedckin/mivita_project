from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from models.order import OrderStatus
from schemas.client import ClientRead, DeliverySlot
from schemas.dish import DishRead


class OrderMeal(BaseModel):
    mealId: str
    slot: str


class OrderDishBase(BaseModel):
    dish_id: int
    servings: int = 1


class OrderDishCreate(OrderDishBase):
    pass


class OrderDishUpdate(BaseModel):
    servings: int


class OrderDishRead(OrderDishBase):
    id: int
    dish: Optional[DishRead] = None

    class Config:
        from_attributes = True


class OrderBase(BaseModel):
    client_id: int
    subscription_id: Optional[int] = None
    order_date: date
    tariff_code: str
    meals: list[OrderMeal] = []
    delivery_slot: Optional[DeliverySlot] = None
    allergens: list[str] = []
    excluded_ingredients: list[str] = []
    payment_method: str = "transfer"
    price_total: float = 0
    is_priority: bool = False
    comment: Optional[str] = None
    notes: Optional[str] = None


class OrderCreate(OrderBase):
    pass


class OrderUpdate(BaseModel):
    subscription_id: Optional[int] = None
    order_date: Optional[date] = None
    tariff_code: Optional[str] = None
    meals: Optional[list[OrderMeal]] = None
    delivery_slot: Optional[DeliverySlot] = None
    allergens: Optional[list[str]] = None
    excluded_ingredients: Optional[list[str]] = None
    payment_method: Optional[str] = None
    price_total: Optional[float] = None
    is_priority: Optional[bool] = None
    comment: Optional[str] = None
    notes: Optional[str] = None


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class OrderRead(OrderBase):
    id: int
    status: OrderStatus
    locked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    dishes: list[OrderDishRead] = []
    client: Optional[ClientRead] = None

    class Config:
        from_attributes = True
