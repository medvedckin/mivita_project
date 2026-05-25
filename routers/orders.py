from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies.auth import require_role
from models.client import Client
from models.dish import Dish
from models.dish_ingredient import DishIngredient
from models.order import Order, OrderStatus
from models.order_dish import OrderDish
from models.user import UserRole
from schemas.order import (
    OrderCreate,
    OrderDishCreate,
    OrderDishRead,
    OrderDishUpdate,
    OrderRead,
    OrderStatusUpdate,
    OrderUpdate,
)

router = APIRouter(prefix="/api/orders", tags=["orders"])


def _get_order_or_404(order_id: int, db: Session) -> Order:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    return order


def _enrich_order_dishes(order: Order, db: Session):
    """Attach allergen_ingredients to each dish in the order."""
    client = db.query(Client).filter(Client.id == order.client_id).first()
    client_allergens = set(client.allergens or [])
    for od in order.dishes:
        dish_ings = (
            db.query(DishIngredient)
            .filter(DishIngredient.dish_id == od.dish_id)
            .all()
        )
        od.allergen_ingredients = [
            di.ingredient_id for di in dish_ings
            if di.ingredient_id in client_allergens
        ]


@router.get("", response_model=list[OrderRead])
def list_orders(
    client_id: Optional[int] = Query(None),
    order_date: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin, UserRole.partner)),
):
    query = db.query(Order)
    if client_id:
        query = query.filter(Order.client_id == client_id)
    if order_date:
        query = query.filter(Order.order_date == order_date)
    if status_filter:
        query = query.filter(Order.status == status_filter)
    orders = query.order_by(Order.order_date.desc()).offset(skip).limit(limit).all()
    for o in orders:
        _enrich_order_dishes(o, db)
    return orders


@router.get("/{order_id}", response_model=OrderRead)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(
        require_role(UserRole.admin, UserRole.partner, UserRole.cook)
    ),
):
    order = _get_order_or_404(order_id, db)
    _enrich_order_dishes(order, db)
    return order


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(
    data: OrderCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin)),
):
    client = db.query(Client).filter(Client.id == data.client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    order = Order(**data.model_dump())
    db.add(order)
    db.commit()
    db.refresh(order)
    _enrich_order_dishes(order, db)
    return order


@router.put("/{order_id}", response_model=OrderRead)
def update_order(
    order_id: int,
    data: OrderUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin)),
):
    order = _get_order_or_404(order_id, db)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(order, key, value)
    db.commit()
    db.refresh(order)
    _enrich_order_dishes(order, db)
    return order


@router.patch("/{order_id}/status", response_model=OrderRead)
def update_order_status(
    order_id: int,
    data: OrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin, UserRole.cook)),
):
    order = _get_order_or_404(order_id, db)
    cook = current_user.role == UserRole.cook
    if cook:
        allowed = {OrderStatus.planned, OrderStatus.in_progress, OrderStatus.completed}
        if data.status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cook can only set status to in_progress or completed",
            )
    order.status = data.status
    db.commit()
    db.refresh(order)
    _enrich_order_dishes(order, db)
    return order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin)),
):
    order = _get_order_or_404(order_id, db)
    db.delete(order)
    db.commit()


@router.get(
    "/{order_id}/dishes",
    response_model=list[OrderDishRead],
)
def list_order_dishes(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(
        require_role(UserRole.admin, UserRole.partner, UserRole.cook)
    ),
):
    order = _get_order_or_404(order_id, db)
    dishes = db.query(OrderDish).filter(OrderDish.order_id == order_id).all()
    client = db.query(Client).filter(Client.id == order.client_id).first()
    client_allergens = set(client.allergens or [])
    for od in dishes:
        dish_ings = (
            db.query(DishIngredient)
            .filter(DishIngredient.dish_id == od.dish_id)
            .all()
        )
        od.allergen_ingredients = [
            di.ingredient_id for di in dish_ings
            if di.ingredient_id in client_allergens
        ]
    return dishes


@router.post(
    "/{order_id}/dishes",
    response_model=OrderDishRead,
    status_code=status.HTTP_201_CREATED,
)
def add_order_dish(
    order_id: int,
    data: OrderDishCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin)),
):
    _get_order_or_404(order_id, db)
    dish = db.query(Dish).filter(Dish.id == data.dish_id).first()
    if not dish:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dish not found",
        )
    od = OrderDish(order_id=order_id, **data.model_dump())
    db.add(od)
    db.commit()
    db.refresh(od)
    return od


@router.put(
    "/{order_id}/dishes/{dish_id}",
    response_model=OrderDishRead,
)
def update_order_dish(
    order_id: int,
    dish_id: int,
    data: OrderDishUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin)),
):
    od = (
        db.query(OrderDish)
        .filter(
            OrderDish.order_id == order_id,
            OrderDish.dish_id == dish_id,
        )
        .first()
    )
    if not od:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dish not found in this order",
        )
    od.servings = data.servings
    db.commit()
    db.refresh(od)
    return od


@router.delete(
    "/{order_id}/dishes/{dish_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_order_dish(
    order_id: int,
    dish_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin)),
):
    od = (
        db.query(OrderDish)
        .filter(
            OrderDish.order_id == order_id,
            OrderDish.dish_id == dish_id,
        )
        .first()
    )
    if not od:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dish not found in this order",
        )
    db.delete(od)
    db.commit()
