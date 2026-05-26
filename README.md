# Mivita backend

FastAPI + SQLAlchemy 2.0 + Postgres 16. Управление схемой — через Alembic.

## Первый запуск

```bash
# 1) Поднять Postgres
docker compose up -d

# 2) Создать виртуальное окружение и поставить зависимости
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3) Применить все миграции
alembic upgrade head

# 4) Залить демо-данные (опционально, но удобно для проверки UI)
python -m scripts.seed_demo

# 5) Запустить сервер
uvicorn main:app --reload --port 8000
```

После старта дефолтные пользователи (`admin/admin`, `kitchen/kitchen`, `partner/partner`),
тарифы и пустой 21-дневный цикл создаются автоматически (в `lifespan`).

## Миграции (Alembic)

| Сценарий | Команда |
| --- | --- |
| Применить всё к голой БД | `alembic upgrade head` |
| Сгенерировать миграцию из изменений в моделях | `alembic revision --autogenerate -m "add foo"` |
| Откатить последнюю миграцию | `alembic downgrade -1` |
| Посмотреть текущую ревизию | `alembic current` |
| Посмотреть историю | `alembic history` |

URL базы Alembic берёт из `config.py` (см. `alembic/env.py`). Если меняешь `DATABASE_URL`
через `.env` — Alembic подхватит автоматически.

## Демо-данные

`scripts/seed_demo.py` — идемпотентный сид: 6 ингредиентов, 5 блюд (по одному на слот) с
граммовками по 4 тарифам, 3 клиента с разными расписаниями, активные подписки на месяц,
3 первых дня меню заполнены, заказы на завтра сразу зафиксированы (`locked_at` выставлен).

Запуск: `python -m scripts.seed_demo`. Повторный запуск НЕ дублирует — все вставки идут
через `get_or_create_*`.

## Снести и пересоздать БД (dev only)

Если в процессе разработки сильно разошлась схема и не хочется писать миграции по очереди:

```bash
docker compose down -v        # удаляет volume pgdata
docker compose up -d
alembic upgrade head
python -m scripts.seed_demo
```

## Структура

```
backend/
├── alembic/                 миграции
│   ├── env.py
│   └── versions/
├── models/                  SQLAlchemy 2.0 модели (Mapped[...])
├── schemas/                 Pydantic v2 схемы запроса/ответа
├── routers/                 FastAPI роутеры по доменам
│   ├── auth.py              JWT login/refresh/me + сид юзеров
│   ├── clients.py
│   ├── subscriptions.py     включая day_overrides
│   ├── orders.py            CRUD + бизнес-процесс (generate/confirm/unlock/supplier-list)
│   ├── kitchen.py           kanban-доска + агрегированный /task для повара
│   ├── menu.py              21-дневный цикл
│   ├── dishes.py
│   ├── ingredients.py
│   ├── tariffs.py
│   ├── finance.py           dashboard + entries
│   └── meta.py              today / allergens / tariffs
├── services/                бизнес-логика (auth_service)
├── dependencies/            FastAPI deps (security)
├── scripts/
│   └── seed_demo.py
├── config.py                pydantic-settings, читает .env
├── database.py              engine / SessionLocal / Base
└── main.py                  FastAPI app + lifespan
```

## Переменные окружения

См. `config.py`. Любую можно переопределить через `.env`:

```
DATABASE_URL=postgresql://mivita:mivita_pass@localhost:5432/mivita_db
SECRET_KEY=change-me-in-prod
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
KITCHEN_USERNAME=kitchen
KITCHEN_PASSWORD=kitchen
PARTNER_USERNAME=partner
PARTNER_PASSWORD=partner
CORS_ORIGINS=["http://localhost:5173"]
```

## Главный бизнес-процесс (отсечка 22:00)

Реализован в `routers/orders.py`:

| Эндпоинт | Что делает |
| --- | --- |
| `POST /api/orders/generate?date=YYYY-MM-DD` | Материализует draft-заказы из активных подписок на дату; применяет `day_overrides` (skipped/tariff/address/timeSlot). Идемпотентный — дубли не создаёт. |
| `POST /api/orders/confirm-day?date=…` | Ставит `locked_at=now()` и переводит draft → confirmed. После этого редактирование заказа возвращает 409. |
| `POST /api/orders/unlock-day?date=…` | Снимает блокировку (для замен до 22:00). |
| `GET /api/orders/supplier-list?date=…` | Агрегирует ингредиенты по всем некэнсельным заказам дня. |

Фронт зашит на эти кнопки в `mivita/src/views/admin/OrdersView.vue`.
