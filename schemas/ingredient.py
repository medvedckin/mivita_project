from typing import Optional

from pydantic import BaseModel


class IngredientBase(BaseModel):
    name: str
    unit: str
    category: Optional[str] = None
    supplier: Optional[str] = None
    price_per_unit: float = 0.0


class IngredientCreate(IngredientBase):
    pass


class IngredientUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    category: Optional[str] = None
    supplier: Optional[str] = None
    price_per_unit: Optional[float] = None


class IngredientRead(IngredientBase):
    id: int

    class Config:
        from_attributes = True
