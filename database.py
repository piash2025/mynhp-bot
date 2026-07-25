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
                total_referrals INTEGER DEFAULT 0,
                ip_address TEXT DEFAULT '',
                country TEXT DEFAULT '',
                city TEXT DEFAULT '',
                is_vpn INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                session_id TEXT DEFAULT ''
            )
        """)

        for col, default in [
            ("ip_address", "''"), ("country", "''"), ("city", "''"),
            ("is_vpn", "0"), ("is_banned", "0"), ("session_id", "''"),
            ("status", "'active'"), ("risk_reason", "''"),
        ]:
            try:
                if col in ("ip_address", "country", "city", "status", "risk_reason"):
                    await db.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT {default}")
                else:
                    await db.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT {default}")
            except Exception:
                pass

        try:
            await db.execute("ALTER TABLE users ADD COLUMN last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except Exception:
            pass

        try:
            await db.execute("ALTER TABLE users ADD COLUMN last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except Exception:
            pass

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
                status TEXT DEFAULT 'pending',
                ads_viewed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                FOREIGN KEY (referred_id) REFERENCES users(user_id)
            )
        """)

        for col, default in [("status", "'pending'"), ("ads_viewed", "0")]:
            try:
                await db.execute(f"ALTER TABLE referrals ADD COLUMN {col} DEFAULT {default}")
            except Exception:
                pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                amount REAL NOT NULL,
                payment_method TEXT DEFAULT 'USDT',
                wallet_address TEXT,
                status TEXT DEFAULT 'pending',
                admin_note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS fraud_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                activity_type TEXT NOT NULL,
                description TEXT,
                ip_address TEXT,
                severity TEXT DEFAULT 'low',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS ad_platforms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                ad_type TEXT DEFAULT 'Rewarded Ad',
                script_code TEXT DEFAULT '',
                placement_id TEXT DEFAULT '',
                api_key TEXT DEFAULT '',
                rate REAL DEFAULT 0.0005,
                daily_limit INTEGER DEFAULT 50,
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE NOT NULL,
                new_users INTEGER DEFAULT 0,
                total_users INTEGER DEFAULT 0,
                impressions INTEGER DEFAULT 0,
                revenue REAL DEFAULT 0.0,
                payouts REAL DEFAULT 0.0,
                ad_views INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS login_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'SUCCESS',
                auth_method TEXT DEFAULT 'telegram_initdata',
                ip_address TEXT DEFAULT '',
                location TEXT DEFAULT '',
                is_vpn INTEGER DEFAULT 0,
                device_platform TEXT DEFAULT '',
                user_agent TEXT DEFAULT '',
                failure_reason TEXT DEFAULT ''
            )
        """)

        await db.execute("CREATE INDEX IF NOT EXISTS idx_login_logs_user_id ON login_logs(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_login_logs_timestamp ON login_logs(timestamp)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_login_logs_status ON login_logs(status)")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS task_activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                platform_name TEXT DEFAULT '',
                ad_type TEXT DEFAULT 'Rewarded',
                reward_amount REAL DEFAULT 0.0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'COMPLETED',
                ip_address TEXT DEFAULT ''
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_task_activities_user_id ON task_activities(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_task_activities_timestamp ON task_activities(timestamp)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_task_activities_platform ON task_activities(platform_name)")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL DEFAULT 'EXPENSE',
                source TEXT DEFAULT '',
                amount REAL DEFAULT 0.0,
                user_id INTEGER DEFAULT 0,
                status TEXT DEFAULT 'COMPLETED',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(timestamp)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status)")

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
            "min_ads_for_referral": "5",
            "farm_rate": "0.001",
            "farm_duration_hours": "4",
            "admin_password": "admin123",
            "vpn_blocker": "0",
            "max_ads_per_minute": "10",
            "max_daily_withdrawals": "3",
            "enable_initdata_check": "1",
            "enable_single_device_login": "0",
            "enable_strict_timer": "1",
            "auto_block_enabled": "0",
            "login_log_cleanup_enabled": "1",
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


async def add_referral(referrer_id: int, referred_id: int, reward: float, referrer_ip: str = "", referred_ip: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        exists = await db.execute(
            "SELECT id FROM referrals WHERE referred_id = ?", (referred_id,)
        )
        row = await exists.fetchone()
        if row:
            return False

        status = "pending"
        if referrer_ip and referred_ip and referrer_ip == referred_ip:
            status = "flagged"

        await db.execute("""
            INSERT INTO referrals (referrer_id, referred_id, reward, status)
            VALUES (?, ?, ?, ?)
        """, (referrer_id, referred_id, reward, status))
        await db.execute("""
            UPDATE users SET total_referrals = total_referrals + 1
            WHERE user_id = ?
        """, (referrer_id,))
        await db.commit()
        return True


async def check_referral_release(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM referrals WHERE referred_id = ? AND status = 'pending'", (user_id,)
        ) as cursor:
            ref = await cursor.fetchone()
            if not ref:
                return

            ref = dict(ref)
            new_count = ref["ads_viewed"] + 1
            await db.execute(
                "UPDATE referrals SET ads_viewed = ? WHERE id = ?", (new_count, ref["id"])
            )

            min_ads = int(dict(await db.execute("SELECT value FROM admin_settings WHERE key='min_ads_for_referral'").fetchone() or {}).get("value", "5") or "5")
            if new_count >= min_ads:
                await db.execute(
                    "UPDATE referrals SET status = 'valid' WHERE id = ?", (ref["id"],)
                )
                await db.execute("""
                    UPDATE users SET balance = balance + ?, total_earned = total_earned + ?
                    WHERE user_id = ?
                """, (ref["reward"], ref["reward"], ref["referrer_id"]))

            await db.commit()


async def get_referral_by_referred(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM referrals WHERE referred_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def flag_referral(referral_id: int, status: str = "flagged"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE referrals SET status = ? WHERE id = ?", (status, referral_id))
        await db.commit()


async def get_referral_summary() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM referrals") as cursor:
            row = await cursor.fetchone()
            total = row[0]

        async with db.execute("SELECT COALESCE(SUM(reward), 0) FROM referrals WHERE status = 'valid'") as cursor:
            row = await cursor.fetchone()
            commission_paid = row[0]

        async with db.execute("""
            SELECT referrer_id, COUNT(*) as cnt FROM referrals
            WHERE status = 'valid' GROUP BY referrer_id ORDER BY cnt DESC LIMIT 1
        """) as cursor:
            row = await cursor.fetchone()
            top_referrer_id = row[0] if row else None
            top_referrer_count = row[1] if row else 0

        top_referrer_name = ""
        if top_referrer_id:
            async with db.execute("SELECT username, first_name FROM users WHERE user_id = ?", (top_referrer_id,)) as cursor:
                urow = await cursor.fetchone()
                if urow:
                    top_referrer_name = urow[0] or urow[1] or str(top_referrer_id)

        return {
            "total_referrals": total,
            "commission_paid": commission_paid,
            "top_referrer_id": top_referrer_id,
            "top_referrer_name": top_referrer_name,
            "top_referrer_count": top_referrer_count,
        }


async def get_all_referrals(page: int = 0, limit: int = 50, search: str = "") -> List[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        offset = page * limit

        if search:
            search_pattern = f"%{search}%"
            query = """
                SELECT r.*, 
                    ru.username as referrer_username, ru.first_name as referrer_name,
                    rd.username as referred_username, rd.first_name as referred_name,
                    rd.ip_address as referred_ip
                FROM referrals r
                LEFT JOIN users ru ON r.referrer_id = ru.user_id
                LEFT JOIN users rd ON r.referred_id = rd.user_id
                WHERE r.referrer_id LIKE ? OR r.referred_id LIKE ?
                    OR ru.username LIKE ? OR rd.username LIKE ?
                ORDER BY r.created_at DESC LIMIT ? OFFSET ?
            """
            async with db.execute(query, (search_pattern, search_pattern, search_pattern, search_pattern, limit, offset)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]
        else:
            query = """
                SELECT r.*, 
                    ru.username as referrer_username, ru.first_name as referrer_name,
                    rd.username as referred_username, rd.first_name as referred_name,
                    rd.ip_address as referred_ip
                FROM referrals r
                LEFT JOIN users ru ON r.referrer_id = ru.user_id
                LEFT JOIN users rd ON r.referred_id = rd.user_id
                ORDER BY r.created_at DESC LIMIT ? OFFSET ?
            """
            async with db.execute(query, (limit, offset)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]


async def auto_flag_same_ip_referrals():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE referrals SET status = 'flagged'
            WHERE id IN (
                SELECT r.id FROM referrals r
                JOIN users u_ref ON r.referrer_id = u_ref.user_id
                JOIN users u_rd ON r.referred_id = u_rd.user_id
                WHERE u_ref.ip_address = u_rd.ip_address
                AND u_ref.ip_address != ''
                AND r.status = 'pending'
            )
        """)
        await db.commit()


