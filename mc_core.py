"""mc_core — 读 .minecraft 里的版本、拼启动命令、微软账号登录。

只依赖标准库，方便在任何机器上跑。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid as uuidlib
import zipfile

def _default_mc_dir():
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    local = os.path.join(base, ".minecraft")
    if os.path.isdir(local):
        return local
    # 公开版：没有自带 .minecraft 就用用户家目录下的标准位置
    return os.path.join(os.path.expanduser("~"), ".minecraft")


MC_DIR = os.environ.get("CZ_MC_DIR") or _default_mc_dir()
_BASE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
JAVA_DIR = os.path.join(_BASE, "java")
try:
    import jre as _jre
except Exception:
    _jre = None


def find_java_for(mc_version):
    """优先用按版本适配、已经下好的 Java。"""
    if _jre:
        try:
            exe, _major = _jre.pick(JAVA_DIR, _jre.required_major(mc_version))
            if exe:
                return exe
        except Exception:
            pass
    return find_java()


JAVA_CANDIDATES = [
    r"C:\Program Files\Java",
    r"C:\Program Files (x86)\Java",
    r"C:\Program Files\Eclipse Adoptium",
]
UA = "ChangzhengLauncher/1.0"


# ────────────────────────────── 版本 ──────────────────────────────

def versions_dir() -> str:
    return os.path.join(MC_DIR, "versions")


def list_versions():
    out = []
    root = versions_dir()
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        folder = os.path.join(root, name)
        js = os.path.join(folder, name + ".json")
        if os.path.isfile(js):
            out.append(name)
    return out


def _load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_version(version_id):
    """读 version json，顺着 inheritsFrom 合并父版本。"""
    folder = os.path.join(versions_dir(), version_id)
    path = os.path.join(folder, version_id + ".json")
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    data = _load(path)
    parent_id = data.get("inheritsFrom")
    if parent_id:
        parent = load_version(parent_id)
        data = _merge(parent, data)
    data.setdefault("id", version_id)
    return data


def _merge(parent, child):
    out = dict(parent)
    out["id"] = child.get("id") or parent.get("id")
    libs = list(parent.get("libraries") or [])
    child_libs = child.get("libraries") or []
    if child_libs:
        libs = child_libs if not libs else (libs + child_libs)
    out["libraries"] = libs
    for key in ("mainClass", "minecraftArguments", "assets", "assetIndex", "javaVersion", "type", "downloads"):
        if key in child:
            out[key] = child[key]
    if "arguments" in child:
        merged = {}
        for side in ("game", "jvm"):
            merged[side] = list((parent.get("arguments") or {}).get(side) or []) + list(child["arguments"].get(side) or [])
        out["arguments"] = merged
    return out


def lib_path(lib):
    art = (lib.get("downloads") or {}).get("artifact") or {}
    if art.get("path"):
        return os.path.join(MC_DIR, "libraries", art["path"].replace("/", os.sep))
    name = lib.get("name") or ""
    parts = name.split(":")
    if len(parts) < 3:
        return None
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) > 3 else None
    path = os.path.join(MC_DIR, "libraries", group.replace(".", os.sep), artifact, version,
                        "%s-%s%s.jar" % (artifact, version, "" if not classifier else "-" + classifier))
    return path


def _rules_allow(rules, features=None):
    """返回 True/False/None：None 表示没有 rules，交给默认。"""
    if not rules:
        return None
    features = features or {}
    allow = False
    for rule in rules:
        action = rule.get("action")
        os_name = (rule.get("os") or {}).get("name")
        if os_name and os_name != "windows":
            continue
        rfeat = rule.get("features") or {}
        if any(features.get(k) != v for k, v in rfeat.items()):
            continue
        allow = action == "allow"
    return allow


def classpath(version):
    entries = []
    for lib in version.get("libraries") or []:
        allowed = _rules_allow(lib.get("rules"))
        if allowed is False:
            continue
        if (lib.get("downloads") or {}).get("classifiers"):
            continue
        path = lib_path(lib)
        if path and os.path.isfile(path):
            entries.append(path)
    jar = os.path.join(versions_dir(), version["id"], version["id"] + ".jar")
    if os.path.isfile(jar):
        entries.append(jar)
    return entries


def extract_natives(version):
    """把 natives 里的 dll 解到 <version>-natives，返回目录。"""
    target = os.path.join(versions_dir(), version["id"], version["id"] + "-natives")
    os.makedirs(target, exist_ok=True)
    for lib in version.get("libraries") or []:
        allowed = _rules_allow(lib.get("rules"))
        if allowed is False:
            continue
        classifiers = (lib.get("downloads") or {}).get("classifiers") or {}
        jar = None
        if classifiers.get("natives-windows"):
            jar = os.path.join(MC_DIR, "libraries", classifiers["natives-windows"]["path"].replace("/", os.sep))
        elif lib.get("natives", {}).get("windows"):
            name = (lib.get("name") or "").split(":")
            if len(name) >= 3:
                jar = os.path.join(MC_DIR, "libraries", name[0].replace(".", os.sep), name[1], name[2],
                                   "%s-%s-%s.jar" % (name[1], name[2], lib["natives"]["windows"]))
        if jar and os.path.isfile(jar):
            try:
                with zipfile.ZipFile(jar) as zf:
                    for member in zf.namelist():
                        if member.endswith("/") or member.startswith("META-INF"):
                            continue
                        zf.extract(member, target)
            except Exception:
                pass
    return target


# ────────────────────────────── Java ──────────────────────────────

def find_java():
    """尽量把机器上的 Java 都翻出来：环境变量、注册表、常见目录、PATH、我们下过的。"""
    import subprocess

    found = []

    def add(path):
        if path and os.path.isfile(path) and path not in found:
            found.append(path)

    home = os.environ.get("JAVA_HOME")
    if home:
        add(os.path.join(home, "bin", "java.exe"))
    for root in JAVA_CANDIDATES:
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            add(os.path.join(root, name, "bin", "java.exe"))
    for base in (r"C:\Program Files\Microsoft", r"C:\Program Files\Amazon Corretto",
                 r"C:\Program Files\Zulu", r"C:\Program Files\BellSoft",
                 r"C:\Program Files\Semeru"):
        if os.path.isdir(base):
            for name in os.listdir(base):
                add(os.path.join(base, name, "bin", "java.exe"))
                add(os.path.join(base, name, "jdk", "bin", "java.exe"))
    try:
        out = subprocess.run(["where", "java"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=8,
                             creationflags=0x08000000 if sys.platform == "win32" else 0).stdout
        for line in out.splitlines():
            add(line.strip())
    except Exception:
        pass
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\JavaSoft\Java Runtime Environment") as key:
            pass
    except Exception:
        pass
    if _jre:
        try:
            for exe in _jre._scan(JAVA_DIR):
                add(exe)
        except Exception:
            pass
    return found[0] if found else ""

# ────────────────────────────── 启动 ──────────────────────────────

def _subst(value, table):
    if not isinstance(value, str):
        return value
    for key, rep in table.items():
        value = value.replace("${%s}" % key, str(rep))
    return value


def build_command(version, profile, java=None, ram_mb=4096, extra_jvm=None, extra_game=None,
                  demo=False, game_dir=None):
    if not java:
        vid = version.get("inheritsFrom") or version.get("id") or ""
        java = find_java_for(vid)
    if not java:
        raise RuntimeError("找不到 java.exe")
    version_id = version["id"]
    natives = extract_natives(version)
    cp = os.pathsep.join(classpath(version))
    asset_index = (version.get("assetIndex") or version.get("assets") or {}).get("id") or version.get("assets") or "legacy"
    table = {
        "auth_player_name": profile["name"],
        "version_name": version_id,
        "game_directory": game_dir or MC_DIR,
        "assets_root": os.path.join(MC_DIR, "assets"),
        "assets_index_name": asset_index,
        "auth_uuid": profile["uuid"],
        "auth_access_token": profile["access_token"],
        "auth_session": profile["access_token"],
        "user_type": profile.get("user_type", "msa"),
        "version_type": version.get("type", "release"),
        "clientid": profile.get("client_id", ""),
        "auth_xuid": profile.get("xuid", ""),
        "user_properties": "{}",
        "resolution_width": "854",
        "resolution_height": "480",
        "game_assets": os.path.join(MC_DIR, "assets", "virtual", "legacy"),
        "natives_directory": natives,
        "launcher_name": "ChangzhengLauncher",
        "launcher_version": "0.1",
        "classpath": cp,
        "classpath_separator": os.pathsep,
        "library_directory": os.path.join(MC_DIR, "libraries"),
    }
    features = {"is_demo_user": demo, "has_custom_resolution": False, "has_quick_plays_support": False,
                "is_quick_play_singleplayer": False, "is_quick_play_multiplayer": False, "is_quick_play_realms": False}
    args = [java, "-Xmx%dm" % ram_mb, "-Xms%dm" % min(ram_mb, 1024),
            "-Djava.library.path=" + natives,
            "-Dminecraft.launcher.brand=" + str(profile.get("brand") or "ChangzhengLauncher"),
            "-Dminecraft.launcher.version=" + str(profile.get("brand_version") or "1.9")]
    if extra_jvm:
        args += list(extra_jvm)
    arguments = version.get("arguments") or {}
    jvm = arguments.get("jvm")
    if jvm:
        for item in jvm:
            if isinstance(item, str):
                args.append(_subst(item, table))
            else:
                allowed = _rules_allow(item.get("rules"), features)
                if allowed is False:
                    continue
                value = item.get("value", "")
                if isinstance(value, list):
                    args += [_subst(v, table) for v in value]
                else:
                    args.append(_subst(value, table))
    else:
        args += ["-Djava.library.path=" + natives, "-cp", cp]
    # 版本 json 自己也会写 -Dminecraft.launcher.brand，放最后才盖得住
    brand = str(profile.get("brand") or "ChangzhengLauncher")
    args += ["-Dminecraft.launcher.brand=" + brand,
             "-Dminecraft.launcher.version=" + str(profile.get("brand_version") or "1.9")]
    args.append(version["mainClass"])
    game = arguments.get("game")
    if game:
        for item in game:
            if isinstance(item, str):
                args.append(_subst(item, table))
            else:
                allowed = _rules_allow(item.get("rules"), features)
                if allowed is False:
                    continue
                value = item.get("value", "")
                if isinstance(value, list):
                    args += [_subst(v, table) for v in value]
                else:
                    args.append(_subst(value, table))
    elif version.get("minecraftArguments"):
        for token in version["minecraftArguments"].split():
            args.append(_subst(token, table))
    if extra_game:
        args += list(extra_game)
    return args


def launch(version, profile, **kwargs):
    cmd = build_command(version, profile, **kwargs)
    workdir = kwargs.get("game_dir") or MC_DIR
    creation = 0x08000000 if sys.platform == "win32" else 0
    proc = subprocess.Popen(cmd, cwd=workdir, creationflags=creation)
    return proc, cmd


# ────────────────────────────── 微软登录 ──────────────────────────────

XBL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS = "https://xsts.auth.xboxlive.com/xsts/authorize"
MC_LOGIN = "https://api.minecraftservices.com/authentication/login_with_xbox"
MC_PROFILE = "https://api.minecraftservices.com/minecraft/profile"
DEVICE_CODE = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
TOKEN = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
SCOPE = "XboxLive.signin offline_access"


def _post(url, payload, headers=None):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", UA)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_form(url, form):
    body = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def device_code_start(client_id):
    return _post_form(DEVICE_CODE, {"client_id": client_id, "scope": SCOPE})


def device_code_poll(client_id, device_code, interval=5, timeout=600):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return _post_form(TOKEN, {
                "client_id": client_id, "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
            })
        except urllib.error.HTTPError as error:
            try:
                data = json.loads(error.read().decode("utf-8"))
            except Exception:
                data = {}
            if data.get("error") == "authorization_pending":
                time.sleep(interval)
                continue
            if data.get("error") == "slow_down":
                interval += 2
                time.sleep(interval)
                continue
            raise RuntimeError(data.get("error_description") or data.get("error") or str(error))
    raise RuntimeError("登录超时")


def refresh_ms(client_id, refresh_token):
    return _post_form(TOKEN, {"client_id": client_id, "grant_type": "refresh_token", "refresh_token": refresh_token})


def ms_to_minecraft(ms_access_token):
    xbl = _post(XBL, {
        "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": "d=" + ms_access_token},
        "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT",
    })
    xbl_token = xbl["Token"]
    xsts = _post(XSTS, {
        "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl_token]},
        "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT",
    })
    xsts_token = xsts["Token"]
    uhs = xsts["DisplayClaims"]["xui"][0]["uhs"]
    mc = _post(MC_LOGIN, {"identityToken": "XBL3.0 x=%s;%s" % (uhs, xsts_token)})
    access = mc["access_token"]
    req = urllib.request.Request(MC_PROFILE)
    req.add_header("Authorization", "Bearer " + access)
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        prof = json.loads(resp.read().decode("utf-8"))
    return {
        "name": prof.get("name"),
        "uuid": (prof.get("id") or "").replace("-", ""),
        "access_token": access,
        "user_type": "msa",
        "xuid": (xsts.get("DisplayClaims", {}).get("xui", [{}])[0] or {}).get("xid", ""),
    }


def offline_profile(name="Player"):
    return {"name": name, "uuid": uuidlib.uuid3(uuidlib.NAMESPACE_DNS, "OfflinePlayer:" + name).hex,
            "access_token": "0", "user_type": "legacy"}


# ────────────────────────────── 服务端 ──────────────────────────────

MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


def _get_json(url):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def server_url(mc_version):
    manifest = _get_json(MANIFEST)
    for item in manifest.get("versions") or []:
        if item.get("id") == mc_version:
            data = _get_json(item["url"])
            server = (data.get("downloads") or {}).get("server")
            if server:
                return server["url"]
            break
    raise RuntimeError("这个版本没有官方服务端：%s" % mc_version)


def download_server(mc_version, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    target = os.path.join(dest_dir, "server.jar")
    url = server_url(mc_version)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req, timeout=120) as resp, open(target, "wb") as handle:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            handle.write(chunk)
    return target


if __name__ == "__main__":
    vers = list_versions()
    print("已装版本:", vers)
    print("Java:", find_java())
    if vers:
        ver = load_version(vers[0])
        cmd = build_command(ver, offline_profile("TestPlayer"), ram_mb=2048)
        print("命令长度:", len(" ".join(cmd)))
        print(" ".join(cmd)[:600])
