import uuid
import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession
from config import BOT_TOKEN, ADMIN_ID, YOO_MONEY_WALLET, YOO_MONEY_CARDS, URALSIB_CARD
import config as cfg  # для безопасного доступа к PROXY_URL, если она есть
import database
from database import create_order, update_order_status, get_order_by_id
from yoomoney_checker import check_payments
from yoomoney_api import create_yoomoney_invoice

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Прокси: берём из config, если есть, иначе None
PROXY_URL = getattr(cfg, "PROXY_URL", None)
session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else None
bot = Bot(token=BOT_TOKEN, session=session)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()


class ExchangeStates(StatesGroup):
    waiting_amount = State()
    waiting_currency = State()
    waiting_payment_details = State()
    waiting_payment_method = State()
    waiting_screenshot = State()

currency_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💎 USDT BEP20", callback_data="currency_USDT_BEP20")],
    [InlineKeyboardButton(text="🇲🇩 Рубли ПМР", callback_data="currency_RUB_PMR")]
])

payment_method_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💳 ЮMoney (автоматическая проверка)", callback_data="pay_yoomoney")],
    [InlineKeyboardButton(text="🏦 Уралсиб (ручная проверка)", callback_data="pay_uralsib")]
])

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("👋 Добро пожаловать в обменник!\nИспользуйте /exchange для начала обмена.")

