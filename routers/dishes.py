from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies.auth import require_role
from models.dish import Dish
from models.dish_ingredient import DishIngredient
from models.ingredient import Ingredient
from models.user import UserRole
from schemas.dish import (
    DishCreate,
    DishIngredientCreate,
    DishIngredientRead,
    DishIngredientUpdate,
    DishRead,
    DishUpdate,
)

router = APIRouter(prefix="/api/dishes", tags=["dishes"])


def _get_dish_or_404(dish_id: int, db: Session) -> Dish:
    dish = db.query(Dish).filter(Dish.id == dish_id).first()
    if not dish:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dish not found",
        )
    return dish


@router.get("", response_model=list[DishRead])
def list_dishes(
    search: Optional[str] = Query(None),
    meal_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(
        require_role(UserRole.admin, UserRole.partner, UserRole.cook)
    ),
):
    query = db.query(Dish)
    if search:
        query = query.filter(Dish.name.ilike(f"%{search}%"))
    if meal_type:
        query = query.filter(Dish.meal_type == meal_type)
    return query.order_by(Dish.name).offset(skip).limit(limit).all()


@router.get("/{dish_id}", response_model=DishRead)
def get_dish(
    dish_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(
        require_role(UserRole.admin, UserRole.partner, UserRole.cook)
    ),
):
    return _get_dish_or_404(dish_id, db)


@router.post("", response_model=DishRead, status_code=status.HTTP_201_CREATED)
def create_dish(
    data: DishCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin)),
):
    existing = db.query(Dish).filter(Dish.name == data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dish with this name already exists",
        )
    dish = Dish(**data.model_dump())
    db.add(dish)
    db.commit()
    db.refresh(dish)
    return dish


@router.put("/{dish_id}", response_model=DishRead)
def update_dish(
    dish_id: int,
    data: DishUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin)),
):
    dish = _get_dish_or_404(dish_id, db)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(dish, key, value)
    db.commit()
    db.refresh(dish)
    return dish


@router.delete("/{dish_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dish(
    dish_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin)),
):
    dish = _get_dish_or_404(dish_id, db)
    db.delete(dish)
    db.commit()


# Dish Ingredients


@router.get(
    "/{dish_id}/ingredients",
    response_model=list[DishIngredientRead],
)
def list_dish_ingredients(
    dish_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(
        require_role(UserRole.admin, UserRole.partner, UserRole.cook)
    ),
):
    _get_dish_or_404(dish_id, db)
    return (
        db.query(DishIngredient)
        .filter(DishIngredient.dish_id == dish_id)
        .all()
    )


@router.post(
    "/{dish_id}/ingredients",
    response_model=DishIngredientRead,
    status_code=status.HTTP_201_CREATED,
)
def add_dish_ingredient(
    dish_id: int,
    data: DishIngredientCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin)),
):
    _get_dish_or_404(dish_id, db)
    ingredient = (
        db.query(Ingredient).filter(Ingredient.id == data.ingredient_id).first()
    )
    if not ingredient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingredient not found",
        )
    existing = (
        db.query(DishIngredient)
        .filter(
            DishIngredient.dish_id == dish_id,
            DishIngredient.ingredient_id == data.ingredient_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ingredient already added to this dish",
        )
    di = DishIngredient(dish_id=dish_id, **data.model_dump())
    db.add(di)
    db.commit()
    db.refresh(di)
    return di


@router.put(
    "/{dish_id}/ingredients/{ingredient_id}",
    response_model=DishIngredientRead,
)
def update_dish_ingredient(
    dish_id: int,
    ingredient_id: int,
    data: DishIngredientUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin)),
):
    di = (
        db.query(DishIngredient)
        .filter(
            DishIngredient.dish_id == dish_id,
            DishIngredient.ingredient_id == ingredient_id,
        )
        .first()
    )
    if not di:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingredient not found in this dish",
        )
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(di, key, value)
    db.commit()
    db.refresh(di)
    return di


@router.delete(
    "/{dish_id}/ingredients/{ingredient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_dish_ingredient(
    dish_id: int,
    ingredient_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin)),
):
    di = (
        db.query(DishIngredient)
        .filter(
            DishIngredient.dish_id == dish_id,
            DishIngredient.ingredient_id == ingredient_id,
        )
        .first()
    )
    if not di:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingredient not found in this dish",
        )
    db.delete(di)
    db.commit()
