from contextlib import asynccontextmanager
import hashlib
import hmac
import time
import json
import struct
import base64
import os
import urllib.parse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import BOT_TOKEN, HOST, PORT
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
    check_referral_release,
    get_referral_summary,
    get_all_referrals,
    flag_referral,
    auto_flag_same_ip_referrals,
    flag_user,
    set_user_status,
    get_flagged_users,
    create_login_log,
    get_login_logs,
    get_login_log_stats,
    cleanup_old_login_logs,
    update_last_active,
    update_last_seen,
    get_live_users_count,
    create_task_activity,
    get_task_activities,
    get_task_activity_stats,
    create_transaction,
    get_accounting_summary,
    get_transactions,
    get_user_accounting_list,
    get_user_transaction_history,
    verify_password,
    create_admin_user,
    get_admin_user_by_username,
    get_admin_user_by_id,
    get_all_admin_users,
    update_admin_user,
    delete_admin_user,
    log_admin_action,
    get_admin_audit_logs,
    set_user_password,
    verify_user_password,
    has_user_password,
    set_user_2fa,
    get_user_2fa,
)
from ads_integration import get_ad
from geoip import get_geo_info, extract_ip


# ===== TOTP (2FA) =====

def generate_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode('utf-8')


def generate_totp_code(secret: str, time_step: int = 30) -> str:
    key = base64.b32decode(secret, casefold=True)
    counter = int(time.time()) // time_step
    msg = struct.pack('>Q', counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0f
    code = struct.unpack('>I', h[offset:offset+4])[0] & 0x7fffffff
    return str(code % 1000000).zfill(6)


def verify_totp_code(secret: str, code: str, window: int = 1) -> bool:
    for offset in range(-window, window + 1):
        key = base64.b32decode(secret, casefold=True)
        counter = (int(time.time()) // 30) + offset
        msg = struct.pack('>Q', counter)
        h = hmac.new(key, msg, hashlib.sha1).digest()
        off = h[-1] & 0x0f
        gen_code = struct.unpack('>I', h[off:off+4])[0] & 0x7fffffff
        if str(gen_code % 1000000).zfill(6) == code:
            return True
    return False


# ===== RBAC AUTH SYSTEM =====

async def authenticate_admin(password: str, request: Request = None) -> dict:
    """Authenticate via legacy admin_password OR new admin_users table.
    Returns {admin_id, username, role, permissions, country_restriction} or None."""
    stored = await get_admin_setting("admin_password")
    if stored and stored == password:
        return {
            "admin_id": 0,
            "username": "super_admin",
            "role": "super_admin",
            "permissions": ["manage_admins", "manage_users", "manage_platforms", "manage_rates",
                            "process_withdrawals", "manage_fraud", "manage_settings", "view_accounting",
                            "manage_referrals", "view_logs", "view_task_activities", "view_audit_log"],
            "country_restriction": "",
        }
    all_admins = await get_all_admin_users()
    for admin in all_admins:
        if verify_password(password, admin["password_hash"], admin["salt"]):
            if admin["status"] != "active":
                continue
            country_allowed = admin.get("country_restriction", "BD") or ""
            if country_allowed and request:
                ip = extract_ip(request)
                if ip:
                    geo = await get_geo_info(ip)
                    user_country = geo.get("country", "")
                    if user_country and user_country != country_allowed:
                        continue
            await update_admin_user(admin["id"], last_login=time.strftime("%Y-%m-%d %H:%M:%S"))
            return {
                "admin_id": admin["id"],
                "username": admin["username"],
                "role": admin["role"],
                "permissions": json.loads(admin["permissions"]) if admin["permissions"] else [],
                "country_restriction": country_allowed,
            }
    return None


def has_permission(admin: dict, perm: str) -> bool:
    if not admin:
        return False
    if admin["role"] == "super_admin":
        return True
    return perm in admin.get("permissions", [])


async def require_admin(request: Request, permission: str = None):
    """Extract password from query params, authenticate, optionally check permission.
    Returns (admin_info, error_response). error_response is None if OK."""
    password = request.query_params.get("password", "")
    admin = await authenticate_admin(password, request)
    if not admin:
        return None, {"error": "Unauthorized"}
    if permission and not has_permission(admin, permission):
        return None, {"error": "Forbidden", "message": f"Missing permission: {permission}"}
    return admin, None


def check_admin(password: str) -> bool:
    """Legacy sync check — kept for backward compatibility."""
    import sqlite3
    conn = sqlite3.connect("bot_users.db")
    row = conn.execute("SELECT value FROM admin_settings WHERE key='admin_password'").fetchone()
    conn.close()
    return row and row[0] == password


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    from database import create_admin_user, get_admin_user_by_username
    existing = await get_admin_user_by_username("admin")
    if not existing:
        await create_admin_user("admin", "admin@bot.local", "admin123", "super_admin")
        print("[auth] Created default super_admin: admin / admin123")
    import asyncio
    async def weekly_login_log_cleanup():
        while True:
            await asyncio.sleep(7 * 24 * 3600)
            try:
                enabled = await get_admin_setting("login_log_cleanup_enabled")
                if enabled == "1":
                    deleted = await cleanup_old_login_logs(30)
                    if deleted > 0:
                        print(f"[cron] Clean up {deleted} old SUCCESS login logs")
            except Exception as e:
                print(f"[cron] Login log cleanup error: {e}")
    task = asyncio.create_task(weekly_login_log_cleanup())
    yield
    task.cancel()


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
    single_device = await get_admin_setting("enable_single_device_login")
    if single_device != "1":
        return True
    return await verify_session(user_id, session_id)


# ===== TELEGRAM INITDATA VERIFICATION =====
def verify_telegram_initdata(init_data: str) -> dict:
    """Verify Telegram WebApp initData using HMAC-SHA256. Returns parsed user dict or empty dict."""
    if not init_data or not BOT_TOKEN:
        return {}
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data))
        received_hash = parsed.pop("hash", "")
        if not received_hash:
            return {}
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )
        secret_key = hmac.new(
            b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
        ).digest()
        computed_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()
        if computed_hash == received_hash:
            user_str = parsed.get("user", "{}")
            return json.loads(user_str) if user_str else {}
        return {}
    except Exception:
        return {}


