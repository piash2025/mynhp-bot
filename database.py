from typing import Optional, List, Dict
import json

import aiosqlite

DB_PATH = "bot_users.db"

ADMIN_USER_IDS = [7123456789]  # Apnar Telegram user ID ekhane likhun

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
                total_earned REAL DEFAULT 0.0,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                total_referrals INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS ad_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                network TEXT UNIQUE NOT NULL,
                rate REAL DEFAULT 0.0005,
                daily_limit INTEGER DEFAULT 50,
                enabled INTEGER DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                reward REAL DEFAULT 0.001,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                FOREIGN KEY (referred_id) REFERENCES users(user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        default_rates = [
            ("adsgream", 0.0005, 50, 1),
            ("monetag", 0.0005, 30, 1),
            ("adexium", 0.0005, 40, 1),
            ("bonus", 0.0050, 5, 1),
        ]
        for network, rate, limit, enabled in default_rates:
            await db.execute("""
                INSERT OR IGNORE INTO ad_rates (network, rate, daily_limit, enabled)
                VALUES (?, ?, ?, ?)
            """, (network, rate, limit, enabled))

        defaults = {
            "referral_reward": "0.001",
            "min_withdraw": "0.01",
            "farm_rate": "0.001",
            "farm_duration_hours": "4",
            "admin_password": "admin123",
        }
        for key, value in defaults.items():
            await db.execute("""
                INSERT OR IGNORE INTO admin_settings (key, value)
                VALUES (?, ?)
            """, (key, value))

        await db.commit()


async def add_or_update_user(user_id: int, username: str = None, first_name: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name, referral_code)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
        """, (user_id, username, first_name, f"ref_{user_id}"))
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
            INSERT INTO users (user_id, balance, tasks_done, total_earned, referral_code)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                balance = balance + ?,
                tasks_done = tasks_done + 1,
                total_earned = total_earned + ?
        """, (user_id, reward, reward, f"ref_{user_id}", reward, reward))
        await db.commit()


async def get_ad_rate(network: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM ad_rates WHERE network = ?", (network,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_all_ad_rates() -> List[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM ad_rates") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def update_ad_rate(network: str, rate: float = None, daily_limit: int = None, enabled: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if rate is not None:
            await db.execute("UPDATE ad_rates SET rate = ? WHERE network = ?", (rate, network))
        if daily_limit is not None:
            await db.execute("UPDATE ad_rates SET daily_limit = ? WHERE network = ?", (daily_limit, network))
        if enabled is not None:
            await db.execute("UPDATE ad_rates SET enabled = ? WHERE network = ?", (enabled, network))
        await db.commit()


async def add_referral(referrer_id: int, referred_id: int, reward: float):
    async with aiosqlite.connect(DB_PATH) as db:
        exists = await db.execute(
            "SELECT id FROM referrals WHERE referred_id = ?", (referred_id,)
        )
        row = await exists.fetchone()
        if row:
            return False

        await db.execute("""
            INSERT INTO referrals (referrer_id, referred_id, reward)
            VALUES (?, ?, ?)
        """, (referrer_id, referred_id, reward))
        await db.execute("""
            UPDATE users SET balance = balance + ?, total_earned = total_earned + ?, total_referrals = total_referrals + 1
            WHERE user_id = ?
        """, (reward, reward, referrer_id))
        await db.commit()
        return True


async def get_referral_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0]


async def get_all_users(page: int = 0, limit: int = 50) -> List[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        offset = page * limit
        async with db.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_total_earnings() -> float:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COALESCE(SUM(total_earned), 0) FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0]


async def get_admin_setting(key: str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM admin_settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def set_admin_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO admin_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        await db.commit()


async def get_all_admin_settings() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM admin_settings") as cursor:
            rows = await cursor.fetchall()
            return {row["key"]: row["value"] for row in rows}
