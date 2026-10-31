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


def check_update(current="1.0.0", url=""):
    """检查更新：多个源依次试，谁先给出结果用谁。"""
    sources = [u for u in (url,
                           "https://cdn.jsdelivr.net/gh/parkdug/changzheng-launcher@latest/version.json",
                           "https://raw.githubusercontent.com/parkdug/changzheng-launcher/main/version.json",
                           "https://cdn.jsdelivr.net/gh/parkdug/changzheng-launcher@main/version.json") if u]
    seen = set()
    errors = []
    best = None
    for src in sources:
        if src in seen:
            continue
        seen.add(src)
        try:
            with _open(src) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latest = str(data.get("version") or "")
            if not latest:
                continue
            item = {"ok": True, "current": current, "latest": latest,
                    "url": data.get("download") or "", "notes": data.get("notes") or "",
                    "newer": latest != current, "source": src}
            key = tuple(int(x) if x.isdigit() else 0 for x in latest.split("."))
            if best is None or key > best[0]:
                best = (key, item)
        except Exception as error:
            errors.append("%s: %s" % (src.split("/")[2], str(error)[:60]))
    if best:
        return best[1]
    return {"ok": False, "error": "都没取到（" + "；".join(errors) + "）"}
