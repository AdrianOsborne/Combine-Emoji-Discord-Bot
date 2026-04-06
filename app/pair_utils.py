
import re

CUSTOM_EMOJI_RE = re.compile(r"<a?:[A-Za-z0-9_]+:\d+>")

def emoji_to_codepoints(emoji: str) -> str:
    cps = []
    for ch in emoji:
        cp = ord(ch)
        if cp == 0xFE0F:
            continue
        cps.append(f"{cp:x}")
    return "-".join(cps)

def extract_single_unicode_emoji(raw: str) -> str | None:
    if not raw:
        return None

    raw = raw.strip()
    if CUSTOM_EMOJI_RE.search(raw):
        return None

    chars = [c for c in raw if not c.isspace()]
    if not chars:
        return None

    found = []
    current = []

    for ch in chars:
        cp = ord(ch)

        if cp in (0xFE0F, 0x200D):
            if current:
                current.append(ch)
            else:
                return None
            continue

        if (
            0x1F000 <= cp <= 0x1FAFF
            or 0x2600 <= cp <= 0x27BF
            or 0x2300 <= cp <= 0x23FF
        ):
            if current:
                found.append("".join(current))
                current = []
            current = [ch]
        else:
            return None

    if current:
        found.append("".join(current))

    if len(found) != 1:
        return None

    return found[0]

def canonicalize_pair(emoji1: str, emoji2: str) -> tuple[str, str, str]:
    pair = sorted([emoji1, emoji2], key=emoji_to_codepoints)
    pair_key = "__".join(emoji_to_codepoints(e) for e in pair)
    return pair[0], pair[1], pair_key
