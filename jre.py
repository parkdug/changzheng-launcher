"""jre — 按游戏版本自动准备 Java：本地没有就去 Adoptium 拉一个 JRE 回来。"""

import json
import os
import re
import shutil
import sys
import urllib.request
import zipfile

import ssl

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


def _open(req, timeout=60):
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except Exception:
        return urllib.request.urlopen(req, timeout=timeout, context=_ctx())


API = "https://api.adoptium.net/v3/assets/latest/%d/hotspot?os=windows&arch=x64&image_type=jre"
UA = "ChangzhengLauncher/1.1"


def required_major(mc_version):
    """这个 Minecraft 版本需要哪个大版本的 Java。"""
    if isinstance(mc_version, dict):
        mc_version = mc_version.get("inheritsFrom") or mc_version.get("id") or ""
    text = str(mc_version or "").strip()
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not m:
        return 17
    major = int(m.group(1))
    minor = int(m.group(2))
    patch = int(m.group(3) or 0)
    if major == 1:
        if minor <= 16:
            return 8
        if minor <= 20 and patch <= 4:
            return 17
        return 21
    return 21


def _scan(base):
    """找出本地已经下过的 java.exe。"""
    found = []
    if not os.path.isdir(base):
        return found
    for name in os.listdir(base):
        exe = os.path.join(base, name, "bin", "java.exe")
        if os.path.isfile(exe):
            found.append(exe)
        deeper = os.path.join(base, name)
        for root, dirs, files in os.walk(deeper):
            if "java.exe" in files and os.path.basename(root) == "bin":
                found.append(os.path.join(root, "java.exe"))
                break
    return found


def _version_of(exe):
    import subprocess
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=12,
                             creationflags=0x08000000 if sys.platform == "win32" else 0)
        text = (out.stderr or "") + (out.stdout or "")
        m = re.search(r'version "(\d+)(?:\.(\d+))?', text)
        if not m:
            return 0
        first = int(m.group(1))
        if first == 1:
            return int(m.group(2) or 8)
        return first
    except Exception:
        return 0


def pick(base, want):
    """本地有没有合适大版本的 java。"""
    best = None
    for exe in _scan(base):
        major = _version_of(exe)
        if major == want or (want == 8 and major == 8):
            return exe, major
        if major and best is None:
            best = (exe, major)
    return (best if best and best[1] == want else (None, 0))


def download(major, base, progress=None):
    """拉一个 JRE 回来，返回 java.exe 路径。"""
    say = progress or (lambda _t: None)
    os.makedirs(base, exist_ok=True)
    say("查 Java %d 下载地址…" % major)
    req = urllib.request.Request(API % major, headers={"User-Agent": UA})
    with _open(req, 40) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data:
        raise RuntimeError("没有找到 Java %d 的安装包" % major)
    binary = data[0]["binary"]
    link = binary["package"]["link"]
    name = binary["package"]["name"]
    target = os.path.join(base, name)
    say("下载 Java %d（%s）" % (major, name))
    tmp = target + ".part"
    with _open(urllib.request.Request(link, headers={"User-Agent": UA}), 300) as resp, open(tmp, "wb") as handle:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            handle.write(chunk)
            done += len(chunk)
            if total:
                say("Java %d：%d%%" % (major, int(done * 100 / total)))
    os.replace(tmp, target)
    folder = os.path.join(base, ("jre%d" % major))
    if os.path.isdir(folder):
        shutil.rmtree(folder, ignore_errors=True)
    say("解压 Java %d…" % major)
    with zipfile.ZipFile(target) as zf:
        zf.extractall(folder)
    os.remove(target)
    for root, dirs, files in os.walk(folder):
        if "java.exe" in files and os.path.basename(root) == "bin":
            say("Java %d 准备好了" % major)
            return os.path.join(root, "java.exe")
    raise RuntimeError("解压完没找到 java.exe")


def ensure(base, mc_version, progress=None):
    """要哪个就保证有哪个，返回 (java.exe, major)。"""
    want = required_major(mc_version)
    exe, major = pick(base, want)
    if exe:
        return exe, major
    return download(want, base, progress), want
