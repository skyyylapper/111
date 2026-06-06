import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

YOO_MONEY_WALLET = os.getenv("YOO_MONEY_WALLET")
YOO_MONEY_CARDS = os.getenv("YOO_MONEY_CARDS", "")
URALSIB_CARD = os.getenv("URALSIB_CARD")

YOO_MONEY_TOKEN = os.getenv("YOO_MONEY_TOKEN")

PROXY_URL = os.getenv("PROXY_URL", "")   # если не задано, будет пустая строка
