import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class RouteStatus(str, enum.Enum):
    pending = "pending"
    assigned = "assigned"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    courier_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("couriers.id"), nullable=True, index=True
    )
    status: Mapped[RouteStatus] = mapped_column(
        String(20), default=RouteStatus.pending.value, nullable=False
    )
    total_distance: Mapped[float] = mapped_column(Float, nullable=True)
    total_duration: Mapped[float] = mapped_column(Float, nullable=True)
    optimized_polyline: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    courier = relationship("Courier")
    points = relationship(
        "RoutePoint", back_populates="route", order_by="RoutePoint.sort_order",
        cascade="all, delete-orphan",
    )


class RoutePoint(Base):
    __tablename__ = "route_points"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    route_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("routes.id"), nullable=False, index=True
    )
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id"), nullable=False
    )
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False
    )
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_arrival: Mapped[str] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    route = relationship("Route", back_populates="points")
    order = relationship("Order")
    client = relationship("Client")
