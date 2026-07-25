from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
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
    get_all_platforms,
    get_platform,
    get_platform_by_slug,
    create_platform,
    update_platform,
    delete_platform,
    get_daily_stats,
    get_dashboard_summary,
    record_daily_stats,
    update_user_ip,
    ban_user,
    unban_user,
    get_users_by_ip,
    get_fraud_ip_groups,
    get_vpn_users,
    update_session_id,
    verify_session,
)
from ads_integration import get_ad
from geoip import get_geo_info, extract_ip


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


BANNED_RESPONSE = JSONResponse(
    status_code=403,
    content={"banned": True, "status": "error", "message": "Your account has been suspended due to policy violation. Contact support for more information."}
)

SESSION_EXPIRED_RESPONSE = JSONResponse(
    status_code=401,
    content={"session_expired": True, "status": "error", "message": "Logged in from another device. Please log in again."}
)


async def check_user_banned(user_id: int):
    user = await get_user(user_id)
    if user and user.get("is_banned"):
        return True
    return False


async def check_user_session(user_id: int, session_id: str) -> bool:
    return await verify_session(user_id, session_id)


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
    session_id = data.get("session_id", "")
    if user_id:
        await add_or_update_user(
            user_id, data.get("username"), data.get("first_name")
        )
        if session_id:
            await update_session_id(user_id, session_id)
        ip = extract_ip(request)
        if ip:
            geo = await get_geo_info(ip)
            await update_user_ip(user_id, ip, geo["country"], geo["city"], geo["is_vpn"])
            if geo["is_vpn"]:
                user = await get_user(user_id)
                uname = user.get("username", "") if user else ""
                await log_fraud(user_id, uname, "vpn_detected", f"VPN/Proxy detected from {geo['country']}", ip, "medium")
        user = await get_user(user_id)
        if user and user.get("is_banned"):
            return BANNED_RESPONSE
        return {"status": "ok"}
    return {"status": "error", "message": "user_id required"}


@app.post("/api/tool/use")
async def tool_use(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    session_id = data.get("session_id", "")
    if user_id:
        if not await check_user_session(user_id, session_id):
            return SESSION_EXPIRED_RESPONSE
        if await check_user_banned(user_id):
            return BANNED_RESPONSE
        await increment_tool_use(user_id)
        return {"status": "ok"}
    return {"status": "error", "message": "user_id required"}


@app.get("/api/stats")
async def stats():
    count = await get_user_count()
    return {"total_users": count}


@app.get("/api/ad/{user_id}")
async def get_ad_for_user(user_id: int, language: str = "en", session_id: str = ""):
    if not await check_user_session(user_id, session_id):
        return SESSION_EXPIRED_RESPONSE
    if await check_user_banned(user_id):
        return BANNED_RESPONSE
    ad = await get_ad(user_id, language)
    if ad:
        return ad
    return {"error": "No ad available"}


@app.post("/api/user/balance")
async def update_user_balance(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    reward = data.get("reward", 0)
    session_id = data.get("session_id", "")
    if user_id and reward > 0:
        if not await check_user_session(user_id, session_id):
            return SESSION_EXPIRED_RESPONSE
        user = await get_user(user_id)
        if user and user.get("is_banned"):
            return BANNED_RESPONSE
        ip = extract_ip(request)
        if ip:
            geo = await get_geo_info(ip)
            await update_user_ip(user_id, ip, geo["country"], geo["city"], geo["is_vpn"])
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
async def get_user_info(user_id: int, session_id: str = ""):
    user = await get_user(user_id)
    if user:
        if user.get("is_banned"):
            return BANNED_RESPONSE
        if session_id and not await check_user_session(user_id, session_id):
            return SESSION_EXPIRED_RESPONSE
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
    limit = int(request.query_params.get("limit", 50))
    users = await get_all_users(page=page, limit=limit)
    return {"users": users}


# ===== WITHDRAWAL API =====

@app.post("/api/withdraw")
async def request_withdrawal(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    amount = data.get("amount", 0)
    payment_method = data.get("payment_method", "USDT")
    wallet_address = data.get("wallet_address", "")
    session_id = data.get("session_id", "")

    if not user_id or not amount or not wallet_address:
        return {"error": "user_id, amount, wallet_address required"}

    if not await check_user_session(user_id, session_id):
        return SESSION_EXPIRED_RESPONSE

    user = await get_user(user_id)
    if not user:
        return {"error": "User not found"}

    if user.get("is_banned"):
        return BANNED_RESPONSE

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


# ===== AD PLATFORM MANAGEMENT API =====

@app.get("/api/admin/platforms")
async def admin_get_platforms(request: Request):
    password = request.query_params.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}
    platforms = await get_all_platforms()
    return {"platforms": platforms}


@app.post("/api/admin/platforms")
async def admin_create_platform(request: Request):
    data = await request.json()
    password = data.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}

    name = data.get("name", "")
    slug = data.get("slug", "")
    if not name or not slug:
        return {"error": "Name and slug required"}

    existing = await get_platform_by_slug(slug)
    if existing:
        return {"error": "Slug already exists"}

    platform_id = await create_platform(
        name=name, slug=slug, ad_type=data.get("ad_type", "Rewarded Ad"),
        script_code=data.get("script_code", ""), placement_id=data.get("placement_id", ""),
        api_key=data.get("api_key", ""), rate=data.get("rate", 0.0005),
        daily_limit=data.get("daily_limit", 50), enabled=data.get("enabled", 1),
    )
    return {"status": "ok", "id": platform_id}


@app.post("/api/admin/platforms/{platform_id}")
async def admin_update_platform(platform_id: int, request: Request):
    data = await request.json()
    password = data.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}

    platform = await get_platform(platform_id)
    if not platform:
        return {"error": "Platform not found"}

    update_data = {}
    for key in ["name", "slug", "ad_type", "script_code", "placement_id", "api_key", "rate", "daily_limit", "enabled"]:
        if key in data:
            update_data[key] = data[key]

    if update_data:
        await update_platform(platform_id, **update_data)
    return {"status": "ok"}


