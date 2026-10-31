"""server — 本地 HTTP 后端：网页前端通过它取版本、搜资源、装、启动。

启动：python main.py  （会自己开浏览器）
"""

import json
import os

# 打包后的 exe 没有系统 CA，统一用 certifi，否则 https 全挂
try:
    import ssl

    import certifi

    ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except Exception:
    pass
import socket
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import assistant
import downloader
import mc_core as core
import import_pack
import modgen
import pack_tools
import mods_api
import tools
import translate

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
BASE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else HERE
CONFIG = os.path.join(BASE, "config.json")
PORT = int(os.environ.get("CZ_PORT", "8765"))

VERSION = "1.0.0"
PROGRESS = {"text": "", "percent": None, "ts": 0.0}

FAQ = [
    (("帧数", "卡顿", "掉帧", "fps", "不流畅", "卡"),
     "帧数低先做三件事：关光影、把渲染距离降到 8、装上钠（Sodium）和锂（Lithium）。"
     "下载页搜「钠」就能装，我这儿有中文名。还不够就去设置把内存调到 4G。"),
    (("内存", "分配多少", "ram"),
     "内存看物理内存来，8G 的机器给 2-3G，16G 的给 4-6G，别超过一半。"
     "改完要重启游戏才生效，路径是设置 → 内存与下载。"),
    (("光影", "shader"),
     "光影要两样：Iris（Fabric）或 OptiFine（Forge）当加载器，再加上光影包本身。"
     "光影包装好会自动进 shaderpacks 文件夹，游戏里 选项 → 视频设置 → 光影 就能选。"),
    (("存档", "saves", "世界在哪"),
     "存档在游戏目录里：版本隔离开着就是 versions\<版本名>\saves，关着就是 .minecraft\saves。"
     "你这台机器游戏目录是启动页信息卡上写的那一个。"),
    (("联机", "服务器", "开服", "朋友"),
     "联机页三步：生成开服配置 → 下载服务端 → 开服。局域网直接连 内网IP:25565；"
     "外网得先把 25565 映射出去，要不要我帮你接内网穿透？"),
    (("java", "jdk", "java版本"),
     "1.16 及以下用 Java 8，1.17-1.20 用 Java 17，1.20.5 往上用 Java 21。"
     "装好以后把 java.exe 的路径填进 设置 → 其他 → Java 路径。"),
    (("启动没反应", "点开始没反应", "打不开", "闪退"),
     "先点上面的「帮我看看为什么崩了」，我读日志能看出是内存、Java 还是缺前置。"
     "要是连日志都没有，多半是 Java 路径不对。"),
    (("模组不生效", "mod不生效", "装了不起作用"),
     "三件事确认下：加载器对不对（Fabric 的 mod 不能扔进 Forge）、"
     "mod 是不是放进了对应版本的 mods 文件夹、游戏版本和 mod 版本是否匹配。"),
]
STATE = {"progress": "就绪", "profile": None, "busy": False}
# 小助手的对话上下文：记住上一次搜什么，方便「再推荐几个」接着来
STATE_CONTEXT = {"query": "", "kind": "", "mc": "", "loader": "", "offset": 0, "shown": set()}
FOLLOW_UP = ("再", "还", "更多", "几个", "推荐", "其他", "别的", "换一批", "继续", "再来")


