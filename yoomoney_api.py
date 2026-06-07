import logging
import aiohttp
from config import YOO_MONEY_TOKEN, YOO_MONEY_WALLET

logger = logging.getLogger(__name__)

async def create_yoomoney_invoice(amount: float, label: str) -> str | None:
    if not YOO_MONEY_TOKEN:
        logger.error("YOO_MONEY_TOKEN не задан")
        return None

    url = "https://yoomoney.ru/api/request-payment"
    headers = {
        "Authorization": f"Bearer {YOO_MONEY_TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = {
        "pattern_id": "p2p",
        "to": YOO_MONEY_WALLET,
        "amount": f"{amount:.2f}",
        "label": label,
        "comment": f"Оплата заявки {label}",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=payload, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "success":
                        return data.get("redirect_url")
                    else:
                        logger.error(f"YooMoney invoice error: {data}")
                else:
                    logger.error(f"YooMoney API returned {resp.status}: {await resp.text()}")
    except Exception as e:
        logger.error(f"Failed to create YooMoney invoice: {e}")
    return None
