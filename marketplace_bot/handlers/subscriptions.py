"""
Subscription management handlers.
"""

from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from models import Platform, Subscription, User, get_db
from utils.logger import logger

router = Router()


class AddSubscriptionStates(StatesGroup):
    """States for adding a new subscription."""

    waiting_for_platform = State()
    waiting_for_query = State()
    waiting_for_min_price = State()
    waiting_for_max_price = State()
    waiting_for_confirmation = State()


@router.message(Command("add"))
async def cmd_add(message: types.Message, state: FSMContext) -> None:
    """Start adding a new subscription."""
    # Create platform selection keyboard
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🇷🇺 Avito (Россия)", callback_data="platform:avito"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🇺🇸 Grailed (США)", callback_data="platform:grailed"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🇯🇵 Mercari (Япония/США)", callback_data="platform:mercari"
                )
            ],
        ]
    )

    await message.answer(
        "🛒 <b>Добавление новой подписки</b>\n\n"
        "Выберите площадку для мониторинга:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await state.set_state(AddSubscriptionStates.waiting_for_platform)


@router.callback_query(F.data.startswith("platform:"))
async def process_platform_selection(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Process platform selection."""
    platform_str = callback.data.split(":")[1]
    platform = Platform(platform_str)

    await state.update_data(platform=platform)

    await callback.message.edit_text(
        f"✅ Выбрана площадка: <b>{platform.value.title()}</b>\n\n"
        f"📝 Введите ключевые слова для поиска:\n"
        f"<i>Например: iPhone 14 Pro 256GB</i>",
        parse_mode="HTML",
    )
    await state.set_state(AddSubscriptionStates.waiting_for_query)
    await callback.answer()


@router.message(AddSubscriptionStates.waiting_for_query)
async def process_query(message: types.Message, state: FSMContext) -> None:
    """Process search query input."""
    query = message.text.strip()

    if len(query) < 2:
        await message.answer(
            "❌ Запрос слишком короткий. Введите минимум 2 символа."
        )
        return

    if len(query) > 255:
        await message.answer(
            "❌ Запрос слишком длинный. Максимум 255 символов."
        )
        return

    await state.update_data(query=query)

    # Create skip keyboard
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_min_price")]
        ]
    )

    await message.answer(
        f"✅ Ключевые слова: <code>{query}</code>\n\n"
        f"💰 Введите <b>минимальную</b> цену (в валюте площадки):\n"
        f"<i>Или нажмите "Пропустить"</i>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await state.set_state(AddSubscriptionStates.waiting_for_min_price)


@router.callback_query(F.data == "skip_min_price")
async def skip_min_price(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Skip minimum price input."""
    await state.update_data(min_price=None)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_max_price")]
        ]
    )

    await callback.message.edit_text(
        "✅ Минимальная цена: не указана\n\n"
        "💰 Введите <b>максимальную</b> цену:\n"
        "<i>Или нажмите "Пропустить"</i>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await state.set_state(AddSubscriptionStates.waiting_for_max_price)
    await callback.answer()


@router.message(AddSubscriptionStates.waiting_for_min_price)
async def process_min_price(message: types.Message, state: FSMContext) -> None:
    """Process minimum price input."""
    try:
        min_price = float(message.text.strip())
        if min_price < 0:
            raise ValueError("Price cannot be negative")
    except ValueError:
        await message.answer(
            "❌ Некорректная цена. Введите число (например: 10000)"
        )
        return

    await state.update_data(min_price=min_price)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_max_price")]
        ]
    )

    await message.answer(
        f"✅ Минимальная цена: <b>{min_price:,.0f}</b>\n\n"
        f"💰 Введите <b>максимальную</b> цену:\n"
        f"<i>Или нажмите "Пропустить"</i>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await state.set_state(AddSubscriptionStates.waiting_for_max_price)


@router.callback_query(F.data == "skip_max_price")
async def skip_max_price(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Skip maximum price input and show confirmation."""
    await state.update_data(max_price=None)
    await show_confirmation(callback.message, state)
    await callback.answer()


@router.message(AddSubscriptionStates.waiting_for_max_price)
async def process_max_price(message: types.Message, state: FSMContext) -> None:
    """Process maximum price input."""
    try:
        max_price = float(message.text.strip())
        if max_price < 0:
            raise ValueError("Price cannot be negative")
    except ValueError:
        await message.answer(
            "❌ Некорректная цена. Введите число (например: 50000)"
        )
        return

    # Check if max_price is greater than min_price
    data = await state.get_data()
    min_price = data.get("min_price")
    if min_price is not None and max_price <= min_price:
        await message.answer(
            f"❌ Максимальная цена должна быть больше минимальной ({min_price:,.0f})"
        )
        return

    await state.update_data(max_price=max_price)
    await show_confirmation(message, state)


async def show_confirmation(message: types.Message, state: FSMContext) -> None:
    """Show subscription confirmation."""
    data = await state.get_data()

    platform = data["platform"].value.title()
    query = data["query"]
    min_price = data.get("min_price")
    max_price = data.get("max_price")

    price_range = "Любая цена"
    if min_price and max_price:
        price_range = f"{min_price:,.0f} - {max_price:,.0f}"
    elif min_price:
        price_range = f"от {min_price:,.0f}"
    elif max_price:
        price_range = f"до {max_price:,.0f}"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить", callback_data="confirm_subscription"
                ),
                InlineKeyboardButton(
                    text="❌ Отменить", callback_data="cancel_subscription"
                ),
            ]
        ]
    )

    await message.answer(
        f"📋 <b>Подтвердите подписку:</b>\n\n"
        f"🛒 Площадка: <b>{platform}</b>\n"
        f"🔍 Запрос: <code>{query}</code>\n"
        f"💰 Ценовой диапазон: <b>{price_range}</b>\n\n"
        f"Бот будет проверять новые товары каждые 5 минут.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await state.set_state(AddSubscriptionStates.waiting_for_confirmation)


@router.callback_query(F.data == "confirm_subscription")
async def confirm_subscription(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Save subscription to database."""
    data = await state.get_data()
    telegram_id = callback.from_user.id

    async for session in get_db():
        # Get or create user
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await callback.message.edit_text(
                "❌ Ошибка: пользователь не найден. Используйте /start"
            )
            await state.clear()
            await callback.answer()
            return

        # Create subscription
        subscription = Subscription(
            user_id=user.id,
            platform=data["platform"],
            query=data["query"],
            min_price=data.get("min_price"),
            max_price=data.get("max_price"),
            is_active=True,
        )
        session.add(subscription)
        await session.commit()

        logger.info(f"New subscription created: {subscription.id} for user {user.id}")

        await callback.message.edit_text(
            "✅ <b>Подписка успешно создана!</b>\n\n"
            f"🛒 Площадка: {subscription.platform.value.title()}\n"
            f"🔍 Запрос: <code>{subscription.query}</code>\n"
            f"💰 Цена: {subscription.price_range_str}\n\n"
            f"Вы получите уведомление при появлении новых товаров.",
            parse_mode="HTML",
        )

    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "cancel_subscription")
async def cancel_subscription(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Cancel subscription creation."""
    await callback.message.edit_text(
        "❌ Создание подписки отменено.\n\n"
        "Используйте /add чтобы попробовать снова."
    )
    await state.clear()
    await callback.answer()


@router.callback_query(F.data.startswith("delete_sub:"))
async def delete_subscription(callback: types.CallbackQuery) -> None:
    """Delete subscription."""
    subscription_id = int(callback.data.split(":")[1])
    telegram_id = callback.from_user.id

    async for session in get_db():
        # Get user
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

        # Get subscription
        result = await session.execute(
            select(Subscription).where(
                Subscription.id == subscription_id,
                Subscription.user_id == user.id,
            )
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            await callback.answer("❌ Подписка не найдена", show_alert=True)
            return

        # Delete subscription
        platform = subscription.platform.value.title()
        query = subscription.query

        await session.delete(subscription)
        await session.commit()

        logger.info(f"Subscription deleted: {subscription_id}")

        await callback.message.edit_text(
            f"✅ <b>Подписка удалена</b>\n\n"
            f"🛒 {platform}\n"
            f"🔍 {query}",
            parse_mode="HTML",
        )

    await callback.answer()
