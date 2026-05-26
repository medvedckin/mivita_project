from datetime import date as _date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from database import get_db
from dependencies.auth import require_role
from models.client import Client
from models.order import Order, OrderStatus
from models.subscription import Subscription, SubscriptionStatus
from models.tariff import Tariff
from models.user import UserRole
from schemas.order import (
    OrderCreate,
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


WEEKDAY_BY_INDEX = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _delivery_slot_for(client: Client, target: _date) -> Optional[dict]:
    schedule = list(client.schedule or [])
    if not schedule:
        return None
    wd = WEEKDAY_BY_INDEX[target.weekday()]
    for slot in schedule:
        if slot.get("weekday") == wd:
            return slot
    return schedule[0]


def _apply_override(order: Order, override: dict) -> None:
    if override.get("skipped"):
        order.status = OrderStatus.cancelled
    if override.get("tariff"):
        order.tariff_code = override["tariff"]
    delivery = dict(order.delivery_slot or {})
    if override.get("address"):
        delivery["address"] = override["address"]
    if override.get("timeSlot"):
        delivery["timeSlot"] = override["timeSlot"]
    if delivery:
        order.delivery_slot = delivery
        flag_modified(order, "delivery_slot")
    if override.get("comment"):
        order.comment = override["comment"]


@router.get("", response_model=list[OrderRead])
def list_orders(
    client_id: Optional[int] = Query(None, alias="clientId"),
    order_date: Optional[str] = Query(None, alias="date"),
    status_filter: Optional[OrderStatus] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=1000),
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin, UserRole.partner, UserRole.kitchen)),
):
    query = db.query(Order)
    if client_id:
        query = query.filter(Order.client_id == client_id)
    if order_date:
        query = query.filter(Order.order_date == order_date)
    if status_filter:
        query = query.filter(Order.status == status_filter)
    return (
        query.order_by(Order.order_date.desc(), Order.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(
    data: OrderCreate,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    client = db.query(Client).filter(Client.id == data.client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    payload = data.model_dump()
    if payload.get("delivery_slot") is None:
        payload["delivery_slot"] = _delivery_slot_for(client, data.order_date) or {}
    order = Order(**payload)
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.put("/{order_id}", response_model=OrderRead)
def update_order(
    order_id: int,
    data: OrderUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    order = _get_order_or_404(order_id, db)
    if order.locked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order is locked. Cancel lock before editing.",
        )
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(order, key, value)
    db.commit()
    db.refresh(order)
    return order


@router.patch("/{order_id}/status", response_model=OrderRead)
def update_order_status(
    order_id: int,
    data: OrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin, UserRole.kitchen)),
):
    order = _get_order_or_404(order_id, db)
    if current_user.role == UserRole.kitchen:
        allowed = {OrderStatus.confirmed, OrderStatus.in_kitchen, OrderStatus.delivered}
        if data.status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Kitchen can only transition between confirmed/in_kitchen/delivered",
            )
    order.status = data.status
    db.commit()
    db.refresh(order)
    return order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(
    order_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    order = _get_order_or_404(order_id, db)
    db.delete(order)
    db.commit()


# ---------- business process: generate / confirm / supplier list ----------


def _materialise_orders_for(db: Session, target: _date) -> list[Order]:
    """Create draft orders for every active subscription that covers `target`.
    Idempotent: if an order already exists (clientId+date) the subscription is skipped.
    """
    subs = (
        db.query(Subscription)
        .filter(
            Subscription.status == SubscriptionStatus.active,
            Subscription.start_date <= target,
            Subscription.end_date >= target,
        )
        .all()
    )

    existing_pairs = {
        (o.client_id, o.order_date)
        for o in db.query(Order).filter(Order.order_date == target).all()
    }

    created: list[Order] = []
    for sub in subs:
        if (sub.client_id, target) in existing_pairs:
            continue
        client = db.query(Client).filter(Client.id == sub.client_id).first()
        if client is None:
            continue

        override = next(
            (o for o in (sub.day_overrides or []) if o.get("date") == target.isoformat()),
            None,
        )
        if override and override.get("skipped"):
            continue

        tariff_code = (override or {}).get("tariff") or sub.tariff_code or client.tariff_code or "1500"
        tariff = db.query(Tariff).filter(Tariff.code == tariff_code).first()
        price = float(tariff.price_per_day) if tariff else 0.0

        delivery = _delivery_slot_for(client, target) or {}
        if override:
            if override.get("address"):
                delivery = {**delivery, "address": override["address"]}
            if override.get("timeSlot"):
                delivery = {**delivery, "timeSlot": override["timeSlot"]}

        order = Order(
            client_id=client.id,
            subscription_id=sub.id,
            order_date=target,
            tariff_code=tariff_code,
            status=OrderStatus.draft,
            meals=[],
            delivery_slot=delivery,
            allergens=list(client.allergens or []),
            excluded_ingredients=list(client.excluded_ingredients or []),
            payment_method=getattr(client, "payment_method", "transfer") or "transfer",
            price_total=price,
            comment=(override or {}).get("comment"),
        )
        db.add(order)
        created.append(order)

    db.commit()
    for o in created:
        db.refresh(o)
    return created


@router.post("/generate", response_model=list[OrderRead])
def generate_orders(
    target: _date = Query(..., alias="date"),
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    """Materialise draft orders for the given date from active subscriptions."""
    _materialise_orders_for(db, target)
    return (
        db.query(Order)
        .filter(Order.order_date == target)
        .order_by(Order.id)
        .all()
    )


@router.post("/confirm-day", response_model=list[OrderRead])
def confirm_day(
    target: _date = Query(..., alias="date"),
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    """Lock all draft orders for the given date: status→confirmed, locked_at=now()."""
    _materialise_orders_for(db, target)
    now = datetime.utcnow()
    orders = (
        db.query(Order)
        .filter(Order.order_date == target)
        .all()
    )
    locked = 0
    for o in orders:
        if o.status == OrderStatus.cancelled:
            continue
        if o.locked_at is None:
            o.locked_at = now
            locked += 1
        if o.status == OrderStatus.draft:
            o.status = OrderStatus.confirmed
    db.commit()
    for o in orders:
        db.refresh(o)
    return orders


@router.post("/unlock-day", response_model=list[OrderRead])
def unlock_day(
    target: _date = Query(..., alias="date"),
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    """Revert lock for the day (allows edits again). Used before 22:00 cutoff if needed."""
    orders = (
        db.query(Order)
        .filter(Order.order_date == target)
        .all()
    )
    for o in orders:
        o.locked_at = None
        if o.status == OrderStatus.confirmed:
            o.status = OrderStatus.draft
    db.commit()
    for o in orders:
        db.refresh(o)
    return orders


@router.get("/supplier-list")
def supplier_list(
    target: _date = Query(..., alias="date"),
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin, UserRole.kitchen)),
):
    """Aggregate ingredient totals for all non-cancelled orders on `target`.

    Walks `Order.meals` (JSON list of {mealId, slot}) — this is the immutable
    record of what each client gets on the day. For every meal we pull
    `DishIngredient.amounts[tariff]` (per-tariff grams) and sum by ingredient.
    """
    from models.dish_ingredient import DishIngredient
    from models.ingredient import Ingredient

    orders = (
        db.query(Order)
        .filter(
            Order.order_date == target,
            Order.status != OrderStatus.cancelled,
        )
        .all()
    )
    if not orders:
        return {
            "date": target.isoformat(),
            "orders_count": 0,
            "lines": [],
            "by_tariff": {},
        }

    totals: dict[int, dict] = {}
    by_tariff: dict[str, int] = {}
    dish_ing_cache: dict[int, list[DishIngredient]] = {}

    def dish_ings(dish_id: int) -> list[DishIngredient]:
        cached = dish_ing_cache.get(dish_id)
        if cached is not None:
            return cached
        rows = db.query(DishIngredient).filter(DishIngredient.dish_id == dish_id).all()
        dish_ing_cache[dish_id] = rows
        return rows

    for o in orders:
        by_tariff[o.tariff_code] = by_tariff.get(o.tariff_code, 0) + 1
        tariff = o.tariff_code
        for meal in (o.meals or []):
            try:
                dish_id = int(meal.get("mealId"))
            except (TypeError, ValueError):
                continue
            for di in dish_ings(dish_id):
                amounts = di.amounts or {}
                amount = float(amounts.get(tariff) or amounts.get(str(tariff)) or di.quantity or 0)
                if amount <= 0:
                    continue
                rec = totals.setdefault(
                    di.ingredient_id,
                    {"ingredient_id": di.ingredient_id, "name": None, "unit": di.unit, "quantity": 0.0},
                )
                rec["quantity"] += amount

    if totals:
        ingredient_ids = list(totals.keys())
        ingredients = (
            db.query(Ingredient).filter(Ingredient.id.in_(ingredient_ids)).all()
        )
        name_by_id = {i.id: i.name for i in ingredients}
        unit_by_id = {i.id: i.unit for i in ingredients}
        for ing_id, rec in totals.items():
            rec["name"] = name_by_id.get(ing_id, f"#{ing_id}")
            if not rec["unit"]:
                rec["unit"] = unit_by_id.get(ing_id)

    lines = sorted(totals.values(), key=lambda r: (r["name"] or ""))
    return {
        "date": target.isoformat(),
        "orders_count": len(orders),
        "by_tariff": by_tariff,
        "lines": lines,
    }


# Param routes registered last so that /generate, /confirm-day, /unlock-day, /supplier-list
# win the GET/POST match before /{order_id} catches them.
@router.get("/{order_id}", response_model=OrderRead)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin, UserRole.partner, UserRole.kitchen)),
):
    return _get_order_or_404(order_id, db)
