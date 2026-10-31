"""icons — 给列表画小方块图标（PIL 生成，不联网）。"""

import os


CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")

SPEC = {
    "mod": ("#4C9A2A", "M"),
    "shader": ("#7B4FA8", "光"),
    "resourcepack": ("#C77C2B", "材"),
    "datapack": ("#2F6FA8", "数"),
    "modpack": ("#2E8B7A", "包"),
    "plugin": ("#5A6B7A", "插"),
    "vanilla": ("#3E8E41", "原"),
    "modrinth": ("#1BD96A", "R"),
    "curseforge": ("#F16436", "C"),
    "map": ("#8D6E63", "图"),
}


def _font(size):
    from PIL import ImageFont
    for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf", "arialbd.ttf"):
        path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name)
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def build(size=28):
    from PIL import Image, ImageDraw
    os.makedirs(CACHE_DIR, exist_ok=True)
    paths = {}
    for key, (color, label) in SPEC.items():
        path = os.path.join(CACHE_DIR, "%s_%d.png" % (key, size))
        if not os.path.isfile(path):
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle([1, 1, size - 2, size - 2], radius=int(size * 0.24), fill=color)
            font = _font(int(size * 0.62))
            box = draw.textbbox((0, 0), label, font=font)
            draw.text(((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1]),
                      label, font=font, fill="white")
            img.save(path)
        paths[key] = path
    return paths


def path_for(key):
    if key not in SPEC:
        key = "mod"
    target = os.path.join(CACHE_DIR, "%s_28.png" % key)
    if not os.path.isfile(target):
        build(28)
    return target
