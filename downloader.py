"""downloader — 装原版和加载器，官方源 / BMCLAPI 镜像都能走。

BMCLAPI 的规矩很简单：把 Mojang 那几个域名换成 bmclapi2.bangbang93.com，路径不变。
"""

import hashlib
import json
import os
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = "ChangzhengLauncher/0.3"

HOSTS = {
    "launchermeta.mojang.com": "bmclapi2.bangbang93.com",
    "launcher.mojang.com": "bmclapi2.bangbang93.com",
    "piston-data.mojang.com": "bmclapi2.bangbang93.com",
    "piston-meta.mojang.com": "bmclapi2.bangbang93.com",
    "libraries.minecraft.net": "bmclapi2.bangbang93.com",
    "resources.download.minecraft.net": "bmclapi2.bangbang93.com",
}

MANIFEST = {
    "official": "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json",
    "bmclapi": "https://bmclapi2.bangbang93.com/mc/game/version_manifest_v2.json",
}


def mirror(url, source):
    if source != "bmclapi":
        return url
    for host, new in HOSTS.items():
        if host in url:
            return url.replace("https://" + host, "https://" + new).replace("http://" + host, "https://" + new)
    return url


def _open(url, timeout=30):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    return urllib.request.urlopen(req, timeout=timeout)


def get_json(url, source="official"):
    with _open(mirror(url, source)) as resp:
        return json.loads(resp.read().decode("utf-8"))


_MANIFEST_CACHE = {}
_MANIFEST_TTL = 600


_MANIFEST_CACHE = {}
_MANIFEST_TTL = 600


def manifest(source="official"):
    import time as _time
    hit = _MANIFEST_CACHE.get(source)
    if hit and _time.time() - hit[0] < _MANIFEST_TTL:
        return hit[1]
    data = get_json(MANIFEST.get(source, MANIFEST["official"]), source)
    out = []
    for item in data.get("versions") or []:
        out.append({"id": item["id"], "type": item.get("type"), "url": item["url"],
                    "release": item.get("releaseTime", "")[:10]})
    _MANIFEST_CACHE[source] = (_time.time(), out)
    return out


def _sha1(path):
    if not os.path.isfile(path):
        return ""
    digest = hashlib.sha1()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url, target, source="official", sha1=None, size=None):
    """带校验的下载：已经完整就跳过。"""
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    if os.path.isfile(target) and (not sha1 or _sha1(target) == sha1):
        return target
    tmp = target + ".part"
    with _open(mirror(url, source), timeout=60) as resp, open(tmp, "wb") as handle:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            handle.write(chunk)
    if sha1 and _sha1(tmp) != sha1:
        os.remove(tmp)
        raise RuntimeError("校验不通过：%s" % os.path.basename(target))
    os.replace(tmp, target)
    return target


def _rules_ok(rules):
    if not rules:
        return True
    ok = False
    for rule in rules:
        os_name = (rule.get("os") or {}).get("name")
        if os_name and os_name != "windows":
            continue
        ok = rule.get("action") == "allow"
    return ok


