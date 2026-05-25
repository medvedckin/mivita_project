from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import Base, engine
from routers import auth, clients, ingredients, dishes, kitchen, orders, subscriptions


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Mivita API", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(clients.router)
app.include_router(ingredients.router)
app.include_router(dishes.router)
app.include_router(kitchen.router)
app.include_router(orders.router)
app.include_router(subscriptions.router)
