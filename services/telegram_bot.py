import asyncio
import logging
from datetime import date
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from sqlalchemy.orm import Session

from database import SessionLocal
from models.client import Client
from models.courier import Courier
from models.order import Order, OrderStatus
from models.route import Route, RoutePoint, RouteStatus
from models.telegram_courier import TelegramCourier

logger = logging.getLogger(__name__)

bot: Bot | None = None
dp: Dispatcher | None = None

# ---------- Menu constants ----------

MENU_ORDERS = "📋 Заказы на сегодня"
MENU_TAKE_ROUTE = "🚗 Взять маршрут"
MENU_MY_ROUTES = "📍 Мои маршруты"
MENU_COMPLETE_ORDER = "✅ Выполнить заказ"
MENU_SEED_ROUTE = "🔄 Создать тестовый маршрут"

BUTTON_SET = {MENU_ORDERS, MENU_TAKE_ROUTE, MENU_MY_ROUTES, MENU_COMPLETE_ORDER, MENU_SEED_ROUTE}

# ---------- Init ----------


def init_bot(token: str) -> Bot:
    global bot, dp
    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()
    _register_handlers(dp)
    return bot


def _register_handlers(dispatcher: Dispatcher) -> None:
    dispatcher.message.register(cmd_start, Command("start"))
    dispatcher.message.register(cmd_menu, Command("menu"))
    dispatcher.message.register(handle_contact, F.contact)
    dispatcher.message.register(handle_main_menu_text, F.text.in_(BUTTON_SET))
    dispatcher.message.register(handle_phone, F.text.regexp(r"^\+?\d[\d\s\-\(\)]{7,20}$"))
    dispatcher.callback_query.register(cb_take_route, F.data.startswith("take_route:"))
    dispatcher.callback_query.register(cb_route_action, F.data.startswith("route_"))
    dispatcher.callback_query.register(cb_order_action, F.data.startswith("order_done:"))
    dispatcher.callback_query.register(cb_order_detail, F.data.startswith("order_detail:"))
    dispatcher.callback_query.register(cb_order_question, F.data.startswith("order_question:"))
    dispatcher.callback_query.register(cb_accept_route, F.data.startswith("route_accept:"))
    dispatcher.callback_query.register(cb_decline_route, F.data.startswith("route_decline:"))


# ---------- Polling ----------


async def start_polling() -> None:
    if bot is None or dp is None:
        logger.error("Bot not initialised")
        return
    retry_delay = 10
    max_delay = 300
    while True:
        try:
            await dp.start_polling(bot, handle_signals=False)
            break
        except Exception as exc:
            logger.error("Bot polling error: %s — retrying in %ds", exc, retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)


async def stop_polling() -> None:
    if bot:
        await bot.session.close()


# ---------- DB helpers ----------


def _get_db() -> Session:
    return SessionLocal()


def _get_courier_by_chat(chat_id: int, db: Session) -> Courier | None:
    link = (
        db.query(TelegramCourier)
        .filter(TelegramCourier.telegram_chat_id == chat_id)
        .first()
    )
    if not link:
        return None
    return db.query(Courier).filter(Courier.id == link.courier_id).first()


def _get_order_field(order: Order, key: str, default: str = "") -> str:
    return (order.delivery_slot or {}).get(key, default)


def _get_meal_name(meal: dict) -> str:
    return str(meal.get("mealId", meal.get("name", "")))


def _get_meals_str(order: Order) -> str:
    return ", ".join(_get_meal_name(m) for m in (order.meals or []))


def _get_time_slot(order: Order) -> str:
    return (order.delivery_slot or {}).get("timeSlot", (order.delivery_slot or {}).get("time", ""))


def _get_comment(order: Order) -> str:
    return order.comment or order.notes or ""


def _get_chat_by_courier(courier_id: int, db: Session) -> int | None:
    link = (
        db.query(TelegramCourier)
        .filter(TelegramCourier.courier_id == courier_id)
        .first()
    )
    return link.telegram_chat_id if link else None


def _get_dish_calories(dish_name: str, db: Session) -> str:
    from models.dish import Dish
    dish = db.query(Dish).filter(Dish.name == dish_name.strip()).first()
    if dish and dish.kcal_by_tariff:
        parts = []
        for k, v in dish.kcal_by_tariff.items():
            k_label = {"premium": "", "economy": "эконом ", "business": "бизнес "}.get(k, f"{k} ")
            parts.append(f"{k_label}{v} ккал")
        return ", ".join(parts)
    return "—"


# ---------- Public API for notifications ----------


