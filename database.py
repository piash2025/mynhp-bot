from typing import Optional

import aiosqlite

DB_PATH = "bot_users.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tool_uses INTEGER DEFAULT 0,
                balance REAL DEFAULT 0.0,
                tasks_done INTEGER DEFAULT 0,
                total_earned REAL DEFAULT 0.0
            )
        """)
        await db.commit()


async def add_or_update_user(user_id: int, username: str = None, first_name: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
        """, (user_id, username, first_name))
        await db.commit()


async def increment_tool_use(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users SET tool_uses = tool_uses + 1
            WHERE user_id = ?
        """, (user_id,))
        await db.commit()


async def get_user_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0]


async def get_user(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_balance(user_id: int, reward: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, balance, tasks_done, total_earned)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                balance = balance + ?,
                tasks_done = tasks_done + 1,
                total_earned = total_earned + ?
        """, (user_id, reward, reward, reward, reward))
        await db.commit()
