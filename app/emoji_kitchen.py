import json
import os
import re
from io import BytesIO

import aiohttp
from PIL import Image

from pair_utils import emoji_to_codepoints

METADATA_URL = os.getenv(
    "EMOJI_KITCHEN_METADATA_URL",
    "https://raw.githubusercontent.com/xsalazar/emoji-kitchen-backend/main/app/metadata.json",
)

CACHE_DIR = "cache"
METADATA_TEXT_PATH = os.path.join(CACHE_DIR, "metadata.json")
INDEX_PATH = os.path.join(CACHE_DIR, "metadata_index.json")
ASSET_CACHE_DIR = os.path.join(CACHE_DIR, "assets")

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(ASSET_CACHE_DIR, exist_ok=True)

GSTATIC_URL_RE = re.compile(
    r"https://www\.gstatic\.com/android/keyboard/emojikitchen/\d+/([0-9a-f\-]+)/([0-9a-f\-]+)_([0-9a-f\-]+)\.png",
    re.IGNORECASE,
)

def normalize_code_string(code: str) -> str:
    parts = [p.lower() for p in code.split("-") if p.lower() != "fe0f"]
    return "-".join(parts)

def make_pair_key(code_a: str, code_b: str) -> str:
    a = normalize_code_string(code_a)
    b = normalize_code_string(code_b)
    return "__".join(sorted([a, b]))

def _walk_urls(obj, found: set[str]):
    if isinstance(obj, dict):
        for value in obj.values():
            _walk_urls(value, found)
    elif isinstance(obj, list):
        for item in obj:
            _walk_urls(item, found)
    elif isinstance(obj, str):
        for match in GSTATIC_URL_RE.finditer(obj):
            found.add(match.group(0))

async def _download_metadata_text(session: aiohttp.ClientSession) -> str:
    async with session.get(METADATA_URL, timeout=aiohttp.ClientTimeout(total=20)) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Failed to download Emoji Kitchen metadata: HTTP {resp.status}")
        text = await resp.text()

    with open(METADATA_TEXT_PATH, "w", encoding="utf-8") as f:
        f.write(text)

    return text

async def ensure_index(session: aiohttp.ClientSession) -> dict[str, str]:
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    if os.path.exists(METADATA_TEXT_PATH):
        with open(METADATA_TEXT_PATH, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = await _download_metadata_text(session)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError("Emoji Kitchen metadata could not be parsed as JSON.")

    urls = set()
    _walk_urls(parsed, urls)

    index = {}
    for url in urls:
        match = GSTATIC_URL_RE.search(url)
        if not match:
            continue

        left_dir = match.group(1).lower()
        first = match.group(2).lower()
        second = match.group(3).lower()

        index[make_pair_key(first, second)] = url
        index[make_pair_key(left_dir, second)] = url
        index[make_pair_key(left_dir, first)] = url

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f)

    return index

async def fetch_kitchen_image(session: aiohttp.ClientSession, emoji1: str, emoji2: str) -> BytesIO:
    code_a = emoji_to_codepoints(emoji1)
    code_b = emoji_to_codepoints(emoji2)
    pair_key = make_pair_key(code_a, code_b)

    cache_name = os.path.join(ASSET_CACHE_DIR, f"{pair_key}.png")
    if os.path.exists(cache_name):
        with open(cache_name, "rb") as f:
            out = BytesIO(f.read())
            out.seek(0)
            return out

    index = await ensure_index(session)
    asset_url = index.get(pair_key)

    if not asset_url:
        raise RuntimeError(
            "That pair does not seem to exist in the current Emoji Kitchen dataset. Try another pair."
        )

    async with session.get(asset_url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
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