async def notify_courier_assigned(courier_id: int, route_id: int) -> None:
    """Send route assignment notification to courier's Telegram (called from API)."""
    if bot is None:
        return
    try:
        async with asyncio.timeout(15):
            db = _get_db()
            try:
                chat_id = _get_chat_by_courier(courier_id, db)
                if not chat_id:
                    return

                route = db.query(Route).filter(Route.id == route_id).first()
                if not route:
                    return

                courier = db.query(Courier).filter(Courier.id == courier_id).first()
                courier_name = courier.name if courier else ""

                points = (
                    db.query(RoutePoint)
                    .filter(RoutePoint.route_id == route.id)
                    .order_by(RoutePoint.sort_order)
                    .all()
                )

                text = _build_route_notification(route, points, courier_name, db)
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(text="✅ Принять маршрут", callback_data=f"route_accept:{route_id}"),
                            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"route_decline:{route_id}"),
                        ]
                    ]
                )
                await bot.send_message(chat_id, text, reply_markup=kb)
            finally:
                db.close()
    except asyncio.TimeoutError:
        logger.error("Route notification timed out for courier %d, route %d", courier_id, route_id)
    except Exception as exc:
        logger.error("Failed to send route notification: %s", exc)


def _build_route_notification(
    route: Route, points: list[RoutePoint], courier_name: str, db: Session
) -> str:
    from models.client import Client
    from models.dish import Dish

    header = (
        f"🚚 <b>Новый маршрут #{route.id} назначен!</b>\n"
        f"👤 Курьер: {courier_name or '—'}\n"
        f"📏 {_fmt_distance(route.total_distance)} | "
        f"⏱ {_fmt_duration(route.total_duration)}\n"
        f"📍 Остановок: {len(points)}\n"
        f"🗓 {route.date}\n\n"
        f"<b>Остановки:</b>"
    )

    lines = [header]
    for i, pt in enumerate(points, 1):
        client = db.query(Client).filter(Client.id == pt.client_id).first()
        order = db.query(Order).filter(Order.id == pt.order_id).first()
        meals = order.meals or []
        time_slot = _get_time_slot(order) if order else ""

        meal_details = []
        total_kcal = 0
        for m in meals:
            name = _get_meal_name(m)
            if name and name != "—":
                calories = _get_dish_calories(name, db)
                total_kcal += sum(
                    int(v.split()[0]) for v in calories.replace(",", "").split()
                    if v.split()[0].isdigit()
                ) if calories != "—" else 0
                meal_details.append(f"🍽 {name}")

        addr_short = pt.address[:40] if pt.address else "—"
        client_name = client.name if client else "—"
        comment = _get_comment(order) if order else ""

        lines.append(
            f"\n{i}. 🏠 {addr_short}"
            f"\n   👤 {client_name}"
        )
        for md in meal_details:
            lines.append(f"   {md}")
        if time_slot:
            lines.append(f"   🕐 {time_slot}")
        if total_kcal > 0:
            lines.append(f"   🔥 ~{total_kcal} ккал")
        if comment:
            lines.append(f"   💬 {comment}")

    lines.append(f"\n<b>Нажми «Принять», чтобы начать доставку:</b>")
    return "\n".join(lines)


async def cb_accept_route(callback: CallbackQuery) -> None:
    data = callback.data or ""
    if not data.startswith("route_accept:"):
        return
    parts = data.split(":")
    if len(parts) != 2:
        await callback.answer("Неверная команда")
        return
    try:
        route_id = int(parts[1])
    except ValueError:
        await callback.answer("Неверный ID")
        return

    chat_id = callback.message.chat.id
    db = _get_db()
    try:
        courier = _get_courier_by_chat(chat_id, db)
        if not courier:
            await callback.answer("Ты не зарегистрирован. Напиши /start")
            return

        route = db.query(Route).filter(Route.id == route_id).first()
        if not route:
            await callback.answer("Маршрут не найден")
            return
        if route.courier_id != courier.id:
            await callback.answer("Этот маршрут назначен другому курьеру")
            return
        if route.status != RouteStatus.assigned:
            await callback.answer("Маршрут уже принят")
            return

        route.status = RouteStatus.in_progress
        db.commit()

        await callback.answer("✅ Маршрут принят!")
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ Маршрут принят и начат!",
            reply_markup=None,
        )

        points = (
            db.query(RoutePoint)
            .filter(RoutePoint.route_id == route.id)
            .order_by(RoutePoint.sort_order)
            .all()
        )
        await _send_route_map(callback.message, route, points, db)
    finally:
        db.close()


