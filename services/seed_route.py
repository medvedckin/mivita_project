from datetime import date

from sqlalchemy.orm import Session

from models import Client, Order, Route, RoutePoint
from models.order import OrderStatus
from models.route import RouteStatus

BATUMI_DATA = [
    ("Георгий Махарадзе", "+995599111111", "пр. Руставели, д. 1, Батуми", 41.6462, 41.6365,
     "Харчо, Шашлык из курицы, Сациви", "Этаж 3, домофон 5"),
    ("Натия Беридзе", "+995599222222", "ул. Чавчавадзе, д. 3, Батуми", 41.6501, 41.6342,
     "Лобио, Оджахури, Компот", "Оставить у соседей"),
    ("Давид Кварацхелия", "+995599333333", "ул. Пушкина, д. 5, Батуми", 41.6483, 41.6390,
     "Чахохбили, Греческий салат, Печеный картофель", ""),
    ("Тамара Джапаридзе", "+995599444444", "ул. Шерифа Химшиашвили, д. 10, Батуми", 41.6331, 41.6234,
     "Борщ, Пхали ассорти, Чай с мятой", "Корпус 2, кв 7"),
    ("Лаша Бежанидзе", "+995599555555", "ул. Меликишвили, д. 4, Батуми", 41.6522, 41.6388,
     "Купаты, Овощи на гриле, Цхалтубо", "Домофон 12"),
    ("Нино Двалишвили", "+995599666666", "ул. Гогебашвили, д. 7, Батуми", 41.6560, 41.6403,
     "Суп из чечевицы, Чкмерули, Лаваш", "Позвонить заранее"),
    ("Заза Циклаури", "+995599777777", "ул. Тамар Меке, д. 15, Батуми", 41.6394, 41.6291,
     "Аджапсандал, Люля-кебаб, Морс", ""),
    ("Эка Чиковани", "+995599888888", "пр. Руставели, д. 100, Батуми", 41.6440, 41.6287,
     "Долма, Хачапури по-аджарски, Тархун", "Вход со двора, 5 этаж"),
]


def seed_test_route(db: Session) -> None:
    today = date.today()
    existing = db.query(Route).filter(Route.date == today).first()
    if existing:
        return

    route = Route(
        date=today, status=RouteStatus.pending,
        total_distance=8500.0, total_duration=90.0,
    )
    db.add(route)
    db.flush()

    for i, (name, phone, addr, lat, lon, meals, comment) in enumerate(BATUMI_DATA):
        client = Client(
            name=name, phone=phone, messenger="telegram",
            payment_method="transfer", tariff_code="premium",
        )
        db.add(client)
        db.flush()

        meals_list = [{"mealId": m.strip(), "slot": "lunch"} for m in meals.split(",")]
        order = Order(
            client_id=client.id, order_date=today,
            status=OrderStatus.confirmed, tariff_code="premium",
            meals=meals_list,
            delivery_slot={"weekday": today.strftime("%A"), "address": addr, "timeSlot": "12:00-15:00"},
            price_total=2500.0, is_priority=False,
            payment_method="transfer", comment=comment,
        )
        db.add(order)
        db.flush()

        pt = RoutePoint(
            route_id=route.id, order_id=order.id,
            client_id=client.id, address=addr,
            latitude=lat, longitude=lon, sort_order=i,
        )
        db.add(pt)

    db.commit()
