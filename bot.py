import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from config import BOT_TOKEN, ADMIN_ID, YOO_MONEY_WALLETS, YOO_MONEY_CARDS, URALSIB_CARDS, PROXY_URL
import database
from database import create_order, update_order_status, get_order_by_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IGNORED_USERS = [8479074062]

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
    waiting_requisite_choice = State()
    waiting_screenshot = State()

# Клавиатуры
currency_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💎 USDT BEP20", callback_data="currency_USDT_BEP20")],
    [InlineKeyboardButton(text="🇲🇩 Рубли ПМР", callback_data="currency_RUB_PMR")]
])

payment_method_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💳 ЮMoney (ручная проверка)", callback_data="pay_yoomoney")],
    [InlineKeyboardButton(text="🏦 Уралсиб (ручная проверка)", callback_data="pay_uralsib")]
])

# Middleware игнорирования
class IgnoreUsersMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if hasattr(event, 'from_user') and event.from_user:
            if event.from_user.id in IGNORED_USERS:
                return
        return await handler(event, data)

dp.update.middleware(IgnoreUsersMiddleware())

# Парсер списков
def parse_list(env_str):
    return [item.strip() for item in env_str.split(",") if item.strip()]

# Старт
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
        await message.answer("❌ Введите число.")
        return
    if amount < 500:
        await message.answer("❌ Минимум 500 рублей.")
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

# Выбор способа оплаты -> показать список реквизитов
@router.callback_query(StateFilter(ExchangeStates.waiting_payment_method), F.data.startswith("pay_"))
async def process_payment_method(callback: types.CallbackQuery, state: FSMContext):
    method = callback.data.split("_", 1)[1]
    await state.update_data(payment_method=method)

    if method == "yoomoney":
        wallets = parse_list(YOO_MONEY_WALLETS)
        if not wallets:
            await callback.message.answer("❌ Нет доступных кошельков ЮMoney.")
            await callback.answer()
            return
        # Показываем список кошельков
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💼 {w}", callback_data=f"req_y_{i}")] for i, w in enumerate(wallets)
        ])
        await callback.message.edit_text("Выберите кошелёк ЮMoney для перевода:", reply_markup=keyboard)
        await state.set_state(ExchangeStates.waiting_requisite_choice)

    elif method == "uralsib":
        cards = parse_list(URALSIB_CARDS)
        if not cards:
            await callback.message.answer("❌ Нет доступных карт Уралсиб.")
            await callback.answer()
            return
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💳 {c}", callback_data=f"req_u_{i}")] for i, c in enumerate(cards)
        ])
        await callback.message.edit_text("Выберите карту Уралсиб для перевода:", reply_markup=keyboard)
        await state.set_state(ExchangeStates.waiting_requisite_choice)
    await callback.answer()

# Пользователь выбрал конкретный реквизит
@router.callback_query(StateFilter(ExchangeStates.waiting_requisite_choice), F.data.startswith("req_"))
async def process_requisite_choice(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    method = data["payment_method"]
    _, target, idx = callback.data.split("_")
    idx = int(idx)

    if method == "yoomoney":
        wallets = parse_list(YOO_MONEY_WALLETS)
        chosen_wallet = wallets[idx]
        cards = parse_list(YOO_MONEY_CARDS)
        cards_text = "\n".join([f"• {c}" for c in cards]) if cards else "список карт не указан"
        text = (
            f"💳 <b>Оплата через ЮMoney</b>\n\n"
            f"Сумма: <b>{data['amount']} ₽</b>\n"
            f"Кошелёк: <code>{chosen_wallet}</code>\n"
            f"Доступные карты:\n{cards_text}\n\n"
            f"⚠️ <b>Ручная проверка:</b> после перевода нажмите «Я оплатил» и приложите скриншот."
        )
        # Создаём заявку
        order_id = await create_order(
            user_id=callback.from_user.id,
            username=callback.from_user.username or "NoUsername",
            amount=data["amount"],
            currency=data["currency"],
            payment_details=data["payment_details"],
            payment_method=method,
            chosen_requisite=chosen_wallet
        )

    else:  # uralsib
        cards = parse_list(URALSIB_CARDS)
        chosen_card = cards[idx]
        text = (
            f"🏦 <b>Оплата через Уралсиб</b>\n\n"
            f"Сумма: <b>{data['amount']} ₽</b>\n"
            f"Карта: <code>{chosen_card}</code>\n\n"
            f"⚠️ <b>Ручная проверка:</b> потребуется скриншот."
        )
        order_id = await create_order(
            user_id=callback.from_user.id,
            username=callback.from_user.username or "NoUsername",
            amount=data["amount"],
            currency=data["currency"],
            payment_details=data["payment_details"],
            payment_method=method,
            chosen_requisite=chosen_card
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"upload_{order_id}")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.clear()

# Нажатие "Я оплатил" -> запрос скриншота
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

# Приём скриншота
@router.message(StateFilter(ExchangeStates.waiting_screenshot))
async def screenshot_handler(message: types.Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Пришлите скриншот как изображение.")
        return

    data = await state.get_data()
    order_id = data["order_id"]
    file_id = message.photo[-1].file_id
    await update_order_status(order_id, "waiting_approval", screenshot_file_id=file_id)
    order = await get_order_by_id(order_id)

    admin_caption = (
        f"📬 <b>Новая заявка #{order_id}</b>\n"
        f"👤 {order['username']} (ID: {order['user_id']})\n"
        f"💰 {order['amount']} ₽ → {order['currency']}\n"
        f"Реквизиты вывода: {order['payment_details']}\n"
        f"Способ оплаты: {order['payment_method']}\n"
        f"Использован реквизит: {order['chosen_requisite']}\n\n"
        f"Для подтверждения ответьте на это сообщение командой /approve"
    )
    await bot.send_photo(ADMIN_ID, file_id, caption=admin_caption, parse_mode="HTML")
    await message.answer("✅ Скриншот отправлен администратору.")
    await state.clear()

# Админские команды
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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
