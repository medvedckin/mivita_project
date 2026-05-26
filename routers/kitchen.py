from collections import defaultdict
from datetime import date as _date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from dependencies.auth import require_role
from models.client import Client
from models.dish import Dish
from models.dish_ingredient import DishIngredient
from models.ingredient import Ingredient
from models.menu_cycle import MenuCycle, MenuCycleDay
from models.order import Order, OrderStatus
from models.user import UserRole
from schemas.order import OrderRead

router = APIRouter(prefix="/api/kitchen", tags=["kitchen"])


TARIFFS = ["1500", "1800", "2000", "2500"]
SLOTS = ["breakfast", "snack1", "lunch", "snack2", "dinner"]
TARIFF_SLOT_MAP = {
    "1500": ["breakfast", "lunch", "dinner"],
    "1800": ["breakfast", "lunch", "snack2", "dinner"],
    "2000": SLOTS,
    "2500": SLOTS,
}


class KanbanBoard(BaseModel):
    confirmed: list[OrderRead] = []
    in_kitchen: list[OrderRead] = []
    delivered: list[OrderRead] = []


@router.get("/board", response_model=KanbanBoard)
def get_kanban_board(
    order_date: Optional[str] = Query(None, alias="date"),
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin, UserRole.partner, UserRole.kitchen)),
):
    query = db.query(Order).filter(
        Order.status.in_(
            [OrderStatus.confirmed, OrderStatus.in_kitchen, OrderStatus.delivered]
        )
    )
    if order_date:
        query = query.filter(Order.order_date == order_date)
    orders = query.order_by(Order.order_date.asc()).all()

    board = KanbanBoard()
    for order in orders:
        if order.status == OrderStatus.confirmed:
            board.confirmed.append(order)
        elif order.status == OrderStatus.in_kitchen:
            board.in_kitchen.append(order)
        elif order.status == OrderStatus.delivered:
            board.delivered.append(order)
    return board


# ---------- task aggregation ----------


class KitchenIngredientLine(BaseModel):
    ingredientId: str
    name: str
    unit: str
    total: float
    byTariff: dict[str, float]


class KitchenMealBlock(BaseModel):
    mealId: str
    slot: str
    name: str
    portionsStandard: int
    portionsLarge: int
    portionsTotal: int
    byTariff: dict[str, int]
    ingredients: list[KitchenIngredientLine]


class KitchenSpecialNote(BaseModel):
    clientId: str
    clientName: str
    mealId: Optional[str] = None
    description: str


class KitchenTask(BaseModel):
    date: str
    totalOrders: int
    ordersByTariff: dict[str, int]
    bySlot: dict[str, list[KitchenMealBlock]]
    notes: list[KitchenSpecialNote]
    totalIngredients: list[KitchenIngredientLine]
    totalCost: float


def _cycle_day_for(db: Session, target: _date) -> dict:
    cycle = db.query(MenuCycle).first()
    if cycle is None:
        return {}
    days_diff = (target - cycle.start_date).days
    idx = (days_diff % 21 + 21) % 21 + 1  # 1..21
    day = (
        db.query(MenuCycleDay)
        .filter(MenuCycleDay.cycle_id == cycle.id, MenuCycleDay.day_index == idx)
        .first()
    )
    return (day.meals or {}) if day else {}


