"""tools — 几个 PCL/HMCL 没有的小功能：环境体检、mod 体检、崩溃分析。"""

import hashlib
import json
import os
import re
import shutil
import socket
import ssl
import urllib.request

try:
    import certifi
    _CA = certifi.where()
except Exception:
    _CA = None


def _ctx():
    return ssl.create_default_context(cafile=_CA) if _CA else ssl.create_default_context()


def _open(url, timeout=12, headers=None):
    """先用系统信任库，不行再用 certifi 兜底。"""
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except Exception:
        return urllib.request.urlopen(req, timeout=timeout, context=_ctx())

import assistant
import mc_core as core

UA = "ChangzhengLauncher/1.9"
CRASH_HINTS = [
    (r"OutOfMemoryError|GC overhead limit", "内存不够，去设置里把内存调大（别超过物理内存一半）"),
    (r"UnsupportedClassVersionError|major version", "Java 版本不对，这个版本要更高或更低的 JDK"),
    (r"[Dd]uplicate ?(mod|mods)|DuplicateModsFound", "有重复的 mod，同一个模组放了两个文件"),
    (r"Missing or unsupported mandatory dependencies|requires .* which is missing", "缺前置模组，去小助手搜一下补上"),
    (r"ModResolutionException|Incompatible mod set", "模组冲突，最近加的 mod 之间有排斥"),
    (r"java\.lang\.NoSuchMethodError|NoClassDefFoundError", "模组版本对不上（游戏版本或加载器不匹配）"),
    (r"Pixel format not accelerated|OpenGL|GLFW error", "显卡驱动或渲染问题，试试关掉光影 / 换驱动"),
    (r"Could not find or load main class", "启动参数或 jar 损坏，建议重新安装这个版本"),
    (r"java\.io\.FileNotFoundException|AccessDenied", "文件权限或路径问题，检查游戏目录是否可写"),
]


def health():
    """环境体检：Java、内存、磁盘、目录权限、网络。"""
    out = {"ok": True, "items": []}
    java = core.find_java()
    out["items"].append({"k": "Java", "v": java or "没找到", "ok": bool(java),
                         "tip": "" if java else "装个 JDK 17 或 21，然后把路径填进设置"})
    if java:
        try:
            import subprocess
            res = subprocess.run([java, "-version"], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=10,
                                 creationflags=0x08000000)
            version = (res.stderr or res.stdout or "").splitlines()[0] if (res.stderr or res.stdout) else ""
            out["items"].append({"k": "Java 版本", "v": version.strip(), "ok": True, "tip": ""})
        except Exception as error:
            out["items"].append({"k": "Java 版本", "v": str(error), "ok": False, "tip": ""})

    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        total_gb = stat.ullTotalPhys / (1024 ** 3)
        out["items"].append({"k": "物理内存", "v": "%.1f GB" % total_gb, "ok": total_gb >= 8,
                             "tip": "" if total_gb >= 8 else "内存偏小，游戏内存别超过 2G"})
    except Exception:
        pass

    try:
        usage = shutil.disk_usage(core.MC_DIR)
        free_gb = usage.free / (1024 ** 3)
        out["items"].append({"k": "游戏盘剩余", "v": "%.1f GB" % free_gb, "ok": free_gb >= 5,
                             "tip": "" if free_gb >= 5 else "空间不够了，清一清缓存"})
    except Exception:
        pass

    try:
        probe = os.path.join(core.MC_DIR, ".write-test")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
        out["items"].append({"k": "游戏目录可写", "v": core.MC_DIR, "ok": True, "tip": ""})
    except Exception as error:
        out["items"].append({"k": "游戏目录可写", "v": str(error), "ok": False,
                             "tip": "路径没权限，换个目录或者用管理员跑一次"})

    for name, host in (("Mojang 清单", "piston-meta.mojang.com"), ("Modrinth", "api.modrinth.com")):
        try:
            socket.create_connection((host, 443), timeout=4).close()
            out["items"].append({"k": name, "v": "通", "ok": True, "tip": ""})
        except Exception:
            out["items"].append({"k": name, "v": "连不上", "ok": False,
                                 "tip": "网络问题，下载源可以切 BMCLAPI"})
    return out


