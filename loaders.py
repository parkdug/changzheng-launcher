"""loaders — 装 Forge / NeoForge：下 installer 再用 java -jar --installClient 装进 .minecraft。"""

import json
import os
import subprocess
import sys
import urllib.request

import mc_core as core

UA = "ChangzhengLauncher/1.1"
FLAGS = 0x08000000 if sys.platform == "win32" else 0


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _json(url):
    return json.loads(_get(url).decode("utf-8", "replace"))


def forge_version(mc_version):
    data = _json("https://maven.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json")
    promos = data.get("promos") or {}
    return promos.get(mc_version + "-latest") or promos.get(mc_version + "-recommended")


def neoforge_version(mc_version):
    """NeoForge 版本号跟 MC 对应：1.20.1 -> 47.x，1.21.1 -> 21.1.x。"""
    try:
        data = _json("https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
                     .replace(".xml", ".xml"))
    except Exception:
        data = None
    return None


def _installer(mc_version, kind, dest_dir, progress=None):
    say = progress or (lambda _t: None)
    jar = os.path.join(dest_dir, "installer-%s.jar" % kind)
    if kind == "forge":
        fv = forge_version(mc_version)
        if not fv:
            raise RuntimeError("Forge 没有 %s 的版本" % mc_version)
        url = ("https://maven.minecraftforge.net/net/minecraftforge/forge/%s-%s/"
               "forge-%s-%s-installer.jar" % (mc_version, fv, mc_version, fv))
    else:
        raise RuntimeError("NeoForge 自动安装还没接好，先用 Fabric 或手动装")
    say("下载 %s 安装器…" % kind)
    os.makedirs(dest_dir, exist_ok=True)
    with open(jar, "wb") as handle:
        handle.write(_get(url, 120))
    java = core.find_java_for(mc_version)
    if not java:
        raise RuntimeError("没找到 Java，装不了 %s" % kind)
    say("运行 %s 安装器…" % kind)
    proc = subprocess.run([java, "-jar", jar, "--installClient", os.path.abspath(dest_dir), "--debug"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          creationflags=FLAGS, timeout=600)
    try:
        os.remove(jar)
    except Exception:
        pass
    if proc.returncode != 0:
        tail = ((proc.stdout or "") + (proc.stderr or ""))[-300:]
        raise RuntimeError("安装器返回 %d：%s" % (proc.returncode, tail))
    say("%s 装好了" % kind)


def install_forge(mc_version, mc_dir, progress=None):
    _installer(mc_version, "forge", mc_dir, progress)


def install_neoforge(mc_version, mc_dir, progress=None):
    _installer(mc_version, "neoforge", mc_dir, progress)
