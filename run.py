import asyncio
import logging

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

bot_application = None


async def run_bot():
    global bot_application
    from telegram.ext import Application
    from bot import setup_handlers

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        return

    bot_application = Application.builder().token(BOT_TOKEN).build()
    setup_handlers(bot_application)

    await bot_application.initialize()
    await bot_application.start()
    await bot_application.updater.start_polling(drop_pending_updates=True)
    logger.info("Bot started polling...")


async def main():
    await init_db()
    logger.info("Database initialized.")

    bot_task = asyncio.create_task(run_bot())

    config = uvicorn.Config(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
    )
    server = uvicorn.Server(config)

    logger.info(f"Starting FastAPI server on {HOST}:{PORT}")
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
