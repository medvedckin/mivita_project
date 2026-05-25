from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies.auth import require_role
from models.client import Client
from models.subscription import Subscription
from models.tariff import Tariff
from models.user import UserRole
from schemas.subscription import (
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


@router.get(
    "/clients/{client_id}/subscriptions",
    response_model=list[SubscriptionRead],
)
def list_subscriptions(
    client_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin, UserRole.partner)),
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
    current_user=Depends(require_role(UserRole.admin, UserRole.partner)),
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
    current_user=Depends(require_role(UserRole.admin)),
):
    _get_client_or_404(client_id, db)
    payload = data.model_dump()

    # Auto-fill from tariff if tariff_code provided
    tariff_code = payload.pop("tariff_code", None)
    if tariff_code:
        tariff = db.query(Tariff).filter(Tariff.code == tariff_code).first()
        if not tariff:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tariff '{tariff_code}' not found",
            )
        payload["tariff_code"] = tariff_code
        if "price" not in data.model_dump(exclude_unset=True) or not data.price:
            payload["price"] = float(tariff.price_per_day)
        if "meals_per_day" not in data.model_dump(exclude_unset=True):
            payload["meals_per_day"] = tariff.meals_per_day

    sub = Subscription(client_id=client_id, **payload)
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
    current_user=Depends(require_role(UserRole.admin)),
):
    sub = _get_subscription_or_404(subscription_id, db)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(sub, key, value)
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
    current_user=Depends(require_role(UserRole.admin)),
):
    sub = _get_subscription_or_404(subscription_id, db)
    sub.status = data.status
    db.commit()
    db.refresh(sub)
    _attach_tariff(sub, db)
    return sub