async def cb_decline_route(callback: CallbackQuery) -> None:
    data = callback.data or ""
    if not data.startswith("route_decline:"):
        return
    parts = data.split(":")
    if len(parts) != 2:
        await callback.answer("Неверная команда")
        return
    try:
        route_id = int(parts[1])
    except ValueError:
        await callback.answer("Неверный ID")
        return

    chat_id = callback.message.chat.id
    db = _get_db()
    try:
        courier = _get_courier_by_chat(chat_id, db)
        if not courier:
            await callback.answer("Ты не зарегистрирован")
            return

        route = db.query(Route).filter(Route.id == route_id).first()
        if not route:
            await callback.answer("Маршрут не найден")
            return
        if route.courier_id != courier.id:
            await callback.answer("Этот маршрут не твой")
            return

        route.courier_id = None
        route.status = RouteStatus.pending
        db.commit()

        await callback.answer("❌ Маршрут отклонён")
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ Ты отклонил маршрут.",
            reply_markup=None,
        )
    finally:
        db.close()


# ---------- Main menu ----------


def _main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MENU_ORDERS)],
            [KeyboardButton(text=MENU_TAKE_ROUTE)],
            [KeyboardButton(text=MENU_MY_ROUTES)],
            [KeyboardButton(text=MENU_COMPLETE_ORDER)],
            [KeyboardButton(text=MENU_SEED_ROUTE)],
        ],
        resize_keyboard=True,
    )


def _phone_request_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ---------- Registration ----------


def _do_register(chat_id: int, phone: str, db: Session) -> Optional[str]:
    """Register a chat_id for a courier. Returns courier name or None on failure."""
    link = db.query(TelegramCourier).filter(
        TelegramCourier.telegram_chat_id == chat_id
    ).first()
    if link:
        courier = db.query(Courier).filter(Courier.id == link.courier_id).first()
        if courier:
            return courier.name
        db.delete(link)
        db.flush()

    courier = (
        db.query(Courier)
        .filter(Courier.phone == phone, Courier.is_active == True)
        .first()
    )
    if not courier:
        return None

    link = TelegramCourier(
        courier_id=courier.id,
        telegram_chat_id=chat_id,
        phone=phone,
    )
    db.add(link)
    db.commit()
    return courier.name


def _is_registered(chat_id: int, db: Session) -> bool:
    return db.query(TelegramCourier).filter(
        TelegramCourier.telegram_chat_id == chat_id
    ).first() is not None


async def _registration_success(target: Message, courier_name: str) -> None:
    await target.answer(
        f"✅ Регистрация прошла успешно, {courier_name}!",
        reply_markup=_main_menu_kb(),
    )


