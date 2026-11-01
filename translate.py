"""translate — 模组/光影中文名：先查 MC百科，查不到按词表拼，再不行保留英文。

带本地缓存 translations.json，查过的下次直接用；空了不缓存，方便以后再试。
"""

import json
import os
import re
import threading
import urllib.parse
import urllib.request

_CACHE_BASE = os.environ.get("CZ_BASE") or os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(_CACHE_BASE, "translations.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
ITEM = re.compile(
    r'<div class="result-item">.*?<a[^>]*href="https://www\.mcmod\.cn/class/(\d+)\.html"[^>]*>(.*?)</a>',
    re.S,
)
TAGS = re.compile(r"<[^>]+>")
BRACKET = re.compile(r"^\[[^\]]*\]\s*")
PAREN = re.compile(r"[\(（]([^\)）]*)[\)）]")
CJK = re.compile(r"[\u4e00-\u9fff]")
_lock = threading.Lock()
_cache = None

GLOSSARY = {
    "sodium": "钠", "lithium": "锂", "iris shaders": "Iris 光影", "create": "机械动力",
    "jei": "JEI 物品管理器", "rei": "REI 物品管理器", "fabric api": "Fabric API",
    "cloth config api": "布制品配置 API", "mod menu": "模组菜单",
    "xaero's minimap": "Xaero 小地图", "xaero's world map": "Xaero 世界地图",
    "journeymap": "旅行地图", "appleskin": "苹果皮", "entity culling": "实体剔除",
    "ferritecore": "铁氧体核心", "ferrite core": "铁氧体核心", "optifine": "OptiFine 高清修复",
    "forge": "Forge", "fabric": "Fabric", "quilt": "Quilt", "neoforge": "NeoForge",
    "complementary shaders": "Complementary 光影", "bsl shaders": "BSL 光影",
    "photon shaders": "Photon 光影", "iris": "Iris 光影", "waystones": "传送石碑",
    "ars nouveau": "新生魔艺", "mowzie's mobs": "莫兹的生物",
    "better archeology": "更好的考古", "spell engine": "法术引擎", "easy magic": "简单魔法",
    "fabulously optimized": "极致优化", "adrenaline": "肾上腺素", "spunky boost": "活力加速",
    "more culling": "更多剔除", "indium": "铟", "sodium extra": "钠扩展",
    "tinkers construct": "匠魂", "blood magic": "血魔法", "pixelmon": "宝可梦",
    "twilight forest": "暮色森林", "ice and fire": "冰与火之歌",
    "applied energistics 2": "应用能源 2", "farmers delight": "农夫乐事",
    "farmer's delight": "农夫乐事", "alexs mobs": "Alex 的生物",
    "alex's mobs": "Alex 的生物", "sophisticated backpacks": "高级背包",
    "create crafts additions": "机械动力：工艺附加",
    "oh the biomes weve gone": "我们的生物群系", "terralith": "Terralith 地形",
    "distant horizons": "遥远地平线", "embeddium": "内嵌ium", "oculus": "眼罩光影",
    "jei": "JEI 物品管理器", "controlling": "按键控制", "catalogue": "目录",
    "mouse tweaks": "鼠标手势", "toast control": "提示控制",
    "voice chat": "语音聊天", "simple voice chat": "简单语音聊天",
    "replay mod": "回放模组", "shulkerboxtooltip": "潜影盒提示",
    "litematica": "投影模组", "minihud": "迷你 HUD", "carry on": "搬运",
    "quark": "夸克", "botania": "植物魔法", "thermal expansion": "热力膨胀",
    "mekanism": "通用机械", "immersive engineering": "沉浸工程",
    "railcraft": "铁路", "forestry": "林业", "extra utilities": "实用设备",
}

WORDS = {
    "better": "更好的", "more": "更多", "extra": "扩展", "plus": "+", "core": "核心",
    "api": "API", "menu": "菜单", "chat": "聊天", "voice": "语音", "map": "地图",
    "minimap": "小地图", "storage": "存储", "backpack": "背包", "inventory": "背包",
    "optimization": "优化", "performance": "性能", "render": "渲染", "culling": "剔除",
    "entity": "实体", "entities": "实体", "block": "方块", "blocks": "方块", "item": "物品",
    "items": "物品", "mob": "生物", "mobs": "生物", "boss": "Boss", "world": "世界",
    "city": "城市", "farm": "农场", "farming": "农业", "armor": "盔甲", "weapon": "武器",
    "weapons": "武器", "enchant": "附魔", "enchantment": "附魔", "recipe": "配方",
    "recipes": "配方", "craft": "合成", "crafting": "合成", "magic": "魔法", "spell": "法术",
    "spells": "法术", "tech": "科技", "energy": "能源", "config": "配置", "library": "库",
    "utils": "工具", "util": "工具", "shader": "光影", "shaders": "光影", "biome": "生物群系",
    "biomes": "生物群系", "dungeon": "地牢", "dungeons": "地牢", "adventure": "冒险",
    "tool": "工具", "tools": "工具", "armour": "盔甲", "engine": "引擎", "legacy": "遗产",
}


def _load():
    global _cache
    if _cache is None:
        try:
            with open(CACHE_PATH, encoding="utf-8") as handle:
                _cache = json.load(handle)
        except Exception:
            _cache = {}
    return _cache


def _save(cache):
    try:
        tmp = CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(cache, handle, ensure_ascii=False, indent=0)
        os.replace(tmp, CACHE_PATH)
    except Exception:
        pass


def clean_name(text):
    name = re.sub(r"\s*[\[\(（].*?[\]\)）]\s*$", "", text or "")
    name = re.sub(r"\s*[-–|]\s*.*$", "", name)
    return name.strip()


def word_fallback(name):
    parts = re.findall(r"[A-Za-z']+|\d+", clean_name(name))
    if not parts:
        return ""
    out, hit = [], False
    for part in parts:
        key = part.lower()
        if key in WORDS:
            out.append(WORDS[key])
            hit = True
        else:
            out.append(part)
    if not hit:
        return ""
    return " ".join(out)


MYMEMORY = "https://api.mymemory.translated.net/get?q=%s&langpair=en|zh-CN"


def machine(name, timeout=8):
    """最后一道：免费机翻。翻不出中文就放弃。"""
    base = clean_name(name)
    if not base:
        return ""
    try:
        url = "https://api.mymemory.translated.net/get?q=" + urllib.parse.quote(base) + "&langpair=en|zh-CN"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        text = (data.get("responseData") or {}).get("translatedText") or ""
        text = text.strip().strip('"').replace("&quot;", '"')
        if text and CJK.search(text) and text.lower() != base.lower() and len(text) <= 20:
            return text
    except Exception:
        pass
    return ""


def _fetch(key, timeout):
    url = "https://search.mcmod.cn/s?key=" + urllib.parse.quote(key)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.mcmod.cn/"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _parse(html, query):
    want = (query or "").strip().lower()
    best, best_score = "", 0
    for m in ITEM.finditer(html):
        title = TAGS.sub("", m.group(2)).replace("&amp;", "&").strip()
        title = BRACKET.sub("", title)
        paren = PAREN.search(title)
        english = paren.group(1).strip().lower() if paren else ""
        head = PAREN.split(title)[0].strip()
        if not head or not CJK.search(head):
            continue
        score = 0
        if english == want:
            score = 3
        elif want and want in head.lower() and len(head) <= max(6, len(want) * 2):
            score = 2
        elif english and want and (want in english or english in want):
            score = 1
        if score > best_score:
            best, best_score = head, score
        if best_score == 3:
            break
    return best


KLP_ITEM = re.compile(r'<a[^>]*href="(?:https?://www\.klpbbs\.com)?/thread-[^"]+"[^>]*>(.*?)</a>', re.S)


def klpbbs(name, timeout=8):
    """在苦力怕论坛搜索里找同名主题，取中文标题（不联网成功就返回空，绝不瞎翻）。"""
    base = clean_name(name)
    if not base:
        return ""
    try:
        url = "https://www.klpbbs.com/search.php?mod=forum&srchtxt=" + urllib.parse.quote(base)
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.klpbbs.com/"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", "replace")
    except Exception:
        return ""
    want = base.lower()
    for match in KLP_ITEM.finditer(html):
        title = TAGS.sub("", match.group(1)).strip()
        title = BRACKET.sub("", title)
        if not title or want not in title.lower():
            continue
        zh = re.sub(r'^\s*[\[【(（]?[^\]】)）]*[\]】)）]?\s*', "", title)
        if re.search(r"[一-鿿]", zh) and len(zh) <= 40:
            return zh
    return ""


