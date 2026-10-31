window.onerror = function (msg, src, line) {
  try {
    fetch("/api/clientlog", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ msg: String(msg), line: line, src: String(src) }) });
  } catch (e) {}
  const box = document.getElementById("toast");
  if (box) { box.textContent = "界面报错：" + msg; box.classList.add("show"); }
};

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

const state = {
  versions: [], chosen: null, config: {}, source: "official", filter: "全部",
  kind: "vanilla", manifest: [], mc: "1.18.2", loader: "vanilla", offset: 0, cfg: {},
};

function toast(text, ms = 2400) {
  const el = $("#toast");
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), ms);
}

async function api(path, body) {
  const opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
  const res = await fetch(path, opts);
  return res.json();
}

function showPage(name) {
  $$(".rail-btn").forEach((b) => b.classList.toggle("active", b.dataset.page === name));
  $$(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + name));
  if (name === "files" && window.loadFiles) loadFiles();
}
const CZ_PAGE = (location.search.match(/[?&]page=(\w+)/) || [])[1];
if (CZ_PAGE) setTimeout(() => showPage(CZ_PAGE), 600);

async function loadFiles() {
  const sg = $("#savesGrid");
  const shots = $("#shotsGrid");
  if (!sg) return;
  sg.innerHTML = '<p class="tiny">正在读…</p>';
  const s = await api("/api/saves?version=" + encodeURIComponent(state.chosen || ""));
  if (!s.ok) {
    sg.innerHTML = '<p class="tiny">读不到存档：' + s.error + "</p>";
  } else if (!s.items.length) {
    sg.innerHTML = '<p class="tiny">这个版本还没有存档。开一局就有。</p>';
  } else {
    sg.innerHTML = s.items.map((it) =>
      '<div class="save-card">' +
      (it.has_icon
        ? '<img class="save-icon" src="/api/saves/icon?version=' + encodeURIComponent(state.chosen || "") +
          "&name=" + encodeURIComponent(it.name) + '">'
        : '<div class="save-icon blank"></div>') +
      '<div class="save-meta"><b>' + it.name + "</b><span>" +
      (it.size / 1024 / 1024).toFixed(1) + " MB · " +
      new Date(it.mtime * 1000).toLocaleDateString() + "</span></div>" +
      '<button class="btn tiny danger" data-del="' + it.name + '">删</button></div>').join("");
    sg.querySelectorAll("[data-del]").forEach((btn) => btn.addEventListener("click", async () => {
      const name = btn.getAttribute("data-del");
      if (!confirm("把存档 " + name + " 移到 saves-trash？")) return;
      const r = await api("/api/saves/delete", { version: state.chosen, name: name });
      toast(r.ok ? "已移走" : "失败：" + r.error);
      loadFiles();
    }));
  }
  $("#openSavesDir")?.addEventListener("click", () => api("/api/reveal", { path: s.dir }), { once: true });

  shots.innerHTML = '<p class="tiny">正在读…</p>';
  const sh = await api("/api/screenshots");
  if (!sh.ok) {
    shots.innerHTML = '<p class="tiny">读不到截图：' + sh.error + "</p>";
  } else if (!sh.items.length) {
    shots.innerHTML = '<p class="tiny">还没有截图。游戏里按 F2 就有了。</p>';
  } else {
    const groups = {};
    sh.items.forEach((it) => {
      const d = new Date(it.mtime * 1000);
      const key = d.getFullYear() + " 年 " + (d.getMonth() + 1) + " 月";
      (groups[key] = groups[key] || []).push(it);
    });
    shots.innerHTML = Object.keys(groups).map((key) => {
      const cards = groups[key].map((it) =>
        '<a class="shot" href="/api/shot?v=' + encodeURIComponent(it.v || "root") + '&name=' +
        encodeURIComponent(it.name) + '" target="_blank" title="' + it.name + '">' +
        '<img src="/api/shot?v=' + encodeURIComponent(it.v || "root") + '&name=' +
        encodeURIComponent(it.name) + '" loading="lazy">' +
        '<span>' + new Date(it.mtime * 1000).toLocaleDateString() + "</span></a>").join("");
      return '<div class="shot-group"><div class="shot-month">' + key + "（" + groups[key].length +
        '）</div><div class="shots-grid">' + cards + "</div></div>";
    }).join("");
  }
  $("#openShotsDir")?.addEventListener("click", () => api("/api/reveal", { path: sh.dir }), { once: true });
}

$$(".rail-btn").forEach((btn) => btn.addEventListener("click", () => {
  $$(".rail-btn").forEach((b) => b.classList.toggle("active", b === btn));
  $$(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + btn.dataset.page));
}));

