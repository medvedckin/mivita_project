from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from dependencies.auth import require_role
from models.client import Client
from models.dish_ingredient import DishIngredient
from models.order import Order, OrderStatus
from models.user import UserRole
from schemas.order import OrderRead

router = APIRouter(prefix="/api/kitchen", tags=["kitchen"])


class KanbanBoard(BaseModel):
    planned: list[OrderRead] = []
    in_progress: list[OrderRead] = []
    completed: list[OrderRead] = []


@router.get("/board", response_model=KanbanBoard)
def get_kanban_board(
    db: Session = Depends(get_db),
    current_user=Depends(
        require_role(UserRole.admin, UserRole.partner, UserRole.cook)
    ),
):
    orders = (
        db.query(Order)
        .filter(
            Order.status.in_([
                OrderStatus.planned,
                OrderStatus.in_progress,
                OrderStatus.completed,
            ])
        )
        .order_by(Order.order_date.asc())
        .all()
    )
    for order in orders:
        client = db.query(Client).filter(Client.id == order.client_id).first()
        client_allergens = set(client.allergens or []) if client else set()
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

    board = KanbanBoard()
    for order in orders:
        if order.status == OrderStatus.planned:
            board.planned.append(order)
        elif order.status == OrderStatus.in_progress:
            board.in_progress.append(order)
        elif order.status == OrderStatus.completed:
            board.completed.append(order)
    return board