@app.post("/api/admin/platforms/{platform_id}/delete")
async def admin_delete_platform(platform_id: int, request: Request):
    data = await request.json()
    password = data.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}

    platform = await get_platform(platform_id)
    if not platform:
        return {"error": "Platform not found"}

    await delete_platform(platform_id)
    return {"status": "ok"}


# ===== DASHBOARD / ANALYTICS API =====

@app.get("/api/admin/dashboard")
async def admin_dashboard(request: Request):
    password = request.query_params.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}

    days = int(request.query_params.get("days", 30))
    await record_daily_stats()
    summary = await get_dashboard_summary()
    daily = await get_daily_stats(days)
    return {"summary": summary, "daily": daily}


@app.get("/api/admin/dashboard/daily")
async def admin_dashboard_daily(request: Request):
    password = request.query_params.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}

    days = int(request.query_params.get("days", 30))
    await record_daily_stats()
    daily = await get_daily_stats(days)
    return {"daily": daily}


# ===== BAN / UNBAN USER =====

@app.post("/api/admin/ban-user")
async def admin_ban_user(request: Request):
    data = await request.json()
    password = data.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}

    user_id = data.get("user_id")
    if not user_id:
        return {"error": "user_id required"}

    await ban_user(user_id)
    user = await get_user(user_id)
    if user:
        ip = user.get("ip_address", "")
        await log_fraud(user_id, user.get("username", ""), "user_banned", "Banned by admin", ip, "high")
    return {"status": "ok"}


@app.post("/api/admin/unban-user")
async def admin_unban_user(request: Request):
    data = await request.json()
    password = data.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}

    user_id = data.get("user_id")
    if not user_id:
        return {"error": "user_id required"}

    await unban_user(user_id)
    return {"status": "ok"}


@app.get("/api/admin/fraud-ip-groups")
async def admin_fraud_ip_groups(request: Request):
    password = request.query_params.get("password", "")
    stored = await get_admin_setting("admin_password")
    if not stored or stored != password:
        return {"error": "Unauthorized"}

    groups = await get_fraud_ip_groups()
    vpn_users = await get_vpn_users()
    return {"ip_groups": groups, "vpn_users": vpn_users}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
