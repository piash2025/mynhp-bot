import asyncio
import logging
import threading

import uvicorn
from dotenv import load_dotenv

load_dotenv()

from config import BOT_TOKEN, HOST, PORT
from database import init_db
from main import app

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def run_bot():
    import asyncio
    from telegram.ext import Application
    from bot import setup_handlers

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        return

    asyncio.set_event_loop(asyncio.new_event_loop())

    application = Application.builder().token(BOT_TOKEN).build()
    setup_handlers(application)

    logger.info("Bot started polling...")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(application.start())
    loop.run_until_complete(application.updater.start_polling(drop_pending_updates=True))
    loop.run_forever()


async def main():
    await init_db()
    logger.info("Database initialized.")


if __name__ == "__main__":
    asyncio.run(main())

    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("Bot thread started.")

    logger.info(f"Starting FastAPI server on {HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)