async def _registration_failed(target: Message) -> None:
    await target.answer(
        "❌ Курьер с таким номером не найден.\n"
        "Проверь номер или обратись к администратору.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def _try_register(message: Message, chat_id: int, phone_or_text: str) -> None:
    db = _get_db()
    try:
        if _is_registered(chat_id, db):
            return
        name = _do_register(chat_id, phone_or_text, db)
        if name:
            await _registration_success(message, name)
        else:
            await _registration_failed(message)
    finally:
        db.close()


# ---------- Command handlers ----------


async def cmd_start(message: Message) -> None:
    chat_id = message.chat.id
    db = _get_db()
    try:
        courier = _get_courier_by_chat(chat_id, db)
        if courier:
            await message.answer(
                f"✅ Привет, {courier.name}!",
                reply_markup=_main_menu_kb(),
            )
        else:
            await message.answer(
                "👋 Добро пожаловать в Mivita Delivery!\n\n"
                "Нажми кнопку ниже, чтобы поделиться номером телефона:",
                reply_markup=_phone_request_kb(),
            )
    finally:
        db.close()


async def cmd_menu(message: Message) -> None:
    chat_id = message.chat.id
    db = _get_db()
    try:
        if not _get_courier_by_chat(chat_id, db):
            await message.answer("❌ Сначала зарегистрируйся через /start")
            return
        await message.answer("📌 Главное меню:", reply_markup=_main_menu_kb())
    finally:
        db.close()


# ---------- Text handlers ----------


async def handle_main_menu_text(message: Message) -> None:
    text = (message.text or "").strip()
    handlers = {
        MENU_ORDERS: _show_orders_today,
        MENU_TAKE_ROUTE: _show_available_routes,
        MENU_MY_ROUTES: _show_my_routes,
        MENU_COMPLETE_ORDER: _send_route_for_completion,
        MENU_SEED_ROUTE: _handle_seed_route,
    }
    handler = handlers.get(text)
    if handler:
        await handler(message)


async def handle_contact(message: Message) -> None:
    contact = message.contact
    if not contact or not contact.phone_number:
        return
    phone = contact.phone_number.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    await _try_register(message, message.chat.id, phone)


async def handle_phone(message: Message) -> None:
    await _try_register(message, message.chat.id, (message.text or "").strip())


# ---------- 1. Orders for today ----------


async def _show_orders_today(msg: Message) -> None:
    chat_id = msg.chat.id
    db = _get_db()
    try:
        courier = _get_courier_by_chat(chat_id, db)
        if not courier:
            await msg.answer("Ты не зарегистрирован")
            return

        today = date.today()
        orders = (
            db.query(Order)
            .filter(
                Order.order_date == today,
                Order.status != OrderStatus.cancelled,
            )
            .order_by(Order.id)
            .all()
        )

        if not orders:
            await msg.answer(f"📭 На сегодня ({today.isoformat()}) заказов нет.")
            return

        await msg.answer(
            f"📋 <b>Заказы на {today.isoformat()}</b>\n"
            f"Всего: {len(orders)}\n"
        )

        for o in orders:
            client = db.query(Client).filter(Client.id == o.client_id).first()
            addr = _get_order_field(o, "address", "—")
            time_slot = _get_time_slot(o)
            comment = _get_comment(o)
            meals_list = _get_meals_str(o)
            status_emoji = {
                OrderStatus.draft: "📝",
                OrderStatus.confirmed: "✅",
                OrderStatus.in_kitchen: "👨‍🍳",
                OrderStatus.delivered: "🎯",
            }.get(o.status, "❓")
            text = (
                f"{status_emoji} <b>Заказ #{o.id}</b>\n"
                f"👤 {client.name if client else '—'} | {o.tariff_code}\n"
                f"📍 {addr}\n"
                f"🍽 {meals_list or '—'}\n"
                f"💰 {o.price_total}₽ | 🕐 {time_slot}"
            )
            if comment:
                text += f"\n💬 {comment}"
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="👀 Подробнее",
                            callback_data=f"order_detail:{o.id}",
                        )
                    ]
                ]
            )
            await msg.answer(text, reply_markup=kb)
    finally:
        db.close()


# ---------- 2. Take a route ----------


async def _show_available_routes(msg: Message) -> None:
    chat_id = msg.chat.id
    db = _get_db()
    try:
        courier = _get_courier_by_chat(chat_id, db)
        if not courier:
            await msg.answer("Ты не зарегистрирован")
            return

        today = date.today()
        routes = (
            db.query(Route)
            .filter(
                Route.date == today,
                Route.status == RouteStatus.pending,
            )
            .order_by(Route.id)
            .all()
        )

        if not routes:
            await msg.answer("📭 Свободных маршрутов на сегодня нет.")
            return

        await msg.answer(f"🚗 <b>Доступные маршруты на {today.isoformat()}</b>")

        for r in routes:
            points = db.query(RoutePoint).filter(RoutePoint.route_id == r.id).count()
            text = (
                f"🆕 Маршрут #{r.id}\n"
                f"📍 Остановок: {points}\n"
                f"📏 {_fmt_distance(r.total_distance)} | "
                f"⏱ {_fmt_duration(r.total_duration)}"
            )
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📋 Взять маршрут",
                            callback_data=f"take_route:{r.id}",
                        )
                    ]
                ]
            )
            await msg.answer(text, reply_markup=kb)
    finally:
        db.close()


async def cb_take_route(callback: CallbackQuery) -> None:
    data = callback.data or ""
    if not data.startswith("take_route:"):
        return
    parts = data.split(":")
    if len(parts) != 2:
        await callback.answer("Неверная команда")
        return
    try:
        route_id = int(parts[1])
    except ValueError:
        await callback.answer("Неверный ID маршрута")
        return

    chat_id = callback.message.chat.id
    db = _get_db()
    try:
        courier = _get_courier_by_chat(chat_id, db)
        if not courier:
            await callback.answer("Ты не зарегистрирован")
            return

        route = db.query(Route).filter(Route.id == route_id).first()
        if not route:
            await callback.answer("Маршрут не найден")
            return
        if route.status != RouteStatus.pending:
            await callback.answer("Этот маршрут уже занят")
            return
        if route.courier_id is not None:
            await callback.answer("У маршрута уже есть курьер")
            return

        route.courier_id = courier.id
        route.status = RouteStatus.assigned
        db.commit()

        await callback.answer(f"Маршрут #{route_id} назначен тебе!")
        await callback.message.edit_text(
            callback.message.text + f"\n\n✅ Ты взял маршрут #{route_id}!",
            reply_markup=None,
        )

        points = (
            db.query(RoutePoint)
            .filter(RoutePoint.route_id == route.id)
            .order_by(RoutePoint.sort_order)
            .all()
        )
        await _send_route_map(callback.message, route, points, db)
    finally:
        db.close()


