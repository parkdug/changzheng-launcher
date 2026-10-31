"""updater — 检查更新与下载更新：并行多源、短超时、断点续传、走国内加速。"""

import json
import os
import ssl
import threading
import time
import urllib.request

UA = "ChangzhengLauncher/1.1"
CACHE = {"ts": 0.0, "data": None}

try:
    import certifi
    _CA = certifi.where()
except Exception:
    _CA = None


def _ctx():
    ctx = ssl.create_default_context()
    try:
        ctx.load_default_certs()
    except Exception:
        pass
    if _CA:
        try:
            ctx.load_verify_locations(cafile=_CA)
        except Exception:
            pass
    return ctx


def _fetch(url, timeout=5):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as resp:
            return json.loads(resp.read().decode("utf-8"))


def _ver_key(text):
    return tuple(int(x) if x.isdigit() else 0 for x in str(text or "0").split("."))


SOURCES = [
    "https://cdn.jsdelivr.net/gh/parkdug/changzheng-launcher@main/version.json",
    "https://raw.githubusercontent.com/parkdug/changzheng-launcher/main/version.json",
    "https://github.com/parkdug/changzheng-launcher/releases/download/app-latest/version.json",
]


def check(current="1.0.0", extra=""):
    """并行问几个源，5 秒超时，取版本号最大的。"""
    if CACHE["data"] and time.time() - CACHE["ts"] < 300:
        data = dict(CACHE["data"])
        data["newer"] = data.get("latest") != current
        data["current"] = current
        return data

    sources = [u for u in ([extra] + SOURCES) if u]
    results = []
    lock = threading.Lock()

    def worker(src):
        try:
            data = _fetch(src, 5)
            latest = str(data.get("version") or "")
            if latest:
                with lock:
                    results.append({
                        "ok": True, "latest": latest, "current": current,
                        "url": data.get("download") or "", "notes": data.get("notes") or "",
                        "newer": latest != current, "source": src,
                    })
        except Exception:
            pass

    threads = [threading.Thread(target=worker, args=(s,), daemon=True) for s in sources]
    for th in threads:
        th.start()
    for th in threads:
        th.join(6)

    if not results:
        return {"ok": False, "error": "几个源都没连上，过会儿再试"}
    best = max(results, key=lambda r: _ver_key(r["latest"]))
    CACHE["ts"] = time.time()
    CACHE["data"] = best
    return best


MIRRORS = (
    "https://gh-proxy.com/",
    "https://ghproxy.net/",
    "https://ghfast.top/",
    "",
)


def remote_size(url, timeout=10):
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.headers.get("Content-Length") or 0)
    except Exception:
        return 0


def download(url, target, progress=None, tries=4):
    """下载更新包：镜像轮换 + Range 续传；已经下全了就直接用。"""
    say = progress or (lambda _t: None)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    want = 0
    for prefix in MIRRORS:
        want = remote_size((prefix + url) if prefix else url)
        if want:
            break
    def valid(path):
        try:
            import zipfile
            with zipfile.ZipFile(path) as zf:
                return zf.testzip() is None
        except Exception:
            return False

    if want and os.path.isfile(target):
        have = os.path.getsize(target)
        if have == want:
            if valid(target):
                say("更新包下好了（100/100）")
                return target, ""
            try:
                os.remove(target)
            except Exception:
                pass
        if have > want:
            try:
                os.remove(target)
            except Exception:
                pass
    last = None
    for attempt in range(tries):
        for prefix in MIRRORS:
            real = prefix + url if prefix else url
            try:
                have = os.path.getsize(target) if os.path.isfile(target) else 0
                headers = {"User-Agent": UA}
                if have:
                    headers["Range"] = "bytes=%d-" % have
                req = urllib.request.Request(real, headers=headers)
                try:
                    resp = urllib.request.urlopen(req, timeout=30)
                except Exception:
                    resp = urllib.request.urlopen(req, timeout=30, context=_ctx())
                mode = "ab" if have and getattr(resp, "status", 200) == 206 else "wb"
                if mode == "wb":
                    have = 0
                total = int(resp.headers.get("Content-Length") or 0) + have
                done = have
                with resp, open(target, mode) as handle:
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        handle.write(chunk)
                        done += len(chunk)
                        if total:
                            say("更新包 %d%%" % int(done * 100 / total))
                size = os.path.getsize(target)
                if total and size < total * 0.99:
                    raise RuntimeError("没下完")
                if not valid(target):
                    raise RuntimeError("包坏了")
                say("更新包下好了（100/100）")
                return target, ""
            except Exception as error:
                last = error
                say("线路断了，换一条重试…")
                time.sleep(1)
    return "", "下载失败：%s" % (str(last)[:80] if last else "未知")
