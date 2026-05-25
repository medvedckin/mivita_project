from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from models.order import MealType, OrderStatus
from schemas.client import ClientRead
from schemas.dish import DishRead


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
    allergen_ingredients: list[int] = []

    class Config:
        from_attributes = True


class OrderBase(BaseModel):
    client_id: int
    subscription_id: Optional[int] = None
    order_date: date
    meal_type: Optional[MealType] = None
    notes: Optional[str] = None


class OrderCreate(OrderBase):
    pass


class OrderUpdate(BaseModel):
    client_id: Optional[int] = None
    subscription_id: Optional[int] = None
    order_date: Optional[date] = None
    meal_type: Optional[MealType] = None
    notes: Optional[str] = None


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class OrderRead(OrderBase):
    id: int
    status: OrderStatus
    created_at: datetime
    updated_at: datetime
    dishes: list[OrderDishRead] = []
    client: Optional[ClientRead] = None

    class Config:
        from_attributes = True