ITEM_BLOCK = re.compile(r'<div class="result-item">(.*?)</div>\s*</div>', re.S)


def intro_cached(name):
    """只查本地缓存，不联网；没抓到过就返回空。"""
    base = clean_name(name)
    if not base:
        return ""
    cache = _load()
    with _lock:
        return cache.get("intro:" + base.lower(), "")


def intro_of(name, timeout=10, limit=400):
    """从 MC百科 搜索页扒这个 mod 的中文简介（结果里自带一段 wiki 摘要）。"""
    base = clean_name(name)
    if not base:
        return ""
    key = "intro:" + base.lower()
    cache = _load()
    with _lock:
        if cache.get(key):
            return cache[key]
    try:
        url = "https://search.mcmod.cn/s?key=" + urllib.parse.quote(base)
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.mcmod.cn/"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", "replace")
    except Exception:
        return ""
    want = base.strip().lower()
    bad = ("扩展", "附属", "修复", "前置", "兼容", "汉化", "整合", "材质", "光影包", "插件")
    best_score, best_title, best_text, best_order = 0, "", "", 999
    chunks = html.split('class="result-item"')[1:]
    for order, chunk in enumerate(chunks):
        raw = chunk[:5000]
        title_match = re.search(r'<a[^>]*href="https://www\.mcmod\.cn/class/\d+\.html"[^>]*>(.*?)</a>', raw, re.S)
        if not title_match:
            continue
        title = BRACKET.sub("", TAGS.sub("", title_match.group(1))).strip()
        head = title.lower()
        paren = ""
        pm = re.search(r"[(（]\s*([^)）]+)[)）]", title)
        if pm:
            paren = pm.group(1).strip().lower()
        def norm(s):
            return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

        pw, pwq = norm(paren), norm(want)
        if pw and pwq and pw == pwq:
            score = 9
        elif pw and pwq and pw.startswith(pwq):
            score = 7
        elif pw and pwq and pwq in pw:
            score = 6
        elif paren == want or head == want:
            score = 8
        elif paren.startswith(want):
            score = 5
        elif head.startswith(want):
            score = 4
        elif want in head and len(head) <= len(want) * 3:
            score = 3
        else:
            continue
        if any(b in title for b in bad):
            score -= 4
        if pw and pwq and len(pw) > len(pwq) * 2 + 3:
            score -= 3   # 括号里英文名比原名词长太多，八成是“XX 扩展”
        cn_part = title.split("(")[0].split("（")[0].strip()
        if len(cn_part) <= len(want) + 6:
            score += 3   # 中文名短，说明是主条目而不是“XX 扩展”
        if score <= 0:
            continue
        text = re.sub(r"<script.*?</script>", " ", raw, flags=re.S)
        text = BRACKET.sub("", TAGS.sub(" ", text))
        text = re.sub(r"\[h\d=[^\]]*\]", " ", text)
        text = re.sub(r"\[mark:[^\]]*\]", " ", text)
        text = text.replace("&nbsp;", " ")
        text = re.sub(r"\s+", " ", text).strip()
        cut = len(text)
        for marker in ("地址：", "地址:", "收录时间", "最后编辑", "- MC百科"):
            pos = text.find(marker)
            if 0 < pos < cut:
                cut = pos
        text = text[:cut].strip()
        if score > best_score or (score == best_score and order < best_order):
            best_score, best_title, best_text, best_order = score, title, text, order
    if best_text:
        best_text = best_text[:limit]
        with _lock:
            cache[key] = best_text
            _save(cache)
    return best_text

