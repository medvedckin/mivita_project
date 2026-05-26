import asyncio
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
    routes,
    subscriptions,
    tariffs,
)
from routers.auth import seed_default_users
from routers.menu import seed_menu_cycle
from routers.tariffs import seed_tariffs
from services.seed_route import seed_test_route


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is managed by Alembic; run `alembic upgrade head` before starting.
    db = SessionLocal()
    try:
        seed_tariffs(db)
        seed_default_users(db)
        seed_menu_cycle(db)
        seed_test_route(db)
    finally:
        db.close()

    bot_task: asyncio.Task | None = None
    if settings.telegram_bot_token:
        from services.telegram_bot import init_bot, start_polling

        try:
            init_bot(settings.telegram_bot_token)
            bot_task = asyncio.create_task(start_polling())
            print("Telegram bot starting")
        except Exception as exc:
            print(f"Telegram bot init error: {exc}")

    yield

    if bot_task and not bot_task.done():
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
        from services.telegram_bot import stop_polling

        await stop_polling()
        print("Telegram bot stopped")


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
app.include_router(routes.router)
app.include_router(finance.router)
