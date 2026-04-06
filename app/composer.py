from io import BytesIO
from PIL import Image, ImageOps

CANVAS_SIZE = 512

def fit_image(img: Image.Image, size: int) -> Image.Image:
    img = img.convert("RGBA")
    return ImageOps.contain(img, (size, size))

def _center_pos(img: Image.Image, x: int, y: int):
    return (x - img.width // 2, y - img.height // 2)

def compose_emojis(images):
    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    count = len(images)

    if count == 1:
        img = fit_image(images[0], 380)
        canvas.alpha_composite(img, _center_pos(img, 256, 256))

    elif count == 2:
        centers = [(160, 256), (352, 256)]
        for img, (cx, cy) in zip(images[:2], centers):
            img = fit_image(img, 220)
            canvas.alpha_composite(img, _center_pos(img, cx, cy))

    elif count == 3:
        centers = [(256, 150), (160, 340), (352, 340)]
        for img, (cx, cy) in zip(images[:3], centers):
            img = fit_image(img, 180)
            canvas.alpha_composite(img, _center_pos(img, cx, cy))

    elif count == 4:
        centers = [(156, 156), (356, 156), (156, 356), (356, 356)]
        for img, (cx, cy) in zip(images[:4], centers):
            img = fit_image(img, 180)
            canvas.alpha_composite(img, _center_pos(img, cx, cy))

    elif count == 5:
        centers = [(156, 146), (356, 146), (100, 336), (256, 336), (412, 336)]
        for img, (cx, cy) in zip(images[:5], centers):
            img = fit_image(img, 145)
            canvas.alpha_composite(img, _center_pos(img, cx, cy))

    else:
        centers = [
            (100, 146), (256, 146), (412, 146),
            (100, 336), (256, 336), (412, 336),
        ]
        for img, (cx, cy) in zip(images[:6], centers):
            img = fit_image(img, 135)
            canvas.alpha_composite(img, _center_pos(img, cx, cy))

    out = BytesIO()
    canvas.save(out, format="PNG")
    out.seek(0)
    return out
