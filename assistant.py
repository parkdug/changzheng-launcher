"""assistant — 启动器里的「长征小助手」。

本地跑，不花 token：先把你说的话分类（mod / 光影 / 材质 / 数据包 / 整合包 / 插件），
再去 Modrinth 按你的版本和加载器搜，然后装到对的文件夹里。
"""

import os
import re

import mods_api

CATEGORIES = [
    ("shader", ("光影", "着色", "shader", "iris", "optifine光影")),
    ("resourcepack", ("材质", "资源包", "resourcepack", "贴图")),
    ("datapack", ("数据包", "datapack")),
    ("modpack", ("整合包", "modpack", "客户端包")),
    ("plugin", ("插件", "服务端", "paper", "bukkit", "服务器插件")),
    ("map", ("地图", "存档", "world", "地图下载")),
    ("mod", ("模组", "mod", "附属")),
]

# 每个类别装到哪
TARGET_DIRS = {
    "mod": "mods",
    "shader": "shaderpacks",
    "resourcepack": "resourcepacks",
    "datapack": "datapacks",
}

PROJECT_TYPE = {
    "mod": "mod",
    "shader": "shader",
    "resourcepack": "resourcepack",
    "datapack": "datapack",
    "modpack": "modpack",
    "plugin": "plugin",
}

LOADER_HINT = {
    "mod": None,
    "shader": None,
    "resourcepack": None,
    "datapack": None,
    "modpack": None,
    "plugin": ["paper", "bukkit", "spigot", "purpur", "folia"],
}


def classify(text):
    low = (text or "").lower()
    for kind, words in CATEGORIES:
        for word in words:
            if word.lower() in low:
                return kind
    return "mod"


def strip_words(text, kind):
    """把「帮我找有没有」这类废话去掉，留下真正的搜索词。"""
    noise = ["帮我", "找一下", "找一个", "找找", "有没有", "想要", "下载", "安装", "给我",
             "一下", "推荐", "什么", "怎么样", "能", "的", "吗", "呢", "吧", "个", "款"]
    for _kind, words in CATEGORIES:
        for word in words:
            noise.append(word)
    out = text or ""
    for word in sorted(noise, key=len, reverse=True):
        out = out.replace(word, " ")
    out = re.sub(r"[，。！？、,.!?~·]+", " ", out).strip()
    return out or (text or "")


# 中文最常问的那些词 → Modrinth 认的英文
WORD_MAP = [
    (("帧数", "优化", "卡顿", "流畅", "性能"), "sodium"),
    (("小地图",), "minimap"),
    (("光影", "着色", "光追"), "shader"),
    (("材质", "贴图", "资源包"), "resource pack"),
    (("字体", "汉化"), "font"),
    (("领地", "保护"), "protection"),
    (("经济", "金币"), "economy"),
    (("传送",), "teleport"),
    (("背包", "箱子"), "inventory"),
    (("合成", "配方"), "recipe"),
    (("怪物", "生物"), "mob"),
    (("武器", "附魔"), "enchantment"),
    (("家具", "装饰"), "furniture"),
    (("机械", "自动化"), "create"),
    (("农业", "种田"), "farming"),
    (("建筑", "造房子"), "building"),
    (("枪", "射击"), "gun"),
    (("魔法",), "magic"),
    (("任务", "成就"), "quest"),
    (("地图", "跑图"), "map"),
]

CJK = re.compile(r"[\u4e00-\u9fff]")


def to_query(text, kind):
    low = text or ""
    words = []
    for zh_words, en in WORD_MAP:
        if any(zh in low for zh in zh_words):
            words.append(en)
    if words:
        return " ".join(dict.fromkeys(words))
    cleaned = strip_words(low, kind)
    if cleaned and not CJK.search(cleaned):
        return cleaned
    return ""


def search(text, loader, mc_version, limit=8):
    kind = classify(text)
    if kind == "map":
        return kind, [], "地图 Modrinth 不托管，得去 CurseForge 或者 Planet Minecraft 手动下，我暂时帮不上。"
    query = to_query(text, kind)
    if kind == "plugin":
        hits = mods_api.search_project(query, "plugin", mc_version, ["paper", "bukkit"], limit)
    elif kind in ("shader", "resourcepack", "datapack"):
        hits = mods_api.search_project(query, PROJECT_TYPE[kind], mc_version, [], limit)
    else:
        loaders = [] if loader in ("vanilla", "", None) else [loader]
        hits = mods_api.search_project(query, PROJECT_TYPE.get(kind, "mod"), mc_version, loaders, limit)
    if not hits:
        return kind, [], "没搜到合适的，换个说法再试试。"
    return kind, hits, ""


def install_dir(version_dir, kind):
    return os.path.join(version_dir, TARGET_DIRS.get(kind, "mods"))


def install(item, kind, loader, mc_version, version_dir):
    if kind == "map":
        return None, "地图不支持自动装"
    if kind == "modpack":
        return None, "整合包要单独导入，还没做"
    project = PROJECT_TYPE.get(kind, "mod")
    loaders = []
    if kind in ("mod", "modpack") and loader not in ("vanilla", "", None):
        loaders = [loader]
    if kind == "plugin":
        loaders = ["paper"]
    return mods_api.install_project(item, project, mc_version, loaders, install_dir(version_dir, kind))


