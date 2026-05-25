from typing import Optional

from pydantic import BaseModel


class TariffRead(BaseModel):
    id: int
    code: str
    title: str
    kcal: int
    meals_per_day: int
    price_per_day: int
    portion_size: str
    is_active: bool

    class Config:
        from_attributes = True


class TariffCreate(BaseModel):
    code: str
    title: str
    kcal: int
    meals_per_day: int
    price_per_day: int
    portion_size: str
    is_active: bool = True


class TariffUpdate(BaseModel):
    title: Optional[str] = None
    kcal: Optional[int] = None
    meals_per_day: Optional[int] = None
    price_per_day: Optional[int] = None
    portion_size: Optional[str] = None
    is_active: Optional[bool] = None