# ---------- 3. My routes ----------


STATUS_EMOJI = {
    RouteStatus.assigned: "📋",
    RouteStatus.in_progress: "🚗",
    RouteStatus.completed: "✅",
    RouteStatus.pending: "⏳",
    RouteStatus.cancelled: "❌",
}


async def _show_my_routes(msg: Message) -> None:
    chat_id = msg.chat.id
    db = _get_db()
    try:
        courier = _get_courier_by_chat(chat_id, db)
        if not courier:
            return

        today = date.today()
        routes = (
            db.query(Route)
            .filter(
                Route.courier_id == courier.id,
                Route.date == today,
            )
            .order_by(Route.id)
            .all()
        )

        if not routes:
            await msg.answer("📭 На сегодня маршрутов нет.")
            return

        for route in routes:
            points = (
                db.query(RoutePoint)
                .filter(RoutePoint.route_id == route.id)
                .order_by(RoutePoint.sort_order)
                .all()
            )

            text = (
                f"{STATUS_EMOJI.get(route.status, '❓')} <b>Маршрут #{route.id}</b>\n"
                f"📍 Остановок: {len(points)}\n"
                f"📏 {_fmt_distance(route.total_distance)} | "
                f"⏱ {_fmt_duration(route.total_duration)}\n"
                f"📊 Статус: {route.status}\n"
                f"🗓 {route.date}"
            )

            if route.status == RouteStatus.assigned:
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🚗 Начать маршрут", callback_data=f"route_start:{route.id}")],
                        [InlineKeyboardButton(text="📍 Полный маршрут", callback_data=f"route_map_detailed:{route.id}")],
                    ]
                )
                await msg.answer(text, reply_markup=kb)
            elif route.status == RouteStatus.in_progress:
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="📍 Полный маршрут", callback_data=f"route_map_detailed:{route.id}")],
                        [InlineKeyboardButton(text="✅ Завершить маршрут", callback_data=f"route_complete:{route.id}")],
                    ]
                )
                await msg.answer(text, reply_markup=kb)
            elif route.status == RouteStatus.completed:
                await msg.answer(text + "\n\n✅ Маршрут завершён!")
            else:
                await msg.answer(text)
    finally:
        db.close()


# ---------- 4. Complete individual order ----------


async def _send_route_for_completion(msg: Message) -> None:
    chat_id = msg.chat.id
    db = _get_db()
    try:
        courier = _get_courier_by_chat(chat_id, db)
        if not courier:
            return

        today = date.today()
        routes = (
            db.query(Route)
            .filter(
                Route.courier_id == courier.id,
                Route.date == today,
                Route.status == RouteStatus.in_progress,
            )
            .all()
        )

        if not routes:
            await msg.answer("📭 Нет активных маршрутов. Сначала начни маршрут.")
            return

        for route in routes:
            points = (
                db.query(RoutePoint)
                .filter(RoutePoint.route_id == route.id)
                .order_by(RoutePoint.sort_order)
                .all()
            )
            await _send_route_map(msg, route, points, db)
    finally:
        db.close()


# ---------- Seed route button ----------


async def _handle_seed_route(message: Message) -> None:
    from services.seed_route import seed_test_route

    db = _get_db()
    try:
        seed_test_route(db)
        await message.answer("✅ Тестовый маршрут на сегодня создан!")
    except Exception as exc:
        logger.error("Seed route failed: %s", exc)
        await message.answer(f"❌ Ошибка: {exc}")
    finally:
        db.close()


# ---------- Order detail + question ----------


