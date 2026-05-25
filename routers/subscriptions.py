from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies.auth import require_role
from models.client import Client
from models.subscription import Subscription
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
    return (
        db.query(Subscription)
        .filter(Subscription.client_id == client_id)
        .all()
    )


@router.get(
    "/subscriptions/{subscription_id}",
    response_model=SubscriptionRead,
)
def get_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin, UserRole.partner)),
):
    return _get_subscription_or_404(subscription_id, db)


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
    sub = Subscription(client_id=client_id, **data.model_dump())
    db.add(sub)
    db.commit()
    db.refresh(sub)
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
    return sub
