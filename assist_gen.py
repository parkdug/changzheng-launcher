"""assist_gen — 小助手「定制生成」：把需求交给 DeepSeek（用用户自己的 key），
让它输出结构化文件，然后自动装到当前版本的对应目录。

支持产出：
- datapack（数据包）：纯 JSON/mcfunction，装完立刻能用
- kubejs（KubeJS 脚本）：只要版本里装了 KubeJS
- plugin（Bukkit/Paper 插件）：生成 Java 源码，用本机 JDK 编译成 jar
- mod（Fabric/Forge 工程）：生成完整 Gradle 工程与源码，交给用户构建
"""

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request

API = "https://api.deepseek.com/chat/completions"

SYSTEM = (
    "你是 Minecraft 模组/插件/数据包开发者。按用户需求产出可直接使用的文件。"
    "只输出一个 JSON 对象，不要解释，不要 markdown 代码块。格式："
    '{"name":"英文小写短名","summary":"一句中文说明","kind":"datapack|kubejs|plugin|mod",'
    '"files":[{"path":"相对路径","content":"文件全文"}]}'
    " 规则：数据包必须有 pack.mcmeta（pack_format 按版本给）和 data/<命名空间>/...；"
    "插件必须是单个 Java 类继承 JavaPlugin，带 plugin.yml；"
    "Fabric 模组给完整工程（build.gradle、settings.gradle、gradle.properties、src/main/java/...、fabric.mod.json）。"
    "带特效/粒子/视觉效果的模组：必须拆成 main 与 client 两个入口（fabric.mod.json 里 client 指向 ClientModInitializer），"
    "粒子要在客户端注册 ParticleType + ParticleFactoryRegistry，贴图路径写 assets/<modid>/textures/particle/<名字>.png，"
    "并在 files 里列出这些 png（content 留空字符串，启动器会自动生成径向发光贴图）。"
    "带模型的道具模组：模型放在 assets/<modid>/models/item/<名字>.json，物品注册用 FabricItemSettings，"
    "并在 files 里加一条 {\"path\":\"assets/<modid>/models/item/<名字>.json\",\"content\":\"__USER_MODEL__\"}，"
    "启动器会把它替换成用户上传的模型或内置模型。"
    "模型也可以不用占位符：让启动器按部件描述生成，content 写 __MODEL_SPEC__{...}，"
    "里面给 parts（每项 from/to/texture）即可；纯色贴图 content 写 __COLOR__#RRGGBB。"
    "盔甲模组：用 armor layer 贴图（64x32），两张（层1、层2）可直接用 __COLOR__ 生成，"
    "代码里注册 ArmorMaterial + ArmorItem，并在 assets/<modid>/models/item/<名字>.json 引用。"
    "武器/道具通用：模型放 models/item，物品用 FabricItemSettings 注册，附上属性（攻击力/耐久）。"
)


def _post(key, payload, timeout=180):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + (key or ""),
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def design(key, requirement, kind, mc_version, loader, progress=None, fix="", previous=None):
    """让模型给出文件清单。"""
    say = progress or (lambda msg: None)
    say("正在让 DeepSeek 设计…")
    user = (
        "需求：%s\n游戏版本：%s\n加载器：%s\n期望类型：%s\n"
        "请严格按系统要求输出 JSON。" % (requirement, mc_version, loader, kind)
    )
    data = _post(key, {
        "model": "deepseek-chat",
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        "temperature": 0.4,
        "max_tokens": 4000,
        "response_format": {"type": "json_object"},
    })
    text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    project = json.loads(text)
    files = project.get("files") or []
    if not files:
        raise RuntimeError("模型没给出任何文件")
    project["files"] = [f for f in files if f.get("path") and f.get("content") is not None]
    return project


def build_item_model(parts, mod_id="custom", texture_size=32):
    """把 {"parts":[{"name","from","to","tex"}]} 拼成 Minecraft 物品模型。"""
    elements = []
    textures = {}
    for index, part in enumerate(parts or []):
        key = str(index % 8)
        textures[key] = part.get("texture") or (mod_id + ":item/part" + key)
        start = part.get("from") or [0, 0, 0]
        end = part.get("to") or [1, 1, 1]
        elements.append({
            "from": [float(v) for v in start],
            "to": [float(v) for v in end],
            "faces": {face: {"texture": "#" + key} for face in ("north", "south", "east", "west", "up", "down")},
        })
    if not elements:
        return make_sword_model(mod_id)
    return {"credit": "长征启动器生成", "texture_size": [texture_size, texture_size],
            "textures": textures, "elements": elements}


