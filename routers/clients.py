from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies.auth import require_role
from models.client import Client
from models.order import Order
from models.user import UserRole
from schemas.client import ClientCreate, ClientRead, ClientUpdate
from schemas.order import OrderRead

router = APIRouter(prefix="/api/clients", tags=["clients"])


@router.get("", response_model=list[ClientRead])
def list_clients(
    search: Optional[str] = Query(None, alias="q"),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    _: Client = Depends(require_role(UserRole.admin, UserRole.partner)),
):
    query = db.query(Client)
    if search:
        query = query.filter(
            Client.name.ilike(f"%{search}%") | Client.phone.ilike(f"%{search}%")
        )
    return query.order_by(Client.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{client_id}", response_model=ClientRead)
def get_client(
    client_id: int,
    db: Session = Depends(get_db),
    _: Client = Depends(require_role(UserRole.admin, UserRole.partner)),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    return client


@router.post("", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
def create_client(
    data: ClientCreate,
    db: Session = Depends(get_db),
    _: Client = Depends(require_role(UserRole.admin)),
):
    payload = data.model_dump()
    payload["schedule"] = [s if isinstance(s, dict) else s.model_dump() for s in payload.get("schedule", [])]
    client = Client(**payload)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.put("/{client_id}", response_model=ClientRead)
def update_client(
    client_id: int,
    data: ClientUpdate,
    db: Session = Depends(get_db),
    _: Client = Depends(require_role(UserRole.admin)),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    payload = data.model_dump(exclude_unset=True)
    if "schedule" in payload and payload["schedule"] is not None:
        payload["schedule"] = [s if isinstance(s, dict) else s.model_dump() for s in payload["schedule"]]
    for key, value in payload.items():
        setattr(client, key, value)
    db.commit()
    db.refresh(client)
    return client


@router.get("/{client_id}/orders", response_model=list[OrderRead])
def get_client_orders(
    client_id: int,
    db: Session = Depends(get_db),
    _: Client = Depends(require_role(UserRole.admin, UserRole.partner)),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    return (
        db.query(Order)
        .filter(Order.client_id == client_id)
        .order_by(Order.order_date.desc())
        .all()
    )


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    _: Client = Depends(require_role(UserRole.admin)),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    db.delete(client)
    db.commit()