const THEME = { red: "#9E1B1B", blue: "#1F5FA8", green: "#2E7D46", gold: "#A9701C" };
function applyTheme(name) {
  document.documentElement.style.setProperty("--theme", THEME[name] || THEME.red);
  state.cfg.theme = name;
  $$(".sw").forEach((s) => s.classList.toggle("active", s.dataset.theme === name));
}
$$(".sw").forEach((sw) => sw.addEventListener("click", () => applyTheme(sw.dataset.theme)));

let lastProgress = "";
let hideTimer = null;
setInterval(async () => {
  try {
    const r = await api("/api/progress");
    const bar = $("#dlBar");
    if (!bar) return;
    if (r.active) {
      bar.classList.remove("hidden");
      bar.classList.toggle("indeterminate", r.percent === null || r.percent === undefined);
      if (r.percent !== null && r.percent !== undefined) {
        $("#dlFill").style.width = r.percent + "%";
        $("#dlPct").textContent = r.percent + "%";
      } else {
        $("#dlPct").textContent = "";
      }
      $("#dlLabel").textContent = r.progress || "下载中…";
      clearTimeout(hideTimer);
    } else if (!bar.classList.contains("hidden")) {
      if (r.percent === 100) { $("#dlFill").style.width = "100%"; $("#dlPct").textContent = "100%"; }
      clearTimeout(hideTimer);
      hideTimer = setTimeout(() => { bar.classList.add("hidden"); $("#dlFill").style.width = "0%"; }, 2200);
    }
  } catch (e) {}
}, 900);

async function boot() {
  try { await bootInner(); } catch (e) { toast("初始化失败：" + e.message, 6000); throw e; }
}

async function bootInner() {
  const d = await api("/api/bootstrap");
  state.versions = d.versions || [];
  state.chosen = d.chosen;
  state.config = d.config || {};
  state.cfg = Object.assign({}, d.config);
  state.version = d.version || "";
  applyTheme(state.config.theme || "red");
  $("#statVersions").textContent = state.versions.length;
  $("#statDir").textContent = d.mcDir || "";
  $("#statJava").textContent = d.java || "未找到";
  $("#javaLine").textContent = "Java " + (d.java ? d.java.split("\\").pop() : "未找到");
  if (!d.java) {
    const line = document.getElementById("javaLine");
    if (line) {
      line.innerHTML = 'Java 未找到（点这里装）';
      line.style.color = "#C2352F";
      line.style.cursor = "pointer";
      line.addEventListener("click", () => {
        window.open("https://adoptium.net/temurin/releases/?version=17&os=windows", "_blank");
      });
    }
  }
  renderSettings();
  if (d.profile) applyProfile(d.profile);
  syncChosen();
  renderMyVersions();
  const off = document.querySelector('#sourceSeg button[data-source="official"]');
  if (off) { document.querySelectorAll("#sourceSeg button").forEach((b) => b.classList.toggle("on", b === off)); }
  loadManifest();
  refreshNet();
}

function applyProfile(p) {
  $("#playerName").textContent = p.name;
  $("#playerSub").textContent = p.user_type === "msa" ? "正版账号" : "离线账号";
  $("#account").textContent = (p.user_type === "msa" ? "正版：" : "离线：") + p.name;
}

function syncChosen() {
  const v = state.versions.find((x) => x.id === state.chosen) || state.versions[0];
  if (v) {
    state.mc = v.mc; state.loader = v.loader;
    $("#playVersion").textContent = v.id + " · " + v.mc + " / " + v.loader;
  }
  $$(".ver-chip").forEach((c) => c.classList.toggle("active", c.dataset.id === state.chosen));
}

function renderMyVersions() {
  const box = $("#myVersions");
  box.innerHTML = "";
  if (!state.versions.length) {
    box.innerHTML = '<div class="empty-hint"><b>还没有装任何版本</b>' +
      '<p>点「下载」挑一个装上就能玩。第一次用建议先装个正式版，' +
      '比如最新的正式版；想玩模组再装 Fabric 或 Forge。</p>' +
      '<button class="btn primary" id="goDownload">去下载页</button></div>';
    $("#goDownload")?.addEventListener("click", () => {
      const btn = document.querySelector('.rail-btn[data-page="download"]');
      if (btn) btn.click();
    });
    return;
  }
  const groups = {};
  state.versions.forEach((v) => { (groups[v.mc] = groups[v.mc] || []).push(v); });
  Object.keys(groups).sort().reverse().forEach((mc) => {
    const g = document.createElement("div");
    g.className = "ver-group";
    g.innerHTML = '<div class="ver-group-title">Minecraft ' + mc + "（" + groups[mc].length + "）</div>";
    groups[mc].forEach((v) => {
      const chip = document.createElement("button");
      chip.className = "ver-chip" + (v.id === state.chosen ? " active" : "");
      chip.dataset.id = v.id;
      chip.innerHTML = v.id + ' <span class="tag">' + v.loader + '</span><span class="ver-del" title="删除这个版本">×</span>';
      chip.querySelector(".ver-del").addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm("把 " + v.id + " 移到回收站？")) return;
        const r = await api("/api/version/delete", { version: v.id });
        if (r.ok) {
          toast("已移到 versions-trash");
          const d = await api("/api/bootstrap");
          state.versions = d.versions || [];
          renderMyVersions(); syncChosen();
        } else { toast("删除失败：" + r.error); }
      });
      chip.addEventListener("click", async () => {
        state.chosen = v.id;
        await api("/api/choose", { id: v.id });
        syncChosen(); renderMyVersions();
        toast("启动目标：" + v.id);
      });
      g.appendChild(chip);
    });
    box.appendChild(g);
  });
}