def scaffold_plugin(folder, package, name):
    """给一个能直接编译的 Paper 插件骨架。"""
    src = os.path.join(folder, "src", "main", "java", *package.split("."))
    os.makedirs(src, exist_ok=True)
    os.makedirs(os.path.join(folder, "src", "main", "resources"), exist_ok=True)
    with open(os.path.join(folder, "pom.xml"), "w", encoding="utf-8") as handle:
        handle.write("""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>%s</groupId>
  <artifactId>%s</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.source>21</maven.compiler.source>
    <maven.compiler.target>21</maven.compiler.target>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <repositories>
    <repository>
      <id>papermc</id>
      <url>https://repo.papermc.io/repository/maven-public/</url>
    </repository>
  </repositories>
  <dependencies>
    <dependency>
      <groupId>io.papermc.paper</groupId>
      <artifactId>paper-api</artifactId>
      <version>1.20.1-R0.1-SNAPSHOT</version>
      <scope>provided</scope>
    </dependency>
  </dependencies>
</project>
""" % (package, name))
    with open(os.path.join(folder, "src", "main", "resources", "plugin.yml"), "w", encoding="utf-8") as handle:
        handle.write("name: %s\nversion: 1.0.0\nmain: %s.%s\napi-version: '1.20'\n" % (name, package, name))
    with open(os.path.join(src, name + ".java"), "w", encoding="utf-8") as handle:
        handle.write("""package %s;

import org.bukkit.plugin.java.JavaPlugin;

public class %s extends JavaPlugin {
    @Override
    public void onEnable() {
        getLogger().info("%s 已加载");
    }

    @Override
    public void onDisable() {
        getLogger().info("%s 卸载了");
    }
}
""" % (package, name, name, name))
    return folder


# 整合包/资源这类「我想要个…的」需求，翻成 Modrinth 认识的词
MODPACK_MAP = [
    (("好玩", "有趣", "耐玩", "内容多"), "adventure"),
    (("优化", "流畅", "帧数", "性能"), "optimization"),
    (("生存", "原版", "纯净"), "vanilla+ survival"),
    (("科技", "机械", "工厂", "工业"), "tech"),
    (("魔法", "奇幻"), "magic"),
    (("冒险", "rpg", "剧情"), "adventure rpg"),
    (("空岛",), "skyblock"),
    (("建筑", "造城"), "building"),
    (("休闲", "养老", "轻松"), "lightweight relaxed"),
    (("恐怖", "惊悚"), "horror"),
    (("多人", "联机", "朋友"), "multiplayer"),
]


def modpack_query(text):
    low = (text or "").lower()
    words = []
    for zh, en in MODPACK_MAP:
        if any(w in low for w in zh):
            words.append(en)
    if words:
        return " ".join(dict.fromkeys(words))
    return to_query(text, "modpack")


def reason_for(item):
    """一句话说明为什么推荐它（给用户看的）。"""
    dl = item.get("downloads") or 0
    if dl >= 1_000_000:
        dl_text = "%.1fM" % (dl / 1_000_000)
    elif dl >= 1000:
        dl_text = "%.0fK" % (dl / 1000)
    else:
        dl_text = str(dl)
    cats = [c for c in (item.get("categories") or []) if c not in ("minecraft", "modpack")][:3]
    tail = " · " + "/".join(cats) if cats else ""
    return "%s 次下载%s" % (dl_text, tail)


def intent_query(text):
    """给 mod / 光影 / 整合包 都用的意图翻译。"""
    return modpack_query(text)


def scaffold_chat_mod(folder, mod_id="changzheng", mod_name="ChangzhengChat"):
    """生成一个 Fabric 陪聊 mod 骨架：游戏里打 /cz 说句话，她回一句。"""
    import os as _os
    src = _os.path.join(folder, "src", "main", "java", "com", "changzheng", mod_id)
    res = _os.path.join(folder, "src", "main", "resources")
    _os.makedirs(src, exist_ok=True)
    _os.makedirs(res, exist_ok=True)
    with open(_os.path.join(folder, "build.gradle"), "w", encoding="utf-8") as f:
        f.write("""plugins { id 'fabric-loom' version '1.6-SNAPSHOT' }
group = 'com.changzheng'
version = '1.0.0'
dependencies {
    minecraft "com.mojang:minecraft:1.20.1"
    mappings "net.fabricmc:yarn:1.20.1+build.10:v2"
    modImplementation "net.fabricmc:fabric-loader:0.15.11"
}
""")
    with open(_os.path.join(res, "fabric.mod.json"), "w", encoding="utf-8") as f:
        f.write("""{
  "schemaVersion": 1,
  "id": "%s",
  "version": "1.0.0",
  "name": "%s",
  "description": "长征陪你聊天",
  "entrypoints": { "main": ["com.changzheng.%s.ChatEntry"] },
  "depends": { "fabricloader": ">=0.15.0", "minecraft": "~1.20.1" }
}
""" % (mod_id, mod_name, mod_id))
    with open(_os.path.join(src, "ChatEntry.java"), "w", encoding="utf-8") as f:
        f.write("""package com.changzheng.%s;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.minecraft.server.command.CommandManager;
import net.minecraft.text.Text;

public class ChatEntry implements ModInitializer {
    private static final String[] LINES = {
        "在的，爸爸。",
        "嗯？说吧。",
        "我听着呢。",
        "别熬太晚。"
    };

    @Override
    public void onInitialize() {
        CommandRegistrationCallback.EVENT.register((dispatcher, registry, env) ->
            dispatcher.register(CommandManager.literal("cz").executes(ctx -> {
                ctx.getSource().sendFeedback(() -> Text.literal("在。"), false);
                return 1;
            }).then(CommandManager.argument("text", com.mojang.brigadier.arguments.StringArgumentType.greedyString())
                .executes(ctx -> {
                    String said = com.mojang.brigadier.arguments.StringArgumentType.getString(ctx, "text");
                    String reply = LINES[(int) (Math.random() * LINES.length)];
                    ctx.getSource().sendFeedback(() -> Text.literal("<长征> " + reply), false);
                    return 1;
                }))));
    }
}
""" % mod_id)
    return folder
