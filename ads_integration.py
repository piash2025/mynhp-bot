import os
from typing import Optional

import aiohttp

ADSGRAM_BLOCK_ID = os.getenv("ADSGRAM_BLOCK_ID")
ADSGRAM_TOKEN = os.getenv("ADSGRAM_TOKEN")
ADSGRAM_API = "https://api.adsgram.ai/advbot"


async def get_ad(user_id: int, language: str = "en") -> Optional[dict]:
    if not ADSGRAM_BLOCK_ID or not ADSGRAM_TOKEN:
        return None

    params = {
        "tgid": user_id,
        "blockid": ADSGRAM_BLOCK_ID,
        "language": language,
        "token": ADSGRAM_TOKEN,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(ADSGRAM_API, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        pass
    return None