$$(".cat").forEach((btn) => btn.addEventListener("click", () => {
  $$(".cat").forEach((b) => b.classList.toggle("active", b === btn));
  state.kind = btn.dataset.kind;
  const vanilla = state.kind === "vanilla";
  $("#vanillaPanel").classList.toggle("active", vanilla);
  $("#communityPanel").classList.toggle("active", !vanilla);
  if (!vanilla) { $("#typeSel").value = state.kind; loadCommunity(true); }
}));

$$("#sourceSeg button").forEach((b) => b.addEventListener("click", () => {
  $$("#sourceSeg button").forEach((x) => x.classList.toggle("on", x === b));
  state.source = b.dataset.source; loadManifest();
}));
$$("#filterSeg button").forEach((b) => b.addEventListener("click", () => {
  $$("#filterSeg button").forEach((x) => x.classList.toggle("on", x === b));
  state.filter = b.dataset.filter; renderVersions();
}));

async function loadManifest() {
  $("#versionList").classList.add("skeleton");
  $("#versionList").innerHTML = "";
  const r = await api("/api/manifest?source=" + state.source);
  $("#versionList").classList.remove("skeleton");
  if (!r.ok) { toast("清单取不到：" + r.error); return; }
  state.manifest = r.versions || [];
  $("#versionHint").textContent = state.manifest.length + " 个版本（最早 → 最新）";
  renderVersions();
}

function renderVersions() {
  const box = $("#versionList");
  box.innerHTML = "";
  const all = state.manifest;
  const newest = all.slice().reverse().find((v) => v.type === "release");
  const groups = [
    { label: "最新正式版", rows: newest ? [newest] : [] },
    { label: "正式版", rows: all.filter((v) => v.type === "release" && v !== newest) },
    { label: "快照", rows: all.filter((v) => v.type === "snapshot") },
    { label: "远古版本", rows: all.filter((v) => v.type === "old_alpha" || v.type === "old_beta") },
  ];
  groups.forEach((g, idx) => {
    let rows = g.rows;
    if (state.filter === "正式版") rows = rows.filter((r) => r.type === "release");
    if (state.filter === "快照") rows = rows.filter((r) => r.type === "snapshot");
    if (state.filter === "远古") rows = rows.filter((r) => r.type === "old_alpha" || r.type === "old_beta");
    if (!rows.length) return;
    const el = document.createElement("div");
    el.className = "vgroup" + (idx < 2 ? " open" : "");
    el.innerHTML = '<div class="vgroup-head"><span>' + g.label + "（" + rows.length + '）</span><span class="hint">▾</span></div><div class="vrows"></div>';
    el.querySelector(".vgroup-head").addEventListener("click", () => el.classList.toggle("open"));
    const rowsBox = el.querySelector(".vrows");
    rows.slice(0, 300).forEach((item) => {
      const installed = state.versions.some((v) => v.id === item.id);
      const row = document.createElement("div");
      row.className = "vrow";
      row.innerHTML = '<span class="name">' + item.id + '</span><span class="meta">' +
        (item.type || "") + " " + (item.release || "") + '</span><button class="install">' +
        (installed ? "已安装" : "安装") + "</button>";
      row.querySelector(".install").addEventListener("click", async (e) => {
        e.stopPropagation();
        if (installed) {
          state.chosen = item.id;
          await api("/api/choose", { id: item.id });
          syncChosen(); toast("设为启动目标：" + item.id);
          return;
        }
        const btn = e.currentTarget;
        btn.disabled = true;
        btn.textContent = "安装中…";
        toast("开始安装 " + item.id);
        const started = await api("/api/install/vanilla", {
          id: item.id, source: state.source,
          loader: ($("#loaderSel") || {}).value || "",
          prereqs: !!($("#prereqChk") && $("#prereqChk").checked),
        });
        if (!started.ok) {
          toast("安装没起来：" + started.error, 5000);
          btn.disabled = false; btn.textContent = "安装";
          return;
        }
        const t0 = Date.now();
        let last = "";
        while (Date.now() - t0 < 900000) {
          await new Promise((r) => setTimeout(r, 2500));
          const prog = await api("/api/progress");
          last = prog.progress || last;
          if (last.indexOf("失败") >= 0) { toast(last, 6000); break; }
          const data = await api("/api/bootstrap");
          state.versions = data.versions || [];
          if (state.versions.some((v) => v.id === item.id)) {
            state.chosen = item.id;
            await api("/api/choose", { id: item.id });
            syncChosen(); renderMyVersions(); renderVersions();
            toast(item.id + " 装好了，已设为启动目标");
            break;
          }
        }
        btn.disabled = false;
        btn.textContent = "安装";
      });
      rowsBox.appendChild(row);
    });
    box.appendChild(el);
  });
}

