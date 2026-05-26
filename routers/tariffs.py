from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies.auth import require_role
from models.tariff import Tariff
from models.user import UserRole
from schemas.tariff import TariffCreate, TariffRead, TariffUpdate

router = APIRouter(prefix="/api/tariffs", tags=["tariffs"])

SEED_TARIFFS = [
    {"code": "1500", "title": "1500 ккал", "kcal": 1500, "meals_per_day": 3, "price_per_day": 35, "portion_size": "standard"},
    {"code": "1800", "title": "1800 ккал", "kcal": 1800, "meals_per_day": 4, "price_per_day": 40, "portion_size": "standard"},
    {"code": "2000", "title": "2000 ккал", "kcal": 2000, "meals_per_day": 5, "price_per_day": 45, "portion_size": "large"},
    {"code": "2500", "title": "2500 ккал", "kcal": 2500, "meals_per_day": 5, "price_per_day": 50, "portion_size": "large"},
]


def seed_tariffs(db: Session):
    if db.query(Tariff).count() > 0:
        return
    for data in SEED_TARIFFS:
        db.add(Tariff(**data))
    db.commit()


@router.get("", response_model=list[TariffRead])
def list_tariffs(
    db: Session = Depends(get_db),
    current_user=Depends(
        require_role(UserRole.admin, UserRole.partner, UserRole.kitchen)
    ),
):
    return db.query(Tariff).order_by(Tariff.kcal).all()


@router.get("/{tariff_id}", response_model=TariffRead)
def get_tariff(
    tariff_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(
        require_role(UserRole.admin, UserRole.partner, UserRole.kitchen)
    ),
):
    tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
    if not tariff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tariff not found",
        )
    return tariff


@router.post("", response_model=TariffRead, status_code=status.HTTP_201_CREATED)
def create_tariff(
    data: TariffCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin)),
):
    existing = db.query(Tariff).filter(Tariff.code == data.code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tariff with this code already exists",
        )
    tariff = Tariff(**data.model_dump())
    db.add(tariff)
    db.commit()
    db.refresh(tariff)
    return tariff


@router.put("/{tariff_id}", response_model=TariffRead)
def update_tariff(
    tariff_id: int,
    data: TariffUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin)),
):
    tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
    if not tariff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tariff not found",
        )
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(tariff, key, value)
    db.commit()
    db.refresh(tariff)
    return tariff


@router.delete("/{tariff_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tariff(
    tariff_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin)),
):
    tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
    if not tariff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tariff not found",
        )
    db.delete(tariff)
    db.commit()
