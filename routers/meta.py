from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from dependencies.auth import get_current_user
from models.tariff import Tariff
from schemas.tariff import TariffRead

router = APIRouter(prefix="/api/meta", tags=["meta"])


class Allergen(BaseModel):
    code: str
    label: str


ALLERGEN_CATALOG: list[Allergen] = [
    Allergen(code="fish", label="Рыба"),
    Allergen(code="mushroom", label="Грибы"),
    Allergen(code="lactose", label="Лактоза"),
    Allergen(code="pork", label="Свинина"),
    Allergen(code="nuts", label="Орехи"),
    Allergen(code="gluten", label="Глютен"),
    Allergen(code="eggs", label="Яйца"),
    Allergen(code="seafood", label="Морепродукты"),
    Allergen(code="soy", label="Соя"),
    Allergen(code="honey", label="Мёд"),
]


class TodayResponse(BaseModel):
    today: str
    tomorrow: str


@router.get("/today", response_model=TodayResponse)
def get_today(_=Depends(get_current_user)):
    today = date.today()
    return TodayResponse(
        today=today.isoformat(),
        tomorrow=(today + timedelta(days=1)).isoformat(),
    )


@router.get("/allergens", response_model=list[Allergen])
def get_allergens(_=Depends(get_current_user)):
    return ALLERGEN_CATALOG


@router.get("/tariffs", response_model=list[TariffRead])
def get_tariffs(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(Tariff).order_by(Tariff.kcal).all()