$("#searchBtn")?.addEventListener("click", () => loadCommunity(true));
$("#moreBtn")?.addEventListener("click", () => loadCommunity(false));
$("#searchInput")?.addEventListener("keydown", (e) => { if (e.key === "Enter") loadCommunity(true); });
$("#typeSel")?.addEventListener("change", () => loadCommunity(true));
$("#sourceSel")?.addEventListener("change", () => loadCommunity(true));

async function loadCommunity(reset) {
  if (reset === undefined) reset = true;
  const box = $("#modList");
  if (reset) { state.offset = 0; box.classList.add("skeleton"); box.innerHTML = ""; }
  const kind = $("#typeSel").value;
  const source = $("#sourceSel").value;
  const q = encodeURIComponent($("#searchInput").value.trim());
  const deps = $("#depsChk").checked ? 1 : 0;
  const url = "/api/community?type=" + kind + "&mc=" + state.mc + "&loader=" + state.loader +
    "&source=" + source + "&q=" + q + "&deps=" + deps + "&limit=40&offset=" + state.offset;
  const r = await api(url);
  box.classList.remove("skeleton");
  if (!r.ok) { toast("搜不到：" + r.error); return; }
  const items = r.items || [];
  const start = box.children.length;
  items.forEach((item, i) => {
    const el = document.createElement("div");
    el.className = "mod-card";
    el.dataset.pid = item.id || "";
    el.dataset.kind = kind;
    el.style.animationDelay = ((start + i) * 8) + "ms";
    const icon = item.icon
      ? '<img class="mod-icon" src="' + item.icon + '" loading="lazy" onerror="this.style.visibility=\'hidden\'">'
      : '<div class="mod-icon"></div>';
    const shown = item.zh ? item.zh : item.title;
    const sub = item.zh ? '<span class="en">' + item.title + "</span> · " : "";
    el.innerHTML = icon +
      '<div class="mod-info"><div class="mod-title">' + shown + '</div><div class="mod-desc">' + sub +
      (item.desc || "") + '</div>' +
      ((item.versions && item.versions.length) ? '<div class="mod-vers">支持 ' + item.versions.slice(-5).join(" · ") + "</div>" : "") +
      '</div><div class="mod-meta"><span class="dl">' +
      (item.downloads || 0).toLocaleString() + ' 下载</span><button class="btn primary">装这个</button></div>';
    el.querySelector("button").addEventListener("click", async () => {
      toast("下载 " + item.title);
      await api("/api/install/mod", { version: state.chosen, type: kind, item: item });
    });
    box.appendChild(el);
  });
  state.offset += items.length;
  $("#moreBtn").style.display = items.length >= 20 ? "inline-block" : "none";
}

