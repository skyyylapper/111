import asyncio
import logging
from datetime import datetime, timedelta
import aiohttp
from config import YOO_MONEY_TOKEN
from database import get_pending_yoomoney_orders, update_order_status

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 30  # секунд

async def check_payments(bot):
    if not YOO_MONEY_TOKEN:
        logger.warning("YOO_MONEY_TOKEN не задан, автоматическая проверка отключена.")
        return

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                orders = await get_pending_yoomoney_orders()
                for order in orders:
                    label = f"{order['user_id']}:{order['invoice_id']}"
                    found = await find_payment(session, label, order['amount'])
                    if found:
                        await update_order_status(order['id'], 'paid')
                        try:
                            await bot.send_message(
                                order['user_id'],
                                "✅ Деньги поступили, администратор вручную отправит вам вывод."
                            )
                            logger.info(f"Order {order['id']} automatically confirmed.")
                        except Exception as e:
                            logger.error(f"Failed to notify user {order['user_id']}: {e}")
            except Exception as e:
                logger.error(f"Error in check_payments: {e}")
            await asyncio.sleep(CHECK_INTERVAL)

async def find_payment(session: aiohttp.ClientSession, label: str, amount: float) -> bool:
    now = datetime.now()
    from_time = now - timedelta(hours=24)
    url = "https://yoomoney.ru/api/operation-history"
    headers = {"Authorization": f"Bearer {YOO_MONEY_TOKEN}"}
    params = {
        "type": "deposition",
        "label": label,
        "from": from_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "till": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "records": 10,
    }
    try:
        async with session.get(url, headers=headers, params=params, timeout=15) as resp:
            if resp.status != 200:
                logger.warning(f"YooMoney history API error: {resp.status}")
                return False
            data = await resp.json()
            for op in data.get("operations", []):
                if op.get("status") == "success" and op.get("label") == label:
                    op_amount = float(op.get("amount", 0))
                    if abs(op_amount - amount) < 0.01:
                        return True
    except Exception as e:
        logger.error(f"YooMoney request failed: {e}")
    return False
