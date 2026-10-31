"""modgen — 按需求生成 Minecraft 模组 / 服务端插件骨架。

不是只做陪聊：命令、物品、方块、进服事件、插件命令、插件监听器都有模板。
"""

import os

FABRIC_KINDS = {
    "chat": "陪聊（/cz 说话）",
    "command": "自定义命令（/hello）",
    "item": "自定义物品",
    "block": "自定义方块",
    "event": "进服欢迎事件",
}

PAPER_KINDS = {
    "command": "插件命令（/hi）",
    "listener": "事件监听（进服提示）",
    "chat": "聊天处理",
}


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def detect_kind(text, target):
    low = (text or "").lower()
    if target == "plugin":
        if any(w in low for w in ("监听", "进服", "加入", "事件")):
            return "listener"
        if any(w in low for w in ("聊天", "说话", "陪聊")):
            return "chat"
        return "command"
    if any(w in low for w in ("物品", "装备", "武器", "道具", "item")):
        return "item"
    if any(w in low for w in ("方块", "block")):
        return "block"
    if any(w in low for w in ("进服", "欢迎", "事件", "event")):
        return "event"
    if any(w in low for w in ("陪聊", "聊天", "说话")):
        return "chat"
    return "command"


FABRIC_BUILD = """plugins { id 'fabric-loom' version '1.6-SNAPSHOT' }
group = 'com.changzheng'
version = '1.0.0'
dependencies {
    minecraft "com.mojang:minecraft:1.20.1"
    mappings "net.fabricmc:yarn:1.20.1+build.10:v2"
    modImplementation "net.fabricmc:fabric-loader:0.15.11"
}
"""


def _fabric_json(mod_id, mod_name, entry):
    return """{
  "schemaVersion": 1,
  "id": "%s",
  "version": "1.0.0",
  "name": "%s",
  "description": "长征启动器生成",
  "entrypoints": { "main": ["com.changzheng.%s.Entry"] },
  "depends": { "fabricloader": ">=0.15.0", "minecraft": "~1.20.1" }
}
""" % (mod_id, mod_name, mod_id)


def scaffold_fabric(folder, kind, mod_id="changzhengmod", mod_name="ChangzhengMod"):
    src = os.path.join(folder, "src", "main", "java", "com", "changzheng", mod_id)
    res = os.path.join(folder, "src", "main", "resources")
    _write(os.path.join(folder, "build.gradle"), FABRIC_BUILD)
    _write(os.path.join(res, "fabric.mod.json"), _fabric_json(mod_id, mod_name, mod_id))

    if kind == "item":
        _write(os.path.join(src, "Entry.java"), """package com.changzheng.%s;

import net.fabricmc.api.ModInitializer;
import net.minecraft.item.Item;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;
import net.minecraft.util.Identifier;

public class Entry implements ModInitializer {
    public static final Item ITEM = new Item(new Item.Settings());

    @Override
    public void onInitialize() {
        Registry.register(Registries.ITEM, new Identifier("%s", "custom_item"), ITEM);
    }
}
""" % (mod_id, mod_id))
    elif kind == "block":
        _write(os.path.join(src, "Entry.java"), """package com.changzheng.%s;

import net.fabricmc.api.ModInitializer;
import net.minecraft.block.AbstractBlock;
import net.minecraft.block.Block;
import net.minecraft.item.BlockItem;
import net.minecraft.item.Item;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;
import net.minecraft.util.Identifier;

public class Entry implements ModInitializer {
    public static final Block BLOCK = new Block(AbstractBlock.Settings.create().strength(2f));

    @Override
    public void onInitialize() {
        Registry.register(Registries.BLOCK, new Identifier("%s", "custom_block"), BLOCK);
        Registry.register(Registries.ITEM, new Identifier("%s", "custom_block"),
            new BlockItem(BLOCK, new Item.Settings()));
    }
}
""" % (mod_id, mod_id, mod_id))
    elif kind == "event":
        _write(os.path.join(src, "Entry.java"), """package com.changzheng.%s;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents;
import net.minecraft.text.Text;

public class Entry implements ModInitializer {
    @Override
    public void onInitialize() {
        ServerPlayConnectionEvents.JOIN.register((handler, sender, server) ->
            server.getPlayerManager().broadcast(
                Text.literal(handler.getPlayer().getName().getString() + " 来了。"), false));
    }
}
""" % mod_id)
    else:  # command / chat
        _write(os.path.join(src, "Entry.java"), """package com.changzheng.%s;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.minecraft.server.command.CommandManager;
import net.minecraft.text.Text;

public class Entry implements ModInitializer {
    @Override
    public void onInitialize() {
        CommandRegistrationCallback.EVENT.register((dispatcher, registry, env) ->
            dispatcher.register(CommandManager.literal("hello")
                .executes(ctx -> {
                    ctx.getSource().sendFeedback(() -> Text.literal("长征在这里。"), false);
                    return 1;
                })));
    }
}
""" % mod_id)
    return {"folder": folder, "kind": kind, "target": "fabric",
            "desc": FABRIC_KINDS.get(kind, kind), "build": "在文件夹里跑 gradlew build"}


