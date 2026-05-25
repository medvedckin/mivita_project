from typing import Optional

from pydantic import BaseModel


class IngredientBase(BaseModel):
    name: str
    unit: str
    category: Optional[str] = None


class IngredientCreate(IngredientBase):
    pass


class IngredientUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    category: Optional[str] = None


class IngredientRead(IngredientBase):
    id: int

    class Config:
        from_attributes = True