# ===== AD TIMING VALIDATION =====
_ad_start_times = {}  # user_id -> timestamp when ad started

VPN_BLOCKED_RESPONSE = JSONResponse(
    status_code=403,
    content={"vpn_blocked": True, "status": "error", "message": "VPN/Proxy usage is not allowed. Please disable your VPN and try again."}
)


async def check_vpn_blocked(user_id: int) -> bool:
    vpn_setting = await get_admin_setting("vpn_blocker")
    if vpn_setting != "1":
        return False
    user = await get_user(user_id)
    if user and user.get("is_vpn"):
        return True
    return False


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
    init_data = data.get("init_data", "")
    device_platform = data.get("platform", "")
    user_agent = request.headers.get("User-Agent", "")

    if not user_id:
        return {"status": "error", "message": "user_id required"}

    ip = extract_ip(request)
    is_vpn = False
    location = ""
    log_status = "SUCCESS"
    failure_reason = ""

    # Silent Telegram initData hash verification
    initdata_check = await get_admin_setting("enable_initdata_check")
    if initdata_check == "1" and init_data:
        verified_user = verify_telegram_initdata(init_data)
        if verified_user and verified_user.get("id"):
            user_id = verified_user["id"]
        elif init_data:
            log_status = "FAILED"
            failure_reason = "Invalid initData hash"

    await add_or_update_user(
        user_id, data.get("username"), data.get("first_name")
    )
    if session_id:
        await update_session_id(user_id, session_id)

    if ip:
        geo = await get_geo_info(ip)
        await update_user_ip(user_id, ip, geo["country"], geo["city"], geo["is_vpn"])
        is_vpn = geo["is_vpn"]
        location = f"{geo['city']}, {geo['country']}".strip(", ")
        if geo["is_vpn"]:
            user = await get_user(user_id)
            uname = user.get("username", "") if user else ""
            await log_fraud(user_id, uname, "vpn_detected", f"VPN/Proxy detected from {geo['country']}", ip, "medium")
            await flag_user(user_id, f"VPN/Proxy detected from {geo['country']}")

    user = await get_user(user_id)
    if user and user.get("is_banned"):
        failure_reason = "Account banned"
        await create_login_log(user_id, data.get("username", ""), data.get("first_name", ""),
                               "FAILED", "telegram_initdata", ip, location, is_vpn,
                               device_platform, user_agent, failure_reason)
        return BANNED_RESPONSE

    await create_login_log(user_id, data.get("username", ""), data.get("first_name", ""),
                           log_status, "telegram_initdata", ip, location, is_vpn,
                           device_platform, user_agent, failure_reason)

    await update_last_active(user_id)
    await update_last_seen(user_id)

    # VPN soft warning — return flag instead of hard block
    vpn_setting = await get_admin_setting("vpn_blocker")
    if vpn_setting == "1" and is_vpn:
        return {"status": "ok", "vpn_warning": True, "message": "VPN/Proxy detected. Please disable VPN to continue earning."}

    return {"status": "ok", "vpn_warning": False}


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
        # VPN soft warning
        user = await get_user(user_id)
        vpn_setting = await get_admin_setting("vpn_blocker")
        if vpn_setting == "1" and user and user.get("is_vpn"):
            return {"status": "error", "vpn_warning": True, "message": "VPN detected. Please disable VPN to earn rewards."}
        await increment_tool_use(user_id)
        await update_last_active(user_id)
        # Record ad start time for invisible time validation
        _ad_start_times[user_id] = time.time()
        return {"status": "ok"}
    return {"status": "error", "message": "user_id required"}


