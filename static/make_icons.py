"""
PWA için PNG ikon üretici. 192x192 ve 512x512 üretir.
Çalıştırmak için:  python static/make_icons.py
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

OUT = Path(__file__).parent


def make_icon(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), "#0d1117")
    d = ImageDraw.Draw(img)
    s = size / 512.0  # scale faktörü

    # Yuvarlatılmış arka plan
    # PIL doesn't have rounded rect easily; draw via mask
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bg)
    bd.rounded_rectangle([0, 0, size, size], radius=int(96 * s),
                          fill="#0d1117")
    img.paste(bg, (0, 0), bg)

    # OTT trend line — 6 segment
    pts = [(60, 380), (140, 320), (220, 360), (300, 220), (380, 260), (460, 120)]
    pts_s = [(int(x * s), int(y * s)) for x, y in pts]
    d.line(pts_s, fill="#2962ff", width=int(22 * s), joint="curve")

    # TOTT yukarı band
    upper = [(60, 350), (140, 290), (220, 330), (300, 190), (380, 230), (460, 90)]
    upper_s = [(int(x * s), int(y * s)) for x, y in upper]
    d.line(upper_s, fill="#ef5350", width=int(5 * s))

    # TOTT aşağı band
    lower = [(60, 410), (140, 350), (220, 390), (300, 250), (380, 290), (460, 150)]
    lower_s = [(int(x * s), int(y * s)) for x, y in lower]
    d.line(lower_s, fill="#26a69a", width=int(5 * s))

    # Signal dots
    for cx, cy, color in [(220, 360, "#26a69a"), (380, 260, "#ef5350")]:
        r = int(14 * s)
        x, y = int(cx * s), int(cy * s)
        d.ellipse([x - r, y - r, x + r, y + r], fill=color,
                  outline="#0d1117", width=int(4 * s))

    # "OTT" yazısı
    try:
        font = ImageFont.truetype("arialbd.ttf", int(64 * s))
    except Exception:
        try:
            font = ImageFont.truetype("Arial Bold.ttf", int(64 * s))
        except Exception:
            font = ImageFont.load_default()
    txt = "OTT"
    bbox = d.textbbox((0, 0), txt, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    d.text(((size - tw) // 2, int(450 * s) - th // 2),
            txt, font=font, fill="#d1d4dc")

    return img


if __name__ == "__main__":
    for sz in (192, 512):
        img = make_icon(sz)
        out_path = OUT / f"icon-{sz}.png"
        img.save(out_path, "PNG", optimize=True)
        print(f"  ✓ {out_path}")
    # Favicon
    fav = make_icon(64)
    fav.save(OUT / "favicon.png", "PNG", optimize=True)
    print(f"  ✓ {OUT}/favicon.png")