@router.message(Command("exchange"))
async def cmd_exchange(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("💰 Введите сумму в рублях РФ (минимум 500):")
    await state.set_state(ExchangeStates.waiting_amount)

@router.message(StateFilter(ExchangeStates.waiting_amount))
async def process_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число.")
        return
    if amount < 500:
        await message.answer("❌ Минимальная сумма обмена 500 рублей.")
        return
    await state.update_data(amount=amount)
    await message.answer("Выберите валюту получения:", reply_markup=currency_keyboard)
    await state.set_state(ExchangeStates.waiting_currency)

@router.callback_query(StateFilter(ExchangeStates.waiting_currency), F.data.startswith("currency_"))
async def process_currency(callback: types.CallbackQuery, state: FSMContext):
    currency = callback.data.split("_", 1)[1]
    await state.update_data(currency=currency)
    await callback.message.edit_reply_markup()
    prompt = "Введите адрес USDT BEP20:" if currency == "USDT_BEP20" else "Введите реквизиты для рублей ПМР:"
    await callback.message.answer(prompt)
    await state.set_state(ExchangeStates.waiting_payment_details)
    await callback.answer()

@router.message(StateFilter(ExchangeStates.waiting_payment_details))
async def process_details(message: types.Message, state: FSMContext):
    details = message.text.strip()
    if not details:
        await message.answer("❌ Реквизиты не могут быть пустыми.")
        return
    await state.update_data(payment_details=details)
    await message.answer("Выберите способ оплаты:", reply_markup=payment_method_keyboard)
    await state.set_state(ExchangeStates.waiting_payment_method)

@router.callback_query(StateFilter(ExchangeStates.waiting_payment_method), F.data.startswith("pay_"))
async def process_payment_method(callback: types.CallbackQuery, state: FSMContext):
    method = callback.data.split("_", 1)[1]
    data = await state.get_data()
    user_id = callback.from_user.id
    username = callback.from_user.username or "NoUsername"

    if method == "yoomoney":
        invoice_id = str(uuid.uuid4())
        label = f"{user_id}:{invoice_id}"
        payment_url = await create_yoomoney_invoice(data["amount"], label)
        if not payment_url:
            await callback.message.answer("❌ Не удалось создать счёт. Попробуйте позже или свяжитесь с администратором.")
            await callback.answer()
            return

        order_id = await create_order(
            user_id=user_id,
            username=username,
            amount=data["amount"],
            currency=data["currency"],
            payment_details=data["payment_details"],
            payment_method=method,
            invoice_id=invoice_id
        )

        cards_list = [c.strip() for c in YOO_MONEY_CARDS.split(",") if c.strip()] if YOO_MONEY_CARDS else []
        cards_text = "\n".join([f"• {c}" for c in cards_list]) if cards_list else "список пуст"
        text = (
            f"💳 <b>Счёт на оплату</b>\n\n"
            f"Сумма: <b>{data['amount']} ₽</b>\n"
            f"Кошелёк получателя: <code>{YOO_MONEY_WALLET}</code>\n"
            f"Доступные карты ЮMoney:\n{cards_text}\n\n"
            f"Для оплаты нажмите кнопку ниже, затем вернитесь и нажмите «✅ Я оплатил»."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💸 Оплатить", url=payment_url)],
            [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"yoomoney_paid_{order_id}")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await state.clear()
    else:
        # Уралсиб
        order_id = await create_order(
            user_id=user_id,
            username=username,
            amount=data["amount"],
            currency=data["currency"],
            payment_details=data["payment_details"],
            payment_method=method
        )
        text = (
            f"🏦 Оплата через Уралсиб\n\n"
            f"Сумма: <b>{data['amount']} ₽</b>\n"
            f"Номер карты: <code>{URALSIB_CARD}</code>\n\n"
            f"⚠️ <b>Ручная проверка:</b> потребуется скриншот."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я оплатил, отправить скриншот", callback_data=f"upload_{order_id}")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await state.clear()
    await callback.answer()

# Нажатие "Я оплатил" для ЮMoney
@router.callback_query(F.data.startswith("yoomoney_paid_"))
async def yoomoney_paid(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[-1])
    order = await get_order_by_id(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заявка не найдена.")
        return
    if order["status"] != "created":
        await callback.answer("Заявка уже обработана.")
        return
    await update_order_status(order_id, "waiting_payment")
    await callback.message.edit_text(
        callback.message.text + "\n\n⏳ <b>Ожидание подтверждения платежа...</b> (обычно до 1 минуты)",
        parse_mode="HTML"
    )
    await callback.answer("Заявка поставлена в очередь на проверку.")

# Нажатие "Я оплатил" для Уралсиб -> запрос скриншота
@router.callback_query(F.data.startswith("upload_"))
async def request_screenshot(callback: types.CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[1])
    order = await get_order_by_id(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заявка не найдена.")
        return
    await callback.message.answer("📸 Прикрепите скриншот оплаты (изображение).")
    await state.set_state(ExchangeStates.waiting_screenshot)
    await state.update_data(order_id=order_id)
    await callback.answer()

@router.message(StateFilter(ExchangeStates.waiting_screenshot), F.photo)
async def receive_screenshot(message: types.Message, state: FSMContext):
    data = await state.get_data()
    order_id = data["order_id"]
    file_id = message.photo[-1].file_id
    await update_order_status(order_id, "waiting_approval", screenshot_file_id=file_id)
    order = await get_order_by_id(order_id)

    admin_caption = (
        f"📬 <b>Новая заявка #{order_id}</b>\n"
        f"👤 {order['username']} (ID: {order['user_id']})\n"
        f"💰 {order['amount']} ₽ → {order['currency']}\n"
        f"Реквизиты: {order['payment_details']}\n"
        f"Способ: {order['payment_method']}\n\n"
        f"Для подтверждения ответьте на это сообщение командой /approve"
    )
    await bot.send_photo(ADMIN_ID, file_id, caption=admin_caption, parse_mode="HTML")
    await message.answer("✅ Скриншот отправлен администратору.")
    await state.clear()

@router.message(StateFilter(ExchangeStates.waiting_screenshot))
async def non_photo(message: types.Message):
    await message.answer("❌ Пришлите скриншот как изображение.")

@router.message(Command("approve"))
async def cmd_approve(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not message.reply_to_message or not message.reply_to_message.caption:
        await message.answer("Ответьте на сообщение со скриншотом.")
        return
    import re
    match = re.search(r"заявка #(\d+)", message.reply_to_message.caption, re.IGNORECASE)
    if not match:
        await message.answer("ID заявки не найден.")
        return
    order_id = int(match.group(1))
    order = await get_order_by_id(order_id)
    if not order or order["status"] != "waiting_approval":
        await message.answer("Заявка не ожидает подтверждения.")
        return
    await update_order_status(order_id, "paid")
    await bot.send_message(order["user_id"], "✅ Оплата подтверждена, администратор отправит вам вывод.")
    await message.answer(f"Заявка #{order_id} подтверждена.")

@router.message(Command("complete"))
async def cmd_complete(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, order_id = message.text.split()
        order_id = int(order_id)
    except (ValueError, IndexError):
        await message.answer("Использование: /complete <номер_заявки>")
        return
    order = await get_order_by_id(order_id)
    if not order:
        await message.answer("Заявка не найдена.")
        return
    if order["status"] != "paid":
        await message.answer(f"Заявка в статусе '{order['status']}', нужно 'paid'.")
        return
    await update_order_status(order_id, "completed")
    await bot.send_message(order["user_id"], "🎉 Вывод отправлен, спасибо за обмен!")
    await message.answer(f"Заявка #{order_id} завершена.")

@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    if await state.get_state():
        await state.clear()
        await message.answer("🚫 Текущая операция отменена.")
    else:
        await message.answer("Нет активной операции.")

@router.message()
async def unknown(message: types.Message):
    await message.answer("Используйте /exchange для начала обмена.")

dp.include_router(router)

async def main():
    await database.init_db()
    # Запускаем фоновую проверку платежей ЮMoney
    asyncio.create_task(check_payments(bot))
    # Запускаем поллинг
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