async def cb_order_detail(callback: CallbackQuery) -> None:
    data = callback.data or ""
    parts = data.split(":")
    if len(parts) != 2:
        await callback.answer("Неверная команда")
        return
    try:
        order_id = int(parts[1])
    except ValueError:
        await callback.answer("Неверный ID")
        return

    chat_id = callback.message.chat.id
    db = _get_db()
    try:
        courier = _get_courier_by_chat(chat_id, db)
        if not courier:
            await callback.answer("Ты не зарегистрирован")
            return

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            await callback.answer("Заказ не найден")
            return

        client = db.query(Client).filter(Client.id == order.client_id).first()
        addr = _get_order_field(order, "address", "—")
        time_slot = _get_time_slot(order)
        comment = _get_comment(order)
        meals_list = "\n".join(f"• {_get_meal_name(m)}" for m in (order.meals or []))

        text = (
            f"<b>Заказ #{order.id}</b>\n"
            f"👤 {client.name if client else '—'} | {order.tariff_code}\n"
            f"📍 {addr}\n"
            f"🕐 {time_slot}\n"
            f"💰 {order.price_total}₽\n"
            f"📊 Статус: {order.status.value}\n"
            f"\n<b>🍽 Рацион:</b>\n{meals_list or '—'}"
        )
        if comment:
            text += f"\n\n💬 <b>Комментарий:</b>\n{comment}"

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❓ Задать вопрос по заказу",
                        callback_data=f"order_question:{order.id}",
                    )
                ]
            ]
        )
        await callback.message.answer(text, reply_markup=kb)
        await callback.answer()
    finally:
        db.close()


async def cb_order_question(callback: CallbackQuery) -> None:
    data = callback.data or ""
    parts = data.split(":")
    if len(parts) != 2:
        await callback.answer("Неверная команда")
        return
    try:
        order_id = int(parts[1])
    except ValueError:
        await callback.answer("Неверный ID")
        return

    await callback.message.answer(
        f"📞 Функция связи по заказу #{order_id} в разработке.\n"
        f"Пока что свяжитесь с администратором вручную."
    )
    await callback.answer()


# ---------- Route actions ----------


async def cb_route_action(callback: CallbackQuery) -> None:
    data = callback.data or ""
    parts = data.split(":")
    if len(parts) != 2:
        return

    action, route_id_str = parts
    if action not in ("route_start", "route_complete", "route_show", "route_orders", "route_map_detailed"):
        return

    try:
        route_id = int(route_id_str)
    except ValueError:
        await callback.answer("Неверный ID маршрута")
        return

    chat_id = callback.message.chat.id
    db = _get_db()
    try:
        courier = _get_courier_by_chat(chat_id, db)
        if not courier:
            await callback.answer("Ты не зарегистрирован")
            return

        route = db.query(Route).filter(Route.id == route_id).first()
        if not route or route.courier_id != courier.id:
            await callback.answer("Маршрут не найден")
            return

        if action == "route_start":
            await _do_start_route(callback, route, db)
        elif action == "route_complete":
            await _do_complete_route(callback, route, db)
        elif action == "route_show":
            await _do_show_route(callback, route, db)
        elif action == "route_orders":
            await _send_route_for_completion(callback.message)
            await callback.answer()
        elif action == "route_map_detailed":
            await _do_show_detailed_route(callback, route, db)
    finally:
        db.close()


async def _do_start_route(callback: CallbackQuery, route: Route, db: Session) -> None:
    if route.status != RouteStatus.assigned:
        await callback.answer("Маршрут можно начать только в статусе «назначен»")
        return

    route.status = RouteStatus.in_progress
    db.commit()

    await callback.answer("Маршрут начат!")
    await callback.message.edit_text(
        callback.message.text + "\n\n🚗 Маршрут начат!",
        reply_markup=None,
    )

    points = (
        db.query(RoutePoint)
        .filter(RoutePoint.route_id == route.id)
        .order_by(RoutePoint.sort_order)
        .all()
    )
    await _send_route_map(callback.message, route, points, db)


async def _do_complete_route(callback: CallbackQuery, route: Route, db: Session) -> None:
    if route.status != RouteStatus.in_progress:
        await callback.answer("Маршрут можно завершить только в статусе «в пути»")
        return

    points = (
        db.query(RoutePoint)
        .filter(RoutePoint.route_id == route.id)
        .all()
    )
    for pt in points:
        order = db.query(Order).filter(Order.id == pt.order_id).first()
        if order and order.status != OrderStatus.cancelled:
            order.status = OrderStatus.delivered

    route.status = RouteStatus.completed
    db.commit()

    count = len(points)
    await callback.answer("Маршрут завершён!")
    await callback.message.edit_text(
        callback.message.text + f"\n\n✅ Маршрут завершён! Доставлено {count} заказов.",
        reply_markup=None,
    )


async def _do_show_route(callback: CallbackQuery, route: Route, db: Session) -> None:
    points = (
        db.query(RoutePoint)
        .filter(RoutePoint.route_id == route.id)
        .order_by(RoutePoint.sort_order)
        .all()
    )
    await _send_route_map(callback.message, route, points, db)
    await callback.answer()


