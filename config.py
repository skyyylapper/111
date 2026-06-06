import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

YOO_MONEY_WALLET = os.getenv("YOO_MONEY_WALLET")
YOO_MONEY_CARDS = os.getenv("YOO_MONEY_CARDS", "")  # "Тинькофф: 1234, Сбер: 5678"
URALSIB_CARD = os.getenv("URALSIB_CARD")

YOO_MONEY_TOKEN = os.getenv("YOO_MONEY_TOKEN")      # OAuth-токен с правами payment-p2p, operation-history
