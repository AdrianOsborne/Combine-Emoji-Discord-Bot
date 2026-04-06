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


def normalize(code: str):
    return "-".join(p for p in code.split("-") if p != "fe0f")


def pair_key(a, b):
    return "__".join(sorted([normalize(a), normalize(b)]))


async def download_metadata(session):
    async with session.get(METADATA_URL) as r:
        if r.status != 200:
            raise RuntimeError("Failed to fetch metadata")
        data = await r.text()

    with open(METADATA_PATH, "w") as f:
        f.write(data)

    return json.loads(data)


async def ensure_index(session):
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r") as f:
            return json.load(f)

    if os.path.exists(METADATA_PATH):
        with open(METADATA_PATH, "r") as f:
            metadata = json.load(f)
    else:
        metadata = await download_metadata(session)

    index = {}

    for base in metadata:
        base_code = normalize(base["leftEmoji"])

        for combo in base.get("combinations", []):
            other = normalize(combo["rightEmoji"])
            date = combo["date"]

            # construct URL deterministically
            url = (
                f"https://www.gstatic.com/android/keyboard/emojikitchen/"
                f"{date}/{base_code}/{base_code}_{other}.png"
            )

            index[pair_key(base_code, other)] = url

    with open(INDEX_PATH, "w") as f:
        json.dump(index, f)

    return index


async def fetch_kitchen_image(session, emoji1, emoji2):
    code_a = emoji_to_codepoints(emoji1)
    code_b = emoji_to_codepoints(emoji2)

    key = pair_key(code_a, code_b)

    cache_file = os.path.join(ASSET_CACHE_DIR, f"{key}.png")
    if os.path.exists(cache_file):
        with open(cache_file, "rb") as f:
            return BytesIO(f.read())

    index = await ensure_index(session)
    url = index.get(key)

    if not url:
        raise RuntimeError("No Emoji Kitchen match found")

    async with session.get(url) as r:
        if r.status != 200:
            raise RuntimeError("Failed to download emoji fusion")
        data = await r.read()

    img = Image.open(BytesIO(data)).convert("RGBA")

    out = BytesIO()
    img.save(out, format="PNG")
    out.seek(0)

    with open(cache_file, "wb") as f:
        f.write(out.getvalue())

    return out