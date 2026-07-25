from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import HOST, PORT
from database import (
    add_or_update_user,
    get_user_count,
    get_user,
    get_all_users,
    increment_tool_use,
    init_db,
    update_balance,
    get_ad_rate,
    get_all_ad_rates,
    update_ad_rate,
    get_all_admin_settings,
    set_admin_setting,
    get_admin_setting,
    get_total_earnings,
    get_referral_count,
    create_withdrawal,
    get_all_withdrawals,
    get_withdrawal,
    update_withdrawal_status,
    get_withdrawal_stats,
    log_fraud,
    get_fraud_logs,
    get_fraud_stats,
)
from ads_integration import get_ad


def check_admin(password: str) -> bool:
    stored = get_admin_setting.__wrapped__ if hasattr(get_admin_setting, '__wrapped__') else None
    import sqlite3
    conn = sqlite3.connect("bot_users.db")
    row = conn.execute("SELECT value FROM admin_settings WHERE key='admin_password'").fetchone()
    conn.close()
    return row and row[0] == password


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="mynhp_bot", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel():
    with open("static/admin.html", "r") as f:
        return HTMLResponse(content=f.read())


# ===== USER API =====

@app.post("/api/user/track")
async def track_user(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    if user_id:
        await add_or_update_user(
            user_id, data.get("username"), data.get("first_name")
        )
        return {"status": "ok"}
    return {"status": "error", "message": "user_id required"}


@app.post("/api/tool/use")
async def tool_use(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    if user_id:
        await increment_tool_use(user_id)
        return {"status": "ok"}
    return {"status": "error", "message": "user_id required"}


@app.get("/api/stats")
async def stats():
    count = await get_user_count()
    return {"total_users": count}


@app.get("/api/ad/{user_id}")
async def get_ad_for_user(user_id: int, language: str = "en"):
    ad = await get_ad(user_id, language)
    if ad:
        return ad
    return {"error": "No ad available"}


@app.post("/api/user/balance")
async def update_user_balance(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    reward = data.get("reward", 0)
    if user_id and reward > 0:
        await update_balance(user_id, reward)
        user = await get_user(user_id)
        if user:
            return {
                "status": "ok",
                "balance": user.get("balance", 0),
                "tasks_done": user.get("tasks_done", 0),
                "total_earned": user.get("total_earned", 0),
            }
    return {"status": "error", "message": "user_id and reward required"}


@app.get("/api/user/{user_id}")
async def get_user_info(user_id: int):
    user = await get_user(user_id)
    if user:
        return user
    return {"error": "User not found"}


@app.get("/api/ad-rate/{network}")
async def get_network_rate(network: str):
    rate = await get_ad_rate(network)
    if rate:
        return rate
    return {"error": "Network not found"}


@app.get("/api/config")
async def get_public_config():
    rates = await get_all_ad_rates()
    settings = await get_all_admin_settings()
    return {
        "ad_rates": {r["network"]: {"rate": r["rate"], "daily_limit": r["daily_limit"], "enabled": r["enabled"]} for r in rates},
        "farm_rate": float(settings.get("farm_rate", "0.001")),
        "farm_duration_hours": float(settings.get("farm_duration_hours", "4")),
        "referral_reward": float(settings.get("referral_reward", "0.001")),
        "min_withdraw": float(settings.get("min_withdraw", "0.01")),
    }


# ===== ADMIN API =====

@app.post("/api/admin/login")
async def admin_login(request: Request):
    data = await request.json()
    password = data.get("password", "")
    stored = await get_admin_setting("admin_password")
    if stored and stored == password:
        return {"status": "ok"}
    return {"status": "error", "message": "Wrong password"}


@app.get("/api/admin/stats")
async def admin_stats(request: Request):
    password = request.query_params.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}

    total_users = await get_user_count()
    total_earnings = await get_total_earnings()

    import sqlite3
    conn = sqlite3.connect("bot_users.db")
    row = conn.execute("SELECT COALESCE(SUM(total_referrals), 0) FROM users").fetchone()
    conn.close()
    total_referrals = row[0] if row else 0

    withdrawal_stats = await get_withdrawal_stats()
    fraud_stats = await get_fraud_stats()

    return {
        "total_users": total_users,
        "total_earnings": total_earnings,
        "total_referrals": total_referrals,
        "pending_withdrawals": withdrawal_stats["pending"]["count"],
        "pending_payout_amount": withdrawal_stats["pending"]["amount"],
        "fraud_alerts": fraud_stats["high"],
    }


@app.get("/api/admin/rates")
async def admin_rates(request: Request):
    password = request.query_params.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}
    return await get_all_ad_rates()


@app.post("/api/admin/rates/{network}")
async def admin_update_rate(network: str, request: Request):
    data = await request.json()
    password = data.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}

    await update_ad_rate(
        network,
        rate=data.get("rate"),
        daily_limit=data.get("daily_limit"),
        enabled=data.get("enabled"),
    )
    return {"status": "ok"}