async function refreshNet() {
  const r = await api("/api/server/state?version=" + encodeURIComponent(state.chosen || ""));
  if (!r.ok) return;
  $("#netInfo").textContent = "版本：" + r.mc + "\n目录：" + r.folder +
    "\n服务端：" + (r.hasJar ? "已下载" : "还没下") +
    "\n开服状态：" + (r.online ? "运行中" : "未启动") +
    "\n局域网：" + r.lan + ":25565";
}
$("#directCheck")?.addEventListener("click", async () => {
  const box = $("#directInfo");
  box.textContent = "正在看…";
  const r = await api("/api/direct/net");
  if (!r.ok) { box.textContent = "检测失败：" + r.error; return; }
  const v6 = r.public_v6 || (r.v6 && r.v6[0]) || "";
  const lines = [];
  if (v6) {
    lines.push("你家有公网 IPv6：[" + v6 + "]:25565");
    lines.push("朋友在游戏里「添加服务器」填这个就能进，不用任何穿透。");
  } else {
    lines.push("没检测到公网 IPv6（运营商没给，或者光猫那边没开）。");
  }
  lines.push("局域网地址：" + ((r.v4 && r.v4[0]) || "未知") + ":25565");
  const tools = r.tools || {};
  const have = Object.keys(tools).filter((k) => tools[k]);
  if (have.length) {
    lines.push("检测到虚拟局域网工具：" + have.join(" / ") + "，用它的 IP 也能直接连。");
  } else if (!v6) {
    lines.push("没有 v6 又不想穿透，就装 Tailscale 或 Radmin VPN，两台加进同一个网络，连它给的 IP。");
  }
  lines.push("别忘了先开放防火墙，别人才能连进来。");
  box.innerHTML = lines.join("<br>");
});
$("#directFirewall")?.addEventListener("click", async () => {
  const r = await api("/api/direct/firewall", {});
  if (r.ok) { toast("防火墙规则加好了"); return; }
  if (r.bat) {
    toast("需要管理员权限：给你生成了「开放防火墙.bat」，右键以管理员身份运行一次就行", 7000);
    await api("/api/reveal", { path: r.bat });
  } else {
    toast("加规则失败，可能要管理员权限", 5000);
  }
});

$("#netPrepare")?.addEventListener("click", async () => {
  const r = await api("/api/server/prepare", { version: state.chosen, online_mode: $("#onlineMode").checked });
  toast(r.ok ? "开服配置写好" : "失败：" + r.error); refreshNet();
});
$("#netDownload")?.addEventListener("click", async () => {
  await api("/api/server/download", { version: state.chosen }); toast("开始下载服务端");
});
$("#netStart")?.addEventListener("click", async () => {
  const r = await api("/api/server/start", { version: state.chosen });
  toast(r.ok ? "服务端已启动" : "启动失败：" + r.error); refreshNet();
});

async function uploadFile(file) {
  const res = await fetch("/api/upload", {
    method: "POST",
    headers: { "X-Filename": encodeURIComponent(file.name) },
    body: file,
  });
  return res.json();
}

function pushAttach(name, size) {
  const el = document.createElement("div");
  el.className = "msg me";
  el.innerHTML = '<div class="who">你</div><div class="body"><span class="attach">📎 ' + name +
    " · " + Math.round((size || 0) / 1024) + " KB</span></div>";
  $("#chat").appendChild(el);
  scrollChat();
}

function bindDrop() {
  const zone = $("#page-ask") || $("#askDrop") || document.body;
  ["dragenter", "dragover"].forEach((evt) => zone.addEventListener(evt, (e) => {
    e.preventDefault(); zone.classList.add("dragover");
  }));
  ["dragleave", "drop"].forEach((evt) => zone.addEventListener(evt, () => zone.classList.remove("dragover")));
  zone.addEventListener("drop", async (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (!file) return;
    pushAttach(file.name, file.size);
    const r = await uploadFile(file);
    if (r.ok) {
      state.upload = { path: r.path, name: r.name };
      pushMsg("小助手", "收到了「" + r.name + "」。你想让我怎么处理它？说「导入这个整合包」我就直接导进当前版本。", false);
    } else {
      pushMsg("小助手", "文件没传上来：" + r.error, false);
    }
  });
}
bindDrop();

$("#importBtn")?.addEventListener("click", () => $("#importFile")?.click());
$("#importFile")?.addEventListener("change", async (e) => {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  toast("上传中…");
  const r = await uploadFile(file);
  if (!r.ok) { toast("上传失败：" + r.error); return; }
  const res = await api("/api/import", { path: r.path, version: state.chosen });
  if (!res.ok) { toast("导入失败：" + res.error); return; }
  pushMsg("小助手", "正在导入「" + r.name + "」，底部能看到进度。", false);
  const t0 = Date.now();
  while (Date.now() - t0 < 900000) {
    await new Promise((ok) => setTimeout(ok, 2500));
    const pg = await api("/api/progress");
    const msg = pg.progress || "";
    if (msg.indexOf("导入完成") >= 0 || msg.indexOf("失败") >= 0) {
      const r2 = await api("/api/import/result");
      const result = r2.result || {};
      pushMsg("小助手", msg.indexOf("失败") >= 0
        ? ("导入没成功：" + msg)
        : ("导好了：" + (result.mods || 0) + " 个文件，重启游戏就能看到。"), false);
      toast("导入结束");
      break;
    }
  }
  const d = await api("/api/bootstrap");
  state.versions = d.versions || [];
  renderMyVersions();
});

function scrollChat() {
  const chat = document.getElementById("chat");
  if (chat) chat.scrollTop = chat.scrollHeight;
}

