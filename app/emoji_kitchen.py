
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

METADATA_TEXT_PATH = "cache/metadata.json"
ASSET_CACHE_DIR = "cache/assets"

os.makedirs("cache", exist_ok=True)
os.makedirs(ASSET_CACHE_DIR, exist_ok=True)

GSTATIC_URL_RE = re.compile(
    r"https://www\.gstatic\.com/android/keyboard/emojikitchen/\d+/[0-9a-f\-]+/[0-9a-f\-]+_[0-9a-f\-]+\.png"
)

async def ensure_metadata_text(session: aiohttp.ClientSession) -> str:
    if os.path.exists(METADATA_TEXT_PATH):
        with open(METADATA_TEXT_PATH, "r", encoding="utf-8") as f:
            return f.read()

    async with session.get(METADATA_URL) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Failed to download Emoji Kitchen metadata: HTTP {resp.status}")
        text = await resp.text()

    with open(METADATA_TEXT_PATH, "w", encoding="utf-8") as f:
        f.write(text)

    return text

def _candidate_urls_from_text(metadata_text: str, code_a: str, code_b: str) -> list[str]:
    found = set()

    # First, scan all explicit gstatic URLs already present in metadata text.
    for url in GSTATIC_URL_RE.findall(metadata_text):
        normalized = url.lower()
        if f"/{code_a}/" in normalized and f"_{code_b}.png" in normalized:
            found.add(normalized)
        if f"/{code_b}/" in normalized and f"_{code_a}.png" in normalized:
            found.add(normalized)

    # Then, build plausible direct URLs if the metadata mentions a matching date bucket.
    date_codes = set(re.findall(r"emojikitchen/(\d+)", metadata_text))
    for date_code in date_codes:
        found.add(
            f"https://www.gstatic.com/android/keyboard/emojikitchen/{date_code}/{code_a}/{code_a}_{code_b}.png"
        )
        found.add(
            f"https://www.gstatic.com/android/keyboard/emojikitchen/{date_code}/{code_b}/{code_a}_{code_b}.png"
        )
        found.add(
            f"https://www.gstatic.com/android/keyboard/emojikitchen/{date_code}/{code_a}/{code_b}_{code_a}.png"
        )
        found.add(
            f"https://www.gstatic.com/android/keyboard/emojikitchen/{date_code}/{code_b}/{code_b}_{code_a}.png"
        )

    return sorted(found)

async def _first_live_url(session: aiohttp.ClientSession, urls: list[str]) -> str | None:
    for url in urls:
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return url
        except Exception:
            continue
    return None

async def fetch_kitchen_image(session: aiohttp.ClientSession, emoji1: str, emoji2: str) -> BytesIO:
    metadata_text = await ensure_metadata_text(session)

    code_a = emoji_to_codepoints(emoji1)
    code_b = emoji_to_codepoints(emoji2)

    cache_name = os.path.join(ASSET_CACHE_DIR, f"{code_a}__{code_b}.png")
    if os.path.exists(cache_name):
        with open(cache_name, "rb") as f:
            out = BytesIO(f.read())
            out.seek(0)
            return out

    candidates = _candidate_urls_from_text(metadata_text, code_a, code_b)
    asset_url = await _first_live_url(session, candidates)

    if not asset_url:
        raise RuntimeError(
            "That emoji pair is not available in the current Emoji Kitchen dataset yet. "
            "Try another pair."
        )

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