@app.get("/api/admin/settings")
async def admin_get_settings(request: Request):
    password = request.query_params.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}
    return await get_all_admin_settings()


@app.post("/api/admin/settings")
async def admin_update_settings(request: Request):
    data = await request.json()
    password = data.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}

    for key in ["referral_reward", "min_withdraw", "farm_rate", "farm_duration_hours", "admin_password", "vpn_blocker", "max_ads_per_minute", "max_daily_withdrawals"]:
        if key in data and data[key]:
            await set_admin_setting(key, str(data[key]))
    return {"status": "ok"}


@app.get("/api/admin/users")
async def admin_users(request: Request):
    password = request.query_params.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}

    page = int(request.query_params.get("page", 0))
    users = await get_all_users(page=page, limit=50)
    return {"users": users}


# ===== WITHDRAWAL API =====

@app.post("/api/withdraw")
async def request_withdrawal(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    amount = data.get("amount", 0)
    payment_method = data.get("payment_method", "USDT")
    wallet_address = data.get("wallet_address", "")

    if not user_id or not amount or not wallet_address:
        return {"error": "user_id, amount, wallet_address required"}

    user = await get_user(user_id)
    if not user:
        return {"error": "User not found"}

    min_withdraw = float(await get_admin_setting("min_withdraw") or "0.01")
    if amount < min_withdraw:
        return {"error": f"Minimum withdrawal is {min_withdraw} USDT"}

    if user.get("balance", 0) < amount:
        return {"error": "Insufficient balance"}

    max_daily = int(await get_admin_setting("max_daily_withdrawals") or "3")
    from database import get_user_withdrawal_count_today
    daily_count = await get_user_withdrawal_count_today(user_id)
    if daily_count >= max_daily:
        return {"error": f"Daily withdrawal limit reached ({max_daily})"}

    await create_withdrawal(user_id, user.get("username", ""), amount, payment_method, wallet_address)
    return {"status": "ok", "message": "Withdrawal request submitted"}


@app.get("/api/admin/withdrawals")
async def admin_get_withdrawals(request: Request):
    password = request.query_params.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}

    status = request.query_params.get("status", None)
    page = int(request.query_params.get("page", 0))
    withdrawals = await get_all_withdrawals(status=status, page=page)
    stats = await get_withdrawal_stats()
    return {"withdrawals": withdrawals, "stats": stats}


@app.post("/api/admin/withdrawals/{withdrawal_id}/approve")
async def admin_approve_withdrawal(withdrawal_id: int, request: Request):
    data = await request.json()
    password = data.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}

    note = data.get("note", "Approved by admin")
    await update_withdrawal_status(withdrawal_id, "approved", note)
    return {"status": "ok"}


@app.post("/api/admin/withdrawals/{withdrawal_id}/reject")
async def admin_reject_withdrawal(withdrawal_id: int, request: Request):
    data = await request.json()
    password = data.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}

    note = data.get("note", "Rejected by admin")
    await update_withdrawal_status(withdrawal_id, "rejected", note)
    return {"status": "ok"}


# ===== FRAUD DETECTION API =====

@app.post("/api/fraud/log")
async def fraud_log_endpoint(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    activity_type = data.get("activity_type")
    description = data.get("description", "")
    ip_address = data.get("ip_address", "")
    severity = data.get("severity", "low")

    user = await get_user(user_id) if user_id else None
    username = user.get("username", "") if user else ""
    await log_fraud(user_id or 0, username, activity_type, description, ip_address, severity)
    return {"status": "ok"}


@app.get("/api/admin/fraud-logs")
async def admin_get_fraud_logs(request: Request):
    password = request.query_params.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}

    page = int(request.query_params.get("page", 0))
    logs = await get_fraud_logs(page=page)
    stats = await get_fraud_stats()
    return {"logs": logs, "stats": stats}


@app.get("/api/admin/fraud-stats")
async def admin_fraud_stats(request: Request):
    password = request.query_params.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}
    return await get_fraud_stats()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