async def _do_show_detailed_route(callback: CallbackQuery, route: Route, db: Session) -> None:
    points = (
        db.query(RoutePoint)
        .filter(RoutePoint.route_id == route.id)
        .order_by(RoutePoint.sort_order)
        .all()
    )

    header = _route_header(route, points)
    links = _route_map_links(points)
    segments = _route_segment_links(points)
    lines = [header]

    if links:
        lines.append(f"\n🗺 <a href=\"{links['google']}\">📍 Google Maps (весь маршрут)</a>")
        lines.append(f"🗺 <a href=\"{links['2gis']}\">📍 2GIS (депо → последняя)</a>")
        lines.append("")
        lines.append("🚗 <b>2GIS по отрезкам:</b>")
        for seg in segments:
            lines.append(f"{seg['num']}. <a href=\"{seg['url']}\">{seg['from'][:20]} → {seg['to'][:20]}</a>")
    else:
        lines.append("\n🗺 Нет координат для построения маршрута.")

    lines.append("\n<b>Все остановки:</b>")
    for i, pt in enumerate(points, 1):
        client = db.query(Client).filter(Client.id == pt.client_id).first()
        order = db.query(Order).filter(Order.id == pt.order_id).first()
        meals = _get_meals_str(order) if order else ""
        comment = _get_comment(order) if order else ""
        done = order and order.status == OrderStatus.delivered
        mark = "✅" if done else f"{i}."
        lines.append(
            f"{mark} <b>{client.name if client else '—'}</b>\n"
            f"   📍 {pt.address}\n"
            f"   🍽 {meals}"
        )
        if comment:
            lines.append(f"   💬 {comment}")
        lines.append("")

    await callback.message.answer("\n".join(lines))
    await _send_route_map(callback.message, route, points, db)
    await callback.answer()


# ---------- Order done button ----------


def _stop_label(pt: RoutePoint, order: Order | None, db: Session, done: bool) -> str:
    client = db.query(Client).filter(Client.id == pt.client_id).first()
    mark = "✅" if done else f"{pt.sort_order + 1}"
    address_lat = _translit(pt.address).strip()
    return f"{mark}. {address_lat[:25]}"[:60]


async def cb_order_action(callback: CallbackQuery) -> None:
    data = callback.data or ""
    if not data.startswith("order_done:"):
        return
    parts = data.split(":")
    if len(parts) != 2:
        await callback.answer("Неверная команда")
        return
    try:
        point_id = int(parts[1])
    except ValueError:
        await callback.answer("Неверный ID")
        return

    chat_id = callback.message.chat.id
    db = _get_db()
    try:
        courier = _get_courier_by_chat(chat_id, db)
        if not courier:
            await callback.answer("Ты не зарегистрирован")
            return

        point = db.query(RoutePoint).filter(RoutePoint.id == point_id).first()
        if not point:
            await callback.answer("Точка не найдена")
            return

        order = db.query(Order).filter(Order.id == point.order_id).first()
        if not order:
            await callback.answer("Заказ не найден")
            return
        if order.status == OrderStatus.delivered:
            await callback.answer("Этот заказ уже выполнен")
            return

        order.status = OrderStatus.delivered
        db.commit()

        await callback.answer("✅ Заказ отмечен как выполненный!")

        markup = callback.message.reply_markup
        if markup and markup.inline_keyboard:
            for row in markup.inline_keyboard:
                for btn in row:
                    if btn.callback_data == data:
                        btn.text = _stop_label(point, order, db, done=True)
                        break
            await callback.message.edit_reply_markup(reply_markup=markup)
    finally:
        db.close()


# ---------- Map links ----------

DEPOT_LAT, DEPOT_LON = 41.637668, 41.634028  # Haidar Abashidze 86, Batumi


def _route_segment_links(points: list[RoutePoint]) -> list[dict]:
    """Generate 2GIS A→B links for each consecutive segment."""
    valid = [p for p in points if p.latitude and p.longitude]
    if not valid:
        return []

    all_pts = [(DEPOT_LAT, DEPOT_LON, "Haidar Abashidze 86")]
    for p in valid:
        all_pts.append((p.latitude, p.longitude, _translit(p.address).strip()))

    segments = []
    for i in range(len(all_pts) - 1):
        lat1, lon1, name1 = all_pts[i]
        lat2, lon2, name2 = all_pts[i + 1]
        url = f"https://2gis.ru/geo/route/{lon1},{lat1}~{lon2},{lat2}"
        segments.append({
            "num": i + 1,
            "from": name1,
            "to": name2,
            "url": url,
        })
    return segments


