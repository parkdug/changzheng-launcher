"""mods_api — 用 Modrinth 的开源接口搜模组、按加载器和版本下载。

不需要密钥，直接能查。
"""

import json
import os
import urllib.parse
import urllib.request

API = "https://api.modrinth.com/v2"
UA = "ChangzhengLauncher/0.1 (local)"

# 说人话 → 搜索词：他问「有没有优化帧数的」也能搜到
# Modrinth 的关键词是「全都要匹配」，所以这里给单个最准的词，别堆。
INTENT = [
    (("卡", "帧数", "fps", "优化", "流畅"), "sodium"),
    (("小地图", "地图"), "minimap"),
    (("背包", "合成", "配方", "查询"), "jei"),
    (("光影", "着色", "shader"), "iris"),
    (("机械", "自动化", "工厂"), "create"),
    (("区块", "加载"), "chunky"),
    (("生命", "血量", "界面", "hud"), "appleskin"),
    (("生物", "怪物", "boss"), "bosses"),
    (("建筑", "造房子"), "building"),
    (("农业", "种田"), "farming"),
    (("整理", "排序"), "inventory"),
    (("跑图", "探索"), "xaero"),
    (("鞘翅", "飞行"), "elytra"),
]


def _get(url):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def detect_loader(version_json):
    """从 version json 的 libraries 里判断加载器。"""
    names = " ".join((lib.get("name") or "") for lib in (version_json.get("libraries") or []))
    low = names.lower()
    if "neoforge" in low:
        return "neoforge"
    if "fabric-loader" in low or "fabric" in low:
        return "fabric"
    if "quilt" in low:
        return "quilt"
    if "forge" in low:
        return "forge"
    return "vanilla"


def guess_query(text):
    low = (text or "").lower()
    for words, query in INTENT:
        if any(word in low for word in words):
            return query
    return text


def search(query, loader="fabric", mc_version="1.18.2", limit=10):
    q = guess_query(query)
    base = [["project_type:mod"]]
    attempts = []
    if loader and loader != "vanilla":
        attempts.append(base + [["categories:%s" % loader], ["versions:%s" % mc_version]])
        attempts.append(base + [["categories:%s" % loader]])
    if mc_version:
        attempts.append(base + [["versions:%s" % mc_version]])
    attempts.append(base)
    attempts.append([])
    hits = []
    for facets in attempts:
        params = {"query": q, "limit": str(limit), "index": "downloads"}
        if facets:
            params["facets"] = json.dumps(facets)
        try:
            data = _get(API + "/search?" + urllib.parse.urlencode(params))
        except Exception:
            continue
        hits = data.get("hits") or []
        if hits:
            break
    out = []
    for hit in hits:
        out.append({
            "id": hit.get("project_id") or hit.get("slug"),
            "slug": hit.get("slug"),
            "title": hit.get("title"),
            "desc": hit.get("description"),
            "downloads": hit.get("downloads", 0),
            "follows": hit.get("follows", 0),
            "categories": hit.get("categories") or [],
            "versions": hit.get("versions") or [],
            "icon": hit.get("icon_url"),
        })
    return out


def search_project(query, project_type, mc_version="", loaders=None, limit=8, offset=0):
    """按项目类型搜（mod / shader / resourcepack / datapack / modpack / plugin）。"""
    base = [["project_type:%s" % project_type]]
    attempts = []
    typed = base[:]
    for loader in loaders or []:
        if loader:
            typed = typed + [["categories:%s" % loader]]
    if mc_version:
        attempts.append(typed + [["versions:%s" % mc_version]])
    if typed != base:
        attempts.append(typed)
    if mc_version:
        attempts.append(base + [["versions:%s" % mc_version]])
    attempts.append(base)
    attempts.append([])
    hits = []
    for facets in attempts:
        params = {"query": query, "limit": str(limit), "index": "downloads", "offset": str(offset)}
        if facets:
            params["facets"] = json.dumps(facets)
        try:
            data = _get(API + "/search?" + urllib.parse.urlencode(params))
        except Exception:
            continue
        hits = data.get("hits") or []
        if hits:
            break
    out = []
    for hit in hits:
        out.append({
            "id": hit.get("project_id") or hit.get("slug"),
            "slug": hit.get("slug"),
            "title": hit.get("title"),
            "desc": hit.get("description"),
            "downloads": hit.get("downloads", 0),
            "categories": hit.get("categories") or [],
            "versions": hit.get("versions") or [],
            "icon": hit.get("icon_url"),
        })
    return out


