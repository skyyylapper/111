import aiosqlite
from datetime import datetime

DB_PATH = "orders.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                payment_details TEXT NOT NULL,
                payment_method TEXT,
                status TEXT DEFAULT 'created',
                invoice_id TEXT,
                screenshot_file_id TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.commit()

async def create_order(user_id, username, amount, currency, payment_details, payment_method=None, invoice_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, username, amount, currency, payment_details, payment_method, invoice_id, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'created')",
            (user_id, username, amount, currency, payment_details, payment_method, invoice_id)
        )
        order_id = cursor.lastrowid
        await db.commit()
        return order_id

async def update_order_status(order_id, status, **kwargs):
    updates = ", ".join([f"{k}=?" for k in kwargs.keys()])
    params = list(kwargs.values()) + [status, datetime.now().isoformat(), order_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE orders SET {updates}, status=?, updated_at=? WHERE id=?",
            params
        )
        await db.commit()

async def get_order_by_id(order_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM orders WHERE id=?", (order_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def get_pending_yoomoney_orders():
    """Заявки ЮMoney, ожидающие оплаты."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM orders WHERE payment_method='yoomoney' AND status='waiting_payment'"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