def make_solid_png(path, color=(200, 200, 210, 255), size=16):
    """纯色贴图（给模型部件/盔甲层用）。"""
    import struct
    import zlib
    row = bytearray([0])
    for _ in range(size):
        row += bytes(color)
    raw = bytes(row) * size

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = (bytes([137, 80, 78, 71, 13, 10, 26, 10]) + chunk(b"IHDR", header) +
           chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(png)


def make_sword_model(mod_id="xianxia_sword"):
    """内置生成一把像素风长剑的物品模型（Blockbench 结构，直接能进资源包）。"""
    return {
        "credit": "长征启动器内置生成",
        "texture_size": [32, 32],
        "textures": {"0": mod_id + ":item/sword_blade", "1": mod_id + ":item/sword_hilt"},
        "elements": [
            {"from": [15.2, 3.0, 7.0], "to": [16.8, 25.0, 9.0],
             "faces": {"north": {"uv": [6, 0, 8, 22], "texture": "#0"},
                       "south": {"uv": [6, 0, 8, 22], "texture": "#0"}}},
            {"from": [12.0, 1.6, 6.4], "to": [20.0, 3.2, 9.6],
             "faces": {"north": {"uv": [0, 22, 8, 24], "texture": "#1"},
                       "south": {"uv": [0, 22, 8, 24], "texture": "#1"}}},
            {"from": [15.2, -3.0, 7.2], "to": [16.8, 1.6, 8.8],
             "faces": {"north": {"uv": [12, 0, 14, 8], "texture": "#1"},
                       "south": {"uv": [12, 0, 14, 8], "texture": "#1"}}},
        ],
        "display": {"thirdperson_righthand": {"rotation": [0, -90, 55], "translation": [0, 4.0, 0.5]},
                    "firstperson_righthand": {"rotation": [0, -90, 25], "translation": [1.13, 3.2, 1.13]}},
    }


def _make_glow_png(path, size=32):
    """生成一张径向渐变的发光贴图，省得模型给不出二进制。"""
    import struct
    import zlib

    rows = []
    center = (size - 1) / 2.0
    radius = size / 2.0
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            dx = x - center
            dy = y - center
            dist = (dx * dx + dy * dy) ** 0.5
            alpha = max(0.0, 1.0 - dist / radius)
            alpha = int((alpha ** 1.6) * 255)
            row += bytes((255, 255, 255, alpha))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = (bytes([137, 80, 78, 71, 13, 10, 26, 10]) + chunk(b"IHDR", header) +
           chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(png)


def load_model(base, model_id):
    """读回用户上传/内置生成的模型 JSON。"""
    path = os.path.join(base, "assist", "models", model_id + ".json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def save_model(base, model_id, text):
    os.makedirs(os.path.join(base, "assist", "models"), exist_ok=True)
    path = os.path.join(base, "assist", "models", model_id + ".json")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _safe_join(base, rel):
    target = os.path.abspath(os.path.join(base, rel.replace("\\", "/")))
    if not (target == os.path.abspath(base) or target.startswith(os.path.abspath(base) + os.sep)):
        raise RuntimeError("路径越界：" + rel)
    return target


def write_project(base, name, files, builtin_model=None):
    root = os.path.join(base, "assist", name)
    if os.path.isdir(root):
        shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root, exist_ok=True)
    for item in files:
        target = _safe_join(root, item["path"])
        os.makedirs(os.path.dirname(target), exist_ok=True)
        content = item.get("content")
        if isinstance(content, str) and content.startswith("__MODEL_SPEC__"):
            spec_text = content[len("__MODEL_SPEC__"):].strip() or "{}"
            try:
                spec = json.loads(spec_text)
            except Exception:
                spec = {}
            model = build_item_model(spec.get("parts") or [], mod_id=name)
            with open(target, "w", encoding="utf-8") as handle:
                json.dump(model, handle, ensure_ascii=False, indent=2)
            continue
        if isinstance(content, str) and content.startswith("__COLOR__"):
            hex_value = content[len("__COLOR__"):].strip().lstrip("#") or "CCCCCC"
            try:
                rgb = tuple(int(hex_value[i:i + 2], 16) for i in (0, 2, 4))
            except Exception:
                rgb = (200, 200, 210)
            make_solid_png(target, rgb + (255,), size=16)
            continue
        if content == "__USER_MODEL__":
            model = builtin_model or make_sword_model()
            with open(target, "w", encoding="utf-8") as handle:
                json.dump(model, handle, ensure_ascii=False, indent=2)
            continue
        if target.lower().endswith(".png"):
            _make_glow_png(target)
            continue
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(item["content"])
    return root


def _newest_world(version_dir):
    saves = os.path.join(version_dir, "saves")
    if not os.path.isdir(saves):
        return ""
    worlds = [os.path.join(saves, d) for d in os.listdir(saves) if os.path.isdir(os.path.join(saves, d))]
    if not worlds:
        return ""
    return max(worlds, key=lambda p: os.path.getmtime(p))


def install_datapack(project_root, name, version_dir):
    saves = os.path.join(version_dir, "saves")
    worlds = []
    if os.path.isdir(saves):
        worlds = [d for d in os.listdir(saves) if os.path.isdir(os.path.join(saves, d))]
    if not worlds:
        target = os.path.join(version_dir, "datapacks", name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copytree(project_root, target, dirs_exist_ok=True)
        return target
    last = ""
    for world in worlds:
        target = os.path.join(saves, world, "datapacks", name)
        if os.path.isdir(target):
            shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(project_root, target)
        last = target
    return last


def install_kubejs(project_root, name, version_dir):
    dest = os.path.join(version_dir, "kubejs", "server_scripts")
    os.makedirs(dest, exist_ok=True)
    count = 0
    for base, _dirs, files in os.walk(project_root):
        for f in files:
            if not f.endswith(".js"):
                continue
            shutil.copyfile(os.path.join(base, f), os.path.join(dest, f))
            count += 1
    return dest if count else ""


def _find_jdk():
    for root in (r"D:\JAVA", r"C:\Program Files\Java", r"C:\Program Files\Eclipse Adoptium"):
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            javac = os.path.join(root, name, "bin", "javac.exe")
            if os.path.isfile(javac):
                return os.path.join(root, name)
    return ""


def install_plugin(project_root, name, base):
    """用本机 JDK 把源码编译成 jar（服务端插件用）。"""
    jdk = _find_jdk()
    if not jdk:
        return "", "没找到 JDK（只装了 JRE），源码已保存到 %s" % project_root
    sources = []
    for root, _dirs, files in os.walk(project_root):
        for f in files:
            if f.endswith(".java"):
                sources.append(os.path.join(root, f))
    if not sources:
        return "", "没有 .java 源码"
    out = os.path.join(project_root, "build", "classes")
    os.makedirs(out, exist_ok=True)
    cp = os.path.join(base, "assist", "lib", "spigot-api.jar")
    if not os.path.isfile(cp):
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        try:
            urllib.request.urlretrieve(
                "https://repo1.maven.org/maven2/org/spigotmc/spigot-api/1.20.1-R0.1-SNAPSHOT/"
                "spigot-api-1.20.1-R0.1-SNAPSHOT.jar", cp)
        except Exception:
            cp = ""
    cmd = [os.path.join(jdk, "bin", "javac.exe"), "-encoding", "UTF-8", "-d", out]
    if cp and os.path.isfile(cp):
        cmd += ["-cp", cp]
    cmd += sources
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception as error:
        return "", "编译失败：%s" % error
    if proc.returncode != 0:
        return "", "编译失败：%s" % (proc.stderr or proc.stdout)[:200]
    jar_path = os.path.join(project_root, name + ".jar")
    try:
        subprocess.run([os.path.join(jdk, "bin", "jar.exe"), "cf", jar_path, "-C", out, "."],
                       capture_output=True, timeout=180)
    except Exception as error:
        return "", "打包失败：%s" % error
    return jar_path, ""


def make_mod(key, need, kind, mc_version, loader, base, version_dir, progress=None, attempts=3,
             builtin_model=None):
    """模组/插件走“生成→构建→拿错误回炉”的循环，最多 attempts 次。"""
    say = progress or (lambda msg: None)
    fix, error = "", ""
    project = None
    last_target = ""
    for attempt in range(1, attempts + 1):
        say("第 %d 次生成并构建…" % attempt)
        project = design(key, need, kind, mc_version, loader, say, fix=fix)
        target, note = install(project, base, "", version_dir, build=(kind == "mod"),
                               progress=say, builtin_model=builtin_model)
        last_target = target
        if kind != "mod":
            return project, target, note
        if "构建失败" not in (note or ""):
            return project, target, note
        error = note
        fix = note
    return project, last_target, error or "构建失败"


def install(project, base, version, version_dir, build=False, progress=None, builtin_model=None):
    """按类型装到对应位置，返回 (装到哪, 提示)。"""
    kind = (project.get("kind") or "datapack").lower()
    name = re.sub(r"[^a-z0-9_-]+", "_", (project.get("name") or "assist").lower()) or "assist"
    root = write_project(base, name, project["files"], builtin_model=builtin_model)
    if kind == "datapack":
        target = install_datapack(root, name, version_dir)
        if os.sep + "saves" + os.sep in target:
            return target, "数据包已装进存档，进游戏 /reload 就能用"
        return target, "还没存档，先开一局游戏，再点一次生成就会装进存档"
    if kind == "kubejs":
        target = install_kubejs(root, name, version_dir)
        return target, "KubeJS 脚本放好了，重启游戏生效" if target else "这个版本没装 KubeJS"
    if kind == "plugin":
        jar, error = install_plugin(root, name, base)
        if error:
            return root, error
        dest = os.path.join(base, "assist", "plugins")
        os.makedirs(dest, exist_ok=True)
        final = os.path.join(dest, os.path.basename(jar))
        shutil.copyfile(jar, final)
        return final, "插件编译好了，放到服务端 plugins 里就能用"
    dest = os.path.join(base, "assist", "mods", name)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.isdir(dest):
        shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(root, dest)
    if build:
        try:
            import assist_build
            jar = assist_build.build_mod(dest, base, progress)
            final = assist_build.install_jar(jar, version_dir, base)
            return final, "模组编译好了，已经放进当前版本的 mods"
        except Exception as error:
            return dest, "工程已生成但构建失败：%s（源码在 %s）" % (str(error)[:120], dest)
    return dest, "工程已生成；勾上“直接构建”就能编成 jar 装进 mods"