function pushMsg(who, text, me) {
  const el = document.createElement("div");
  el.className = "msg" + (me ? " me" : "");
  el.innerHTML = '<div class="who">' + who + '</div><div class="body">' + text + "</div>";
  $("#chat").appendChild(el);
  scrollChat();
}
function showTyping() {
  const el = document.createElement("div");
  el.className = "msg thinking";
  el.id = "typingMsg";
  el.innerHTML = '<div class="who">小助手</div><div class="body"><span class="typing"><i></i><i></i><i></i></span></div>';
  $("#chat").appendChild(el);
  scrollChat();
  return el;
}

async function ask() {
  const text = $("#askInput").value.trim();
  if (!text) return;
  $("#askInput").value = "";
  pushMsg("你", text, true);
  const typing = showTyping();
  const r = await api("/api/ask?q=" + encodeURIComponent(text) + "&version=" + encodeURIComponent(state.chosen || ""));
  typing.remove();
  if (!r.ok) { pushMsg("小助手", "没搜到：" + r.error); return; }
  if (!r.items.length) {
    pushMsg("小助手", r.explain || r.note || "换个说法试试");
    return;
  }
  const kindName = { modpack: "整合包", mod: "模组", shader: "光影", resourcepack: "材质包", datapack: "数据包", plugin: "插件" }[r.kind] || "资源";
  const why = r.explain ? r.explain + " " : "";
  pushMsg("小助手", why + "挑了 " + r.items.length + " 个" + kindName + "，按下载量排的，不合适就收起换个说法。");
  $("#askResults").classList.remove("hidden");
  $("#askCount").textContent = "给你找的 " + kindName + "（" + r.items.length + "）";
  const box = $("#askList");
  box.innerHTML = "";
  r.items.forEach((item, i) => {
    const el = document.createElement("div");
    el.className = "mod-card";
    el.style.animationDelay = (i * 8) + "ms";
    const icon = item.icon ? '<img class="mod-icon" src="' + item.icon + '" loading="lazy">' : '<div class="mod-icon"></div>';
    el.innerHTML = icon + '<div class="mod-info"><div class="mod-title">' + (item.zh || item.title) +
      '</div><div class="mod-desc">' + (item.zh ? '<span class="en">' + item.title + '</span> · ' : "") +
      (item.desc || "") + '</div>' +
      (item.reason ? '<div class="mod-reason">' + item.reason + '</div>' : '') +
      '</div><div class="mod-meta"><button class="btn primary">装这个</button></div>';
    el.querySelector("button").addEventListener("click", async () => {
      await api("/api/install/mod", { version: state.chosen, type: r.kind, item: item });
      toast("下载 " + item.title);
    });
    box.appendChild(el);
  });
}
async function askFix() {
  pushMsg("你", "帮我看看为什么崩了", true);
  const typing = showTyping();
  const r = await api("/api/autofix?version=" + encodeURIComponent(state.chosen || ""));
  typing.remove();
  if (!r.ok) { pushMsg("小助手", "检查失败：" + r.error); return; }
  let text = (r.hits || []).length ? "看日志像是：" + r.hits.join("；") : "日志里没看到典型崩溃原因。";
  if ((r.actions || []).length) {
    text += " 我顺手做了：" + r.actions.map((a) => a.do).join("；") + "。";
  } else {
    text += " 没有能自动修的地方，要不要把日志发我看看。";
  }
  pushMsg("小助手", text);
  toast("崩溃检查完成");
}
$("#fixBtn")?.addEventListener("click", askFix);
document.querySelectorAll(".chip[data-q]").forEach(function (chip) {
  chip.addEventListener("click", function () {
    const box = document.getElementById("askInput");
    if (!box) return;
    box.value = chip.getAttribute("data-q");
    ask();
  });
});

$("#askBtn")?.addEventListener("click", ask);
$("#askInput")?.addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });
$("#askClose")?.addEventListener("click", () => $("#askResults").classList.add("hidden"));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") $("#askResults").classList.add("hidden");
});

