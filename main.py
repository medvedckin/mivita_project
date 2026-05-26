from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import SessionLocal
from routers import (
    auth,
    clients,
    dishes,
    finance,
    ingredients,
    kitchen,
    menu,
    meta,
    orders,
    subscriptions,
    tariffs,
)
from routers.auth import seed_default_users
from routers.menu import seed_menu_cycle
from routers.tariffs import seed_tariffs


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is managed by Alembic; run `alembic upgrade head` before starting.
    db = SessionLocal()
    try:
        seed_tariffs(db)
        seed_default_users(db)
        seed_menu_cycle(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Mivita API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(meta.router)
app.include_router(clients.router)
app.include_router(ingredients.router)
app.include_router(dishes.router)
app.include_router(kitchen.router)
app.include_router(menu.router)
app.include_router(orders.router)
app.include_router(subscriptions.router)
app.include_router(tariffs.router)
app.include_router(finance.router)