CACHE_VER = "v2:"


def zh_title(name, timeout=10):
    """只从 MC百科 搜索结果里取中文名（括号外那段）。"""
    base = clean_name(name)
    if not base:
        return ""
    want = re.sub(r"[^a-z0-9]+", "", base.lower())
    try:
        url = "https://search.mcmod.cn/s?key=" + urllib.parse.quote(base)
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.mcmod.cn/"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", "replace")
    except Exception:
        return ""
    bad = ("扩展", "附属", "修复", "前置", "兼容", "汉化", "整合", "材质", "插件")
    best_score, best_cn, best_len = 0, "", 999
    for chunk in html.split('class="result-item"')[1:]:
        raw = chunk[:4000]
        m = re.search(r'href="https://www\.mcmod\.cn/class/\d+\.html"[^>]*>(.*?)</a>', raw, re.S)
        if not m:
            continue
        title = BRACKET.sub("", TAGS.sub("", m.group(1))).strip()
        pm = re.search(r"[(（]\s*([^)）]+)[)）]", title)
        paren_norm = re.sub(r"[^a-z0-9]+", "", (pm.group(1) if pm else "").lower())
        cn = re.split(r"[(（]", title)[0].strip()
        if not cn or not re.search(r"[一-鿿]", cn):
            continue
        if any(b in title for b in bad):
            continue
        if paren_norm and want and paren_norm == want:
            score = 9
        elif paren_norm and want and paren_norm.startswith(want):
            score = 6
        elif re.sub(r"[^a-z0-9]+", "", cn.lower()) == want:
            score = 8
        else:
            continue
        if score > best_score or (score == best_score and len(cn) < best_len):
            best_score, best_cn, best_len = score, cn, len(cn)
    return best_cn


