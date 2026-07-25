import json
import logging

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN, WEBAPP_URL
from database import add_or_update_user, get_user_count, get_user, add_referral, get_admin_setting

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args

    referral_reward = float(await get_admin_setting("referral_reward") or "0.001")

    if args and args[0].startswith("ref_"):
        try:
            referrer_id = int(args[0].replace("ref_", ""))
            if referrer_id != user.id:
                await add_or_update_user(user.id, user.username, user.first_name)
                referrer = await get_user(referrer_id)
                referrer_ip = referrer.get("ip_address", "") if referrer else ""
                referred_user = await get_user(user.id)
                referred_ip = referred_user.get("ip_address", "") if referred_user else ""
                success = await add_referral(referrer_id, user.id, referral_reward, referrer_ip, referred_ip)
                if success:
                    ref_name = referrer.get("first_name", "Someone") if referrer else "Someone"
                    await update.message.reply_text(
                        f"You were referred by {ref_name}!\n"
                        f"Complete {5} ad views to unlock your {referral_reward} USDT bonus!"
                    )
                else:
                    await add_or_update_user(user.id, user.username, user.first_name)
            else:
                await add_or_update_user(user.id, user.username, user.first_name)
        except (ValueError, IndexError):
            await add_or_update_user(user.id, user.username, user.first_name)
    else:
        await add_or_update_user(user.id, user.username, user.first_name)

    user_data = await get_user(user.id)
    ref_link = f"https://t.me/{context.bot.username}?start=ref_{user.id}"
    ref_count = user_data.get("total_referrals", 0) if user_data else 0
    balance = user_data.get("balance", 0) if user_data else 0

    keyboard = ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(
                    text="Open Mini App",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ]
        ],
        resize_keyboard=True,
    )

    await update.message.reply_text(
        f"Welcome {user.first_name}!\n\n"
        f"Balance: {balance:.4f} USDT\n"
        f"Referrals: {ref_count}\n\n"
        f"Share your referral link to earn {referral_reward} USDT per invite:\n"
        f"{ref_link}\n\n"
        f"Open Mini App to complete tasks and earn!",
        reply_markup=keyboard,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Commands:\n\n"
        "/start - Start bot\n"
        "/help - Help\n"
        "/stats - Total users\n"
        "/referral - Get referral link\n\n"
        "Open Mini App to earn USDT!"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    count = await get_user_count()
    await update.message.reply_text(f"Total Users: {count}")


async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_data = await get_user(user.id)
    ref_link = f"https://t.me/{context.bot.username}?start=ref_{user.id}"
    ref_count = user_data.get("total_referrals", 0) if user_data else 0
    referral_reward = float(await get_admin_setting("referral_reward") or "0.001")

    await update.message.reply_text(
        f"Referral Program\n\n"
        f"Your referral link:\n{ref_link}\n\n"
        f"Total referrals: {ref_count}\n"
        f"Reward per referral: {referral_reward} USDT\n\n"
        f"Share this link with friends. When they join, you both earn!"
    )


async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = json.loads(update.effective_message.web_app_data.data)
    await update.message.reply_text(f"Data received:\n{json.dumps(data, indent=2)}")


def setup_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("referral", referral))
    application.add_handler(
        MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data)
    )


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set. Check your .env file.")

    app = Application.builder().token(BOT_TOKEN).build()
    setup_handlers(app)

    logger.info("Bot started polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
