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

    logger.info(f"Создаём счёт: amount={amount}, to={YOO_MONEY_WALLET}, label={label}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=payload, timeout=15) as resp:
                text = await resp.text()
                logger.info(f"API ЮMoney ответ {resp.status}: {text}")

                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "success":
                        # Если есть redirect_url — используем его
                        redirect_url = data.get("redirect_url")
                        if redirect_url:
                            return redirect_url
                        # Иначе собираем ссылку через request_id
                        request_id = data.get("request_id")
                        if request_id:
                            return (
                                "https://yoomoney.ru/transfer/quickpay"
                                f"?requestId={request_id}"
                                f"&sum={amount:.2f}"
                                f"&label={label}"
                                "&comment=Оплата+заявки"
                            )
                            
                        logger.error("Нет ни redirect_url, ни request_id в ответе")
                        return None
                    else:
                        logger.error(f"YooMoney invoice error: {data}")
                else:
                    logger.error(f"YooMoney API returned {resp.status}: {text}")
    except Exception as e:
        logger.error(f"Failed to create YooMoney invoice: {e}")
    return None
