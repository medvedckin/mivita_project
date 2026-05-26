from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from database import get_db
from dependencies.auth import require_role
from models.menu_cycle import MenuCycle, MenuCycleDay
from models.user import UserRole

router = APIRouter(prefix="/api/menu", tags=["menu"])


class MenuCycleDayRead(BaseModel):
    dayIndex: int
    meals: dict[str, int]

    class Config:
        from_attributes = True


class MenuCycleRead(BaseModel):
    id: int
    startDate: str
    days: list[MenuCycleDayRead]


class MenuCycleDayPatch(BaseModel):
    slot: str
    dishId: int | None = None


def _get_or_seed_cycle(db: Session) -> MenuCycle:
    cycle = db.query(MenuCycle).first()
    if cycle is None:
        cycle = MenuCycle(start_date=date.today())
        db.add(cycle)
        db.flush()
        for i in range(1, 22):
            db.add(MenuCycleDay(cycle_id=cycle.id, day_index=i, meals={}))
        db.commit()
        db.refresh(cycle)
    return cycle


def seed_menu_cycle(db: Session) -> None:
    _get_or_seed_cycle(db)


@router.get("/cycle", response_model=MenuCycleRead)
def get_cycle(db: Session = Depends(get_db), _=Depends(require_role(UserRole.admin, UserRole.partner, UserRole.kitchen))):
    cycle = _get_or_seed_cycle(db)
    return MenuCycleRead(
        id=cycle.id,
        startDate=cycle.start_date.isoformat(),
        days=[MenuCycleDayRead(dayIndex=d.day_index, meals=d.meals or {}) for d in cycle.days],
    )


@router.patch("/cycle/{day_index}", response_model=MenuCycleDayRead)
def update_cycle_day(
    day_index: int,
    data: MenuCycleDayPatch,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    if not (1 <= day_index <= 21):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="dayIndex must be 1..21")
    cycle = _get_or_seed_cycle(db)
    day = (
        db.query(MenuCycleDay)
        .filter(MenuCycleDay.cycle_id == cycle.id, MenuCycleDay.day_index == day_index)
        .first()
    )
    if day is None:
        day = MenuCycleDay(cycle_id=cycle.id, day_index=day_index, meals={})
        db.add(day)
    meals = dict(day.meals or {})
    if data.dishId is None:
        meals.pop(data.slot, None)
    else:
        meals[data.slot] = int(data.dishId)
    day.meals = meals
    flag_modified(day, "meals")
    db.commit()
    db.refresh(day)
    return MenuCycleDayRead(dayIndex=day.day_index, meals=day.meals or {})
