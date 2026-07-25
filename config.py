import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADSGRAM_BLOCK_ID = os.getenv("ADSGRAM_BLOCK_ID")
ADSGRAM_TOKEN = os.getenv("ADSGRAM_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "http://localhost:8000")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