@app.post("/api/user/heartbeat")
async def user_heartbeat(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    if not user_id:
        return {"status": "error", "message": "user_id required"}
    await update_last_seen(user_id)
    return {"status": "ok"}


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
    if await check_vpn_blocked(user_id):
        return VPN_BLOCKED_RESPONSE
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

        # Invisible time validation — block cheaters who skip ad wait
        strict_timer = await get_admin_setting("enable_strict_timer")
        if strict_timer == "1":
            min_ad_seconds = 4
            start_time = _ad_start_times.get(user_id)
            if start_time:
                elapsed = time.time() - start_time
                if elapsed < min_ad_seconds:
                    _ad_start_times.pop(user_id, None)
                    return {"status": "error", "message": "Too fast. Please wait for the ad to finish.", "time_reject": True}
                _ad_start_times.pop(user_id, None)

        # VPN soft warning
        ip = extract_ip(request)
        is_vpn = False
        if ip:
            geo = await get_geo_info(ip)
            await update_user_ip(user_id, ip, geo["country"], geo["city"], geo["is_vpn"])
            is_vpn = geo["is_vpn"]

        vpn_setting = await get_admin_setting("vpn_blocker")
        if vpn_setting == "1" and is_vpn:
            return {"status": "error", "vpn_warning": True, "message": "VPN detected. Please disable VPN to earn rewards."}

        await update_balance(user_id, reward)
        await update_last_active(user_id)
        await check_referral_release(user_id)

        platform_name = data.get("platform_name", "")
        await create_task_activity(
            user_id=user_id,
            username=user.get("username", "") if user else "",
            first_name=user.get("first_name", "") if user else "",
            platform_name=platform_name,
            ad_type="Rewarded",
            reward_amount=reward,
            status="COMPLETED",
            ip_address=ip or "",
        )

        await create_transaction(
            txn_type="EXPENSE",
            source=f"Reward: {platform_name or 'Unknown'}",
            amount=reward,
            user_id=user_id,
            status="COMPLETED",
        )

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
        twofa = await get_admin_setting("admin_2fa_enabled")
        if twofa == "1":
            return {"status": "2fa_required", "admin_username": "super_admin"}
        return {"status": "ok"}
    all_admins = await get_all_admin_users()
    for admin in all_admins:
        if verify_password(password, admin["password_hash"], admin["salt"]):
            if admin["status"] != "active":
                return {"status": "error", "message": "Account disabled"}
            if admin["two_factor_enabled"]:
                return {"status": "2fa_required", "admin_username": admin["username"]}
            return {"status": "ok"}
    return {"status": "error", "message": "Wrong password"}


@app.post("/api/admin/2fa/verify-login")
async def admin_2fa_verify_login(request: Request):
    data = await request.json()
    password = data.get("password", "")
    code = data.get("code", "")
    if not password or not code:
        return {"status": "error", "message": "Password and code required"}
    stored = await get_admin_setting("admin_password")
    if stored and stored == password:
        secret = await get_admin_setting("admin_2fa_secret")
        if not secret:
            return {"status": "error", "message": "2FA not configured"}
        if not verify_totp_code(secret, code):
            return {"status": "error", "message": "Invalid code"}
        return {"status": "ok"}
    all_admins = await get_all_admin_users()
    for admin in all_admins:
        if verify_password(password, admin["password_hash"], admin["salt"]):
            if not admin["two_factor_enabled"] or not admin["two_factor_secret"]:
                return {"status": "error", "message": "2FA not enabled"}
            if not verify_totp_code(admin["two_factor_secret"], code):
                return {"status": "error", "message": "Invalid code"}
            return {"status": "ok"}
    return {"status": "error", "message": "Invalid credentials"}


@app.get("/api/admin/2fa/status")
async def admin_2fa_status(request: Request):
    admin, err = await require_admin(request)
    if err:
        return err
    if admin["admin_id"] == 0:
        val = await get_admin_setting("admin_2fa_enabled")
        return {"enabled": val == "1"}
    admin_user = await get_admin_user_by_id(admin["admin_id"])
    if not admin_user:
        return {"error": "Admin not found"}
    return {"enabled": bool(admin_user["two_factor_enabled"])}


@app.post("/api/admin/2fa/setup")
async def admin_2fa_setup(request: Request):
    admin, err = await require_admin(request)
    if err:
        return err
    if admin["admin_id"] == 0:
        val = await get_admin_setting("admin_2fa_enabled")
        if val == "1":
            return {"error": "2FA already enabled. Disable first."}
        secret = generate_totp_secret()
        await set_admin_setting("admin_2fa_secret", secret)
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=otpauth://totp/AdBot:super_admin?secret={secret}&issuer=AdBot&digits=6&period=30"
        return {"secret": secret, "qr_url": qr_url}
    admin_user = await get_admin_user_by_id(admin["admin_id"])
    if not admin_user:
        return {"error": "Admin not found"}
    if admin_user["two_factor_enabled"]:
        return {"error": "2FA already enabled. Disable first."}
    secret = generate_totp_secret()
    await update_admin_user(admin["admin_id"], two_factor_secret=secret)
    issuer = "AdBot"
    label = admin["username"]
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=otpauth://totp/{issuer}:{label}?secret={secret}&issuer={issuer}&digits=6&period=30"
    return {"secret": secret, "qr_url": qr_url}


@app.post("/api/admin/2fa/verify")
async def admin_2fa_verify(request: Request):
    admin, err = await require_admin(request)
    if err:
        return err
    data = await request.json()
    code = data.get("code", "")
    if not code:
        return {"error": "Code required"}
    if admin["admin_id"] == 0:
        secret = await get_admin_setting("admin_2fa_secret")
        if not secret:
            return {"error": "Run setup first"}
        if not verify_totp_code(secret, code):
            return {"error": "Invalid code"}
        await set_admin_setting("admin_2fa_enabled", "1")
        await log_admin_action(0, "super_admin", "Enabled 2FA", "", "")
        return {"status": "ok"}
    admin_user = await get_admin_user_by_id(admin["admin_id"])
    if not admin_user:
        return {"error": "Admin not found"}
    secret = admin_user["two_factor_secret"]
    if not secret:
        return {"error": "Run setup first"}
    if not verify_totp_code(secret, code):
        return {"error": "Invalid code"}
    await update_admin_user(admin["admin_id"], two_factor_enabled=1)
    await log_admin_action(admin["admin_id"], admin["username"], "Enabled 2FA", "", "")
    return {"status": "ok"}


@app.post("/api/admin/2fa/disable")
async def admin_2fa_disable(request: Request):
    admin, err = await require_admin(request)
    if err:
        return err
    data = await request.json()
    password = data.get("password", "")
    if not password:
        return {"error": "Password required to disable 2FA"}
    if admin["admin_id"] == 0:
        stored = await get_admin_setting("admin_password")
        if stored != password:
            return {"error": "Wrong password"}
        await set_admin_setting("admin_2fa_enabled", "0")
        await set_admin_setting("admin_2fa_secret", "")
        await log_admin_action(0, "super_admin", "Disabled 2FA", "", "")
        return {"status": "ok"}
    admin_user = await get_admin_user_by_id(admin["admin_id"])
    if not admin_user:
        return {"error": "Admin not found"}
    if not verify_password(password, admin_user["password_hash"], admin_user["salt"]):
        return {"error": "Wrong password"}
    await update_admin_user(admin["admin_id"], two_factor_enabled=0, two_factor_secret="")
    await log_admin_action(admin["admin_id"], admin["username"], "Disabled 2FA", "", "")
    return {"status": "ok"}


@app.get("/api/admin/me")
async def admin_me(request: Request):
    admin, err = await require_admin(request)
    if err:
        return err
    return {"admin_id": admin["admin_id"], "username": admin["username"], "role": admin["role"], "permissions": admin["permissions"]}


@app.get("/api/admin/stats")
async def admin_stats(request: Request):
    admin, err = await require_admin(request)
    if err:
        return err

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


@app.get("/api/admin/live-users-count")
async def admin_live_users_count(request: Request):
    admin, err = await require_admin(request)
    if err:
        return err
    count = await get_live_users_count(2)
    return {"live_users": count}


@app.get("/api/admin/rates")
async def admin_rates(request: Request):
    admin, err = await require_admin(request)
    if err:
        return err
    return await get_all_ad_rates()


@app.post("/api/admin/rates/{network}")
async def admin_update_rate(network: str, request: Request):
    admin, err = await require_admin(request, "manage_rates")
    if err:
        return err
    data = await request.json()

    await update_ad_rate(
        network,
        rate=data.get("rate"),
        daily_limit=data.get("daily_limit"),
        enabled=data.get("enabled"),
    )
    return {"status": "ok"}


@app.get("/api/admin/settings")
async def admin_get_settings(request: Request):
    admin, err = await require_admin(request)
    if err:
        return err
    return await get_all_admin_settings()


@app.post("/api/admin/settings")
async def admin_update_settings(request: Request):
    admin, err = await require_admin(request, "manage_settings")
    if err:
        return err
    data = await request.json()

    for key in ["referral_reward", "min_withdraw", "farm_rate", "farm_duration_hours", "admin_password", "vpn_blocker", "max_ads_per_minute", "max_daily_withdrawals", "min_ads_for_referral", "enable_initdata_check", "enable_single_device_login", "enable_strict_timer", "auto_block_enabled"]:
        if key in data and data[key]:
            await set_admin_setting(key, str(data[key]))
    return {"status": "ok"}


@app.get("/api/admin/users")
async def admin_users(request: Request):
    admin, err = await require_admin(request, "manage_users")
    if err:
        return err

    page = int(request.query_params.get("page", 0))
    limit = int(request.query_params.get("limit", 50))
    filter_type = request.query_params.get("filter", "")
    search = request.query_params.get("search", "")
    result = await get_all_users(page=page, limit=limit, filter_type=filter_type, search=search)
    return result


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
    admin, err = await require_admin(request, "process_withdrawals")
    if err:
        return err

    status = request.query_params.get("status", None)
    page = int(request.query_params.get("page", 0))
    withdrawals = await get_all_withdrawals(status=status, page=page)
    stats = await get_withdrawal_stats()
    return {"withdrawals": withdrawals, "stats": stats}


@app.post("/api/admin/withdrawals/{withdrawal_id}/approve")
async def admin_approve_withdrawal(withdrawal_id: int, request: Request):
    admin, err = await require_admin(request, "process_withdrawals")
    if err:
        return err
    data = await request.json()

    note = data.get("note", "Approved by admin")
    await update_withdrawal_status(withdrawal_id, "approved", note)
    withdrawal = await get_withdrawal(withdrawal_id)
    if withdrawal:
        await create_transaction(
            txn_type="EXPENSE",
            source=f"Withdrawal: {withdrawal.get('username', '') or withdrawal.get('user_id', '')}",
            amount=withdrawal.get("amount", 0),
            user_id=withdrawal.get("user_id", 0),
            status="COMPLETED",
        )
    return {"status": "ok"}


@app.post("/api/admin/withdrawals/{withdrawal_id}/reject")
async def admin_reject_withdrawal(withdrawal_id: int, request: Request):
    admin, err = await require_admin(request, "process_withdrawals")
    if err:
        return err
    data = await request.json()

    note = data.get("note", "Rejected by admin")
    await update_withdrawal_status(withdrawal_id, "rejected", note)
    return {"status": "ok"}


# ===== REFERRAL MANAGEMENT API =====

@app.get("/api/admin/referral-summary")
async def admin_referral_summary(request: Request):
    admin, err = await require_admin(request, "manage_referrals")
    if err:
        return err
    return await get_referral_summary()


@app.get("/api/admin/referrals")
async def admin_referrals(request: Request):
    admin, err = await require_admin(request, "manage_referrals")
    if err:
        return err

    page = int(request.query_params.get("page", 0))
    search = request.query_params.get("search", "")
    referrals = await get_all_referrals(page=page, search=search)
    return {"referrals": referrals}


@app.post("/api/admin/referrals/{referral_id}/flag")
async def admin_flag_referral(referral_id: int, request: Request):
    admin, err = await require_admin(request, "manage_referrals")
    if err:
        return err
    data = await request.json()

    status = data.get("status", "flagged")
    await flag_referral(referral_id, status)
    return {"status": "ok"}


@app.post("/api/admin/referrals/auto-flag-ip")
async def admin_auto_flag_ip(request: Request):
    admin, err = await require_admin(request, "manage_referrals")
    if err:
        return err
    data = await request.json()

    await auto_flag_same_ip_referrals()
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
    admin, err = await require_admin(request, "manage_fraud")
    if err:
        return err

    page = int(request.query_params.get("page", 0))
    logs = await get_fraud_logs(page=page)
    stats = await get_fraud_stats()
    return {"logs": logs, "stats": stats}


@app.get("/api/admin/fraud-stats")
async def admin_fraud_stats(request: Request):
    admin, err = await require_admin(request, "manage_fraud")
    if err:
        return err
    return await get_fraud_stats()


# ===== AD PLATFORM MANAGEMENT API =====

@app.get("/api/admin/platforms")
async def admin_get_platforms(request: Request):
    admin, err = await require_admin(request)
    if err:
        return err
    platforms = await get_all_platforms()
    return {"platforms": platforms}


@app.post("/api/admin/platforms")
async def admin_create_platform(request: Request):
    admin, err = await require_admin(request)
    if err:
        return err
    data = await request.json()

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
    admin, err = await require_admin(request)
    if err:
        return err
    data = await request.json()

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
    admin, err = await require_admin(request)
    if err:
        return err
    data = await request.json()

    platform = await get_platform(platform_id)
    if not platform:
        return {"error": "Platform not found"}

    await delete_platform(platform_id)
    return {"status": "ok"}


# ===== DASHBOARD / ANALYTICS API =====

@app.get("/api/admin/dashboard")
async def admin_dashboard(request: Request):
    admin, err = await require_admin(request)
    if err:
        return err

    days = int(request.query_params.get("days", 30))
    await record_daily_stats()
    summary = await get_dashboard_summary()
    daily = await get_daily_stats(days)
    return {"summary": summary, "daily": daily}


@app.get("/api/admin/dashboard/daily")
async def admin_dashboard_daily(request: Request):
    admin, err = await require_admin(request)
    if err:
        return err

    days = int(request.query_params.get("days", 30))
    await record_daily_stats()
    daily = await get_daily_stats(days)
    return {"daily": daily}


# ===== BAN / UNBAN USER =====

@app.post("/api/admin/ban-user")
async def admin_ban_user(request: Request):
    admin, err = await require_admin(request, "manage_users")
    if err:
        return err
    data = await request.json()

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
    admin, err = await require_admin(request, "manage_users")
    if err:
        return err
    data = await request.json()

    user_id = data.get("user_id")
    if not user_id:
        return {"error": "user_id required"}

    await unban_user(user_id)
    return {"status": "ok"}


# ===== FLAGGED USERS / SILENT MONITORING =====

@app.get("/api/admin/flagged-users")
async def admin_flagged_users(request: Request):
    admin, err = await require_admin(request, "manage_fraud")
    if err:
        return err
    users = await get_flagged_users()
    return {"flagged_users": users}


@app.post("/api/admin/flag-user")
async def admin_flag_user_endpoint(request: Request):
    admin, err = await require_admin(request, "manage_fraud")
    if err:
        return err
    data = await request.json()
    user_id = data.get("user_id")
    reason = data.get("reason", "Suspicious activity")
    if not user_id:
        return {"error": "user_id required"}
    await flag_user(user_id, reason)
    return {"status": "ok"}


@app.post("/api/admin/dismiss-flag")
async def admin_dismiss_flag(request: Request):
    admin, err = await require_admin(request, "manage_fraud")
    if err:
        return err
    data = await request.json()
    user_id = data.get("user_id")
    if not user_id:
        return {"error": "user_id required"}
    await set_user_status(user_id, "active", "")
    return {"status": "ok"}


@app.get("/api/admin/fraud-ip-groups")
async def admin_fraud_ip_groups(request: Request):
    admin, err = await require_admin(request, "manage_fraud")
    if err:
        return err

    groups = await get_fraud_ip_groups()
    vpn_users = await get_vpn_users()
    return {"ip_groups": groups, "vpn_users": vpn_users}


# ===== LOGIN LOGS =====

@app.get("/api/admin/login-logs")
async def admin_login_logs(request: Request):
    admin, err = await require_admin(request, "view_logs")
    if err:
        return err

    page = int(request.query_params.get("page", 1))
    per_page = int(request.query_params.get("per_page", 50))
    search = request.query_params.get("search", "")
    status_filter = request.query_params.get("status", "")
    vpn_filter = request.query_params.get("vpn", "")

    result = await get_login_logs(page, per_page, search, status_filter, vpn_filter)
    stats = await get_login_log_stats()
    result["stats"] = stats
    result["cleanup_enabled"] = (await get_admin_setting("login_log_cleanup_enabled")) == "1"
    return result


@app.post("/api/admin/login-logs/cleanup")
async def admin_login_logs_cleanup(request: Request):
    admin, err = await require_admin(request, "view_logs")
    if err:
        return err
    data = await request.json()

    enabled = data.get("enabled")
    if enabled is not None:
        await set_admin_setting("login_log_cleanup_enabled", "1" if enabled else "0")

    deleted = await cleanup_old_login_logs(30)
    return {"status": "ok", "deleted": deleted}


# ===== TASK ACTIVITIES =====

@app.get("/api/admin/task-activities")
async def admin_task_activities(request: Request):
    admin, err = await require_admin(request, "view_task_activities")
    if err:
        return err

    page = int(request.query_params.get("page", 1))
    per_page = int(request.query_params.get("per_page", 50))
    search = request.query_params.get("search", "")
    platform_filter = request.query_params.get("platform", "")

    result = await get_task_activities(page, per_page, search, platform_filter)
    stats = await get_task_activity_stats()
    result["stats"] = stats
    return result


# ===== ACCOUNTING API =====

@app.get("/api/admin/accounting")
async def admin_accounting(request: Request):
    admin, err = await require_admin(request, "view_accounting")
    if err:
        return err

    date_filter = request.query_params.get("date_filter", "")
    page = int(request.query_params.get("page", 1))

    summary = await get_accounting_summary()
    txns = await get_transactions(page=page, date_filter=date_filter)

    return {**summary, **txns}


@app.get("/api/admin/accounting/users")
async def admin_accounting_users(request: Request):
    admin, err = await require_admin(request, "view_accounting")
    if err:
        return err

    search = request.query_params.get("search", "")
    page = int(request.query_params.get("page", 1))

    return await get_user_accounting_list(search=search, page=page)


@app.get("/api/admin/accounting/users/{user_id}/history")
async def admin_accounting_user_history(user_id: int, request: Request):
    admin, err = await require_admin(request, "view_accounting")
    if err:
        return err

    return await get_user_transaction_history(user_id)


# ===== ADMIN USER MANAGEMENT =====

@app.get("/api/admin/admin-users")
async def list_admin_users(request: Request):
    admin, err = await require_admin(request, "manage_admins")
    if err:
        return err
    users = await get_all_admin_users()
    return {"admin_users": users}


@app.post("/api/admin/admin-users")
async def create_new_admin(request: Request):
    admin, err = await require_admin(request, "manage_admins")
    if err:
        return err
    data = await request.json()
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    role = data.get("role", "moderator")
    permissions = data.get("permissions", [])
    country_restriction = data.get("country_restriction", "BD")
    if not username or not password:
        return {"error": "Username and password required"}
    result = await create_admin_user(username, email, password, role, permissions, country_restriction)
    if result.get("error"):
        return result
    await log_admin_action(admin["admin_id"], admin["username"],
                           f"Created admin user: {username}", f"role={role}", "")
    return {"status": "ok"}


@app.post("/api/admin/admin-users/{admin_id}/update")
async def update_existing_admin(admin_id: int, request: Request):
    admin, err = await require_admin(request, "manage_admins")
    if err:
        return err
    data = await request.json()
    updates = {}
    if "email" in data:
        updates["email"] = data["email"]
    if "role" in data:
        updates["role"] = data["role"]
    if "permissions" in data:
        updates["permissions"] = data["permissions"]
    if "status" in data:
        updates["status"] = data["status"]
    if "country_restriction" in data:
        updates["country_restriction"] = data["country_restriction"]
    if "password" in data and data["password"]:
        from database import hash_password
        pw_hash, salt = hash_password(data["password"])
        updates["password_hash"] = pw_hash
        updates["salt"] = salt
    await update_admin_user(admin_id, **updates)
    target = await get_admin_user_by_id(admin_id)
    await log_admin_action(admin["admin_id"], admin["username"],
                           f"Updated admin: {target['username'] if target else admin_id}",
                           json.dumps(list(updates.keys())), "")
    return {"status": "ok"}


@app.post("/api/admin/admin-users/{admin_id}/delete")
async def delete_existing_admin(admin_id: int, request: Request):
    admin, err = await require_admin(request, "manage_admins")
    if err:
        return err
    target = await get_admin_user_by_id(admin_id)
    if target and target["role"] == "super_admin":
        return {"error": "Cannot delete super admin"}
    await delete_admin_user(admin_id)
    await log_admin_action(admin["admin_id"], admin["username"],
                           f"Deleted admin: {target['username'] if target else admin_id}", "", "")
    return {"status": "ok"}


@app.get("/api/admin/audit-logs")
async def list_audit_logs(request: Request):
    admin, err = await require_admin(request, "view_audit_log")
    if err:
        return err
    page = int(request.query_params.get("page", 1))
    search = request.query_params.get("search", "")
    return await get_admin_audit_logs(page=page, search=search)


@app.post("/api/admin/change-password")
async def admin_change_password(request: Request):
    admin, err = await require_admin(request)
    if err:
        return err
    data = await request.json()
    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")
    if not current_password or not new_password:
        return {"error": "Both current and new password required"}
    if len(new_password) < 6:
        return {"error": "New password must be at least 6 characters"}
    if admin["admin_id"] == 0:
        stored = await get_admin_setting("admin_password")
        if stored != current_password:
            return {"error": "Current password is wrong"}
        await set_admin_setting("admin_password", new_password)
    else:
        admin_user = await get_admin_user_by_id(admin["admin_id"])
        if not admin_user or not verify_password(current_password, admin_user["password_hash"], admin_user["salt"]):
            return {"error": "Current password is wrong"}
        pw_hash, salt = hash_password(new_password)
        await update_admin_user(admin["admin_id"], password_hash=pw_hash, salt=salt)
    await log_admin_action(admin["admin_id"], admin["username"], "Changed own password", "", "")
    return {"status": "ok"}


# ===== USER PASSWORD & 2FA =====

@app.post("/api/user/set-password")
async def user_set_password(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    password = data.get("password", "")
    session_id = data.get("session_id", "")
    if not user_id or len(password) < 6:
        return {"error": "Password must be at least 6 characters"}
    if not await check_user_session(user_id, session_id):
        return SESSION_EXPIRED_RESPONSE
    await set_user_password(user_id, password)
    return {"status": "ok"}


@app.post("/api/user/verify-password")
async def user_verify_password(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    password = data.get("password", "")
    session_id = data.get("session_id", "")
    if not user_id or not password:
        return {"error": "Invalid request"}
    if not await check_user_session(user_id, session_id):
        return SESSION_EXPIRED_RESPONSE
    ok = await verify_user_password(user_id, password)
    if not ok:
        return {"error": "Wrong password"}
    return {"status": "ok"}


@app.get("/api/user/2fa/status")
async def user_2fa_status(request: Request):
    user_id = request.query_params.get("user_id", "")
    session_id = request.query_params.get("session_id", "")
    if not user_id:
        return {"error": "Invalid request"}
    if not await check_user_session(int(user_id), session_id):
        return SESSION_EXPIRED_RESPONSE
    return await get_user_2fa(int(user_id))


@app.post("/api/user/2fa/setup")
async def user_2fa_setup(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    session_id = data.get("session_id", "")
    if not user_id:
        return {"error": "Invalid request"}
    if not await check_user_session(user_id, session_id):
        return SESSION_EXPIRED_RESPONSE
    secret = generate_totp_secret()
    await set_user_2fa(user_id, secret, enabled=False)
    otpauth_url = f"otpauth://totp/mynhp:{user_id}?secret={secret}&issuer=mynhp&digits=6&period=30"
    return {"secret": secret, "otpauth_url": otpauth_url}


@app.post("/api/user/2fa/verify")
async def user_2fa_verify(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    code = data.get("code", "")
    session_id = data.get("session_id", "")
    if not user_id or not code:
        return {"error": "Invalid request"}
    if not await check_user_session(user_id, session_id):
        return SESSION_EXPIRED_RESPONSE
    info = await get_user_2fa(user_id)
    if not info["secret"]:
        return {"error": "2FA not set up"}
    if verify_totp_code(info["secret"], code):
        await set_user_2fa(user_id, info["secret"], enabled=True)
        return {"status": "ok"}
    return {"error": "Invalid code"}


@app.post("/api/user/2fa/disable")
async def user_2fa_disable(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    password = data.get("password", "")
    session_id = data.get("session_id", "")
    if not user_id or not password:
        return {"error": "Invalid request"}
    if not await check_user_session(user_id, session_id):
        return SESSION_EXPIRED_RESPONSE
    ok = await verify_user_password(user_id, password)
    if not ok:
        return {"error": "Wrong password"}
    await set_user_2fa(user_id, "", enabled=False)
    return {"status": "ok"}


@app.get("/api/user/has-password")
async def user_has_password(request: Request):
    user_id = request.query_params.get("user_id", "")
    if not user_id:
        return {"has_password": False}
    return {"has_password": await has_user_password(int(user_id))}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
