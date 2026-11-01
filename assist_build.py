"""assist_build — 给「小助手定制」补上构建能力：自动下载 Gradle，编 Fabric/Forge 工程。

Gradle 只在第一次构建时下载（腾讯镜像，约 120MB），之后一直复用。
"""

import glob
import os
import shutil
import subprocess
import urllib.request
import zipfile

GRADLE_VERSION = "8.7"
MIRRORS = [
    "https://mirrors.cloud.tencent.com/gradle/gradle-%s-bin.zip" % GRADLE_VERSION,
    "https://services.gradle.org/distributions/gradle-%s-bin.zip" % GRADLE_VERSION,
]


def _jdk_home(base):
    for root in (r"D:\JAVA", os.path.join(base, "java"), r"C:\Program Files\Java",
                 r"C:\Program Files\Eclipse Adoptium"):
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            if os.path.isfile(os.path.join(root, name, "bin", "javac.exe")):
                return os.path.join(root, name)
        if os.path.isfile(os.path.join(root, "bin", "javac.exe")):
            return root
    return ""


def ensure_gradle(base, progress=None):
    say = progress or (lambda msg: None)
    tools = os.path.join(base, "tools")
    target_dir = os.path.join(tools, "gradle-%s" % GRADLE_VERSION)
    if os.path.isdir(target_dir):
        return target_dir
    os.makedirs(tools, exist_ok=True)
    zip_path = os.path.join(tools, "gradle-%s-bin.zip" % GRADLE_VERSION)
    last_error = ""
    for url in MIRRORS:
        try:
            say("正在下载 Gradle %s…" % GRADLE_VERSION)

            def hook(blocks, block_size, total):
                if total > 0 and blocks % 40 == 0:
                    say("Gradle %d%%" % int(min(100, blocks * block_size * 100 / total)))

            urllib.request.urlretrieve(url, zip_path, reporthook=hook)
            break
        except Exception as error:
            last_error = str(error)
            continue
    if not os.path.isfile(zip_path) or os.path.getsize(zip_path) < 10 * 1024 * 1024:
        raise RuntimeError("Gradle 下载失败：%s" % last_error)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tools)
    if os.path.isdir(target_dir):
        return target_dir
    for name in os.listdir(tools):
        if name.startswith("gradle-") and os.path.isdir(os.path.join(tools, name)):
            return os.path.join(tools, name)
    raise RuntimeError("Gradle 解压后找不到目录")


def build_mod(project_root, base, progress=None, timeout=1200):
    """跑 gradle build，返回产出的 jar 路径。"""
    say = progress or (lambda msg: None)
    gradle_home = ensure_gradle(base, progress)
    gradle_bat = os.path.join(gradle_home, "bin", "gradle.bat")
    jdk = _jdk_home(base)
    if not os.path.isfile(gradle_bat):
        raise RuntimeError("Gradle 不完整")
    env = dict(os.environ)
    if jdk:
        env["JAVA_HOME"] = jdk
        env["PATH"] = os.path.join(jdk, "bin") + os.pathsep + env.get("PATH", "")
    say("正在构建（首次会拉依赖，久一点）…")
    cmd = [gradle_bat, "build", "--no-daemon", "-q", "-x", "test"]
    try:
        proc = subprocess.run(cmd, cwd=project_root, env=env, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError("构建超时（20 分钟）")
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-300:]
        raise RuntimeError("构建失败：%s" % tail.replace("\n", " ")[:220])
    jars = [p for p in glob.glob(os.path.join(project_root, "build", "libs", "*.jar"))
            if "-sources" not in p and "-dev" not in p]
    if not jars:
        raise RuntimeError("构建完成但没找到 jar")
    return max(jars, key=os.path.getmtime)


def install_jar(jar, version_dir, base):
    dest_dir = os.path.join(version_dir, "mods")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(jar))
    shutil.copyfile(jar, dest)
    return dest