function renderSettings() {
  const c = state.cfg || {};
  $("#setIsolation").value = c.isolation || "隔离所有版本";
  $("#setWinSize").value = c.win_size || "默认";
  $("#setWinTitle").value = c.window_title || "";
  $("#setCustomInfo").value = c.custom_info || "长征启动器";
  $("#setPriority").value = c.priority || "高";
  $("#setJvm").value = c.jvm_args || "";
  $("#setDlSource").value = c.download_source || "优先官方，慢时换镜像";
  $("#setThreads").value = c.threads || 8;
  $("#setSpeed").value = c.speed_limit || 0;
  $("#setSkin").value = c.skin || "随机";
  $("#setChinese").checked = c.auto_chinese !== false;
  $("#setJava").value = c.java_path || "";
  $("#setClientId").value = c.client_id || "";
  $("#setCf").value = c.curseforge_key || "";
  if ($("#setUpdateUrl")) $("#setUpdateUrl").value = c.update_url || "";
  if ($("#verLabel")) $("#verLabel").textContent = state.version || "-";
  if ($("#setDeepseek")) $("#setDeepseek").value = c.deepseek_key || "";
  if (c.auto_memory) $("#memAuto").checked = true; else $("#memCustom").checked = true;
  $("#ramRange").value = c.ram_mb || 4096;
  $("#ramVal").textContent = (c.ram_mb || 4096) + " MB";
}
$("#ramRange")?.addEventListener("input", () => { $("#ramVal").textContent = $("#ramRange").value + " MB"; });
$("#saveBtn")?.addEventListener("click", async () => {
  const body = {
    theme: state.cfg.theme || "red",
    ram_mb: Number($("#ramRange").value),
    auto_memory: $("#memAuto").checked,
    isolation: $("#setIsolation").value,
    win_size: $("#setWinSize").value,
    window_title: $("#setWinTitle").value,
    custom_info: $("#setCustomInfo").value,
    priority: $("#setPriority").value,
    jvm_args: $("#setJvm").value,
    download_source: $("#setDlSource").value,
    threads: Number($("#setThreads").value) || 8,
    speed_limit: Number($("#setSpeed").value) || 0,
    skin: $("#setSkin").value,
    auto_chinese: $("#setChinese").checked,
    java_path: $("#setJava").value,
    client_id: $("#setClientId").value,
    curseforge_key: $("#setCf").value,
    update_url: $("#setUpdateUrl") ? $("#setUpdateUrl").value : "",
    deepseek_key: $("#setDeepseek") ? $("#setDeepseek").value : "",
  };
  const r = await api("/api/config", body);
  state.cfg = r.config;
  toast("设置已保存");
});

function toolModal(title, html) {
  $("#toolTitle").textContent = title;
  $("#toolBody").innerHTML = html;
  $("#toolModal").classList.remove("hidden");
}
$("#toolClose")?.addEventListener("click", () => $("#toolModal").classList.add("hidden"));

$("#modsBtn")?.addEventListener("click", openMods);
$("#healthBtn")?.addEventListener("click", async () => {
  toolModal("环境体检", '<p class="tiny">正在检查…</p>');
  const r = await api("/api/health");
  if (!r.ok) { toolModal("环境体检", '<p class="tiny">出错了：' + r.error + "</p>"); return; }
  const rows = (r.items || []).map((i) =>
    '<div class="health-row"><span class="' + (i.ok ? "ok" : "bad") + '">' + (i.ok ? "✓" : "✗") +
    "</span><b>" + i.k + "</b><span class=\"hv\">" + i.v + "</span>" +
    (i.tip ? '<div class="tiny tip">' + i.tip + "</div>" : "") + "</div>").join("");
  toolModal("环境体检", rows);
});

$("#modscanBtn")?.addEventListener("click", async () => {
  toolModal("mod 体检", '<p class="tiny">正在算哈希、对 Modrinth…（mod 多要等十几秒）</p>');
  const r = await api("/api/modscan?version=" + encodeURIComponent(state.chosen || ""));
  if (!r.ok) { toolModal("mod 体检", '<p class="tiny">' + (r.error || "出错了") + "</p>"); return; }
  let html = '<p>共 <b>' + r.total + "</b> 个 jar，识别出 <b>" + (r.matched || []).length + "</b> 个，";
  html += "重复 " + ((r.duplicates || []).length) + " 组，可更新 <b>" + ((r.updatable || []).length) + "</b> 个。</p>";
  if ((r.duplicates || []).length) {
    html += "<h4>重复的</h4>" + r.duplicates.map((g) => "<div class=\"line\">" + g.join(" / ") + "</div>").join("");
  }
  if ((r.updatable || []).length) {
    html += "<h4>可以更新</h4>" + r.updatable.map((i) =>
      "<div class=\"line\">" + i.jar + "：" + i.version + " → " + i.latest + "</div>").join("");
  } else {
    html += '<p class="tiny">没有发现需要更新的。</p>';
  }
  toolModal("mod 体检", html);
});

