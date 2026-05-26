from datetime import date as _date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from dependencies.auth import require_role
from models.order import Order, OrderStatus
from models.subscription import Subscription, SubscriptionStatus
from models.user import UserRole

router = APIRouter(prefix="/api/finance", tags=["finance"])


class FinanceEntry(BaseModel):
    id: str
    date: str
    type: str
    category: str
    amount: float
    clientId: Optional[str] = None
    description: Optional[str] = None


class DashboardStats(BaseModel):
    date: str
    ordersToday: int
    ordersTomorrow: int
    activeSubscriptions: int
    endingSoon: int
    revenueToday: float
    revenueMonth: float
    avgCheck: float


@router.get("/dashboard", response_model=DashboardStats)
def dashboard(
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin, UserRole.partner)),
):
    today = _date.today()
    tomorrow = today + timedelta(days=1)

    orders_today = (
        db.query(func.count(Order.id))
        .filter(Order.order_date == today, Order.status != OrderStatus.cancelled)
        .scalar()
        or 0
    )
    orders_tomorrow = (
        db.query(func.count(Order.id))
        .filter(Order.order_date == tomorrow, Order.status != OrderStatus.cancelled)
        .scalar()
        or 0
    )
    active = (
        db.query(func.count(Subscription.id))
        .filter(Subscription.status == SubscriptionStatus.active)
        .scalar()
        or 0
    )
    ending_limit = today + timedelta(days=2)
    ending_soon = (
        db.query(func.count(Subscription.id))
        .filter(
            Subscription.status == SubscriptionStatus.active,
            Subscription.end_date >= today,
            Subscription.end_date <= ending_limit,
        )
        .scalar()
        or 0
    )

    revenue_today = (
        db.query(func.coalesce(func.sum(Order.price_total), 0.0))
        .filter(
            Order.order_date == today,
            Order.status == OrderStatus.delivered,
        )
        .scalar()
        or 0.0
    )

    month_start = today.replace(day=1)
    month_orders = (
        db.query(Order)
        .filter(
            Order.order_date >= month_start,
            Order.status == OrderStatus.delivered,
        )
        .all()
    )
    revenue_month = sum(float(o.price_total or 0.0) for o in month_orders)
    avg_check = round(revenue_month / len(month_orders), 2) if month_orders else 0.0

    return DashboardStats(
        date=today.isoformat(),
        ordersToday=int(orders_today),
        ordersTomorrow=int(orders_tomorrow),
        activeSubscriptions=int(active),
        endingSoon=int(ending_soon),
        revenueToday=float(revenue_today),
        revenueMonth=float(revenue_month),
        avgCheck=avg_check,
    )


@router.get("/entries", response_model=list[FinanceEntry])
def entries(
    from_: Optional[_date] = Query(None, alias="from"),
    to: Optional[_date] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin, UserRole.partner)),
):
    """Derive finance entries from delivered orders (sales) within optional date range."""
    query = db.query(Order).filter(Order.status == OrderStatus.delivered)
    if from_:
        query = query.filter(Order.order_date >= from_)
    if to:
        query = query.filter(Order.order_date <= to)
    orders = query.order_by(Order.order_date.desc()).all()
    out: list[FinanceEntry] = []
    for o in orders:
        out.append(
            FinanceEntry(
                id=f"ord-{o.id}",
                date=o.order_date.isoformat(),
                type="sale",
                category="orders",
                amount=float(o.price_total or 0.0),
                clientId=str(o.client_id),
                description=f"Заказ #{o.id} · {o.tariff_code}",
            )
        )
    return out
