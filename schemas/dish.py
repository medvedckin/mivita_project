from typing import Optional

from pydantic import BaseModel

from models.dish import MealSlot
from schemas.ingredient import IngredientRead


class RecipeStep(BaseModel):
    order: int
    description: str
    durationMin: Optional[int] = None


class DishIngredientBase(BaseModel):
    ingredient_id: int
    quantity: float = 0
    unit: Optional[str] = None
    amounts: dict[str, float] = {}


class DishIngredientCreate(DishIngredientBase):
    pass


class DishIngredientUpdate(BaseModel):
    quantity: Optional[float] = None
    unit: Optional[str] = None
    amounts: Optional[dict[str, float]] = None


class DishIngredientRead(DishIngredientBase):
    id: int
    ingredient: Optional[IngredientRead] = None

    class Config:
        from_attributes = True


class DishBase(BaseModel):
    name: str
    slot: MealSlot = MealSlot.lunch
    description: Optional[str] = None
    kcal_by_tariff: dict[str, int] = {}
    allergens: list[str] = []
    steps: list[RecipeStep] = []
    cook_time_min: int = 0


class DishCreate(DishBase):
    pass


class DishUpdate(BaseModel):
    name: Optional[str] = None
    slot: Optional[MealSlot] = None
    description: Optional[str] = None
    kcal_by_tariff: Optional[dict[str, int]] = None
    allergens: Optional[list[str]] = None
    steps: Optional[list[RecipeStep]] = None
    cook_time_min: Optional[int] = None
    is_active: Optional[bool] = None


class DishRead(DishBase):
    id: int
    is_active: bool
    ingredients: list[DishIngredientRead] = []

    class Config:
        from_attributes = True
