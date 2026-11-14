"""Generate LiveFloat icon.png and icon.ico (requires Pillow)."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_PNG = ROOT / "assets" / "icon.png"
OUT_ICO = ROOT / "assets" / "icon.ico"

SIZE = 512


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient_image(size):
    top = (91, 140, 255)      # #5B8CFF
    bottom = (124, 92, 255)   # #7C5CFF
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    for y in range(size):
        c = lerp(top, bottom, y / size)
        for x in range(size):
            px[x, y] = (*c, 255)
    return img


def rounded_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def main():
    img = gradient_image(SIZE)
    # Apply rounded corners.
    mask = rounded_mask(SIZE, int(SIZE * 0.24))
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.paste(img, (0, 0), mask)
    d = ImageDraw.Draw(canvas)

    # Speech bubble.
    bubble = [(92, 108), (420, 340)]
    d.rounded_rectangle(bubble, radius=52, fill=(255, 255, 255, 255))
    # Tail.
    d.polygon([(176, 332), (214, 400), (252, 330)], fill=(255, 255, 255, 255))

    # "译" glyph in the accent blue.
    accent = (91, 110, 245, 255)
    font = None
    for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf", "arial.ttf"):
        try:
            font = ImageFont.truetype(name, 180)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
    text = "译"
    bbox = d.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (SIZE - w) / 2 - bbox[0]
    y = (SIZE - h) / 2 - bbox[1] - 8
    d.text((x, y), text, font=font, fill=accent)

    canvas = canvas.resize((256, 256), Image.LANCZOS)
    canvas.save(OUT_PNG)
    canvas.save(OUT_ICO, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", OUT_PNG, OUT_ICO)


if __name__ == "__main__":
    main()
