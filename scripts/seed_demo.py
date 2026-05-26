"""Idempotent demo data seed.

Usage:
    python -m scripts.seed_demo

Creates a small but coherent dataset:
  - 6 ingredients
  - 5 dishes (one per slot) with per-tariff amounts
  - 3 clients (different tariffs, different schedules)
  - 1 active subscription per client
  - Menu cycle days 1..3 populated with the 5 dishes
  - Tomorrow's orders materialised + confirmed (locked) so the
    `Лист поставщику` button has something to aggregate.

Re-running the script does NOT duplicate data: it looks up entities
by their natural key (name / phone / dish name etc.) before inserting.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from database import SessionLocal
from models.client import Client, Messenger, PaymentMethod
from models.dish import Dish, MealSlot
from models.dish_ingredient import DishIngredient
from models.ingredient import Ingredient
from models.menu_cycle import MenuCycle, MenuCycleDay
from models.order import Order, OrderStatus
from models.subscription import Subscription, SubscriptionStatus
from models.tariff import Tariff
from routers.auth import seed_default_users
from routers.menu import seed_menu_cycle
from routers.orders import _materialise_orders_for
from routers.tariffs import seed_tariffs


def get_or_create_ingredient(db: Session, *, name: str, **fields) -> Ingredient:
    obj = db.query(Ingredient).filter(Ingredient.name == name).first()
    if obj:
        return obj
    obj = Ingredient(name=name, **fields)
    db.add(obj)
    db.flush()
    return obj


def get_or_create_dish(db: Session, *, name: str, **fields) -> Dish:
    obj = db.query(Dish).filter(Dish.name == name).first()
    if obj:
        return obj
    obj = Dish(name=name, **fields)
    db.add(obj)
    db.flush()
    return obj


def upsert_dish_ingredient(
    db: Session,
    *,
    dish: Dish,
    ingredient: Ingredient,
    amounts: dict[str, float],
) -> None:
    existing = (
        db.query(DishIngredient)
        .filter(
            DishIngredient.dish_id == dish.id,
            DishIngredient.ingredient_id == ingredient.id,
        )
        .first()
    )
    if existing:
        existing.amounts = amounts
        existing.quantity = float(amounts.get("2000", 0))
        existing.unit = ingredient.unit
        return
    db.add(
        DishIngredient(
            dish_id=dish.id,
            ingredient_id=ingredient.id,
            amounts=amounts,
            quantity=float(amounts.get("2000", 0)),
            unit=ingredient.unit,
        )
    )


def get_or_create_client(db: Session, *, phone: str, **fields) -> Client:
    obj = db.query(Client).filter(Client.phone == phone).first()
    if obj:
        return obj
    obj = Client(phone=phone, **fields)
    db.add(obj)
    db.flush()
    return obj


def get_or_create_subscription(
    db: Session,
    *,
    client_id: int,
    start_date: date,
    end_date: date,
    tariff_code: str,
) -> Subscription:
    obj = (
        db.query(Subscription)
        .filter(
            Subscription.client_id == client_id,
            Subscription.start_date == start_date,
        )
        .first()
    )
    if obj:
        return obj
    tariff = db.query(Tariff).filter(Tariff.code == tariff_code).first()
    price = float(tariff.price_per_day) if tariff else 0.0
    days = max(1, (end_date - start_date).days + 1)
    obj = Subscription(
        client_id=client_id,
        tariff_code=tariff_code,
        start_date=start_date,
        end_date=end_date,
        status=SubscriptionStatus.active,
        total_price=price * days,
        day_overrides=[],
        change_log=[
            {
                "id": "seed",
                "at": datetime.utcnow().isoformat(timespec="minutes"),
                "field": "created",
                "description": f"Demo seed: {tariff_code}, {days} дн.",
            }
        ],
    )
    db.add(obj)
    db.flush()
    return obj


def set_cycle_day(db: Session, day_index: int, meals: dict[str, int]) -> None:
    cycle = db.query(MenuCycle).first()
    if cycle is None:
        return
    day = (
        db.query(MenuCycleDay)
        .filter(MenuCycleDay.cycle_id == cycle.id, MenuCycleDay.day_index == day_index)
        .first()
    )
    if day is None:
        day = MenuCycleDay(cycle_id=cycle.id, day_index=day_index, meals=meals)
        db.add(day)
    else:
        day.meals = meals


def seed_demo(db: Session) -> None:
    # ---------- foundation (idempotent helpers from the app) ----------
    seed_tariffs(db)
    seed_default_users(db)
    seed_menu_cycle(db)

    # ---------- ingredients ----------
    chicken = get_or_create_ingredient(db, name="Куриная грудка", unit="g", category="meat", supplier="МясоПрофи", price_per_unit=0.025)
    rice = get_or_create_ingredient(db, name="Рис басмати", unit="g", category="grain", supplier="ЭкоСклад", price_per_unit=0.005)
    broccoli = get_or_create_ingredient(db, name="Брокколи", unit="g", category="vegetable", supplier="Овощебаза №1", price_per_unit=0.008)
    oats = get_or_create_ingredient(db, name="Овсяные хлопья", unit="g", category="grain", supplier="ЭкоСклад", price_per_unit=0.004)
    yogurt = get_or_create_ingredient(db, name="Греческий йогурт", unit="ml", category="dairy", supplier="МолокоЛюкс", price_per_unit=0.012)
    apple = get_or_create_ingredient(db, name="Яблоко", unit="pcs", category="fruit", supplier="Овощебаза №1", price_per_unit=0.5)
    db.flush()

    # ---------- dishes ----------
    breakfast = get_or_create_dish(
        db,
        name="Овсянка с йогуртом",
        slot=MealSlot.breakfast,
        kcal_by_tariff={"1500": 280, "1800": 320, "2000": 380, "2500": 450},
        allergens=["lactose", "gluten"],
        cook_time_min=10,
        steps=[{"order": 1, "description": "Залить овсянку кипятком на 5 мин", "durationMin": 5},
               {"order": 2, "description": "Добавить йогурт, перемешать", "durationMin": 1}],
    )
    snack_morning = get_or_create_dish(
        db,
        name="Яблоко",
        slot=MealSlot.snack1,
        kcal_by_tariff={"1500": 0, "1800": 0, "2000": 80, "2500": 80},
        allergens=[],
        cook_time_min=0,
        steps=[],
    )
    lunch = get_or_create_dish(
        db,
        name="Курица с рисом и брокколи",
        slot=MealSlot.lunch,
        kcal_by_tariff={"1500": 520, "1800": 580, "2000": 640, "2500": 720},
        allergens=[],
        cook_time_min=25,
        steps=[{"order": 1, "description": "Отварить рис", "durationMin": 15},
               {"order": 2, "description": "Запечь курицу 200°C", "durationMin": 20},
               {"order": 3, "description": "Бланшировать брокколи", "durationMin": 5}],
    )
    snack_evening = get_or_create_dish(
        db,
        name="Йогурт греческий",
        slot=MealSlot.snack2,
        kcal_by_tariff={"1500": 0, "1800": 140, "2000": 160, "2500": 200},
        allergens=["lactose"],
        cook_time_min=0,
        steps=[],
    )
    dinner = get_or_create_dish(
        db,
        name="Курица с овощами",
        slot=MealSlot.dinner,
        kcal_by_tariff={"1500": 420, "1800": 460, "2000": 520, "2500": 580},
        allergens=[],
        cook_time_min=20,
        steps=[{"order": 1, "description": "Запечь курицу с овощами", "durationMin": 20}],
    )
    db.flush()

    # ---------- dish ingredients (per-tariff amounts in grams or ml or pcs) ----------
    upsert_dish_ingredient(db, dish=breakfast, ingredient=oats, amounts={"1500": 50, "1800": 60, "2000": 70, "2500": 80})
    upsert_dish_ingredient(db, dish=breakfast, ingredient=yogurt, amounts={"1500": 100, "1800": 120, "2000": 140, "2500": 160})

    upsert_dish_ingredient(db, dish=snack_morning, ingredient=apple, amounts={"1500": 0, "1800": 0, "2000": 1, "2500": 1})

    upsert_dish_ingredient(db, dish=lunch, ingredient=chicken, amounts={"1500": 120, "1800": 140, "2000": 160, "2500": 180})
    upsert_dish_ingredient(db, dish=lunch, ingredient=rice, amounts={"1500": 80, "1800": 100, "2000": 120, "2500": 140})
    upsert_dish_ingredient(db, dish=lunch, ingredient=broccoli, amounts={"1500": 100, "1800": 120, "2000": 140, "2500": 160})

    upsert_dish_ingredient(db, dish=snack_evening, ingredient=yogurt, amounts={"1500": 0, "1800": 150, "2000": 170, "2500": 200})

    upsert_dish_ingredient(db, dish=dinner, ingredient=chicken, amounts={"1500": 100, "1800": 120, "2000": 140, "2500": 160})
    upsert_dish_ingredient(db, dish=dinner, ingredient=broccoli, amounts={"1500": 120, "1800": 140, "2000": 160, "2500": 180})

    db.flush()

    # ---------- menu cycle days 1..3 ----------
    full_day = {
        "breakfast": breakfast.id,
        "snack1": snack_morning.id,
        "lunch": lunch.id,
        "snack2": snack_evening.id,
        "dinner": dinner.id,
    }
    set_cycle_day(db, 1, dict(full_day))
    set_cycle_day(db, 2, dict(full_day))
    set_cycle_day(db, 3, dict(full_day))

    # ---------- clients ----------
    client_a = get_or_create_client(
        db,
        phone="+995555111222",
        name="Анна Кобахидзе",
        email="anna@example.ge",
        messenger=Messenger.telegram.value,
        messenger_handle="@anna_k",
        payment_method=PaymentMethod.transfer.value,
        tariff_code="1500",
        allergens=["mushroom"],
        excluded_ingredients=["лук"],
        schedule=[
            {"weekday": "mon", "address": "ул. Шота Руставели, 12", "timeSlot": "09-10"},
            {"weekday": "tue", "address": "ул. Шота Руставели, 12", "timeSlot": "09-10"},
            {"weekday": "wed", "address": "ул. Шота Руставели, 12", "timeSlot": "09-10"},
            {"weekday": "thu", "address": "ул. Шота Руставели, 12", "timeSlot": "09-10"},
            {"weekday": "fri", "address": "ул. Шота Руставели, 12", "timeSlot": "09-10"},
        ],
    )
    client_b = get_or_create_client(
        db,
        phone="+995555333444",
        name="Гиоргий Бакурадзе",
        email="giorgi@example.ge",
        messenger=Messenger.whatsapp.value,
        payment_method=PaymentMethod.cash.value,
        tariff_code="2000",
        allergens=[],
        excluded_ingredients=[],
        schedule=[
            {"weekday": "mon", "address": "пр. Агмашенебели, 45", "timeSlot": "10-11"},
            {"weekday": "wed", "address": "пр. Агмашенебели, 45", "timeSlot": "10-11"},
            {"weekday": "fri", "address": "пр. Агмашенебели, 45", "timeSlot": "10-11"},
        ],
    )
    client_c = get_or_create_client(
        db,
        phone="+995555777888",
        name="Нино Цулукидзе",
        email="nino@example.ge",
        messenger=Messenger.instagram.value,
        payment_method=PaymentMethod.transfer.value,
        tariff_code="1800",
        allergens=["lactose"],
        excluded_ingredients=[],
        schedule=[
            {"weekday": "mon", "address": "ул. Лермонтова, 3", "timeSlot": "11-12"},
            {"weekday": "tue", "address": "ул. Лермонтова, 3", "timeSlot": "11-12"},
            {"weekday": "wed", "address": "ул. Лермонтова, 3", "timeSlot": "11-12"},
            {"weekday": "thu", "address": "ул. Лермонтова, 3", "timeSlot": "11-12"},
            {"weekday": "fri", "address": "ул. Лермонтова, 3", "timeSlot": "11-12"},
            {"weekday": "sat", "address": "ул. Лермонтова, 3", "timeSlot": "11-12"},
        ],
    )
    db.flush()

    # ---------- subscriptions (today → +30 days) ----------
    today = date.today()
    in_a_month = today + timedelta(days=30)
    get_or_create_subscription(db, client_id=client_a.id, start_date=today, end_date=in_a_month, tariff_code="1500")
    get_or_create_subscription(db, client_id=client_b.id, start_date=today, end_date=in_a_month, tariff_code="2000")
    get_or_create_subscription(db, client_id=client_c.id, start_date=today, end_date=in_a_month, tariff_code="1800")
    db.flush()

    # ---------- tomorrow's orders: generate + lock ----------
    tomorrow = today + timedelta(days=1)
    _materialise_orders_for(db, tomorrow)
    now = datetime.utcnow()
    for o in db.query(Order).filter(Order.order_date == tomorrow).all():
        if o.status == OrderStatus.draft:
            o.status = OrderStatus.confirmed
        if o.locked_at is None:
            o.locked_at = now
        # Attach the menu (so /api/orders/supplier-list has data via OrderDish if you go that route,
        # and /api/kitchen/task can aggregate from order.meals).
        slot_to_dish = {
            "breakfast": breakfast.id,
            "snack1": snack_morning.id,
            "lunch": lunch.id,
            "snack2": snack_evening.id,
            "dinner": dinner.id,
        }
        # Pick the slots that match the tariff
        tariff_slots = {
            "1500": ["breakfast", "lunch", "dinner"],
            "1800": ["breakfast", "lunch", "snack2", "dinner"],
            "2000": ["breakfast", "snack1", "lunch", "snack2", "dinner"],
            "2500": ["breakfast", "snack1", "lunch", "snack2", "dinner"],
        }.get(o.tariff_code, ["breakfast", "lunch", "dinner"])
        o.meals = [{"mealId": str(slot_to_dish[slot]), "slot": slot} for slot in tariff_slots]

    db.commit()


def main() -> None:
    db = SessionLocal()
    try:
        seed_demo(db)
        print("Demo data seeded.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
