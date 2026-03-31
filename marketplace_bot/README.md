# Marketplace Monitor Bot

Production-ready Telegram бот для мониторинга товаров на маркетплейсах (Avito, Grailed, Mercari).

## 🚀 Возможности

- 📊 **Мониторинг нескольких площадок**: Avito, Grailed, Mercari
- 🔍 **Гибкий поиск**: Ключевые слова + ценовой диапазон
- 🔔 **Мгновенные уведомления**: О новых товарах в Telegram
- ⏰ **Автоматическая проверка**: Каждые 5 минут
- 🛡️ **Защита от блокировок**: Playwright + stealth mode, ротация User-Agent
- 📦 **Асинхронная архитектура**: Не блокирует Event Loop
- 💾 **База данных**: SQLite (для старта) / PostgreSQL (для production)

## 📁 Структура проекта

```
marketplace_bot/
├── bot.py                 # Главный файл (точка входа)
├── config.py              # Конфигурация (Pydantic Settings)
├── requirements.txt       # Зависимости
├── .env.example          # Пример конфигурации окружения
├── models/               # SQLAlchemy модели
│   ├── __init__.py
│   ├── database.py       # Инициализация БД
│   └── models.py         # Модели User, Subscription, Item
├── scrapers/             # Парсеры
│   ├── __init__.py
│   ├── base.py           # Абстрактный класс BaseScraper
│   ├── avito.py          # Avito (Playwright + stealth)
│   ├── grailed.py        # Grailed (aiohttp)
│   ├── mercari.py        # Mercari (aiohttp)
│   └── manager.py        # Менеджер парсеров + шедулер
├── handlers/             # Telegram хендлеры
│   ├── __init__.py
│   ├── commands.py       # Команды (/start, /help, /list, /delete)
│   └── subscriptions.py  # Управление подписками (/add)
└── utils/                # Утилиты
    ├── __init__.py
    ├── logger.py         # Loguru конфигурация
    └── retry.py          # Tenacity retry декоратор
```

## 🛠️ Установка

### 1. Клонирование и настройка окружения

```bash
cd marketplace_bot
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows
```

### 2. Установка зависимостей

```bash
pip install -r requirements.txt

# Установка Playwright browsers
playwright install chromium
```

### 3. Настройка конфигурации

```bash
cp .env.example .env
# Отредактируйте .env файл
```

Обязательные переменные:
- `BOT_TOKEN` - Токен от @BotFather

Опциональные:
- `DATABASE_URL` - URL базы данных (по умолчанию SQLite)
- `HTTP_PROXY` / `HTTPS_PROXY` - Прокси для запросов
- `PARSING_INTERVAL_MINUTES` - Интервал проверки (по умолчанию 5)

### 4. Запуск

```bash
python bot.py
```

## 📝 Использование

### Команды бота

- `/start` - Начать работу с ботом
- `/add` - Добавить новую подписку
- `/list` - Показать все подписки
- `/delete` - Удалить подписку
- `/help` - Помощь

### Пример создания подписки

1. Отправьте `/add`
2. Выберите площадку (Avito / Grailed / Mercari)
3. Введите ключевые слова (например: "iPhone 14 Pro")
4. Укажите минимальную цену (или пропустите)
5. Укажите максимальную цену (или пропустите)
6. Подтвердите создание подписки

## 🔧 Production-настройка

### 1. Переход на PostgreSQL

```bash
# Установите PostgreSQL и создайте базу
pip install asyncpg

# Обновите DATABASE_URL в .env
DATABASE_URL=postgresql+asyncpg://user:password@localhost/dbname
```

### 2. Использование прокси

Для обхода блокировок рекомендуется использовать резидентные прокси:

```env
HTTP_PROXY=http://user:pass@host:port
HTTPS_PROXY=http://user:pass@host:port
```

### 3. Запуск на VPS

```bash
# Используйте systemd или supervisor для автозапуска
# Пример systemd service:
sudo systemctl enable marketplace-bot
sudo systemctl start marketplace-bot
```

### 4. Docker (опционально)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN playwright install chromium

COPY . .
CMD ["python", "bot.py"]
```

## ⚠️ Важные замечания

### Защита от блокировок

- **Avito**: Использует Playwright с stealth mode, но может требовать резидентных прокси
- **Grailed**: API-ориентирован, менее подвержен блокировкам
- **Mercari**: Имеет сильную защиту, может требовать дополнительной настройки

### Рекомендации

1. **Не создавайте слишком много подписок** - это увеличивает нагрузку
2. **Используйте конкретные ключевые слова** - снижает количество ложных срабатываний
3. **Указывайте реалистичные ценовые диапазоны** - фильтрует нерелевантные товары
4. **Используйте прокси** - для стабильной работы 24/7

## 🐛 Отладка

Логи сохраняются в директории `logs/`:
- `bot.log` - Все логи
- `error.log` - Только ошибки

Уровень логирования настраивается через `LOG_LEVEL` в `.env`.

## 📄 Лицензия

MIT License
