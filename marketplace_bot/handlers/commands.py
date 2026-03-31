"""
Command handlers for the bot.
"""

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from models import User, get_db
from utils.logger import logger

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    """Handle /start command."""
    telegram_user = message.from_user

    async for session in get_db():
        # Check if user exists
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            # Create new user
            user = User(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
            )
            session.add(user)
            await session.commit()
            logger.info(f"New user registered: {telegram_user.id}")

    welcome_text = (
        f"👋 Привет, {telegram_user.first_name}!\n\n"
        f"Я бот для мониторинга товаров на маркетплейсах.\n\n"
        f"🔍 <b>Доступные команды:</b>\n"
        f"/add - Добавить новую подписку\n"
        f"/list - Список ваших подписок\n"
        f"/delete - Удалить подписку\n"
        f"/help - Помощь\n\n"
        f"Начните с команды /add чтобы создать первую подписку!"
    )

    await message.answer(welcome_text, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    """Handle /help command."""
    help_text = (
        "📖 <b>Справка по использованию бота</b>\n\n"
        "<b>Как работает бот:</b>\n"
        "1. Вы создаете подписку с ключевыми словами и ценовым диапазоном\n"
        "2. Бот каждые 5 минут проверяет новые товары\n"
        "3. При появлении новых товаров вы получаете уведомление\n\n"
        "<b>Команды:</b>\n"
        "/start - Начать работу с ботом\n"
        "/add - Добавить новую подписку\n"
        "/list - Показать все подписки\n"
        "/delete - Удалить подписку\n"
        "/help - Показать эту справку\n\n"
        "<b>Поддерживаемые площадки:</b>\n"
        "• Avito (Россия)\n"
        "• Grailed (США, одежда)\n"
        "• Mercari (США/Япония)\n\n"
        "<b>Советы:</b>\n"
        "• Используйте конкретные ключевые слова\n"
        "• Указывайте реалистичный ценовой диапазон\n"
        "• Не создавайте слишком много подписок"
    )

    await message.answer(help_text, parse_mode="HTML")


@router.message(Command("list"))
async def cmd_list(message: types.Message) -> None:
    """Handle /list command."""
    telegram_id = message.from_user.id

    async for session in get_db():
        # Get user with subscriptions
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await message.answer(
                "❌ Вы не зарегистрированы. Используйте /start"
            )
            return

        if not user.subscriptions:
            await message.answer(
                "📭 У вас пока нет подписок.\n\n"
                "Используйте /add чтобы создать подписку."
            )
            return

        # Build subscriptions list
        lines = ["📋 <b>Ваши подписки:</b>\n"]

        for i, sub in enumerate(user.subscriptions, 1):
            status = "✅" if sub.is_active else "⏸"
            lines.append(
                f"{i}. {status} <b>{sub.platform.value.title()}</b>\n"
                f"   🔍 {sub.query}\n"
                f"   💰 {sub.price_range_str}\n"
            )

        lines.append("\nИспользуйте /delete чтобы удалить подписку")

        await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("delete"))
async def cmd_delete(message: types.Message) -> None:
    """Handle /delete command."""
    telegram_id = message.from_user.id

    async for session in get_db():
        # Get user with subscriptions
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        if not user or not user.subscriptions:
            await message.answer(
                "📭 У вас нет подписок для удаления."
            )
            return

        # Build keyboard with subscriptions
        keyboard_buttons = []
        for sub in user.subscriptions:
            button_text = f"{sub.platform.value.title()}: {sub.query[:30]}"
            callback_data = f"delete_sub:{sub.id}"
            keyboard_buttons.append(
                [InlineKeyboardButton(text=button_text, callback_data=callback_data)]
            )

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await message.answer(
            "🗑 Выберите подписку для удаления:",
            reply_markup=keyboard,
        )
