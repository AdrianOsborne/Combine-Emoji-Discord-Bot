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

CACHE_DIR = "cache"
METADATA_PATH = os.path.join(CACHE_DIR, "metadata.json")
INDEX_PATH = os.path.join(CACHE_DIR, "metadata_index.json")
ASSET_CACHE_DIR = os.path.join(CACHE_DIR, "assets")

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(ASSET_CACHE_DIR, exist_ok=True)


def normalize(code: str) -> str:
    return "-".join(part for part in code.lower().split("-") if part != "fe0f")


def pair_key(a: str, b: str) -> str:
    return "__".join(sorted([normalize(a), normalize(b)]))


async def load_metadata(session: aiohttp.ClientSession) -> dict:
    if os.path.exists(METADATA_PATH):
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    async with session.get(METADATA_URL, timeout=aiohttp.ClientTimeout(total=30)) as r:
        if r.status != 200:
            raise RuntimeError(f"Failed to fetch metadata: HTTP {r.status}")
        text = await r.text()

    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        f.write(text)

    return json.loads(text)


async def ensure_index(session: aiohttp.ClientSession) -> dict[str, str]:
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    metadata = await load_metadata(session)
    data = metadata.get("data", {})

    index: dict[str, str] = {}

    for left_code, left_entry in data.items():
        left_code = normalize(left_code)

        combos = left_entry.get("combinations") if isinstance(left_entry, dict) else None
        if not combos:
            continue

        for right_code, combo_list in combos.items():
            right_code = normalize(right_code)

            if not isinstance(combo_list, list):
                continue

            chosen = None
            for item in combo_list:
                if item.get("isLatest") is True:
                    chosen = item
                    break
            if chosen is None and combo_list:
                chosen = combo_list[0]

            if not chosen:
                continue

            url = chosen.get("gStaticUrl")
            if not url:
                continue

            left_cp = normalize(chosen.get("leftEmojiCodepoint", left_code))
            right_cp = normalize(chosen.get("rightEmojiCodepoint", right_code))

            index[pair_key(left_cp, right_cp)] = url

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f)

    return index


async def fetch_kitchen_image(session: aiohttp.ClientSession, emoji1: str, emoji2: str) -> BytesIO:
    code_a = emoji_to_codepoints(emoji1)
    code_b = emoji_to_codepoints(emoji2)
    key = pair_key(code_a, code_b)

    cache_file = os.path.join(ASSET_CACHE_DIR, f"{key}.png")
    if os.path.exists(cache_file):
        with open(cache_file, "rb") as f:
            out = BytesIO(f.read())
            out.seek(0)
            return out

    index = await ensure_index(session)
    url = index.get(key)

    if not url:
        raise RuntimeError("No Emoji Kitchen match found")

    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
        if r.status != 200:
            raise RuntimeError(f"Failed to download emoji fusion: HTTP {r.status}")
        data = await r.read()

    img = Image.open(BytesIO(data)).convert("RGBA")

    out = BytesIO()
    img.save(out, format="PNG")
    out.seek(0)

    with open(cache_file, "wb") as f:
        f.write(out.getvalue())

    return out