@router.get("/task", response_model=KitchenTask)
def kitchen_task(
    target: _date = Query(..., alias="date"),
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin, UserRole.kitchen, UserRole.partner)),
):
    orders = (
        db.query(Order)
        .filter(Order.order_date == target, Order.status != OrderStatus.cancelled)
        .all()
    )
    cycle_map = _cycle_day_for(db, target)  # slot -> dish_id

    orders_by_tariff: dict[str, int] = {t: 0 for t in TARIFFS}
    total_cost = 0.0
    notes: list[KitchenSpecialNote] = []

    block_by_meal: dict[str, KitchenMealBlock] = {}
    by_slot: dict[str, list[KitchenMealBlock]] = {s: [] for s in SLOTS}
    total_ingredients: dict[int, KitchenIngredientLine] = {}

    dish_cache: dict[int, Dish] = {}

    def get_dish(dish_id: int) -> Optional[Dish]:
        if dish_id in dish_cache:
            return dish_cache[dish_id]
        dish = db.query(Dish).filter(Dish.id == dish_id).first()
        if dish is not None:
            dish_cache[dish_id] = dish
        return dish

    ing_cache: dict[int, Ingredient] = {}

    def get_ing(ing_id: int) -> Optional[Ingredient]:
        if ing_id in ing_cache:
            return ing_cache[ing_id]
        ing = db.query(Ingredient).filter(Ingredient.id == ing_id).first()
        if ing is not None:
            ing_cache[ing_id] = ing
        return ing

    def is_large(t: str) -> bool:
        return t in ("2000", "2500")

    for order in orders:
        tariff = order.tariff_code if order.tariff_code in TARIFFS else "1500"
        orders_by_tariff[tariff] = orders_by_tariff.get(tariff, 0) + 1

        client = db.query(Client).filter(Client.id == order.client_id).first()
        client_allergens = set(client.allergens or []) if client else set()
        exclusions = set(client.excluded_ingredients or []) if client else set()

        # Order-level meals (preferred) or fall back to cycle template
        meals = order.meals or []
        if not meals and cycle_map:
            meals = [
                {"mealId": str(cycle_map[slot]), "slot": slot}
                for slot in TARIFF_SLOT_MAP.get(tariff, SLOTS)
                if slot in cycle_map
            ]

        for meal in meals:
            try:
                dish_id = int(meal.get("mealId"))
            except (TypeError, ValueError):
                continue
            slot = meal.get("slot") or "lunch"

            dish = get_dish(dish_id)
            if dish is None:
                continue

            dish_ings = (
                db.query(DishIngredient)
                .filter(DishIngredient.dish_id == dish_id)
                .all()
            )

            conflict_allergens = [a for a in (dish.allergens or []) if a in client_allergens]
            conflict_ings: list[str] = []
            for di in dish_ings:
                ing = get_ing(di.ingredient_id)
                if not ing:
                    continue
                if any(excl.lower() in ing.name.lower() for excl in exclusions):
                    conflict_ings.append(ing.name)

            block = block_by_meal.get(str(dish_id))
            if block is None:
                block = KitchenMealBlock(
                    mealId=str(dish_id),
                    slot=slot,
                    name=dish.name,
                    portionsStandard=0,
                    portionsLarge=0,
                    portionsTotal=0,
                    byTariff={t: 0 for t in TARIFFS},
                    ingredients=[],
                )
                block_by_meal[str(dish_id)] = block
                if slot in by_slot:
                    by_slot[slot].append(block)

            if conflict_allergens or conflict_ings:
                parts: list[str] = []
                if conflict_allergens:
                    parts.append("аллергены: " + ", ".join(conflict_allergens))
                if conflict_ings:
                    parts.append("исключить: " + ", ".join(conflict_ings))
                notes.append(
                    KitchenSpecialNote(
                        clientId=str(order.client_id),
                        clientName=client.name if client else f"#{order.client_id}",
                        mealId=str(dish_id),
                        description=f"{dish.name} — {'; '.join(parts)}. Сделать замену.",
                    )
                )
                continue

            if is_large(tariff):
                block.portionsLarge += 1
            else:
                block.portionsStandard += 1
            block.portionsTotal += 1
            block.byTariff[tariff] = block.byTariff.get(tariff, 0) + 1

            block_ing_by_id: dict[int, KitchenIngredientLine] = {
                int(it.ingredientId): it for it in block.ingredients
            }

            for di in dish_ings:
                ing = get_ing(di.ingredient_id)
                if not ing:
                    continue
                amounts = di.amounts or {}
                amount = float(amounts.get(tariff) or amounts.get(str(tariff)) or di.quantity or 0)
                if amount <= 0:
                    continue

                line = block_ing_by_id.get(di.ingredient_id)
                if line is None:
                    line = KitchenIngredientLine(
                        ingredientId=str(di.ingredient_id),
                        name=ing.name,
                        unit=ing.unit,
                        total=0.0,
                        byTariff={t: 0.0 for t in TARIFFS},
                    )
                    block.ingredients.append(line)
                    block_ing_by_id[di.ingredient_id] = line
                line.total += amount
                line.byTariff[tariff] = line.byTariff.get(tariff, 0.0) + amount

                total_line = total_ingredients.get(di.ingredient_id)
                if total_line is None:
                    total_line = KitchenIngredientLine(
                        ingredientId=str(di.ingredient_id),
                        name=ing.name,
                        unit=ing.unit,
                        total=0.0,
                        byTariff={t: 0.0 for t in TARIFFS},
                    )
                    total_ingredients[di.ingredient_id] = total_line
                total_line.total += amount
                total_line.byTariff[tariff] = total_line.byTariff.get(tariff, 0.0) + amount
                total_cost += amount * float(ing.price_per_unit or 0.0)

    # Sorts
    for slot in SLOTS:
        by_slot[slot].sort(key=lambda b: b.portionsTotal, reverse=True)
        for block in by_slot[slot]:
            block.ingredients.sort(key=lambda i: i.total, reverse=True)

    total_list = sorted(total_ingredients.values(), key=lambda i: i.total, reverse=True)

    return KitchenTask(
        date=target.isoformat(),
        totalOrders=len(orders),
        ordersByTariff=orders_by_tariff,
        bySlot=by_slot,
        notes=notes,
        totalIngredients=total_list,
        totalCost=round(total_cost * 100) / 100,
    )