CACHE_VER = "v3:"


def lookup(name, timeout=8):
    """中文名：先 MC百科 搜索匹配，再苦力怕论坛；查不到就空着，不编。"""
    key = CACHE_VER + clean_name(name).lower()
    if not key.strip("v3:"):
        return ""
    if key in GLOSSARY:
        return GLOSSARY[key]
    cache = _load()
    with _lock:
        if cache.get(key):
            return cache[key]
    zh = ""
    try:
        zh = zh_title(name, timeout)
    except Exception:
        zh = ""
    if not zh:
        try:
            zh = _parse(_fetch(clean_name(name), timeout), clean_name(name))
        except Exception:
            zh = ""
    if not zh:
        try:
            zh = klpbbs(name)
        except Exception:
            zh = ""
    if zh:
        with _lock:
            cache[key] = zh
            _save(cache)
    return zh


def zh_of(name):
    """只查缓存和词典，不联网卡住界面；查不到就返回空，前端下一步再补。"""
    key = CACHE_VER + clean_name(name).lower()
    if not key:
        return ""
    if key in GLOSSARY:
        return GLOSSARY[key]
    cache = _load()
    return cache.get(key, "")


def decorate(items, limit=12, workers=4):
    from concurrent.futures import ThreadPoolExecutor

    targets = items[:limit]

    def one(item):
        if not item.get("zh"):
            item["zh"] = lookup(item.get("title") or "")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, targets))
    return items


def warm(names, workers=3):
    def run():
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(lambda n: lookup(n), names))
    threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    for name in ("Sodium", "Iris Shaders", "Better Archeology", "Entity Culling",
                 "Waystones", "Ars Nouveau", "More Culling", "Fabulously Optimized"):
        print(name, "->", lookup(name))


def _my_translate(chunk, timeout=12):
    url = ("https://api.mymemory.translated.net/get?q=" + urllib.parse.quote(chunk[:480])
           + "&langpair=en|zh-CN")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    return ((data.get("responseData") or {}).get("translatedText") or "").strip()


def translate_long(text, max_chars=1200, timeout=12):
    """整段英文翻中文，分段请求，带缓存。"""
    raw = (text or "").strip()
    if not raw:
        return ""
    raw = raw[:max_chars]
    cache = _load()
    key = "body:" + str(abs(hash(raw)))
    with _lock:
        if cache.get(key):
            return cache[key]
    chunks = []
    buffer = ""
    for sentence in re.split(r"(?<=[.!?])\s+", raw):
        if len(buffer) + len(sentence) > 420:
            if buffer:
                chunks.append(buffer)
            buffer = sentence
        else:
            buffer = (buffer + " " + sentence).strip()
    if buffer:
        chunks.append(buffer)
    out = []
    for chunk in chunks[:6]:
        try:
            part = _my_translate(chunk, timeout)
        except Exception:
            part = ""
        if part:
            out.append(part)
    result = "\n".join(out)
    if result:
        with _lock:
            cache[key] = result
            _save(cache)
    return result