def _route_map_links(points: list[RoutePoint]) -> dict[str, str]:
    valid = [p for p in points if p.latitude and p.longitude]
    if not valid:
        return {}

    gis_coords = f"{DEPOT_LON},{DEPOT_LAT}"
    gm_coords = f"{DEPOT_LAT},{DEPOT_LON}"
    for pt in valid:
        gis_coords += f"~{pt.longitude},{pt.latitude}"
        gm_coords += f"/{pt.latitude},{pt.longitude}"

    return {
        "2gis": f"https://2gis.ru/geo/route/{gis_coords}",
        "google": f"https://www.google.com/maps/dir/{gm_coords}",
    }


# ---------- Route map send ----------


def _stops_keyboard(points: list[RoutePoint], db: Session) -> InlineKeyboardMarkup:
    buttons = []
    for pt in points:
        order = db.query(Order).filter(Order.id == pt.order_id).first()
        done = order and order.status == OrderStatus.delivered
        buttons.append([
            InlineKeyboardButton(
                text=_stop_label(pt, order, db, done)[:60],
                callback_data=f"order_done:{pt.id}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _route_header(route: Route, points: list[RoutePoint]) -> str:
    return (
        f"📏 <b>Маршрут #{route.id}</b>\n"
        f"📍 Остановок: {len(points)} | {_fmt_distance(route.total_distance)} | ⏱ {_fmt_duration(route.total_duration)}"
    )


async def _send_route_map(
    msg: Message, route: Route, points: list[RoutePoint], db: Session
) -> None:
    if not points:
        return

    links = _route_map_links(points)
    segments = _route_segment_links(points)
    header = _route_header(route, points)

    if links:
        text = (
            f"{header}\n\n"
            f"🗺 <b>Карта маршрута:</b>\n"
            f"• <a href=\"{links['google']}\">📍 Google Maps (весь маршрут)</a>\n"
            f"• <a href=\"{links['2gis']}\">📍 2GIS (депо → последняя)</a>\n\n"
            f"🚗 <b>2GIS по отрезкам:</b>\n"
        )
        for seg in segments:
            text += f"{seg['num']}. <a href=\"{seg['url']}\">→ {seg['to'][:20]}</a>\n"
        text += "\n"
    else:
        text = f"{header}\n\n🗺 Нет координат для построения маршрута.\n\n"

    text += "<b>Остановки — нажми на выполненную:</b>"
    await msg.answer(text, reply_markup=_stops_keyboard(points, db))


# ---------- Helpers ----------


def _translit(text: str) -> str:
    table = {
        ord("а"): "a", ord("б"): "b", ord("в"): "v", ord("г"): "g",
        ord("д"): "d", ord("е"): "e", ord("ё"): "e", ord("ж"): "zh",
        ord("з"): "z", ord("и"): "i", ord("й"): "y", ord("к"): "k",
        ord("л"): "l", ord("м"): "m", ord("н"): "n", ord("о"): "o",
        ord("п"): "p", ord("р"): "r", ord("с"): "s", ord("т"): "t",
        ord("у"): "u", ord("ф"): "f", ord("х"): "kh", ord("ц"): "ts",
        ord("ч"): "ch", ord("ш"): "sh", ord("щ"): "shch", ord("ъ"): "",
        ord("ы"): "y", ord("ь"): "", ord("э"): "e", ord("ю"): "yu",
        ord("я"): "ya",
        ord("А"): "A", ord("Б"): "B", ord("В"): "V", ord("Г"): "G",
        ord("Д"): "D", ord("Е"): "E", ord("Ё"): "E", ord("Ж"): "Zh",
        ord("З"): "Z", ord("И"): "I", ord("Й"): "Y", ord("К"): "K",
        ord("Л"): "L", ord("М"): "M", ord("Н"): "N", ord("О"): "O",
        ord("П"): "P", ord("Р"): "R", ord("С"): "S", ord("Т"): "T",
        ord("У"): "U", ord("Ф"): "F", ord("Х"): "Kh", ord("Ц"): "Ts",
        ord("Ч"): "Ch", ord("Ш"): "Sh", ord("Щ"): "Shch", ord("Ъ"): "",
        ord("Ы"): "Y", ord("Ь"): "", ord("Э"): "E", ord("Ю"): "Yu",
        ord("Я"): "Ya",
    }
    return text.translate(table)


def _fmt_distance(meters: float | None) -> str:
    if meters is None:
        return "—"
    km = meters / 1000
    if km >= 1:
        return f"{km:.1f} км"
    return f"{int(meters)} м"


def _fmt_duration(minutes: float | None) -> str:
    if minutes is None:
        return "—"
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    if hours > 0:
        return f"{hours}ч {mins}мин"
    return f"{mins} мин"