async def get_referral_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0]


async def get_all_users(page: int = 0, limit: int = 50, filter_type: str = "", search: str = "") -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        where_clauses = []
        params = []

        if search:
            where_clauses.append("(user_id = ? OR username LIKE ? OR first_name LIKE ?)")
            params.extend([search, f"%{search}%", f"%{search}%"])

        if filter_type == "active_24h":
            where_clauses.append("last_active >= datetime('now', '-24 hours')")
        elif filter_type == "online":
            where_clauses.append("last_active >= datetime('now', '-15 minutes')")
        elif filter_type == "banned":
            where_clauses.append("is_banned = 1")

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        count_query = f"SELECT COUNT(*) FROM users{where_sql}"
        async with db.execute(count_query, params) as cursor:
            total = (await cursor.fetchone())[0]

        offset = page * limit
        query = f"SELECT * FROM users{where_sql} ORDER BY last_active DESC, created_at DESC LIMIT ? OFFSET ?"
        async with db.execute(query, params + [limit, offset]) as cursor:
            rows = [dict(r) for r in await cursor.fetchall()]

        return {"users": rows, "total": total, "page": page, "pages": max(1, -(-total // limit))}


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


async def create_withdrawal(user_id: int, username: str, amount: float, payment_method: str, wallet_address: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO withdrawals (user_id, username, amount, payment_method, wallet_address)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, amount, payment_method, wallet_address))
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        await db.commit()
        return True


async def get_all_withdrawals(status: str = None, page: int = 0, limit: int = 50) -> List[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        offset = page * limit
        if status:
            async with db.execute(
                "SELECT * FROM withdrawals WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset)
            ) as cursor:
                return [dict(r) for r in await cursor.fetchall()]
        else:
            async with db.execute(
                "SELECT * FROM withdrawals ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ) as cursor:
                return [dict(r) for r in await cursor.fetchall()]


async def get_withdrawal(withdrawal_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM withdrawals WHERE id = ?", (withdrawal_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_withdrawal_status(withdrawal_id: int, status: str, admin_note: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE withdrawals SET status = ?, admin_note = ?, processed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, admin_note, withdrawal_id)
        )
        if status == "rejected":
            w = await get_withdrawal(withdrawal_id)
            if w:
                await db.execute(
                    "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                    (w["amount"], w["user_id"])
                )
        await db.commit()


async def get_withdrawal_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM withdrawals WHERE status = 'pending'") as cursor:
            row = await cursor.fetchone()
            pending_count, pending_amount = row[0], row[1]
        async with db.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM withdrawals WHERE status = 'approved'") as cursor:
            row = await cursor.fetchone()
            approved_count, approved_amount = row[0], row[1]
        async with db.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM withdrawals WHERE status = 'rejected'") as cursor:
            row = await cursor.fetchone()
            rejected_count, rejected_amount = row[0], row[1]
        return {
            "pending": {"count": pending_count, "amount": pending_amount},
            "approved": {"count": approved_count, "amount": approved_amount},
            "rejected": {"count": rejected_count, "amount": rejected_amount},
        }


async def log_fraud(user_id: int, username: str, activity_type: str, description: str, ip_address: str = "", severity: str = "low"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO fraud_logs (user_id, username, activity_type, description, ip_address, severity)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, username, activity_type, description, ip_address, severity))
        await db.commit()


async def get_fraud_logs(page: int = 0, limit: int = 50) -> List[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        offset = page * limit
        async with db.execute(
            "SELECT * FROM fraud_logs ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_fraud_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM fraud_logs") as cursor:
            row = await cursor.fetchone()
            total = row[0]
        async with db.execute("SELECT COUNT(*) FROM fraud_logs WHERE severity = 'high'") as cursor:
            row = await cursor.fetchone()
            high = row[0]
        async with db.execute("SELECT COUNT(*) FROM fraud_logs WHERE severity = 'medium'") as cursor:
            row = await cursor.fetchone()
            medium = row[0]
        return {"total": total, "high": high, "medium": medium}


async def get_user_ad_count_today(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM fraud_logs WHERE user_id = ? AND activity_type = 'fast_ads' AND DATE(created_at) = DATE('now')",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0]


async def get_user_withdrawal_count_today(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM withdrawals WHERE user_id = ? AND DATE(created_at) = DATE('now')",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0]


# ===== AD PLATFORM CRUD =====

async def get_all_platforms() -> List[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM ad_platforms ORDER BY created_at DESC") as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_platform(platform_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM ad_platforms WHERE id = ?", (platform_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_platform_by_slug(slug: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM ad_platforms WHERE slug = ?", (slug,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_platform(name: str, slug: str, ad_type: str = "Rewarded Ad", script_code: str = "", placement_id: str = "", api_key: str = "", rate: float = 0.0005, daily_limit: int = 50, enabled: int = 1) -> Optional[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO ad_platforms (name, slug, ad_type, script_code, placement_id, api_key, rate, daily_limit, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, slug, ad_type, script_code, placement_id, api_key, rate, daily_limit, enabled))
        await db.commit()
        return cursor.lastrowid


async def update_platform(platform_id: int, **kwargs):
    async with aiosqlite.connect(DB_PATH) as db:
        allowed = ["name", "slug", "ad_type", "script_code", "placement_id", "api_key", "rate", "daily_limit", "enabled"]
        updates = []
        values = []
        for key in allowed:
            if key in kwargs and kwargs[key] is not None:
                updates.append(f"{key} = ?")
                values.append(kwargs[key])
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            values.append(platform_id)
            await db.execute(f"UPDATE ad_platforms SET {', '.join(updates)} WHERE id = ?", values)
            await db.commit()


async def delete_platform(platform_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM ad_platforms WHERE id = ?", (platform_id,))
        await db.commit()


# ===== DAILY STATS / DASHBOARD =====

async def record_daily_stats():
    today = __import__('datetime').date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        total_users_row = await db.execute("SELECT COUNT(*) FROM users")
        total_users = (await total_users_row.fetchone())[0]
        new_users_row = await db.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = ?", (today,))
        new_users = (await new_users_row.fetchone())[0]
        impressions_row = await db.execute("SELECT COUNT(*) FROM fraud_logs WHERE activity_type = 'ad_view' AND DATE(created_at) = ?", (today,))
        impressions = (await impressions_row.fetchone())[0]
        revenue_row = await db.execute("SELECT COALESCE(SUM(amount), 0) FROM withdrawals WHERE status = 'approved' AND DATE(processed_at) = ?", (today,))
        payouts = (await revenue_row.fetchone())[0]
        ad_views_row = await db.execute("SELECT COUNT(*) FROM fraud_logs WHERE activity_type = 'ad_view' AND DATE(created_at) = ?", (today,))
        ad_views = (await ad_views_row.fetchone())[0]
        await db.execute("""
            INSERT INTO daily_stats (date, new_users, total_users, impressions, revenue, payouts, ad_views)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                new_users = excluded.new_users, total_users = excluded.total_users,
                impressions = excluded.impressions, revenue = excluded.revenue,
                payouts = excluded.payouts, ad_views = excluded.ad_views
        """, (today, new_users, total_users, impressions, 0, payouts, ad_views))
        await db.commit()


async def get_daily_stats(days: int = 30) -> List[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM daily_stats ORDER BY date DESC LIMIT ?", (days,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in reversed(rows)]


async def get_dashboard_summary() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        total_users_row = await db.execute("SELECT COUNT(*) FROM users")
        total_users = (await total_users_row.fetchone())[0]
        total_earnings_row = await db.execute("SELECT COALESCE(SUM(total_earned), 0) FROM users")
        total_earnings = (await total_earnings_row.fetchone())[0]
        today = __import__('datetime').date.today().isoformat()
        new_today_row = await db.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = ?", (today,))
        new_today = (await new_today_row.fetchone())[0]
        total_platforms_row = await db.execute("SELECT COUNT(*) FROM ad_platforms")
        total_platforms = (await total_platforms_row.fetchone())[0]
        active_platforms_row = await db.execute("SELECT COUNT(*) FROM ad_platforms WHERE enabled = 1")
        active_platforms = (await active_platforms_row.fetchone())[0]
        total_payouts_row = await db.execute("SELECT COALESCE(SUM(amount), 0) FROM withdrawals WHERE status = 'approved'")
        total_payouts = (await total_payouts_row.fetchone())[0]
        pending_payouts_row = await db.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM withdrawals WHERE status = 'pending'")
        pending_data = (await pending_payouts_row.fetchone())
        return {
            "total_users": total_users,
            "total_earnings": total_earnings,
            "new_today": new_today,
            "total_platforms": total_platforms,
            "active_platforms": active_platforms,
            "total_payouts": total_payouts,
            "pending_payout_count": pending_data[0],
            "pending_payout_amount": pending_data[1],
        }


# ===== IP TRACKING & BAN =====

async def update_user_ip(user_id: int, ip_address: str, country: str = "", city: str = "", is_vpn: bool = False):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users SET ip_address = ?, country = ?, city = ?, is_vpn = ?
            WHERE user_id = ?
        """, (ip_address, country, city, 1 if is_vpn else 0, user_id))
        await db.commit()


async def ban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned = 1, status = 'banned' WHERE user_id = ?", (user_id,))
        await db.commit()


async def unban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned = 0, status = 'active' WHERE user_id = ?", (user_id,))
        await db.commit()


async def set_user_status(user_id: int, status: str, risk_reason: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET status = ?, risk_reason = ? WHERE user_id = ?", (status, risk_reason, user_id))
        await db.commit()


async def flag_user(user_id: int, reason: str):
    auto_block = (await get_admin_setting("auto_block_enabled")) == "1"
    new_status = "banned" if auto_block else "flagged"
    new_banned = 1 if auto_block else 0
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned = ?, status = ?, risk_reason = ? WHERE user_id = ?",
                         (new_banned, new_status, reason, user_id))
        await db.commit()


async def get_flagged_users() -> List[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, username, first_name, ip_address, country, city, is_vpn, status, risk_reason, created_at FROM users WHERE status = 'flagged' ORDER BY created_at DESC"
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_users_by_ip(ip_address: str) -> List[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, username, first_name, created_at, ip_address, country, city, is_vpn, is_banned FROM users WHERE ip_address = ? AND ip_address != ''",
            (ip_address,)
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_fraud_ip_groups() -> List[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT ip_address, COUNT(*) as user_count,
                   GROUP_CONCAT(user_id) as user_ids,
                   GROUP_CONCAT(username) as usernames,
                   country, city
            FROM users
            WHERE ip_address != '' AND ip_address IS NOT NULL
            GROUP BY ip_address
            HAVING user_count > 1
            ORDER BY user_count DESC
        """) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_vpn_users() -> List[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, username, first_name, ip_address, country, city, is_vpn, is_banned FROM users WHERE is_vpn = 1"
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


# ===== SESSION MANAGEMENT =====

async def update_session_id(user_id: int, session_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET session_id = ? WHERE user_id = ?", (session_id, user_id))
        await db.commit()


async def update_last_active(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
        await db.commit()


async def update_last_seen(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET last_seen = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_live_users_count(minutes: int = 2) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE last_seen >= datetime('now', ?)",
            (f"-{minutes} minutes",)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_session_id(user_id: int) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT session_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] else None


async def verify_session(user_id: int, session_id: str) -> bool:
    if not session_id:
        return False
    stored = await get_session_id(user_id)
    if not stored:
        return True
    return stored == session_id


# ===== LOGIN LOGS =====

async def create_login_log(user_id: int, username: str = "", first_name: str = "",
                           status: str = "SUCCESS", auth_method: str = "telegram_initdata",
                           ip_address: str = "", location: str = "", is_vpn: bool = False,
                           device_platform: str = "", user_agent: str = "", failure_reason: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO login_logs (user_id, username, first_name, status, auth_method,
                                    ip_address, location, is_vpn, device_platform, user_agent, failure_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, first_name, status, auth_method,
              ip_address, location, 1 if is_vpn else 0, device_platform, user_agent, failure_reason))
        await db.commit()


async def get_login_logs(page: int = 1, per_page: int = 50, search: str = "",
                         status_filter: str = "", vpn_filter: str = "") -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        where_clauses = []
        params = []

        if search:
            where_clauses.append("(user_id = ? OR username LIKE ? OR first_name LIKE ? OR ip_address = ?)")
            params.extend([search, f"%{search}%", f"%{search}%", search])
        if status_filter:
            where_clauses.append("status = ?")
            params.append(status_filter)
        if vpn_filter == "1":
            where_clauses.append("is_vpn = 1")
        elif vpn_filter == "0":
            where_clauses.append("is_vpn = 0")

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        count_query = f"SELECT COUNT(*) FROM login_logs{where_sql}"
        async with db.execute(count_query, params) as cursor:
            total = (await cursor.fetchone())[0]

        offset = (page - 1) * per_page
        query = f"SELECT * FROM login_logs{where_sql} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        async with db.execute(query, params + [per_page, offset]) as cursor:
            rows = [dict(r) for r in await cursor.fetchall()]

        return {"logs": rows, "total": total, "page": page, "per_page": per_page, "pages": max(1, -(-total // per_page))}


async def get_login_log_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM login_logs") as c:
            total = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM login_logs WHERE status='SUCCESS'") as c:
            success = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM login_logs WHERE status='FAILED'") as c:
            failed = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM login_logs WHERE is_vpn=1") as c:
            vpn = (await c.fetchone())[0]
        return {"total": total, "success": success, "failed": failed, "vpn": vpn}


async def cleanup_old_login_logs(days: int = 30) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM login_logs WHERE status = 'SUCCESS' AND timestamp < datetime('now', ?)",
            (f"-{days} days",)
        )
        await db.commit()
        return cursor.rowcount


# ===== TASK ACTIVITIES =====

async def create_task_activity(user_id: int, username: str = "", first_name: str = "",
                               platform_name: str = "", ad_type: str = "Rewarded",
                               reward_amount: float = 0.0, status: str = "COMPLETED",
                               ip_address: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO task_activities (user_id, username, first_name, platform_name, ad_type,
                                         reward_amount, status, ip_address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, first_name, platform_name, ad_type, reward_amount, status, ip_address))
        await db.commit()


async def get_task_activities(page: int = 1, per_page: int = 50, search: str = "",
                              platform_filter: str = "") -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        where_clauses = []
        params = []

        if search:
            where_clauses.append("(user_id = ? OR username LIKE ? OR first_name LIKE ?)")
            params.extend([search, f"%{search}%", f"%{search}%"])
        if platform_filter:
            where_clauses.append("platform_name = ?")
            params.append(platform_filter)

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        count_query = f"SELECT COUNT(*) FROM task_activities{where_sql}"
        async with db.execute(count_query, params) as cursor:
            total = (await cursor.fetchone())[0]

        offset = (page - 1) * per_page
        query = f"SELECT * FROM task_activities{where_sql} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        async with db.execute(query, params + [per_page, offset]) as cursor:
            rows = [dict(r) for r in await cursor.fetchall()]

        return {"logs": rows, "total": total, "page": page, "per_page": per_page, "pages": max(1, -(-total // per_page))}


async def get_task_activity_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM task_activities") as c:
            total = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM task_activities WHERE status='COMPLETED'") as c:
            completed = (await c.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(reward_amount), 0) FROM task_activities WHERE status='COMPLETED'") as c:
            total_reward = (await c.fetchone())[0]
        async with db.execute("SELECT platform_name, COUNT(*) as cnt FROM task_activities WHERE status='COMPLETED' GROUP BY platform_name ORDER BY cnt DESC") as c:
            platforms = [{"name": r[0], "count": r[1]} for r in await c.fetchall()]
        return {"total": total, "completed": completed, "total_reward": total_reward, "platforms": platforms}


# ===== TRANSACTIONS / ACCOUNTING =====

async def create_transaction(txn_type: str, source: str, amount: float, user_id: int = 0, status: str = "COMPLETED"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO transactions (type, source, amount, user_id, status)
            VALUES (?, ?, ?, ?, ?)
        """, (txn_type, source, amount, user_id, status))
        await db.commit()


async def get_accounting_summary() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='INCOME' AND status='COMPLETED'") as c:
            total_income = (await c.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='EXPENSE' AND status='COMPLETED'") as c:
            total_expense = (await c.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(balance), 0) FROM users") as c:
            pending_liability = (await c.fetchone())[0]
        return {
            "total_revenue": total_income,
            "total_payouts": total_expense,
            "net_profit": total_income - total_expense,
            "pending_liability": pending_liability,
        }


async def get_transactions(page: int = 1, per_page: int = 50, date_filter: str = "") -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        where_clauses = []
        params = []

        if date_filter == "today":
            where_clauses.append("DATE(timestamp) = DATE('now')")
        elif date_filter == "week":
            where_clauses.append("timestamp >= datetime('now', '-7 days')")
        elif date_filter == "month":
            where_clauses.append("timestamp >= datetime('now', '-30 days')")

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        count_query = f"SELECT COUNT(*) FROM transactions{where_sql}"
        async with db.execute(count_query, params) as cursor:
            total = (await cursor.fetchone())[0]

        offset = (page - 1) * per_page
        query = f"SELECT * FROM transactions{where_sql} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        async with db.execute(query, params + [per_page, offset]) as cursor:
            rows = [dict(r) for r in await cursor.fetchall()]

        return {"txns": rows, "total": total, "page": page, "per_page": per_page, "pages": max(1, -(-total // per_page))}
