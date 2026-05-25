from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import Base, engine, SessionLocal
from routers import auth, clients, ingredients, dishes, kitchen, orders, subscriptions, tariffs
from routers.tariffs import seed_tariffs


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_tariffs(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Mivita API", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(clients.router)
app.include_router(ingredients.router)
app.include_router(dishes.router)
app.include_router(kitchen.router)
app.include_router(orders.router)
app.include_router(subscriptions.router)
app.include_router(tariffs.router)
