# CamAlert - simple picons (camera icon + name) for the camera channels. Needs python3-pillow.
# Copyright (C) 2026 CamAlert developers. GPL v2. Plain Python (no Enigma2 imports).
import glob
import os
import re

MADE = "/etc/enigma2/camalert_picons.txt"  # picons we made ourselves: only these are ever overwritten
FONTS = ("/usr/share/fonts/nmsbd.ttf", "/usr/share/fonts/lsansd.ttf", "/usr/share/fonts/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def picon_name(title):
    """Service-name picon file name (as Enigma2 looks it up for stream services): 'Grüner Weg' ->
    'grunerweg.png'."""
    import unicodedata
    name = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^a-z0-9]", "", name.replace("&", "and").replace("+", "plus").replace("*", "star").lower())
    return (name + ".png") if name else None


def picon_folder():
    for d in sorted(glob.glob("/media/*/picon")) + ["/usr/share/enigma2/picon", "/picon"]:
        if os.path.isdir(d) and os.access(d, os.W_OK):
            return d
    return None


def draw(title, path, size=(220, 132)):
    from PIL import Image, ImageDraw, ImageFont
    w, h = size
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((2, 2, w - 3, h - 3), radius=14, fill=(32, 36, 44, 235))
    # camera: body, lens, mount
    cx, cy = w // 2, int(h * 0.36)
    d.rounded_rectangle((cx - 38, cy - 20, cx + 28, cy + 20), radius=6, fill=(220, 224, 230, 255))
    d.polygon([(cx + 28, cy - 8), (cx + 46, cy - 18), (cx + 46, cy + 18), (cx + 28, cy + 8)], fill=(220, 224, 230, 255))
    d.ellipse((cx - 20, cy - 13, cx + 6, cy + 13), fill=(32, 36, 44, 255))
    d.ellipse((cx - 13, cy - 6, cx - 1, cy + 6), fill=(70, 160, 230, 255))
    d.ellipse((cx - 33, cy - 15, cx - 27, cy - 9), fill=(230, 60, 60, 255))
    font = None
    for f in FONTS:
        if os.path.exists(f):
            for pt in range(28, 13, -2):
                font = ImageFont.truetype(f, pt)
                if d.textlength(title, font=font) <= w - 16:
                    break
            break
    font = font or ImageFont.load_default()
    tw = d.textlength(title, font=font)
    d.text(((w - tw) / 2, int(h * 0.66)), title, font=font, fill=(255, 255, 255, 255))
    im.save(path, "PNG")


def make(titles, folder=None):
    """Writes picons for [title, ...]; never overwrites a picon we did not make. Returns (written, skipped, folder)."""
    folder = folder or picon_folder()
    if not folder:
        return 0, len(titles), None
    try:
        made = set(open(MADE).read().split())
    except OSError:
        made = set()
    written = skipped = 0
    for title in titles:
        name = picon_name(title)
        if not name:
            continue
        path = os.path.join(folder, name)
        if os.path.exists(path) and path not in made:
            skipped += 1
            continue
        draw(title, path)
        made.add(path)
        written += 1
    try:
        with open(MADE, "w") as f:
            f.write("\n".join(sorted(made)) + "\n")
    except OSError:
        pass
    return written, skipped, folder