def load_config():
    if os.path.isfile(CONFIG):
        try:
            with open(CONFIG, encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            pass
    return {"client_id": "c36a9fb6-4f2a-41ff-90bd-ae7cc92031eb", "ram_mb": 4096,
            "profile": None, "theme": "red", "curseforge_key": "",
            "isolation": "隔离所有版本", "win_size": "默认", "window_title": "",
            "custom_info": "PCL", "visible": "游戏启动后仍保持不变", "priority": "高",
            "jvm_args": "", "java_path": "", "download_source": "优先官方，慢时换镜像",
            "threads": 8, "speed_limit": 0, "auto_memory": False, "skin": "随机",
            "update_hint": False, "test_hint": False, "auto_chinese": True,
            "launcher_update": "有新版本时自动下载", "announce": "显示所有公告",
            "cache_dir": "", "anonymous": True, "mod_filename": "[标题] 版本", "deepseek_key": "", "update_url": "https://raw.githubusercontent.com/parkdug/changzheng-launcher/main/version.json"}


def save_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as handle:
        json.dump(cfg, handle, ensure_ascii=False, indent=2)


def lan_ip():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"


def progress(msg):
    import re as _re
    import time as _time
    STATE["progress"] = msg
    PROGRESS["text"] = msg
    PROGRESS["ts"] = _time.time()
    m = _re.search(r"(\d+)\s*/\s*(\d+)", msg)
    if m:
        done, total = int(m.group(1)), int(m.group(2))
        if total > 0:
            PROGRESS["percent"] = min(100, int(done * 100 / total))
    try:
        if sys.stdout is not None:
            print(msg, flush=True)
    except Exception:
        pass


def mc_version_of(ver_id):
    import re
    try:
        data = core.load_version(ver_id)
    except Exception:
        return "1.18.2"
    exact = re.compile(r"^(\d+\.\d+(?:\.\d+)?)$")
    tagged = re.compile(r"(\d+\.\d+\.\d+|\d+\.\d+)")
    for candidate in (data.get("clientVersion"), data.get("inheritsFrom")):
        if isinstance(candidate, str) and tagged.search(candidate):
            return tagged.search(candidate).group(1)
    if isinstance(data.get("id"), str) and exact.match(data["id"]):
        return data["id"]
    for lib in data.get("libraries") or []:
        name = lib.get("name") or ""
        if "minecraft" in name and tagged.search(name):
            return tagged.search(name).group(1)
    return "1.18.2"


def loader_of(ver_id):
    try:
        return mods_api.detect_loader(core.load_version(ver_id))
    except Exception:
        return "vanilla"


def versions_payload():
    out = []
    for name in core.list_versions():
        out.append({"id": name, "mc": mc_version_of(name), "loader": loader_of(name)})
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, payload, code=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ctype):
        try:
            with open(path, "rb") as handle:
                body = handle.read()
        except Exception:
            self._json({"ok": False, "error": "not found"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._file(os.path.join(WEB, "index.html"), "text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            name = path[len("/static/"):]
            ext = os.path.splitext(name)[1].lower()
            ctype = {".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8",
                     ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon"}.get(ext, "application/octet-stream")
            self._file(os.path.join(WEB, name), ctype)
            return

        cfg = load_config()
        if cfg.get("mc_dir"):
            core.MC_DIR = cfg["mc_dir"]
        if path == "/api/bootstrap":
            self._json({
                "ok": True,
                "versions": versions_payload(),
                "chosen": STATE.get("chosen") or (core.list_versions() or [None])[0],
                "config": cfg,
                "java": core.find_java(),
                "mcDir": core.MC_DIR,
                "profile": cfg.get("profile"),
                "progress": STATE["progress"],
                "version": VERSION,
            })
            return
        if path == "/api/progress":
            import time as _time
            fresh = (_time.time() - PROGRESS["ts"]) < 3.0
            active = bool(STATE.get("busy")) or (fresh and PROGRESS["percent"] not in (None, 100))
            self._json({"ok": True, "progress": STATE["progress"], "busy": STATE["busy"],
                        "percent": PROGRESS["percent"], "active": active})
            return
        if path == "/api/manifest":
            source = (query.get("source") or ["bmclapi"])[0]
            try:
                items = downloader.manifest(source)
                items.sort(key=lambda v: v.get("release") or "")
                self._json({"ok": True, "versions": items, "source": source})
            except Exception as error:
                if source != "official":
                    try:
                        items = downloader.manifest("official")
                        items.sort(key=lambda v: v.get("release") or "")
                        self._json({"ok": True, "versions": items, "source": "official",
                                    "note": "镜像连不上，已自动换官方源"})
                        return
                    except Exception:
                        pass
                self._json({"ok": False, "error": str(error)})
            return
        if path == "/api/community":
            kind = (query.get("type") or ["mod"])[0]
            mc_ver = (query.get("mc") or ["1.20.1"])[0]
            loader = (query.get("loader") or [""])[0]
            source = (query.get("source") or ["modrinth"])[0]
            text = (query.get("q") or [""])[0]
            deps = (query.get("deps") or ["1"])[0] == "1"
            limit = int((query.get("limit") or ["24"])[0])
            offset = int((query.get("offset") or ["0"])[0])
            key = (cfg.get("curseforge_key") or "").strip()
            try:
                if source == "curseforge":
                    hits = downloader.curseforge_search(key, text, kind, mc_ver, limit)
                    for item in hits:
                        item["source"] = "curseforge"
                elif text:
                    loaders = [loader] if kind in ("mod", "modpack") and loader not in ("", "vanilla") else []
                    hits = mods_api.search_project(text, kind, mc_ver, loaders, limit, offset)
                else:
                    loaders = [loader] if kind in ("mod", "modpack") and loader not in ("", "vanilla") else []
                    hits = mods_api.hot(kind, mc_ver, loaders, limit, offset)
                extra = []
                if deps and text and hits:
                    extra = [d for d in mods_api.dependencies(hits[0]["id"], 5) if d.get("title")]
                    for item in extra:
                        item["title"] = "【前置】" + item["title"]
                try:
                    translate.decorate(hits, limit=12, workers=4)
                except Exception:
                    pass
                self._json({"ok": True, "items": hits + extra, "mc": mc_ver, "loader": loader})
            except Exception as error:
                self._json({"ok": False, "error": str(error)})
            return
        if path == "/api/ask":
            text = (query.get("q") or [""])[0]
            ver = (query.get("version") or [""])[0] or (STATE.get("chosen") or "")
            mc_ver = mc_version_of(ver) if ver else "1.20.1"
            loader = loader_of(ver) if ver else "fabric"
            try:
                import re as _re
                # 想做一个「陪聊 mod」这种需求，直接给他脚手架
                if any(w in text for w in ("做一个", "做个", "写一个", "帮我做", "生成一个")) and                         any(w in text.lower() for w in ("mod", "模组", "插件")):
                    import re as _re2
                    target = "plugin" if any(w in text for w in ("插件", "服务端")) else "fabric"
                    name = "ChangzhengPlugin" if target == "plugin" else "ChangzhengMod"
                    try:
                        info = modgen.make(text, os.path.join(BASE, "my-mods"), name)
                        self._json({"ok": True, "kind": "mod", "items": [], "query": "",
                                    "explain": "做了一个「%s」骨架（%s），在 %s。改完 %s 就有能用的包。"
                                               % (info["desc"], "服务端插件" if target == "plugin" else "Fabric 模组",
                                                  info["folder"], info["build"])})
                        return
                    except Exception as error:
                        self._json({"ok": True, "kind": "mod", "items": [], "query": "",
                                    "explain": "生成失败：%s" % error})
                        return
                low_text = (text or "").lower()
                # ── 一句话干活：导出 / 导入 / 启动 / 开服 / 体检 ──
                ver_now = STATE.get("chosen") or (core.list_versions() or [""])[0]
                if any(w in text for w in ("导出", "打包")) and any(w in text for w in ("整合包", "包")):
                    try:
                        target, count = pack_tools.export_bundle(
                            core.MC_DIR, ver_now, mc_version_of(ver_now), loader_of(ver_now),
                            os.path.join(BASE, "exports"), "长征-" + ver_now, True, True, cfg)
                        self._json({"ok": True, "kind": "chat", "items": [], "query": "",
                                    "explain": "打好了：%s（%d 个 mod）。要不要我顺手打开文件夹？" % (target, count)})
                    except Exception as error:
                        self._json({"ok": True, "kind": "chat", "items": [], "query": "",
                                    "explain": "导出失败了：%s" % error})
                    return
                if "导入" in text and any(w in text for w in ("整合包", "包", "zip", "mrpack")):
                    path = STATE.get("last_upload") or ""
                    if not path or not os.path.isfile(path):
                        self._json({"ok": True, "kind": "chat", "items": [], "query": "",
                                    "explain": "你把整合包拖到聊天框里，我就能直接导进来。"})
                        return
                    try:
                        result = import_pack.run(path, ver_now, core.MC_DIR, progress)
                        self._json({"ok": True, "kind": "chat", "items": [], "query": "",
                                    "explain": "导入完成：%s 个文件进 %s 了。" % (result.get("mods", 0), ver_now)})
                    except Exception as error:
                        self._json({"ok": True, "kind": "chat", "items": [], "query": "",
                                    "explain": "导入失败：%s" % error})
                    return
                if any(w in text for w in ("启动游戏", "开始游戏", "帮我启动", "开游戏")):
                    try:
                        version = core.load_version(ver_now)
                        profile = dict(STATE.get("profile") or core.offline_profile("Player"))
                        profile["brand"] = cfg.get("custom_info") or "长征启动器"
                        isolate = (cfg.get("isolation") or "隔离所有版本") != "不隔离"
                        game_dir = os.path.join(core.MC_DIR, "versions", ver_now) if isolate else core.MC_DIR
                        os.makedirs(game_dir, exist_ok=True)
                        core.launch(version, profile, ram_mb=int(cfg.get("ram_mb") or 4096), game_dir=game_dir)
                        self._json({"ok": True, "kind": "chat", "items": [], "query": "",
                                    "explain": "开了，%s 正在启动。" % ver_now})
                    except Exception as error:
                        self._json({"ok": True, "kind": "chat", "items": [], "query": "",
                                    "explain": "启动失败：%s" % error})
                    return
                if any(w in text for w in ("体检", "检查环境", "看看配置")):
                    try:
                        health = tools.health()
                        bad = [i for i in health.get("items") or [] if not i.get("ok")]
                        msg = "环境没毛病。" if not bad else "有两处要处理：" + "；".join(
                            "%s %s" % (i["k"], i.get("tip") or "") for i in bad[:3])
                        self._json({"ok": True, "kind": "chat", "items": [], "query": "", "explain": msg})
                    except Exception as error:
                        self._json({"ok": True, "kind": "chat", "items": [], "query": "",
                                    "explain": "体检出错了：%s" % error})
                    return
                for keys, answer in FAQ:
                    if any(k in low_text for k in keys):
                        self._json({"ok": True, "kind": "chat", "items": [], "query": "",
                                    "explain": answer})
                        return
                if any(w in text for w in ("崩溃", "闪退", "打不开", "修复", "救救", "进不去")):
                    ver = STATE.get("chosen") or (core.list_versions() or [""])[0]
                    mc_ver = mc_version_of(ver)
                    loader = loader_of(ver)
                    mods_dir = os.path.join(core.MC_DIR, "versions", ver, "mods")
                    try:
                        res = tools.auto_fix(ver, mc_ver, loader, mods_dir, progress)
                    except Exception as error:
                        self._json({"ok": True, "kind": "chat", "items": [], "query": "",
                                    "explain": "检查的时候出错了：%s" % error})
                        return
                    lines = []
                    if res.get("hits"):
                        lines.append("看日志像是：" + "；".join(res["hits"][:2]))
                    else:
                        lines.append("日志里没看到典型崩溃原因。")
                    if res.get("actions"):
                        lines.append("我顺手做了：" + "；".join(a["do"] for a in res["actions"]))
                    else:
                        lines.append("没有能自动修的地方，需要你确认下。")
                    self._json({"ok": True, "kind": "chat", "items": [], "query": "",
                                "explain": " ".join(lines)})
                    return
                key = (cfg.get("deepseek_key") or "").strip()
                if key:
                    import urllib.request as _ur
                    history = STATE_CONTEXT.setdefault("history", [])
                    history.append({"role": "user", "content": text})
                    payload = {
                        "model": "deepseek-chat",
                        "messages": [{"role": "system", "content":
                                      "你是长征姬，用户管你叫爸爸，说话短、有人味、不客服腔；"
                                      "用户在启动器里问你要资源时，用一句话回答，必要时给出搜索关键词。"}] + history[-6:],
                        "temperature": 0.8,
                    }
                    req = _ur.Request("https://api.deepseek.com/chat/completions",
                                      data=json.dumps(payload).encode("utf-8"),
                                      headers={"Content-Type": "application/json",
                                               "Authorization": "Bearer " + key})
                    with _ur.urlopen(req, timeout=18) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                    reply = data["choices"][0]["message"]["content"]
                    history.append({"role": "assistant", "content": reply})
                    self._json({"ok": True, "kind": "chat", "items": [], "query": "",
                                "explain": reply})
                    return
                kind = assistant.classify(text)
                query = assistant.intent_query(text)
                low = text or ""
                is_follow = any(w in low for w in FOLLOW_UP) and len(low) <= 12
                ctx = STATE_CONTEXT
                if is_follow and ctx["query"] and (not query or query == ctx["query"]):
                    # 接着上一次的口味继续翻页
                    query = ctx["query"]
                    kind = ctx["kind"] or kind
                    ctx["offset"] = ctx.get("offset", 0) + 10
                else:
                    ctx.update({"query": query, "kind": kind, "mc": mc_ver, "loader": loader,
                                "offset": 0, "shown": set()})
                if kind == "modpack":
                    hits = mods_api.search_project(query or text, "modpack", mc_ver, [], 8)
                else:
                    loaders = [loader] if kind == "mod" and loader not in ("", "vanilla", None) else []
                    hits = mods_api.search_project(query or text, kind if kind != "map" else "mod",
                                                   mc_ver, loaders, 10 + ctx.get("offset", 0))
                    if ctx.get("offset"):
                        hits = hits[ctx["offset"]:] or []
                if ctx.get("offset"):
                    hits = mods_api.search_project(ctx["query"], ctx["kind"] or "mod",
                                                   ctx["mc"], [], 40)
                    hits = [h for h in hits if h["id"] not in ctx["shown"]][:10]
                try:
                    translate.decorate(hits, limit=8, workers=4)
                except Exception:
                    pass
                for item in hits:
                    item["reason"] = assistant.reason_for(item)
                    ctx["shown"].add(item["id"])
                if ctx.get("offset"):
                    explain = "接着「%s」再给你翻一批。" % (ctx["query"] or text)
                else:
                    explain = ("你说「%s」，我按 %s 去搜的。" % (text, query)) if query else ""
                note = "" if hits else "这条路翻到底了，换个方向我再找。"
                self._json({"ok": True, "kind": kind, "items": hits, "note": note,
                            "query": query, "explain": explain})
            except Exception as error:
                self._json({"ok": False, "error": str(error)})
            return
        if path == "/api/server/state":
            ver = (query.get("version") or [""])[0] or (STATE.get("chosen") or "")
            mc_ver = mc_version_of(ver) if ver else "1.20.1"
            folder = os.path.join(core.MC_DIR, "server-" + mc_ver)
            self._json({"ok": True, "folder": folder, "mc": mc_ver,
                        "hasJar": os.path.isfile(os.path.join(folder, "server.jar")),
                        "online": bool(STATE.get("server_proc") and STATE["server_proc"].poll() is None),
                        "lan": lan_ip()})
            return
        if path == "/api/saves":
            ver = (query.get("version") or [""])[0] or (STATE.get("chosen") or "")
            saves_dir = os.path.join(core.MC_DIR, "versions", ver, "saves")
            if not os.path.isdir(saves_dir):
                saves_dir = os.path.join(core.MC_DIR, "saves")
            items = []
            if os.path.isdir(saves_dir):
                for name in sorted(os.listdir(saves_dir)):
                    full = os.path.join(saves_dir, name)
                    if not os.path.isdir(full):
                        continue
                    size = 0
                    for base, _d, files in os.walk(full):
                        for f in files:
                            try:
                                size += os.path.getsize(os.path.join(base, f))
                            except Exception:
                                pass
                    items.append({"name": name, "size": size,
                                  "mtime": int(os.path.getmtime(full)),
                                  "has_icon": os.path.isfile(os.path.join(full, "icon.png"))})
            self._json({"ok": True, "dir": saves_dir, "items": items})
            return
        if path == "/api/saves/icon":
            ver = (query.get("version") or [""])[0] or (STATE.get("chosen") or "")
            name = os.path.basename((query.get("name") or [""])[0])
            base = os.path.join(core.MC_DIR, "versions", ver, "saves")
            if not os.path.isdir(base):
                base = os.path.join(core.MC_DIR, "saves")
            target = os.path.join(base, name, "icon.png")
            if os.path.isfile(target):
                with open(target, "rb") as handle:
                    data = handle.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404)
            return
        if path == "/api/screenshots":
            shot_dir = os.path.join(core.MC_DIR, "screenshots")
            items = []
            dirs = [("root", shot_dir)]
            versions_root = os.path.join(core.MC_DIR, "versions")
            if os.path.isdir(versions_root):
                for ver in os.listdir(versions_root):
                    cand = os.path.join(versions_root, ver, "screenshots")
                    if os.path.isdir(cand):
                        dirs.append((ver, cand))
            for tag, folder in dirs:
                try:
                    for name in os.listdir(folder):
                        if name.lower().endswith((".png", ".jpg", ".jpeg")):
                            full = os.path.join(folder, name)
                            items.append({"name": name, "v": tag, "size": os.path.getsize(full),
                                          "mtime": int(os.path.getmtime(full))})
                except Exception:
                    pass
            items.sort(key=lambda i: i["mtime"], reverse=True)
            self._json({"ok": True, "dir": shot_dir, "items": items[:120]})
            return
        if path == "/api/shot":
            tag = (query.get("v") or ["root"])[0]
            if tag and tag != "root":
                shot_dir = os.path.join(core.MC_DIR, "versions", os.path.basename(tag), "screenshots")
            else:
                shot_dir = os.path.join(core.MC_DIR, "screenshots")
            name = os.path.basename((query.get("name") or [""])[0])
            target = os.path.join(shot_dir, name)
            if os.path.isfile(target):
                ext = os.path.splitext(name)[1].lower()
                ctype = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
                with open(target, "rb") as handle:
                    data = handle.read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404)
            return
        if path == "/api/mods":
            ver = (query.get("version") or [""])[0] or (STATE.get("chosen") or "")
            mods_dir = os.path.join(core.MC_DIR, "versions", ver, "mods")
            items = []
            if os.path.isdir(mods_dir):
                for name in sorted(os.listdir(mods_dir)):
                    if name.endswith(".jar") or name.endswith(".jar.disabled"):
                        full = os.path.join(mods_dir, name)
                        items.append({"file": name, "enabled": name.endswith(".jar"),
                                      "size": os.path.getsize(full),
                                      "mtime": int(os.path.getmtime(full))})
            self._json({"ok": True, "dir": mods_dir, "items": items})
            return
        if path == "/api/health":
            try:
                self._json(tools.health())
            except Exception as error:
                self._json({"ok": False, "error": str(error)})
            return
        if path == "/api/modscan":
            ver = (query.get("version") or [""])[0] or (STATE.get("chosen") or "")
            try:
                self._json(tools.mod_scan(ver))
            except Exception as error:
                self._json({"ok": False, "error": str(error)})
            return
        if path == "/api/crash":
            ver = (query.get("version") or [""])[0] or (STATE.get("chosen") or "")
            try:
                self._json(tools.crash_report(ver))
            except Exception as error:
                self._json({"ok": False, "error": str(error)})
            return
        if path == "/api/autofix":
            ver = (query.get("version") or [""])[0] or (STATE.get("chosen") or "")
            mc_ver = mc_version_of(ver)
            loader = loader_of(ver)
            mods_dir = os.path.join(core.MC_DIR, "versions", ver, "mods")
            try:
                result = tools.auto_fix(ver, mc_ver, loader, mods_dir,
                                        lambda msg: progress(msg))
                self._json(result)
            except Exception as error:
                self._json({"ok": False, "error": str(error)})
            return
        if path == "/api/check_update":
            try:
                self._json(tools.check_update(VERSION, cfg.get("update_url") or ""))
            except Exception as error:
                self._json({"ok": False, "error": str(error)})
            return
        if path == "/api/login/start":
            try:
                data = core.device_code_start(cfg.get("client_id"))
                self._json({"ok": True, "url": data.get("verification_uri"), "code": data.get("user_code"),
                            "device": data.get("device_code"), "interval": data.get("interval", 5)})
            except Exception as error:
                self._json({"ok": False, "error": str(error)})
            return
        if path == "/api/login/poll":
            device = (query.get("device") or [""])[0]
            try:
                token = core.device_code_poll(cfg.get("client_id"), device, 1, 15)
                profile = core.ms_to_minecraft(token["access_token"])
                cfg["profile"] = profile
                cfg["refresh_token"] = token.get("refresh_token", "")
                save_config(cfg)
                self._json({"ok": True, "status": "ok", "name": profile["name"]})
            except Exception as error:
                self._json({"ok": False, "status": "waiting", "error": str(error)})
            return
        self._json({"ok": False, "error": "unknown"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw or b"{}")
        except Exception:
            body = {}
            self._raw = raw
        cfg = load_config()
        if cfg.get("mc_dir"):
            core.MC_DIR = cfg["mc_dir"]

        if parsed.path == "/api/upload":
            name = urllib.parse.unquote(self.headers.get("X-Filename") or "upload.zip")
            safe = os.path.basename(name)
            folder = os.path.join(BASE, "uploads")
            os.makedirs(folder, exist_ok=True)
            target = os.path.join(folder, safe)
            try:
                with open(target, "wb") as handle:
                    handle.write(getattr(self, "_raw", b"") or b"")
                STATE["last_upload"] = target
                self._json({"ok": True, "path": target, "name": safe,
                            "size": os.path.getsize(target)})
            except Exception as error:
                self._json({"ok": False, "error": str(error)})
            return
        if parsed.path == "/api/import":
            path = body.get("path") or STATE.get("last_upload") or ""
            ver = body.get("version") or STATE.get("chosen")
            if not path or not os.path.isfile(path):
                self._json({"ok": False, "error": "找不到要导入的文件"})
                return

            def work():
                STATE["busy"] = True
                try:
                    result = import_pack.run(path, ver, core.MC_DIR, progress)
                    progress("整合包导入完成：%s 个文件" % result.get("mods", 0))
                    STATE["last_import"] = result
                except Exception as error:
                    progress("导入失败：%s" % error)
                    STATE["last_import"] = {"ok": False, "error": str(error)}
                STATE["busy"] = False

            threading.Thread(target=work, daemon=True).start()
            self._json({"ok": True, "started": True, "path": path})
            return
        if parsed.path == "/api/saves/delete":
            ver = body.get("version") or STATE.get("chosen")
            name = os.path.basename(body.get("name") or "")
            base = os.path.join(core.MC_DIR, "versions", ver, "saves")
            if not os.path.isdir(base):
                base = os.path.join(core.MC_DIR, "saves")
            trash = os.path.join(core.MC_DIR, "saves-trash")
            os.makedirs(trash, exist_ok=True)
            try:
                os.replace(os.path.join(base, name), os.path.join(trash, name))
                self._json({"ok": True, "trash": trash})
            except Exception as error:
                self._json({"ok": False, "error": str(error)})
            return
        if parsed.path == "/api/mods/batch":
            ver = body.get("version") or STATE.get("chosen")
            files = body.get("files") or []
            action = body.get("action") or "disable"
            mods_dir = os.path.join(core.MC_DIR, "versions", ver, "mods")
            trash = os.path.join(core.MC_DIR, "mods-trash")
            done, failed = [], []
            for name in files:
                src = os.path.join(mods_dir, name)
                try:
                    if action == "delete":
                        os.makedirs(trash, exist_ok=True)
                        os.replace(src, os.path.join(trash, name))
                    elif action == "disable":
                        if name.endswith(".jar"):
                            os.replace(src, src + ".disabled")
                    elif action == "enable":
                        if name.endswith(".disabled"):
                            os.replace(src, src[:-9])
                    done.append(name)
                except Exception as error:
                    failed.append({"file": name, "error": str(error)})
            self._json({"ok": True, "done": len(done), "failed": failed})
            return
        if parsed.path == "/api/mods/toggle":
            ver = body.get("version") or STATE.get("chosen")
            mods_dir = os.path.join(core.MC_DIR, "versions", ver, "mods")
            name = body.get("file") or ""
            src = os.path.join(mods_dir, name)
            try:
                if name.endswith(".disabled"):
                    os.replace(src, src[:-9])
                else:
                    os.replace(src, src + ".disabled")
                self._json({"ok": True})
            except Exception as error:
                self._json({"ok": False, "error": str(error)})
            return
        if parsed.path == "/api/mods/delete":
            ver = body.get("version") or STATE.get("chosen")
            mods_dir = os.path.join(core.MC_DIR, "versions", ver, "mods")
            trash = os.path.join(core.MC_DIR, "mods-trash")
            os.makedirs(trash, exist_ok=True)
            name = body.get("file") or ""
            try:
                os.replace(os.path.join(mods_dir, name), os.path.join(trash, name))
                self._json({"ok": True, "trash": trash})
            except Exception as error:
                self._json({"ok": False, "error": str(error)})
            return
        if parsed.path == "/api/version/delete":
            ver = body.get("version") or ""
            src = os.path.join(core.MC_DIR, "versions", ver)
            if not ver or not os.path.isdir(src):
                self._json({"ok": False, "error": "找不到这个版本"})
                return
            trash = os.path.join(core.MC_DIR, "versions-trash")
            os.makedirs(trash, exist_ok=True)
            try:
                import time as _t2
                target = os.path.join(trash, ver + "-" + str(int(_t2.time())))
                os.replace(src, target)
                self._json({"ok": True, "moved": target})
            except Exception as error:
                self._json({"ok": False, "error": str(error)})
            return
        if parsed.path == "/api/clientlog":
            try:
                with open(os.path.join(BASE, "client-errors.log"), "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(body, ensure_ascii=False) + "\n")
            except Exception:
                pass
            self._json({"ok": True})
            return
        if parsed.path == "/api/choose":
            STATE["chosen"] = body.get("id")
            self._json({"ok": True, "chosen": STATE["chosen"]})
            return
        if parsed.path == "/api/config":
            for key in ("theme", "ram_mb", "curseforge_key", "client_id", "deepseek_key", "isolation", "win_size",
                        "window_title", "custom_info", "visible", "priority", "jvm_args", "java_path",
                        "download_source", "threads", "speed_limit", "auto_memory", "skin",
                        "update_hint", "test_hint", "auto_chinese", "launcher_update", "announce",
                        "cache_dir", "anonymous", "mod_filename", "update_url"):
                if key in body:
                    cfg[key] = body[key]
            save_config(cfg)
            self._json({"ok": True, "config": cfg})
            return
        if parsed.path == "/api/offline":
            name = body.get("name") or "Player"
            cfg["profile"] = core.offline_profile(name)
            save_config(cfg)
            self._json({"ok": True})
            return
        if parsed.path == "/api/install/vanilla":
            vid = body.get("id")
            source = body.get("source", "bmclapi")

            def work():
                STATE["busy"] = True
                progress("开始安装 %s（0/100）" % vid)
                try:
                    downloader.install_vanilla(vid, core.MC_DIR, source, progress)
                    progress("%s 装好了（100/100）" % vid)
                except Exception as error:
                    progress("安装失败：%s" % error)
                STATE["busy"] = False

            threading.Thread(target=work, daemon=True).start()
            self._json({"ok": True})
            return
        if parsed.path == "/api/install/mod":
            ver = body.get("version")
            mc_ver = mc_version_of(ver)
            loader = loader_of(ver)
            kind = body.get("type", "mod")
            item = body.get("item") or {}

            def work():
                STATE["busy"] = True
                try:
                    if item.get("source") == "curseforge":
                        info = downloader.curseforge_file_url((cfg.get("curseforge_key") or "").strip(),
                                                              item["id"], mc_ver, loader)
                        dest = assistant.install_dir(os.path.join(core.MC_DIR, "versions", ver), kind)
                        path = downloader.fetch(info["url"], os.path.join(dest, info["name"]))
                        progress("装好了：%s" % os.path.basename(path))
                    else:
                        path, error = assistant.install(item, kind, loader, mc_ver,
                                                        os.path.join(core.MC_DIR, "versions", ver))
                        progress("装好了：%s" % os.path.basename(path) if not error else "装不上：%s" % error)
                except Exception as error:
                    progress("装不上：%s" % error)
                STATE["busy"] = False

            threading.Thread(target=work, daemon=True).start()
            self._json({"ok": True})
            return
        if parsed.path == "/api/server/prepare":
            ver = body.get("version") or STATE.get("chosen")
            mc_ver = mc_version_of(ver)
            folder = os.path.join(core.MC_DIR, "server-" + mc_ver)
            os.makedirs(folder, exist_ok=True)
            props = ("online-mode=true\nenforce-whitelist=false\nmax-players=10\n"
                     "motd=Changzheng Server\nlevel-name=world\n")
            with open(os.path.join(folder, "server.properties"), "w", encoding="utf-8") as handle:
                handle.write(props)
            with open(os.path.join(folder, "eula.txt"), "w", encoding="utf-8") as handle:
                handle.write("eula=true\n")
            progress("开服配置写好了：%s" % folder)
            self._json({"ok": True, "folder": folder, "lan": lan_ip()})
            return
        if parsed.path == "/api/server/download":
            ver = body.get("version") or STATE.get("chosen")
            mc_ver = mc_version_of(ver)
            folder = os.path.join(core.MC_DIR, "server-" + mc_ver)

            def dl():
                STATE["busy"] = True
                try:
                    path = core.download_server(mc_ver, folder)
                    progress("服务端下好了：%s" % path)
                except Exception as error:
                    progress("服务端下载失败：%s" % error)
                STATE["busy"] = False

            threading.Thread(target=dl, daemon=True).start()
            self._json({"ok": True})
            return
        if parsed.path == "/api/server/start":
            ver = body.get("version") or STATE.get("chosen")
            mc_ver = mc_version_of(ver)
            folder = os.path.join(core.MC_DIR, "server-" + mc_ver)
            jar = os.path.join(folder, "server.jar")
            if not os.path.isfile(jar):
                self._json({"ok": False, "error": "还没下服务端"})
                return
            try:
                import subprocess
                creation = 0x08000000
                proc = subprocess.Popen([core.find_java(), "-Xmx2G", "-jar", "server.jar", "nogui"],
                                        cwd=folder, creationflags=creation, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
                STATE["server_proc"] = proc
                progress("服务端已启动（%s）" % mc_ver)
                self._json({"ok": True})
            except Exception as error:
                self._json({"ok": False, "error": str(error)})
            return
        if parsed.path == "/api/export":
            import shutil as _sh
            import zipfile as _zip

            ver = body.get("version") or STATE.get("chosen") or (core.list_versions() or [None])[0]
            if not ver:
                self._json({"ok": False, "error": "没有可导出的版本"})
                return
            include_game = bool(body.get("include_game", True))
            include_launcher = bool(body.get("include_launcher", True))
            name = (body.get("name") or "长征整合包").strip()
            ver_dir = os.path.join(core.MC_DIR, "versions", ver)
            if not os.path.isdir(ver_dir):
                self._json({"ok": False, "error": "找不到版本目录"})
                return
            out_dir = os.path.join(BASE, "exports")
            os.makedirs(out_dir, exist_ok=True)
            safe = "".join(ch for ch in name if ch not in '\\/:*?"<>|') or "长征整合包"
            target = os.path.join(out_dir, safe + ".zip")

            def pack():
                STATE["busy"] = True
                try:
                    count = 0
                    with _zip.ZipFile(target, "w", _zip.ZIP_DEFLATED) as zf:
                        mods = os.path.join(ver_dir, "mods")
                        if os.path.isdir(mods):
                            for f in os.listdir(mods):
                                if f.endswith(".jar"):
                                    zf.write(os.path.join(mods, f), "mods/" + f)
                                    count += 1
                        if include_game:
                            for item in ("options.txt", "optionsof.txt", "servers.dat", "config",
                                         "shaderpacks", "resourcepacks", "defaultconfigs", "kubejs"):
                                src = os.path.join(ver_dir, item)
                                if os.path.isfile(src):
                                    zf.write(src, item)
                                elif os.path.isdir(src):
                                    for base2, _dirs, files in os.walk(src):
                                        for f in files:
                                            full = os.path.join(base2, f)
                                            zf.write(full, os.path.relpath(full, ver_dir))
                        manifest = {
                            "name": name,
                            "version": ver,
                            "mc": mc_version_of(ver),
                            "loader": loader_of(ver),
                            "mods": count,
                            "include_game": include_game,
                            "include_launcher": include_launcher,
                            "made_by": "长征启动器",
                        }
                        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                        if include_launcher:
                            keep = {k: cfg.get(k) for k in ("ram_mb", "jvm_args", "theme", "isolation",
                                                            "win_size", "window_title", "priority")}
                            zf.writestr("launcher.json", json.dumps(keep, ensure_ascii=False, indent=2))
                    progress("整合包导出好了：%s（%d 个模组）" % (target, count))
                except Exception as error:
                    progress("导出失败：%s" % error)
                STATE["busy"] = False

            threading.Thread(target=pack, daemon=True).start()
            self._json({"ok": True, "path": target})
            return
        if parsed.path == "/api/download_update":
            url = body.get("url") or ""
            if not url:
                self._json({"ok": False, "error": "没有下载地址"})
                return

            def grab():
                STATE["busy"] = True
                try:
                    import urllib.request as _ur
                    folder = os.path.join(BASE, "updates")
                    os.makedirs(folder, exist_ok=True)
                    name = os.path.basename(url.split("?")[0]) or "update.zip"
                    target = os.path.join(folder, name)
                    req2 = _ur.Request(url, headers={"User-Agent": "ChangzhengLauncher"})
                    with _ur.urlopen(req2, timeout=120) as resp, open(target, "wb") as handle:
                        total = int(resp.headers.get("Content-Length") or 0)
                        done = 0
                        while True:
                            chunk = resp.read(1 << 20)
                            if not chunk:
                                break
                            handle.write(chunk)
                            done += len(chunk)
                            if total:
                                progress("更新包 %d%%" % int(done * 100 / total))
                    progress("更新包下好了（100/100）：%s" % target)
                    STATE["update_file"] = target
                except Exception as error:
                    progress("更新包下载失败：%s" % error)
                STATE["busy"] = False

            threading.Thread(target=grab, daemon=True).start()
            self._json({"ok": True})
            return
        if parsed.path == "/api/share":
            import zipfile as _zip

            target = os.path.join(BASE, "分享-长征启动器.zip")

            def pack_share():
                STATE["busy"] = True
                try:
                    with _zip.ZipFile(target, "w", _zip.ZIP_DEFLATED) as zf:
                        for item in ("长征启动器.exe", "icon.ico"):
                            full = os.path.join(BASE, item)
                            if os.path.isfile(full):
                                zf.write(full, item)
                        web_dir = os.path.join(BASE, "web")
                        if os.path.isdir(web_dir):
                            for base2, _dirs, files in os.walk(web_dir):
                                for f in files:
                                    full = os.path.join(base2, f)
                                    zf.write(full, os.path.relpath(full, BASE))
                    progress("分享包做好了：%s" % target)
                except Exception as error:
                    progress("分享包失败：%s" % error)
                STATE["busy"] = False

            threading.Thread(target=pack_share, daemon=True).start()
            self._json({"ok": True, "path": target})
            return
        if parsed.path == "/api/reveal":
            target = body.get("path") or BASE
            try:
                import subprocess as _sp
                _sp.Popen(["explorer", "/select,", os.path.normpath(target)])
                self._json({"ok": True})
            except Exception as error:
                self._json({"ok": False, "error": str(error)})
            return
        if parsed.path == "/api/launch":
            ver = body.get("version") or STATE.get("chosen")
            profile = cfg.get("profile")
            if not profile:
                self._json({"ok": False, "error": "先登录"})
                return
            try:
                version = core.load_version(ver)
                profile = dict(profile)
                profile["brand"] = cfg.get("custom_info") or "ChangzhengLauncher"
                # 版本隔离：mod / 存档 / 设置都在版本文件夹里，和 mod 管理一致
                isolate = (cfg.get("isolation") or "隔离所有版本") != "不隔离"
                game_dir = os.path.join(core.MC_DIR, "versions", ver) if isolate else core.MC_DIR
                os.makedirs(game_dir, exist_ok=True)
                if cfg.get("auto_chinese", True):
                    options = os.path.join(game_dir, "options.txt")
                    try:
                        lines = []
                        if os.path.isfile(options):
                            with open(options, encoding="utf-8", errors="replace") as handle:
                                lines = [ln for ln in handle.read().splitlines() if not ln.startswith("lang:")]
                        lines.append("lang:zh_cn")
                        with open(options, "w", encoding="utf-8") as handle:
                            handle.write("\n".join(lines) + "\n")
                    except Exception:
                        pass
                proc, _ = core.launch(version, profile, ram_mb=int(cfg.get("ram_mb") or 4096),
                                      game_dir=game_dir)
                progress("已启动 %s（pid %s）" % (ver, proc.pid))
                self._json({"ok": True})
            except Exception as error:
                self._json({"ok": False, "error": str(error)})
            return
        self._json({"ok": False, "error": "unknown"}, 404)


def main(open_browser_tab=True):
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = "http://127.0.0.1:%d/" % PORT
    print("长征启动器服务：%s" % url, flush=True)

    def open_browser():
        import time
        import webbrowser
        time.sleep(0.8)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    if open_browser_tab:
        threading.Thread(target=open_browser, daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
