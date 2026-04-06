
import json
import os
from io import BytesIO

import aiohttp
from PIL import Image

from pair_utils import emoji_to_codepoints

METADATA_URL = os.getenv(
    "EMOJI_KITCHEN_METADATA_URL",
    "https://raw.githubusercontent.com/xsalazar/emoji-kitchen-backend/main/app/metadata.json",
)

METADATA_PATH = "cache/metadata.json"
ASSET_CACHE_DIR = "cache/assets"

os.makedirs("cache", exist_ok=True)
os.makedirs(ASSET_CACHE_DIR, exist_ok=True)

async def ensure_metadata(session: aiohttp.ClientSession) -> dict:
    if os.path.exists(METADATA_PATH):
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    async with session.get(METADATA_URL) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Failed to download Emoji Kitchen metadata: HTTP {resp.status}")
        text = await resp.text()

    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        f.write(text)

    return json.loads(text)

def _candidate_keys(e1: str, e2: str) -> list[str]:
    c1 = emoji_to_codepoints(e1)
    c2 = emoji_to_codepoints(e2)
    return [
        f"{c1}_{c2}",
        f"{c2}_{c1}",
        f"{c1}__{c2}",
        f"{c2}__{c1}",
        f"{c1}-{c2}",
        f"{c2}-{c1}",
        f"{c1}+{c2}",
        f"{c2}+{c1}",
    ]

def _find_asset_url(metadata: dict, e1: str, e2: str) -> str | None:
    candidates = _candidate_keys(e1, e2)

    if isinstance(metadata, dict):
        for key in candidates:
            value = metadata.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
            if isinstance(value, dict):
                for field in ("url", "gStaticUrl", "imageUrl", "asset_url", "assetUrl", "src"):
                    maybe = value.get(field)
                    if isinstance(maybe, str) and maybe.startswith("http"):
                        return maybe

        combos = metadata.get("combinations") or metadata.get("pairs") or metadata.get("data")
        if isinstance(combos, dict):
            for key in candidates:
                value = combos.get(key)
                if isinstance(value, str) and value.startswith("http"):
                    return value
                if isinstance(value, dict):
                    for field in ("url", "gStaticUrl", "imageUrl", "asset_url", "assetUrl", "src"):
                        maybe = value.get(field)
                        if isinstance(maybe, str) and maybe.startswith("http"):
                            return maybe

        if isinstance(combos, list):
            code_a = emoji_to_codepoints(e1)
            code_b = emoji_to_codepoints(e2)
            target = {code_a, code_b}
            for item in combos:
                if not isinstance(item, dict):
                    continue

                item_codes = set()
                for field in ("leftEmojiCodepoint", "rightEmojiCodepoint", "emoji1", "emoji2", "left", "right"):
                    value = item.get(field)
                    if isinstance(value, str):
                        item_codes.add(value.replace("_", "-"))

                if target.issubset(item_codes) or target == item_codes:
                    for field in ("url", "gStaticUrl", "imageUrl", "asset_url", "assetUrl", "src"):
                        maybe = item.get(field)
                        if isinstance(maybe, str) and maybe.startswith("http"):
                            return maybe
    return None

async def fetch_kitchen_image(session: aiohttp.ClientSession, emoji1: str, emoji2: str) -> BytesIO:
    metadata = await ensure_metadata(session)
    asset_url = _find_asset_url(metadata, emoji1, emoji2)
    if not asset_url:
        raise RuntimeError(
            "That emoji pair is not available in the current Emoji Kitchen dataset yet. "
            "Try another pair."
        )

    cache_name = os.path.join(
        ASSET_CACHE_DIR,
        f"{emoji_to_codepoints(emoji1)}__{emoji_to_codepoints(emoji2)}.png"
    )

    if os.path.exists(cache_name):
        with open(cache_name, "rb") as f:
            out = BytesIO(f.read())
            out.seek(0)
            return out

    async with session.get(asset_url) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Failed to download mashup image: HTTP {resp.status}")
        data = await resp.read()

    img = Image.open(BytesIO(data)).convert("RGBA")
    out = BytesIO()
    img.save(out, format="PNG")
    out.seek(0)

    with open(cache_name, "wb") as f:
        f.write(out.getvalue())

    return out
