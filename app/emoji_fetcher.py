import os
import re
import aiohttp
from io import BytesIO
from PIL import Image

CACHE_DIR = "cache"
TWEMOJI_BASE = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@latest/assets/72x72"
DISCORD_EMOJI_RE = re.compile(r"<(a?):([A-Za-z0-9_]+):(\d+)>")

os.makedirs(CACHE_DIR, exist_ok=True)


def emoji_to_codepoints(emoji: str) -> str:
    codepoints = []
    for char in emoji:
        cp = ord(char)
        if cp == 0xFE0F:
            continue
        codepoints.append(f"{cp:x}")
    return "-".join(codepoints)


def is_custom_discord_emoji(value: str) -> bool:
    return bool(DISCORD_EMOJI_RE.fullmatch(value))


async def fetch_unicode_emoji_image(session: aiohttp.ClientSession, emoji: str) -> Image.Image:
    code = emoji_to_codepoints(emoji)
    path = os.path.join(CACHE_DIR, f"twemoji_{code}.png")

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


async def fetch_discord_custom_emoji_image(session: aiohttp.ClientSession, emoji_tag: str) -> Image.Image:
    match = DISCORD_EMOJI_RE.fullmatch(emoji_tag)
    if not match:
        raise ValueError(f"Invalid Discord emoji format: {emoji_tag}")

    animated, name, emoji_id = match.groups()
    ext = "gif" if animated else "png"
    cache_name = f"discord_{emoji_id}.{ext}"
    path = os.path.join(CACHE_DIR, cache_name)

    if os.path.exists(path):
        return Image.open(path).convert("RGBA")

    url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=128&quality=lossless"

    async with session.get(url) as resp:
        if resp.status != 200:
            raise ValueError(f"Could not fetch Discord emoji asset for {emoji_tag}")
        data = await resp.read()

    with open(path, "wb") as f:
        f.write(data)

    img = Image.open(BytesIO(data))
    if getattr(img, "is_animated", False):
        img.seek(0)

    return img.convert("RGBA")


async def fetch_emoji_image(session: aiohttp.ClientSession, emoji: str) -> Image.Image:
    if is_custom_discord_emoji(emoji):
        return await fetch_discord_custom_emoji_image(session, emoji)

    return await fetch_unicode_emoji_image(session, emoji)