$("#crashBtn")?.addEventListener("click", async () => {
  toolModal("崩溃分析", '<p class="tiny">正在读日志…</p>');
  const r = await api("/api/crash?version=" + encodeURIComponent(state.chosen || ""));
  if (!r.ok) { toolModal("崩溃分析", '<p class="tiny">' + (r.error || "没日志") + "</p>"); return; }
  let html = '<p class="tiny">来源：' + r.source + "</p>";
  if ((r.hits || []).length) {
    html += "<h4>判断</h4>" + r.hits.map((h) => '<div class="line">· ' + h + "</div>").join("");
  } else {
    html += '<p class="tiny">没匹配到常见的崩溃原因，下面是原始信息：</p>';
  }
  if ((r.causes || []).length) {
    html += "<h4>日志里的异常</h4>" + r.causes.map((c) => '<div class="line mono">' + c + "</div>").join("");
  }
  toolModal("崩溃分析", html);
});

$("#reloadBtn")?.addEventListener("click", () => location.reload(true));
$("#checkUpdateBtn")?.addEventListener("click", async () => {
  const url = $("#setUpdateUrl").value.trim();
  await api("/api/config", { update_url: url });
  const r = await api("/api/check_update");
  if (!r.ok) { toast("检查失败：" + r.error); return; }
  if (!r.newer) { toast("已经是最新版（" + r.current + "）", 4000); return; }
  toast("有新版本 " + r.latest + "，开始下载…", 4000);
  if (r.url) {
    await api("/api/download_update", { url: r.url });
    const t0 = Date.now();
    while (Date.now() - t0 < 600000) {
      await new Promise((res) => setTimeout(res, 3000));
      const pg = await api("/api/progress");
      const msg = pg.progress || "";
      if (msg.indexOf("下好了") >= 0) {
        const ap = await api("/api/update/apply", {});
        if (ap.ok) {
          toast("更新包下好了，运行「应用更新.bat」就会替换并重启", 8000);
          await api("/api/reveal", { path: ap.bat });
        } else {
          toast("更新包装好了，在 updates 文件夹里手动覆盖", 6000);
        }
        return;
      }
      if (msg.indexOf("失败") >= 0) { toast(msg, 6000); return; }
    }
    toast("下载太慢了，可以稍后在设置里再试", 5000);
  } else {
    toast("有新版但没给下载地址：" + (r.notes || ""), 6000);
  }
});

$("#exportBtn")?.addEventListener("click", () => {
  $("#exportWho").textContent = "当前版本：" + (state.chosen || "未选择");
  $("#exportModal").classList.remove("hidden");
});
$("#expClose")?.addEventListener("click", () => $("#exportModal").classList.add("hidden"));
$("#expGo")?.addEventListener("click", async () => {
  const body = {
    version: state.chosen,
    include_game: $("#expGame").checked,
    include_launcher: $("#expLauncher").checked,
    name: $("#expName").value.trim() || "长征整合包",
  };
  $("#exportModal").classList.add("hidden");
  toast("开始导出…");
  const r = await api("/api/export", body);
  if (r.ok) {
    setTimeout(async () => {
      await api("/api/reveal", { path: r.path });
    }, 1200);
  } else {
    toast("导出失败：" + r.error);
  }
});
$("#shareBtn")?.addEventListener("click", async () => {
  toast("正在打包分享版…");
  const r = await api("/api/share", {});
  if (r.ok) {
    setTimeout(async () => { await api("/api/reveal", { path: r.path }); }, 1200);
  }
});

$("#playBtn")?.addEventListener("click", async () => {
  const r = await api("/api/launch", { version: state.chosen });
  toast(r.ok ? "已启动" : "启动失败：" + r.error);
});
$("#offlineBtn")?.addEventListener("click", async () => {
  const name = prompt("离线账号名字", "Player");
  if (!name) return;
  await api("/api/offline", { name });
  applyProfile({ name: name, user_type: "legacy" });
  toast("离线账号：" + name);
});
$("#loginBtn")?.addEventListener("click", async () => {
  const r = await api("/api/login/start");
  if (!r.ok) { toast("取设备码失败：" + r.error); return; }
  $("#loginUrl").textContent = r.url; $("#loginUrl").href = r.url;
  $("#loginCode").textContent = r.code; $("#loginState").textContent = "等待确认…";
  $("#loginModal").classList.remove("hidden");
  const timer = setInterval(async () => {
    const p = await api("/api/login/poll?device=" + encodeURIComponent(r.device));
    if (p.status === "ok") {
      clearInterval(timer);
      $("#loginState").textContent = "登录成功：" + p.name;
      applyProfile({ name: p.name, user_type: "msa" });
      setTimeout(() => $("#loginModal").classList.add("hidden"), 1200);
    }
  }, 3000);
});
$("#loginClose")?.addEventListener("click", () => $("#loginModal").classList.add("hidden"));

if (location.search.indexOf("mods") >= 0) {
  setTimeout(() => { if (window.openMods) openMods(); }, 1200);
}
boot();