def install_vanilla(version_id, mc_dir, source="official", progress=None, workers=8):
    """装一个原版版本：json + client.jar + libraries + assets。"""
    say = progress or (lambda _t: None)
    say("正在获取版本清单…")
    entries = manifest(source)
    entry = next((v for v in entries if v["id"] == version_id), None)
    if not entry:
        raise RuntimeError("清单里没有 %s" % version_id)
    say("取版本清单")
    meta = get_json(entry["url"], source)
    ver_dir = os.path.join(mc_dir, "versions", version_id)
    os.makedirs(ver_dir, exist_ok=True)

    jobs = []
    client = (meta.get("downloads") or {}).get("client") or {}
    if client.get("url"):
        jobs.append((client["url"], os.path.join(ver_dir, version_id + ".jar"), client.get("sha1")))

    for lib in meta.get("libraries") or []:
        if not _rules_ok(lib.get("rules")):
            continue
        art = (lib.get("downloads") or {}).get("artifact") or {}
        if art.get("path") and art.get("url"):
            jobs.append((art["url"], os.path.join(mc_dir, "libraries", art["path"].replace("/", os.sep)), art.get("sha1")))
        classifiers = (lib.get("downloads") or {}).get("classifiers") or {}
        nat = classifiers.get("natives-windows") or {}
        if nat.get("path") and nat.get("url"):
            jobs.append((nat["url"], os.path.join(mc_dir, "libraries", nat["path"].replace("/", os.sep)), nat.get("sha1")))

    total = len(jobs)
    done = [0]
    lock = threading.Lock()

    def one(job):
        url, path, sha1 = job
        try:
            fetch(url, path, source, sha1)
        except Exception as error:
            say("跳过 %s（%s）" % (os.path.basename(path), error))
        with lock:
            done[0] += 1
            if done[0] % 10 == 0 or done[0] == total:
                say("依赖 %d/%d" % (done[0], total))

    say("下载依赖 %d 个" % total)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, jobs))

    index = meta.get("assetIndex") or {}
    if index.get("url"):
        idx_path = os.path.join(mc_dir, "assets", "indexes", (index.get("id") or version_id) + ".json")
        fetch(index["url"], idx_path, source, index.get("sha1"))
        say("资源索引好了")
        try:
            with open(idx_path, encoding="utf-8") as handle:
                idx = json.load(handle)
            objects = idx.get("objects") or {}
            asset_jobs = []
            for name, info in objects.items():
                h = info["hash"]
                asset_jobs.append(("https://resources.download.minecraft.net/%s/%s" % (h[:2], h),
                                   os.path.join(mc_dir, "assets", "objects", h[:2], h), h))
            ast_total = len(asset_jobs)
            ast_done = [0]

            def one_asset(job):
                url, path, sha1 = job
                try:
                    fetch(url, path, source, sha1)
                except Exception:
                    pass
                with lock:
                    ast_done[0] += 1
                    if ast_done[0] % 100 == 0 or ast_done[0] == ast_total:
                        say("资源 %d/%d" % (ast_done[0], ast_total))

            with ThreadPoolExecutor(max_workers=workers * 2) as pool:
                list(pool.map(one_asset, asset_jobs))
        except Exception as error:
            say("资源下载出问题：%s" % error)

    with open(os.path.join(ver_dir, version_id + ".json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=2)
    say("%s 装好了（100/100）" % version_id)
    return ver_dir


def fabric_loaders(mc_version):
    """fabric 官方源国内经常握手超时，退回 BMCLAPI 的 fabric-meta 镜像。"""
    urls = [
        "https://meta.fabricmc.net/v2/versions/loader/%s" % mc_version,
        "https://bmclapi2.bangbang93.com/fabric-meta/v2/versions/loader/%s" % mc_version,
    ]
    last = None
    for url in urls:
        try:
            data = get_json(url)
            return [item["loader"]["version"] for item in data]
        except Exception as error:
            last = error
    raise RuntimeError("拿不到 Fabric loader 列表：%s" % last)


def install_fabric(mc_version, mc_dir, loader=None):
    """写一份 fabric 版本 json，复用原版的文件。"""
    loaders = fabric_loaders(mc_version)
    if not loaders:
        raise RuntimeError("Fabric 没有 %s 的 loader" % mc_version)
    loader = loader or loaders[0]
    urls = [
        "https://meta.fabricmc.net/v2/versions/loader/%s/%s/profile/json" % (mc_version, loader),
        "https://bmclapi2.bangbang93.com/fabric-meta/v2/versions/loader/%s/%s/profile/json" % (mc_version, loader),
    ]
    profile = None
    last = None
    for url in urls:
        try:
            profile = get_json(url)
            break
        except Exception as error:
            last = error
    if not profile:
        raise RuntimeError("拿不到 Fabric profile：%s" % last)
    vid = profile.get("id") or "fabric-loader-%s-%s" % (loader, mc_version)
    ver_dir = os.path.join(mc_dir, "versions", vid)
    os.makedirs(ver_dir, exist_ok=True)
    libs = []
    for lib in profile.get("libraries") or []:
        name = lib.get("name") or ""
        parts = name.split(":")
        url = (lib.get("url") or "https://maven.fabricmc.net/").rstrip("/")
        if len(parts) >= 3:
            group, artifact, version = parts[0], parts[1], parts[2]
            rel = "%s/%s/%s/%s-%s.jar" % (group.replace(".", "/"), artifact, version, artifact, version)
            libs.append({"name": name,
                         "downloads": {"artifact": {"path": rel, "url": url + "/" + rel}}})
    data = {
        "id": vid,
        "inheritsFrom": mc_version,
        "type": "release",
        "mainClass": profile.get("mainClass", "net.fabricmc.loader.impl.launch.knot.KnotClient"),
        "arguments": {"game": [], "jvm": []},
        "libraries": libs,
    }
    with open(os.path.join(ver_dir, vid + ".json"), "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    return vid


def forge_installer_url(mc_version, forge_version):
    return ("https://maven.minecraftforge.net/net/minecraftforge/forge/%s-%s/forge-%s-%s-installer.jar"
            % (mc_version, forge_version, mc_version, forge_version))


def neoforge_installer_url(neoforge_version):
    return ("https://maven.neoforged.net/releases/net/neoforged/neoforge/%s/neoforge-%s-installer.jar"
            % (neoforge_version, neoforge_version))


def download_file(url, target, source="official", progress=None):
    say = progress or (lambda _t: None)
    say("下载 %s" % os.path.basename(target))
    fetch(url, target, source)
    return target


# ─────────────────────── CurseForge ───────────────────────

CF_API = "https://api.curseforge.com/v1"
CF_GAME_ID = 432
CF_CLASS = {"mod": 6, "modpack": 4471, "resourcepack": 12, "shader": 6552, "datapack": 6945, "plugin": 5}


def _cf_headers(key):
    return {"x-api-key": key, "Accept": "application/json", "User-Agent": UA}


def _cf_get(url, key):
    req = urllib.request.Request(url)
    for k, v in _cf_headers(key).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def curseforge_search(key, query, kind="mod", mc_version="", limit=12):
    if not key:
        raise RuntimeError("CurseForge 要 API key，去设置页填")
    class_id = CF_CLASS.get(kind, 6)
    params = ["gameId=%d" % CF_GAME_ID, "classId=%d" % class_id,
              "searchFilter=%s" % urllib.request.quote(query), "pageSize=%d" % limit,
              "sortField=2", "sortOrder=desc"]
    if mc_version:
        params.append("gameVersion=%s" % mc_version)
    data = _cf_get(CF_API + "/mods/search?" + "&".join(params), key)
    out = []
    for item in data.get("data") or []:
        out.append({
            "id": str(item.get("id")),
            "title": item.get("name"),
            "desc": item.get("summary"),
            "downloads": item.get("downloadCount", 0),
            "source": "curseforge",
        })
    return out


def curseforge_file_url(key, mod_id, mc_version="", loader=None):
    params = ["gameVersion=%s" % mc_version] if mc_version else []
    if loader:
        params.append("modLoaderType=%s" % {"fabric": 4, "forge": 1, "quilt": 5, "neoforge": 6}.get(loader, 1))
    data = _cf_get(CF_API + "/mods/%s/files?%s" % (mod_id, "&".join(params) or "pageSize=1"), key)
    files = data.get("data") or []
    if not files:
        raise RuntimeError("CurseForge 没有匹配文件")
    file_id = files[0]["id"]
    info = _cf_get(CF_API + "/mods/%s/files/%s/download-url" % (mod_id, file_id), key)
    url = (info.get("data") or "")
    if not url:
        raise RuntimeError("CurseForge 不给下载直链")
    return {"url": url, "name": files[0].get("fileName") or ("%s.jar" % mod_id)}


# ─────────────────────── mrpack 整合包 ───────────────────────

def import_mrpack(pack_path, mc_dir, progress=None, source="bmclapi"):
    """把 .mrpack 装成一个独立版本：先装原版，再铺 mods/config。"""
    import zipfile
    say = progress or (lambda _t: None)
    name = os.path.splitext(os.path.basename(pack_path))[0]
    say("打开整合包 %s" % name)
    with zipfile.ZipFile(pack_path) as zf:
        index = json.loads(zf.read("modrinth.index.json").decode("utf-8"))
        deps = index.get("dependencies") or {}
        mc_ver = deps.get("minecraft")
        fabric_ver = deps.get("fabric-loader")
        forge_ver = deps.get("forge")
        quilt_ver = deps.get("quilt-loader")
        if not mc_ver:
            raise RuntimeError("整合包没写 minecraft 版本")
        installed = os.path.join(mc_dir, "versions")
        has_base = os.path.isdir(os.path.join(installed, mc_ver))
        if not has_base:
            say("先装原版 %s" % mc_ver)
            install_vanilla(mc_ver, mc_dir, source, say)
        base = mc_ver
        if fabric_ver:
            say("装 Fabric %s" % fabric_ver)
            base = install_fabric(mc_ver, mc_dir, fabric_ver if not fabric_ver.startswith("-") else None)
        elif forge_ver:
            say("Forge 版本要手动装安装器：%s" % forge_ver)
            base = mc_ver
        elif quilt_ver:
            base = mc_ver

        target_name = "%s-%s" % (name, mc_ver)
        ver_dir = os.path.join(installed, target_name)
        os.makedirs(ver_dir, exist_ok=True)
        say("铺文件")
        files = index.get("files") or []
        done = 0
        for item in files:
            path = item.get("path") or ""
            downloads = item.get("downloads") or []
            if not path or not downloads:
                continue
            dest = os.path.join(ver_dir, path.replace("/", os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            ok = False
            for url in downloads:
                try:
                    fetch(url, dest, source)
                    ok = True
                    break
                except Exception:
                    continue
            done += 1
            if done % 10 == 0 or done == len(files):
                say("整合包文件 %d/%d" % (done, len(files)))

        overrides = [n for n in zf.namelist() if n.startswith("overrides/")]
        for member in overrides:
            rel = member[len("overrides/"):]
            if not rel or member.endswith("/"):
                continue
            dest = os.path.join(ver_dir, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with zf.open(member) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)

    meta = {
        "id": target_name,
        "inheritsFrom": base,
        "type": "release",
        "arguments": {"game": [], "jvm": []},
        "libraries": [],
    }
    with open(os.path.join(ver_dir, target_name + ".json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=2)
    say("整合包装好：%s" % target_name)
    return target_name


# ─────────────────────── OptiFine ───────────────────────

OPTIFINE_PAGE = "https://optifine.net/downloads"


def optifine_install(jar_path, mc_dir, progress=None):
    """OptiFine 官方是点选下载，本地拿到 jar 后走它的安装器（会弹 GUI）。"""
    say = progress or (lambda _t: None)
    if not os.path.isfile(jar_path):
        raise RuntimeError("找不到 %s" % jar_path)
    java = shutil.which("java") or "java"
    say("启动 OptiFine 安装器（会弹窗，选 Install）")
    creation = 0x08000000 if os.name == "nt" else 0
    subprocess.Popen([java, "-jar", jar_path], creationflags=creation)
    return jar_path
