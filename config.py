import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# Списки реквизитов (через запятую)
YOO_MONEY_WALLETS = os.getenv("YOO_MONEY_WALLETS", "")   # "41001..., 41002..."
YOO_MONEY_CARDS = os.getenv("YOO_MONEY_CARDS", "")        # "Тинькофф: 1234, Сбер: 5678"
URALSIB_CARDS = os.getenv("URALSIB_CARDS", "")            # "5559..., 4444..."

PROXY_URL = os.getenv("PROXY_URL", "")
