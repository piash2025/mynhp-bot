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
from database import add_or_update_user, get_user_count, init_db

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await add_or_update_user(user.id, user.username, user.first_name)

    keyboard = ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(
                    text="🚀 Open Tools App",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ]
        ],
        resize_keyboard=True,
    )

    await update.message.reply_text(
        f"Assalamu Alaikum {user.first_name}!\n\n"
        "Welcome to mynhp_bot!\n\n"
        "Amader Mini App e aapni paben:\n\n"
        "Text Tools (Reverse, Count, etc.)\n"
        "Password Generator\n"
        "QR Code Generator\n"
        "Color Picker\n"
        "JSON Formatter\n\n"
        "Button e click kore Open App e jaaan!",
        reply_markup=keyboard,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Bot Commands:\n\n"
        "/start - Bot shuru koro\n"
        "/help - Ei help message\n"
        "/stats - Total user shongkhya\n\n"
        "Open App button e click kore tools use koro!"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    count = await get_user_count()
    await update.message.reply_text(f"Total Users: {count}")


async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = json.loads(update.effective_message.web_app_data.data)
    await update.message.reply_text(f"Data received:\n{json.dumps(data, indent=2)}")


def setup_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats))
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
