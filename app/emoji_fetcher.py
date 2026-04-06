
import os
from io import BytesIO

import aiohttp
from PIL import Image

from pair_utils import emoji_to_codepoints

CACHE_DIR = "cache/twemoji"
TWEMOJI_BASE = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@latest/assets/72x72"

os.makedirs(CACHE_DIR, exist_ok=True)

async def fetch_unicode_emoji_image(session: aiohttp.ClientSession, emoji: str) -> Image.Image:
    code = emoji_to_codepoints(emoji)
    path = os.path.join(CACHE_DIR, f"{code}.png")

    if os.path.exists(path):
        return Image.open(path).convert("RGBA")

    url = f"{TWEMOJI_BASE}/{code}.png"
    async with session.get(url) as resp:
        if resp.status != 200:
            raise ValueError(f"Could not fetch Twemoji asset for {emoji}")
        data = await resp.read()

    with open(path, "wb") as f:
        f.write(data)

    return Image.open(BytesIO(data)).convert("RGBA")
