from typing import Optional

from pydantic import BaseModel

from models.dish import MealType
from schemas.ingredient import IngredientRead


class DishIngredientBase(BaseModel):
    ingredient_id: int
    quantity: float
    unit: Optional[str] = None


class DishIngredientCreate(DishIngredientBase):
    pass


class DishIngredientUpdate(BaseModel):
    quantity: Optional[float] = None
    unit: Optional[str] = None


class DishIngredientRead(DishIngredientBase):
    id: int
    ingredient: Optional[IngredientRead] = None

    class Config:
        from_attributes = True


class DishBase(BaseModel):
    name: str
    meal_type: Optional[MealType] = None
    description: Optional[str] = None
    calories: Optional[float] = None


class DishCreate(DishBase):
    pass


class DishUpdate(BaseModel):
    name: Optional[str] = None
    meal_type: Optional[MealType] = None
    description: Optional[str] = None
    calories: Optional[float] = None
    is_active: Optional[bool] = None


class DishRead(DishBase):
    id: int
    is_active: bool
    ingredients: list[DishIngredientRead] = []

    class Config:
        from_attributes = True
