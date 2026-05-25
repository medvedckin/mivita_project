from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies.auth import get_current_user, require_role
from models.client import Client
from models.order import Order
from models.order_dish import OrderDish
from models.dish_ingredient import DishIngredient
from models.user import UserRole
from schemas.client import ClientCreate, ClientRead, ClientUpdate
from schemas.order import OrderRead

router = APIRouter(prefix="/api/clients", tags=["clients"])


@router.get("", response_model=list[ClientRead])
def list_clients(
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Client = Depends(require_role(UserRole.admin, UserRole.partner)),
):
    query = db.query(Client)
    if search:
        query = query.filter(
            Client.name.ilike(f"%{search}%") | Client.phone.ilike(f"%{search}%")
        )
    return query.offset(skip).limit(limit).all()


@router.get("/{client_id}", response_model=ClientRead)
def get_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: Client = Depends(require_role(UserRole.admin, UserRole.partner)),
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
    current_user: Client = Depends(require_role(UserRole.admin)),
):
    client = Client(**data.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.put("/{client_id}", response_model=ClientRead)
def update_client(
    client_id: int,
    data: ClientUpdate,
    db: Session = Depends(get_db),
    current_user: Client = Depends(require_role(UserRole.admin)),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(client, key, value)
    db.commit()
    db.refresh(client)
    return client


@router.get("/{client_id}/orders", response_model=list[OrderRead])
def get_client_orders(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: Client = Depends(require_role(UserRole.admin, UserRole.partner)),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    orders = (
        db.query(Order)
        .filter(Order.client_id == client_id)
        .order_by(Order.order_date.desc())
        .all()
    )
    client_allergens = set(client.allergens or [])
    for order in orders:
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
    return orders


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: Client = Depends(require_role(UserRole.admin)),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    db.delete(client)
    db.commit()
