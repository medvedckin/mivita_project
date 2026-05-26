from datetime import date as _date
from typing import Optional

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies.auth import require_role
from models.courier import Courier
from models.order import Order, OrderStatus
from models.route import Route, RoutePoint, RouteStatus
from models.user import UserRole
from schemas.courier import CourierCreate, CourierRead, CourierUpdate
from schemas.route import (
    RouteAssignCourier,
    RouteRead,
    RouteStatusUpdate,
)
from services.gis2_maps import geocode_address, optimize_route

router = APIRouter(prefix="/api", tags=["routes"])


# ---------- Courier CRUD ----------


@router.get("/couriers", response_model=list[CourierRead])
def list_couriers(
    active_only: bool = Query(False, alias="activeOnly"),
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin, UserRole.kitchen)),
):
    q = db.query(Courier)
    if active_only:
        q = q.filter(Courier.is_active == True)
    return q.order_by(Courier.name).all()


@router.post("/couriers", response_model=CourierRead, status_code=status.HTTP_201_CREATED)
def create_courier(
    data: CourierCreate,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    courier = Courier(**data.model_dump())
    db.add(courier)
    db.commit()
    db.refresh(courier)
    return courier


@router.get("/couriers/{courier_id}", response_model=CourierRead)
def get_courier(
    courier_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin, UserRole.kitchen)),
):
    courier = db.query(Courier).filter(Courier.id == courier_id).first()
    if not courier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Courier not found")
    return courier


@router.put("/couriers/{courier_id}", response_model=CourierRead)
def update_courier(
    courier_id: int,
    data: CourierUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    courier = db.query(Courier).filter(Courier.id == courier_id).first()
    if not courier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Courier not found")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(courier, key, val)
    db.commit()
    db.refresh(courier)
    return courier


@router.delete("/couriers/{courier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_courier(
    courier_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    courier = db.query(Courier).filter(Courier.id == courier_id).first()
    if not courier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Courier not found")
    db.delete(courier)
    db.commit()


# ---------- Route endpoints ----------


@router.get("/routes", response_model=list[RouteRead])
def list_routes(
    route_date: Optional[str] = Query(None, alias="date"),
    status_filter: Optional[RouteStatus] = Query(None, alias="status"),
    courier_id: Optional[int] = Query(None, alias="courierId"),
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin, UserRole.kitchen)),
):
    q = db.query(Route)
    if route_date:
        q = q.filter(Route.date == route_date)
    if status_filter:
        q = q.filter(Route.status == status_filter)
    if courier_id:
        q = q.filter(Route.courier_id == courier_id)
    return q.order_by(Route.date.desc(), Route.id.desc()).all()


@router.post("/routes/generate", response_model=list[RouteRead])
def generate_routes(
    target: _date = Query(..., alias="date"),
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    """Create a single route for all confirmed orders on the given date,
    geocode delivery addresses and optimise the stop order via Yandex Maps.
    """
    existing = db.query(Route).filter(Route.date == target).all()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Routes already exist for {target.isoformat()}. Delete them first.",
        )

    orders = (
        db.query(Order)
        .filter(
            Order.order_date == target,
            Order.status != OrderStatus.cancelled,
        )
        .all()
    )
    if not orders:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No non-cancelled orders for this date",
        )

    route = Route(
        date=target,
        status=RouteStatus.pending,
    )
    db.add(route)
    db.flush()

    waypoints: list[dict] = []
    temp_points: list[dict] = []

    for idx, order in enumerate(orders):
        address = (order.delivery_slot or {}).get("address", "")
        if not address:
            continue

        coords = geocode_address(address)
        lat = coords[1] if coords else None
        lon = coords[0] if coords else None

        point_data = {
            "route_id": route.id,
            "order_id": order.id,
            "client_id": order.client_id,
            "address": address,
            "latitude": lat,
            "longitude": lon,
            "sort_order": idx,
        }
        temp_points.append(point_data)
        waypoints.append({
            "address": address,
            "lat": lat,
            "lon": lon,
        })

    if waypoints:
        optimised = optimize_route(waypoints)
        ordered_indices = optimised["order"]

        for new_order, orig_idx in enumerate(ordered_indices):
            temp_points[orig_idx]["sort_order"] = new_order

        route.total_distance = optimised["total_distance_m"]
        route.total_duration = optimised["total_duration_min"]
        route.optimized_polyline = optimised["polyline"]

    for pt in temp_points:
        db.add(RoutePoint(**pt))

    db.commit()
    db.refresh(route)
    return [route]


@router.get("/routes/{route_id}", response_model=RouteRead)
def get_route(
    route_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin, UserRole.kitchen)),
):
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")
    return route


@router.delete("/routes/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_route(
    route_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")
    db.delete(route)
    db.commit()


@router.patch("/routes/{route_id}/status", response_model=RouteRead)
def update_route_status(
    route_id: int,
    data: RouteStatusUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin, UserRole.kitchen)),
):
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")
    route.status = data.status
    db.commit()
    db.refresh(route)
    return route


@router.patch("/routes/{route_id}/assign-courier", response_model=RouteRead)
def assign_courier(
    route_id: int,
    data: RouteAssignCourier,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")

    if data.courier_id is None:
        route.courier_id = None
        if route.status == RouteStatus.assigned:
            route.status = RouteStatus.pending
        db.commit()
        db.refresh(route)
        return route

    courier = db.query(Courier).filter(Courier.id == data.courier_id).first()
    if not courier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Courier not found")

    route.courier_id = data.courier_id
    if route.status == RouteStatus.pending:
        route.status = RouteStatus.assigned
    db.commit()
    db.refresh(route)

    try:
        from services.telegram_bot import notify_courier_assigned
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(notify_courier_assigned(data.courier_id, route_id))
        else:
            loop.run_until_complete(notify_courier_assigned(data.courier_id, route_id))
    except Exception:
        pass

    return route


@router.post("/routes/{route_id}/optimize", response_model=RouteRead)
def reoptimize_route(
    route_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_role(UserRole.admin)),
):
    """Re-geocode addresses and re-optimize the route stop order."""
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")

    points = (
        db.query(RoutePoint)
        .filter(RoutePoint.route_id == route_id)
        .order_by(RoutePoint.sort_order)
        .all()
    )
    if not points:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Route has no points")

    waypoints: list[dict] = []
    for pt in points:
        if pt.latitude is None or pt.longitude is None:
            coords = geocode_address(pt.address)
            if coords:
                pt.latitude = coords[1]
                pt.longitude = coords[0]
            else:
                pt.latitude = pt.latitude or 0
                pt.longitude = pt.longitude or 0

        waypoints.append({
            "address": pt.address,
            "lat": pt.latitude,
            "lon": pt.longitude,
        })

    if len(waypoints) >= 2:
        optimised = optimize_route(waypoints)
        ordered_indices = optimised["order"]

        for new_order, orig_idx in enumerate(ordered_indices):
            points[orig_idx].sort_order = new_order

        route.total_distance = optimised["total_distance_m"]
        route.total_duration = optimised["total_duration_min"]
        route.optimized_polyline = optimised["polyline"]

    db.commit()
    db.refresh(route)
    return route



