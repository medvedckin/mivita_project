from datetime import datetime
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from database import get_db
from dependencies.auth import require_role
from models.client import Client
from models.subscription import Subscription, SubscriptionStatus
from models.tariff import Tariff
from models.user import UserRole
from schemas.subscription import (
    DayOverride,
    SubscriptionCreate,
    SubscriptionRead,
    SubscriptionStatusUpdate,
    SubscriptionUpdate,
)

router = APIRouter(prefix="/api", tags=["subscriptions"])


def _get_client_or_404(client_id: int, db: Session) -> Client:
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    return client


def _get_subscription_or_404(sub_id: int, db: Session) -> Subscription:
    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    return sub


def _attach_tariff(sub: Subscription, db: Session):
    if sub.tariff_code:
        tariff = db.query(Tariff).filter(Tariff.code == sub.tariff_code).first()
        sub.tariff = tariff


def _log_change(sub: Subscription, field: str, description: str):
    entry = {
        "id": uuid.uuid4().hex[:12],
        "at": datetime.utcnow().isoformat(timespec="minutes"),
        "field": field,
        "description": description,
    }
    log = list(sub.change_log or [])
    log.insert(0, entry)
    sub.change_log = log
    flag_modified(sub, "change_log")


@router.get(
    "/subscriptions",
    response_model=list[SubscriptionRead],
)
def list_all_subscriptions(
    status_filter: Optional[SubscriptionStatus] = Query(None, alias="status"),
    client_id: Optional[int] = Query(None, alias="clientId"),
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin, UserRole.partner)),
):
    query = db.query(Subscription)
    if status_filter:
        query = query.filter(Subscription.status == status_filter)
    if client_id:
        query = query.filter(Subscription.client_id == client_id)
    subs = query.order_by(Subscription.start_date.desc()).all()
    for s in subs:
        _attach_tariff(s, db)
    return subs


@router.get(
    "/subscriptions/ending-soon",
    response_model=list[SubscriptionRead],
)
def ending_soon(
    days: int = Query(2, ge=1, le=30),
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin, UserRole.partner)),
):
    from datetime import date as _date, timedelta

    today = _date.today()
    limit = today + timedelta(days=days)
    subs = (
        db.query(Subscription)
        .filter(
            Subscription.status == SubscriptionStatus.active,
            Subscription.end_date >= today,
            Subscription.end_date <= limit,
        )
        .order_by(Subscription.end_date)
        .all()
    )
    for s in subs:
        _attach_tariff(s, db)
    return subs


@router.get(
    "/clients/{client_id}/subscriptions",
    response_model=list[SubscriptionRead],
)
def list_subscriptions(
    client_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin, UserRole.partner)),
):
    _get_client_or_404(client_id, db)
    subs = (
        db.query(Subscription)
        .filter(Subscription.client_id == client_id)
        .all()
    )
    for s in subs:
        _attach_tariff(s, db)
    return subs


@router.get(
    "/subscriptions/{subscription_id}",
    response_model=SubscriptionRead,
)
def get_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin, UserRole.partner)),
):
    sub = _get_subscription_or_404(subscription_id, db)
    _attach_tariff(sub, db)
    return sub


@router.post(
    "/clients/{client_id}/subscriptions",
    response_model=SubscriptionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_subscription(
    client_id: int,
    data: SubscriptionCreate,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    _get_client_or_404(client_id, db)
    tariff = db.query(Tariff).filter(Tariff.code == data.tariff_code).first()
    if not tariff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tariff '{data.tariff_code}' not found",
        )

    total_price = data.total_price
    if not total_price:
        days = max(1, (data.end_date - data.start_date).days + 1)
        total_price = float(tariff.price_per_day) * days

    sub = Subscription(
        client_id=client_id,
        tariff_code=data.tariff_code,
        start_date=data.start_date,
        end_date=data.end_date,
        total_price=total_price,
        notes=data.notes,
        day_overrides=[],
        change_log=[
            {
                "id": uuid.uuid4().hex[:12],
                "at": datetime.utcnow().isoformat(timespec="minutes"),
                "field": "created",
                "description": f"Подписка создана: {tariff.code}",
            }
        ],
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    _attach_tariff(sub, db)
    return sub


@router.put(
    "/subscriptions/{subscription_id}",
    response_model=SubscriptionRead,
)
def update_subscription(
    subscription_id: int,
    data: SubscriptionUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    sub = _get_subscription_or_404(subscription_id, db)
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        before = getattr(sub, key, None)
        setattr(sub, key, value)
        if before != value:
            _log_change(sub, key, f"{key}: {before} → {value}")
    db.commit()
    db.refresh(sub)
    _attach_tariff(sub, db)
    return sub


@router.patch(
    "/subscriptions/{subscription_id}/status",
    response_model=SubscriptionRead,
)
def update_subscription_status(
    subscription_id: int,
    data: SubscriptionStatusUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    sub = _get_subscription_or_404(subscription_id, db)
    before = sub.status
    sub.status = data.status
    if before != data.status:
        _log_change(sub, "status", f"Статус: {before.value} → {data.status.value}")
    db.commit()
    db.refresh(sub)
    _attach_tariff(sub, db)
    return sub


@router.post(
    "/subscriptions/{subscription_id}/overrides",
    response_model=SubscriptionRead,
)
def upsert_override(
    subscription_id: int,
    override: DayOverride,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    sub = _get_subscription_or_404(subscription_id, db)
    overrides = list(sub.day_overrides or [])
    overrides = [o for o in overrides if o.get("date") != override.date]
    overrides.append(override.model_dump(exclude_none=True))
    overrides.sort(key=lambda o: o.get("date", ""))
    sub.day_overrides = overrides
    flag_modified(sub, "day_overrides")
    _log_change(sub, "override", f"Изменение на {override.date}")
    db.commit()
    db.refresh(sub)
    _attach_tariff(sub, db)
    return sub


@router.delete(
    "/subscriptions/{subscription_id}/overrides/{day}",
    response_model=SubscriptionRead,
)
def delete_override(
    subscription_id: int,
    day: str,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    sub = _get_subscription_or_404(subscription_id, db)
    overrides = [o for o in (sub.day_overrides or []) if o.get("date") != day]
    sub.day_overrides = overrides
    flag_modified(sub, "day_overrides")
    _log_change(sub, "override", f"Удалена замена на {day}")
    db.commit()
    db.refresh(sub)
    _attach_tariff(sub, db)
    return sub
