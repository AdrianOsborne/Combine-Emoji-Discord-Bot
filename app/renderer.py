
import hashlib
import os
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter, ImageOps

OUTPUT_CACHE_DIR = "cache/output"
os.makedirs(OUTPUT_CACHE_DIR, exist_ok=True)

CANVAS = 512

def _pair_hash(pair_key: str) -> bytes:
    return hashlib.sha256(pair_key.encode("utf-8")).digest()

def _gradient_background(pair_key: str) -> Image.Image:
    digest = _pair_hash(pair_key)
    base = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    px = base.load()

    c1 = (digest[0], digest[1], digest[2])
    c2 = (digest[3], digest[4], digest[5])
    c3 = (digest[6], digest[7], digest[8])

    for y in range(CANVAS):
        for x in range(CANVAS):
            t = (x + y) / (2 * CANVAS)
            r = int(c1[0] * (1 - t) + c2[0] * t)
            g = int(c1[1] * (1 - t) + c3[1] * t)
            b = int(c1[2] * (1 - t) + c2[2] * t)
            px[x, y] = (r, g, b, 255)

    mask = Image.new("L", (CANVAS, CANVAS), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((22, 22, CANVAS - 22, CANVAS - 22), fill=255)
    base.putalpha(mask)
    return base

def _sticker_outline(alpha_source: Image.Image, width: int = 18) -> Image.Image:
    alpha = alpha_source.getchannel("A")
    outline = alpha.filter(ImageFilter.MaxFilter(width * 2 + 1))
    outline_img = Image.new("RGBA", alpha_source.size, (255, 255, 255, 255))
    outline_img.putalpha(outline)
    return outline_img

def _resize(img: Image.Image, size: int) -> Image.Image:
    return ImageOps.contain(img.convert("RGBA"), (size, size))

def _paste_center(canvas: Image.Image, img: Image.Image, cx: int, cy: int):
    x = cx - img.width // 2
    y = cy - img.height // 2
    canvas.alpha_composite(img, (x, y))

def render_pair(image_a: Image.Image, image_b: Image.Image, pair_key: str) -> BytesIO:
    cached_path = os.path.join(OUTPUT_CACHE_DIR, f"{pair_key}.png")
    if os.path.exists(cached_path):
        with open(cached_path, "rb") as f:
            out = BytesIO(f.read())
            out.seek(0)
            return out

    bg = _gradient_background(pair_key)

    img_a = _resize(image_a, 325)
    img_b = _resize(image_b, 235)

    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.alpha_composite(bg)

    shadow = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    draw.ellipse((58, 72, 454, 468), fill=(0, 0, 0, 42))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas.alpha_composite(shadow)

    _paste_center(canvas, img_a, 228, 260)

    accent_crop = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    _paste_center(accent_crop, img_b, 338, 186)
    outline = _sticker_outline(accent_crop, width=16)
    canvas.alpha_composite(outline)
    canvas.alpha_composite(accent_crop)

    gloss = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    gloss_draw = ImageDraw.Draw(gloss)
    gloss_draw.ellipse((80, 60, 280, 155), fill=(255, 255, 255, 62))
    gloss = gloss.filter(ImageFilter.GaussianBlur(16))
    canvas.alpha_composite(gloss)

    border = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border)
    border_draw.ellipse((22, 22, CANVAS - 22, CANVAS - 22), outline=(255, 255, 255, 170), width=6)
    canvas.alpha_composite(border)

    out = BytesIO()
    canvas.save(out, format="PNG")
    out.seek(0)

    with open(cached_path, "wb") as f:
        f.write(out.getvalue())

    return out
