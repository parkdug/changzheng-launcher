"""import_pack — 导入整合包：支持长征自己导出的 zip 和 Modrinth 的 .mrpack。"""

import hashlib
import json
import os
import shutil
import urllib.request
import zipfile

UA = "ChangzhengLauncher/1.9"


def detect(path):
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if "modrinth.index.json" in names:
                return "mrpack"
            if "manifest.json" in names:
                try:
                    data = json.loads(zf.read("manifest.json").decode("utf-8", "replace"))
                except Exception:
                    data = {}
                if "made_by" in data or "include_game" in data:
                    return "changzheng"
                return "curseforge"
            if any(n.startswith("mods/") for n in names):
                return "plain"
    except Exception:
        return ""
    return ""


def _safe_dir(path):
    return os.path.join(path)


def import_changzheng(path, version_id, mc_dir, progress=None):
    say = progress or (lambda _t: None)
    ver_dir = os.path.join(mc_dir, "versions", version_id)
    mods_dir = os.path.join(ver_dir, "mods")
    os.makedirs(mods_dir, exist_ok=True)
    count = 0
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        info = {}
        try:
            info = json.loads(zf.read("manifest.json").decode("utf-8", "replace"))
        except Exception:
            info = {}
        for name in names:
            if name.startswith("mods/") and name.endswith(".jar"):
                target = os.path.join(mods_dir, os.path.basename(name))
                with zf.open(name) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                count += 1
                if count % 10 == 0:
                    say("导入 mod %d" % count)
        if info.get("include_game", True):
            for name in names:
                if name.startswith(("config/", "shaderpacks/", "resourcepacks/", "defaultconfigs/", "kubejs/")):
                    target = os.path.join(ver_dir, name.replace("/", os.sep))
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with zf.open(name) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
    return {"ok": True, "mods": count, "kind": "changzheng", "version": version_id,
            "name": os.path.basename(path)}


def _download(url, target, sha1=None, progress=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    tmp = target + ".part"
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as handle:
        shutil.copyfileobj(resp, handle, 1 << 20)
    if sha1:
        digest = hashlib.sha1()
        with open(tmp, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        if digest.hexdigest() != sha1:
            os.remove(tmp)
            raise RuntimeError("sha1 不对：%s" % url)
    os.replace(tmp, target)


def import_mrpack(path, version_id, mc_dir, progress=None):
    say = progress or (lambda _t: None)
    ver_dir = os.path.join(mc_dir, "versions", version_id)
    with zipfile.ZipFile(path) as zf:
        index = json.loads(zf.read("modrinth.index.json").decode("utf-8", "replace"))
        files = index.get("files") or []
        total = len(files)
        for i, item in enumerate(files, 1):
            dst_rel = (item.get("path") or "").replace("/", os.sep)
            if not dst_rel:
                continue
            target = os.path.join(ver_dir, dst_rel)
            url = (item.get("downloads") or [""])[0]
            hashes = item.get("hashes") or {}
            try:
                _download(url, target, hashes.get("sha1"))
                say("导入 %d/%d" % (i, total))
            except Exception as error:
                say("跳过 %s（%s）" % (os.path.basename(dst_rel), error))
        for name in zf.namelist():
            if name.startswith("overrides/"):
                rel = name[len("overrides/"):]
                if not rel or rel.endswith("/"):
                    continue
                target = os.path.join(ver_dir, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(name) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    return {"ok": True, "mods": len(files), "kind": "mrpack", "version": version_id,
            "name": index.get("name") or os.path.basename(path)}


def import_plain(path, version_id, mc_dir, progress=None):
    return import_changzheng(path, version_id, mc_dir, progress)


def run(path, version_id, mc_dir, progress=None):
    kind = detect(path)
    if kind == "changzheng":
        return import_changzheng(path, version_id, mc_dir, progress)
    if kind == "mrpack":
        return import_mrpack(path, version_id, mc_dir, progress)
    if kind == "plain":
        return import_plain(path, version_id, mc_dir, progress)
    if kind == "curseforge":
        return {"ok": False, "error": "CurseForge 整合包需要在设置里填 API Key，暂时先别用这种"}
    return {"ok": False, "error": "认不出这个压缩包"}
