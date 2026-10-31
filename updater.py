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
    """只取数字段比较，1.2.0 > 1.1.101 这种要先补齐长度。"""
    import re as _re
    nums = _re.findall(r"\d+", str(text or "0"))
    if not nums:
        return (0,)
    parts = [int(n) for n in nums[:4]]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts)


GITEE_API_JSON = ("https://gitee.com/api/v5/repos/parkty/changzheng-launcher/"
                  "contents/version.json?ref=main")


def _gitee_api_json(timeout=6):
    """Gitee 的 raw 有缓存，走 API 拿最新的版本清单。"""
    import base64
    with _open(GITEE_API_JSON + "&t=%d" % int(time.time()), timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = (data or {}).get("content") or ""
    if not content:
        raise RuntimeError("没有内容")
    return json.loads(base64.b64decode(content).decode("utf-8"))


# 只认 Gitee：国内快、是唯一发布口
SOURCES = [
    "https://gitee.com/parkty/changzheng-launcher/raw/main/version.json",
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
        data["newer"] = _ver_key(data.get("latest") or "") > _ver_key(current)
        data["current"] = current
        return data

    sources = [u for u in (["gitee-api", extra] + SOURCES) if u]
    results = []
    lock = threading.Lock()

    def worker(src):
        try:
            if src == "gitee-api":
                data = _gitee_api_json(6)
                src_label = GITEE_API_JSON
            else:
                with _open(src, 5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                src_label = src
            latest = str(data.get("version") or "")
            if latest:
                with lock:
                    results.append({
                        "ok": True, "latest": latest, "current": current,
                        "url": data.get("download") or "", "notes": data.get("notes") or "",
                        "parts": data.get("parts") or [],
                        "newer": _ver_key(latest) > _ver_key(current), "source": src_label,
                    })
        except Exception:
            pass

    threads = [threading.Thread(target=worker, args=(s,), daemon=True) for s in sources]
    for th in threads:
        th.start()
    started = time.time()
    for th in threads:
        th.join(2.5)
    if not results:
        for th in threads:
            th.join(max(1.0, 6 - (time.time() - started)))
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


GITEE_API = "https://gitee.com/api/v5/repos/parkty/changzheng-launcher/releases"
GITEE_RELEASE = "https://gitee.com/parkty/changzheng-launcher/releases/download/app-latest/"
GITEE_CACHE = {"ts": 0.0, "url": ""}


def gitee_asset():
    """去 Gitee 找一个叫 changzheng-launcher.zip 的附件，返回直链。"""
    import time
    if GITEE_CACHE["url"] and time.time() - GITEE_CACHE["ts"] < 600:
        return GITEE_CACHE["url"]
    try:
        with _open(GITEE_API, 8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for rel in data if isinstance(data, list) else []:
            for asset in rel.get("assets") or []:
                if asset.get("name") == "changzheng-launcher.zip":
                    GITEE_CACHE["ts"] = time.time()
                    GITEE_CACHE["url"] = asset.get("browser_download_url") or ""
                    return GITEE_CACHE["url"]
    except Exception:
        pass
    return ""


def _candidates(url):
    """GitHub 的包，同时试试 Gitee 上同名附件（有就自动用，没有探测会返回 0）。"""
    out = []
    name = url.rstrip("/").split("/")[-1]
    gitee = gitee_asset()
    if gitee:
        out.append((gitee, ""))
    if name.endswith(".zip"):
        out.append((GITEE_RELEASE + name, ""))
        out.append(("https://gitee.com/parkty/changzheng-launcher/raw/main/" + name, ""))
    for prefix in MIRRORS:
        out.append(((prefix + url) if prefix else url, prefix))
    return out


def speed_test(url):
    scored = []

    def worker(real, _prefix):
        scored.append((_probe(real), real))

    threads = [threading.Thread(target=worker, args=(real, p), daemon=True)
               for real, p in _candidates(url)]
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


def _stream_download(real, target, say):
    with _open(real, 120) as resp, open(target, "wb") as handle:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            handle.write(chunk)
            done += len(chunk)
            if total:
                say("更新包 %d%%" % int(done * 100 / total))
    return os.path.getsize(target)


def _download_parts(parts, target, say):
    """分卷：一个个下，拼成完整 zip。"""
    tmp_files = []
    for idx, part_url in enumerate(parts, 1):
        tmp = "%s.part%d" % (target, idx)
        say("下载分卷 %d/%d" % (idx, len(parts)))
        ok = False
        for attempt in range(3):
            try:
                _stream_download(part_url, tmp, lambda m: say("分卷 %d/%d %s" % (idx, len(parts), m)))
                ok = True
                break
            except Exception:
                continue
        if not ok:
            raise RuntimeError("分卷 %d 下载失败" % idx)
        tmp_files.append(tmp)
    with open(target, "wb") as out:
        for tmp in tmp_files:
            with open(tmp, "rb") as src:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
    for tmp in tmp_files:
        try:
            os.remove(tmp)
        except Exception:
            pass
    return target


def download(url, target, progress=None, tries=2, chunks=24, parts=None):
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

    if parts and not url:
        url = parts[0]
    if parts:
        try:
            say("共 %d 个分卷" % len(parts))
            _download_parts(parts, target, say)
            if not valid(target):
                raise RuntimeError("合并后的包坏了")
            say("更新包下好了（100/100）")
            return target, ""
        except Exception as error:
            say("分卷下载失败：%s，换单文件" % str(error)[:40])

    gitee_first = gitee_asset()
    if gitee_first:
        try:
            say("从 Gitee 国内节点下载")
            _stream_download(gitee_first, target, say)
            if valid(target):
                say("更新包下好了（100/100）")
                return target, ""
            raise RuntimeError("包坏了")
        except Exception:
            say("Gitee 那边没成功，换别的线路")
            try:
                if os.path.isfile(target):
                    os.remove(target)
            except Exception:
                pass
    candidates = []
    if gitee_first:
        candidates.append((0, gitee_first))
    for item in speed_test(url):
        if item[1] != gitee_first:
            candidates.append(item)
    if not candidates:
        candidates = [(0, url)]
    say("找到 %d 条可用线路，正在挑最快的下" % len(candidates))

    for speed, real in candidates[:3]:
        try:
            head = _open(real, 20, {"User-Agent": UA, "Range": "bytes=0-0"})
            supports_range = getattr(head, "status", 200) == 206
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
            if not supports_range:
                say("这条线路不支持分块，整包下载")
                with _open(real, 120) as resp, open(target, "wb") as handle:
                    done = 0
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        handle.write(chunk)
                        done += len(chunk)
                        say("更新包 %d%%" % int(done * 100 / size))
                if not valid(target):
                    raise RuntimeError("包坏了")
                say("更新包下好了（100/100）")
                return target, ""
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
