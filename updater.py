"""updater — 检查更新与下载更新。

下载策略：先给所有镜像做测速，挑最快的；然后多线程分块下载（8 线程），最后合并校验。
"""

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


def _open(url, timeout=30, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except Exception:
        return urllib.request.urlopen(req, timeout=timeout, context=_ctx())


def _ver_key(text):
    return tuple(int(x) if x.isdigit() else 0 for x in str(text or "0").split("."))


SOURCES = [
    "https://cdn.jsdelivr.net/gh/parkdug/changzheng-launcher@main/version.json",
    "https://raw.githubusercontent.com/parkdug/changzheng-launcher/main/version.json",
    "https://github.com/parkdug/changzheng-launcher/releases/download/app-latest/version.json",
]

MIRRORS = (
    "https://gh-proxy.com/",
    "https://ghproxy.net/",
    "https://ghfast.top/",
    "https://hub.gitmirror.com/",
    "https://gh.llkk.cc/",
    "https://ghproxy.cc/",
    "",
)


def check(current="1.0.0", extra=""):
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
            with _open(src, 5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
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


def _probe(url, size=200000, timeout=6):
    started = time.time()
    try:
        with _open(url, timeout, {"User-Agent": UA, "Range": "bytes=0-%d" % size}) as resp:
            got = len(resp.read(size + 1024))
        return got / max(0.001, time.time() - started)
    except Exception:
        return 0


def speed_test(url):
    scored = []

    def worker(prefix):
        real = (prefix + url) if prefix else url
        scored.append((_probe(real), real))

    threads = [threading.Thread(target=worker, args=(p,), daemon=True) for p in MIRRORS]
    for th in threads:
        th.start()
    for th in threads:
        th.join(8)
    scored.sort(key=lambda item: item[0], reverse=True)
    return [(speed, real) for speed, real in scored if speed > 0]


def _fetch_range(real, start, end, path, counter, size, say, lock):
    headers = {"User-Agent": UA, "Range": "bytes=%d-%d" % (start, end)}
    with _open(real, 60, headers) as resp:
        data = resp.read()
    with open(path, "wb") as handle:
        handle.write(data)
    with lock:
        counter[0] += len(data)
        done = counter[0]
    if size:
        say("更新包 %d%%" % int(done * 100 / size))


def download(url, target, progress=None, tries=2, chunks=24):
    say = progress or (lambda _t: None)
    os.makedirs(os.path.dirname(target), exist_ok=True)

    def valid(path):
        try:
            import zipfile
            with zipfile.ZipFile(path) as zf:
                return zf.testzip() is None
        except Exception:
            return False

    if os.path.isfile(target) and valid(target):
        say("更新包下好了（100/100）")
        return target, ""

    candidates = speed_test(url)
    if not candidates:
        candidates = [(0, url)]
    say("找到 %d 条可用线路，正在挑最快的下" % len(candidates))

    for speed, real in candidates[:3]:
        try:
            head = _open(real, 20, {"User-Agent": UA, "Range": "bytes=0-0"})
            size = 0
            content_range = head.headers.get("Content-Range") or ""
            if "/" in content_range:
                try:
                    size = int(content_range.split("/")[-1])
                except Exception:
                    size = 0
            if not size:
                size = int(head.headers.get("Content-Length") or 0)
            head.close()
            if not size:
                continue
            tmp_dir = target + ".parts"
            os.makedirs(tmp_dir, exist_ok=True)
            step = max(1, size // chunks)
            ranges = []
            for i in range(chunks):
                start = i * step
                end = size - 1 if i == chunks - 1 else (start + step - 1)
                if start <= end:
                    ranges.append((start, end, os.path.join(tmp_dir, "part%d" % i)))
            counter = [0]
            lock = threading.Lock()
            threads = [
                threading.Thread(target=_fetch_range,
                                 args=(real, s, e, path, counter, size, say, lock), daemon=True)
                for s, e, path in ranges
            ]
            for th in threads:
                th.start()
            for th in threads:
                th.join(180)
            if counter[0] < size * 0.99:
                raise RuntimeError("只下了 %d/%d" % (counter[0], size))
            with open(target, "wb") as out:
                for _s, _e, path in ranges:
                    with open(path, "rb") as part:
                        out.write(part.read())
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
            if not valid(target):
                raise RuntimeError("包坏了")
            say("更新包下好了（100/100）")
            return target, ""
        except Exception as error:
            say("这条线路不行（%s），换下一条" % str(error)[:40])
            continue
    return "", "所有线路都没下成功，过会儿再试"