PAPER_BUILD = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.changzheng</groupId>
  <artifactId>%s</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.source>21</maven.compiler.source>
    <maven.compiler.target>21</maven.compiler.target>
  </properties>
  <repositories>
    <repository><id>papermc</id><url>https://repo.papermc.io/repository/maven-public/</url></repository>
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
"""


def scaffold_paper(folder, kind, name="MyPlugin", package="com.changzheng.myplugin"):
    src = os.path.join(folder, "src", "main", "java", *package.split("."))
    res = os.path.join(folder, "src", "main", "resources")
    _write(os.path.join(folder, "pom.xml"), PAPER_BUILD % name)
    _write(os.path.join(res, "plugin.yml"),
           "name: %s\nversion: 1.0.0\nmain: %s.%s\napi-version: '1.20'\n" % (name, package, name))
    if kind == "listener":
        _write(os.path.join(src, name + ".java"), """package %s;

import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.plugin.java.JavaPlugin;

public class %s extends JavaPlugin implements Listener {
    @Override
    public void onEnable() {
        getServer().getPluginManager().registerEvents(this, this);
        getLogger().info("%s 已加载");
    }

    @EventHandler
    public void onJoin(PlayerJoinEvent event) {
        event.getPlayer().sendMessage("欢迎回来，" + event.getPlayer().getName());
    }
}
""" % (package, name, name))
    elif kind == "chat":
        _write(os.path.join(src, name + ".java"), """package %s;

import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.AsyncPlayerChatEvent;
import org.bukkit.plugin.java.JavaPlugin;

public class %s extends JavaPlugin implements Listener {
    @Override
    public void onEnable() {
        getServer().getPluginManager().registerEvents(this, this);
    }

    @EventHandler
    public void onChat(AsyncPlayerChatEvent event) {
        if (event.getMessage().contains("卡")) {
            event.getPlayer().sendMessage("卡的话换低配光影试试。");
        }
    }
}
""" % (package, name))
    else:
        _write(os.path.join(src, name + ".java"), """package %s;

import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.plugin.java.JavaPlugin;

public class %s extends JavaPlugin {
    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (command.getName().equalsIgnoreCase("hi")) {
            sender.sendMessage("长征在这里。");
            return true;
        }
        return false;
    }
}
""" % (package, name))
    return {"folder": folder, "kind": kind, "target": "paper",
            "desc": PAPER_KINDS.get(kind, kind), "build": "在文件夹里跑 mvn package"}


def make(text, base_dir, name="ChangzhengMod"):
    """按用户说的话挑模板生成，返回说明。"""
    target = "plugin" if any(w in (text or "") for w in ("插件", "服务端", "paper", "bukkit")) else "fabric"
    kind = detect_kind(text, target)
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_") or "ChangzhengMod"
    safe = safe + "-" + kind
    folder = os.path.join(base_dir, safe)
    if target == "plugin":
        info = scaffold_paper(folder, kind, safe, "com.changzheng." + safe.lower())
    else:
        info = scaffold_fabric(folder, kind, safe.lower(), safe)
    info["name"] = safe
    return info