def _sha1(path):
    digest = hashlib.sha1()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mod_scan(version_id, limit=40):
    """mod 体检：本地 jar 拿去 Modrinth 对哈希，看有没有重复/可更新。"""
    ver_dir = os.path.join(core.MC_DIR, "versions", version_id)
    mods_dir = os.path.join(ver_dir, "mods")
    if not os.path.isdir(mods_dir):
        return {"ok": False, "error": "这个版本没有 mods 文件夹"}
    jars = [f for f in os.listdir(mods_dir) if f.endswith(".jar")]
    result = {"ok": True, "total": len(jars), "duplicates": [], "unknown": 0,
              "matched": [], "updatable": [], "loader": "", "mc": ""}
    names = {}
    for jar in jars:
        base = re.sub(r"[-_]?\d[\d.]*.*$", "", jar.lower())
        names.setdefault(base, []).append(jar)
    for base, group in names.items():
        if len(group) > 1:
            result["duplicates"].append(group)

    hashes = {}
    for jar in jars[:limit]:
        try:
            hashes[_sha1(os.path.join(mods_dir, jar))] = jar
        except Exception:
            pass
    if not hashes:
        return result
    try:
        payload = json.dumps({"hashes": list(hashes.keys()), "algorithm": "sha1"}).encode("utf-8")
        req = urllib.request.Request("https://api.modrinth.com/v2/version_files",
                                     data=payload, headers={"Content-Type": "application/json",
                                                            "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as error:
        result["error"] = "查不到 Modrinth：%s" % error
        return result
    result["unknown"] = len(jars) - len(data)
    seen = set()
    for h, info in data.items():
        jar = hashes.get(h, "")
        project_id = info.get("project_id")
        if not project_id or project_id in seen:
            continue
        seen.add(project_id)
        result["matched"].append({"jar": jar, "project": project_id,
                                  "version": info.get("version_number")})
    try:
        for item in result["matched"][:12]:
            url = "https://api.modrinth.com/v2/project/%s/version?limit=1" % item["project"]
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=12) as resp:
                latest = json.loads(resp.read().decode("utf-8"))
            if latest and latest[0].get("version_number") != item["version"]:
                item["latest"] = latest[0].get("version_number")
                result["updatable"].append(item)
    except Exception:
        pass
    return result


def crash_report(version_id):
    """崩溃分析：从 crash-reports 和 latest.log 里找原因。"""
    ver_dir = os.path.join(core.MC_DIR, "versions", version_id)
    texts = []
    crash_dir = os.path.join(ver_dir, "crash-reports")
    if os.path.isdir(crash_dir):
        files = sorted(os.listdir(crash_dir))[-2:]
        for name in files:
            try:
                with open(os.path.join(crash_dir, name), encoding="utf-8", errors="replace") as handle:
                    texts.append((name, handle.read()[:60000]))
            except Exception:
                pass
    if not texts:
        for name in ("logs/latest.log", "logs/debug.log"):
            path = os.path.join(ver_dir, name)
            if os.path.isfile(path):
                try:
                    with open(path, encoding="utf-8", errors="replace") as handle:
                        texts.append((name, handle.read()[-40000:]))
                except Exception:
                    pass
    if not texts:
        return {"ok": False, "error": "没找到日志，先启动一次游戏才会有"}

    source, text = texts[-1]
    hits = []
    for pattern, tip in CRASH_HINTS:
        if re.search(pattern, text):
            hits.append(tip)
    causes = re.findall(r"(?:Caused by|Exception in thread)[^\n]{0,160}", text)[-3:]
    return {"ok": True, "source": source, "hits": hits, "causes": causes,
            "size": len(text)}


def check_update(current="1.9", url=""):
    """检查更新：拿远端 version.json 和本地比。"""
    if not url:
        return {"ok": False, "error": "没配置更新地址（设置里 update_url）"}
    try:
        with _open(url) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        latest = str(data.get("version") or "")
        return {"ok": True, "current": current, "latest": latest,
                "url": data.get("download") or "", "notes": data.get("notes") or "",
                "newer": latest != current}
    except Exception as error:
        return {"ok": False, "error": str(error)}


def _modrinth_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def auto_fix(version_id, mc_version, loader, mods_dir, progress=None):
    """小助手自动修：重复 mod 移走、补前置、内存不足调大。"""
    say = progress or (lambda _t: None)
    actions = []
    report = crash_report(version_id)
    hits = report.get("hits") or []

    # 1) 重复的挪走（不删，留个备份目录）
    scan = mod_scan(version_id)
    dups = scan.get("duplicates") or []
    if dups:
        trash = os.path.join(mods_dir, "_duplicates")
        os.makedirs(trash, exist_ok=True)
        moved = 0
        for group in dups:
            keep = max(group, key=len)  # 名字长的一般带版本号
            for jar in group:
                if jar == keep:
                    continue
                try:
                    os.replace(os.path.join(mods_dir, jar), os.path.join(trash, jar))
                    moved += 1
                except Exception:
                    pass
        if moved:
            actions.append({"do": "移走重复 mod %d 个（在 mods/_duplicates）" % moved})

    # 2) 补前置（只有日志明确说缺前置/依赖时才动手，免得乱装）
    need_deps = any(("前置" in h) or ("依赖" in h) for h in hits)
    matched = scan.get("matched") or [] if need_deps else []
    installed = set()
    for item in matched:
        installed.add(item["project"])
    missing = []
    for item in matched[:20]:
        try:
            deps = _modrinth_json("https://api.modrinth.com/v2/project/%s/dependencies" % item["project"])
        except Exception:
            continue
        for dep in deps.get("projects") or []:
            pid = dep.get("id")
            if pid and pid not in installed:
                missing.append({"id": pid, "title": dep.get("title") or pid})
    fixed = []
    for dep in missing[:6]:
        try:
            path, error = assistant.install({"id": dep["id"], "title": dep["title"]}, "mod",
                                            loader, mc_version, os.path.dirname(mods_dir))
            if not error:
                fixed.append(os.path.basename(path))
        except Exception:
            continue
    if fixed:
        actions.append({"do": "补了前置：" + "、".join(fixed)})

    # 3) 内存不足
    if any("内存" in h for h in hits):
        actions.append({"do": "建议把内存调到 4096 MB 以上", "kind": "ram"})

    return {"ok": True, "hits": hits, "actions": actions,
            "report": {"source": report.get("source", ""), "causes": report.get("causes") or []}}