def pick_file_for(project_id, mc_version, loaders=None):
    """按游戏版本（和加载器，如果有）挑最新匹配文件。"""
    for use_loaders in ([l for l in (loaders or []) if l], []):
        params = {}
        if mc_version:
            params["game_versions"] = json.dumps([mc_version])
        if use_loaders:
            params["loaders"] = json.dumps(use_loaders)
        url = API + "/project/%s/version" % project_id
        if params:
            url += "?" + urllib.parse.urlencode(params)
        try:
            versions = _get(url)
        except Exception:
            continue
        for latest in versions:
            for f in latest.get("files") or []:
                if f.get("primary") or str(f.get("filename", "")).endswith(".jar"):
                    return {
                        "name": f.get("filename"),
                        "url": f.get("url"),
                        "size": f.get("size"),
                        "version": latest.get("version_number"),
                    }
    return None


def install_project(item, project_type, mc_version, loaders, dest_dir, filename=None):
    file = pick_file_for(item["id"], mc_version, loaders)
    if not file:
        return None, "这个项目没有适配 %s 的文件" % mc_version
    path = download(file["url"], dest_dir, filename or file["name"])
    return path, ""


def download(url, dest_dir, filename=None):
    os.makedirs(dest_dir, exist_ok=True)
    name = filename or os.path.basename(urllib.parse.urlparse(url).path) or "mod.jar"
    target = os.path.join(dest_dir, name)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req, timeout=60) as resp, open(target, "wb") as handle:
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            handle.write(chunk)
    return target


def install(project, loader, mc_version, mods_dir):
    file = pick_file(project["id"], loader, mc_version)
    if not file:
        return None, "这个模组没有适配 %s/%s 的文件" % (mc_version, loader)
    path = download(file["url"], mods_dir, file["name"])
    return path, ""


def hot(project_type, mc_version="", loaders=None, limit=12, offset=0):
    """不搜关键词，直接给这个类型里下载量最高的。"""
    return search_project("", project_type, mc_version, loaders, limit, offset)


def dependencies(project_id, limit=6):
    """这个项目依赖谁（前置 mod）。"""
    try:
        data = _get(API + "/project/%s/dependencies" % project_id)
    except Exception:
        return []
    out = []
    for item in (data.get("projects") or [])[:limit]:
        out.append({"id": item.get("id"), "slug": item.get("slug"), "title": item.get("title"),
                    "desc": item.get("description") or "", "downloads": 0, "source": "modrinth"})
    return out


def project_detail(project_id, mc_version="", limit=60, loader=""):
    """项目详情 + 版本列表；指定版本/加载器时先精确取“能装的”，再补一批最新的。"""
    import json as _json
    import urllib.parse as _up
    project = _get("https://api.modrinth.com/v2/project/" + project_id)
    rows, seen = [], set()

    def pull(url, compatible):
        try:
            items = _get(url)
        except Exception:
            items = []
        for item in items:
            vid = item.get("id")
            if vid in seen:
                continue
            seen.add(vid)
            files = item.get("files") or []
            primary = next((f for f in files if f.get("primary")), files[0] if files else {})
            rows.append({
                "id": vid,
                "name": item.get("name"),
                "number": item.get("version_number"),
                "mc": item.get("game_versions") or [],
                "loaders": item.get("loaders") or [],
                "date": (item.get("date_published") or "")[:10],
                "downloads": item.get("downloads") or 0,
                "url": primary.get("url"),
                "filename": primary.get("filename"),
                "compatible": compatible,
            })

    base = "https://api.modrinth.com/v2/project/%s/version" % project_id
    if mc_version:
        q = {"game_versions": _json.dumps([mc_version])}
        if loader:
            q["loaders"] = _json.dumps([loader])
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(pull, base + "?" + _up.urlencode(q), True)
            f2 = pool.submit(pull, base, False)
            f1.result()
            f2.result()
    else:
        pull(base, False)
    rows.sort(key=lambda r: (not r["compatible"], r["date"]), reverse=False)
    return {
        "id": project.get("id"),
        "slug": project.get("slug"),
        "title": project.get("title"),
        "desc": project.get("description"),
        "body": project.get("body") or "",
        "icon": project.get("icon_url"),
        "downloads": project.get("downloads") or 0,
        "followers": project.get("followers") or 0,
        "categories": project.get("categories") or [],
        "mc": project.get("game_versions") or [],
        "versions": rows[:limit],
        "mc_version": mc_version,
        "loader": loader,
    }
