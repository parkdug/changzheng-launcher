// mod 管理：多选 / 全选 / 搜索 / 排序 / 批量操作
const modState = { items: [], selected: new Set(), filter: "", dir: "", sort: "name", desc: false };

async function openMods() {
  modState.selected = new Set();
  modState.filter = "";
  modState.sort = "name";
  modState.desc = false;
  toolModal("mod 管理", '<p class="tiny">正在读…</p>');
  await reloadMods();
}

async function reloadMods() {
  const r = await api("/api/mods?version=" + encodeURIComponent(state.chosen || ""));
  if (!r.ok) { toolModal("mod 管理", '<p class="tiny">' + (r.error || "打不开") + "</p>"); return; }
  modState.items = r.items || [];
  modState.dir = r.dir || "";
  renderMods();
}

function modsSorted(list) {
  const key = modState.sort;
  const dir = modState.desc ? -1 : 1;
  return list.slice().sort((a, b) => {
    if (key === "size") return (a.size - b.size) * dir;
    if (key === "mtime") return ((a.mtime || 0) - (b.mtime || 0)) * dir;
    if (key === "state") return ((a.enabled === b.enabled) ? 0 : (a.enabled ? -1 : 1)) * dir;
    return a.file.localeCompare(b.file) * dir;
  });
}

function renderMods() {
  const all = modState.items;
  if (!all.length) {
    toolModal("mod 管理", '<div class="mm-empty">这个版本还没装 mod。去下载页挑几个吧。</div>');
    return;
  }
  const q = modState.filter.trim().toLowerCase();
  const filtered = q ? all.filter((i) => i.file.toLowerCase().includes(q)) : all;
  const list = modsSorted(filtered);
  const onCount = all.filter((i) => i.enabled).length;

  const head = '<div class="mm-top">' +
    '<div class="mm-sum"><b>' + all.length + "</b> 个模组<span>启用 " + onCount +
    " · 停用 " + (all.length - onCount) + " · 已选 " + modState.selected.size + "</span></div>" +
    '<label class="mm-check"><input type="checkbox" id="mmAll">全选</label>' +
    '<input id="mmSearch" class="mm-search" placeholder="搜文件名…" value="' + escapeAttr(modState.filter) + '">' +
    '<select id="mmSort" class="mm-select">' +
    '<option value="name">按名称</option><option value="mtime">按时间</option>' +
    '<option value="size">按大小</option><option value="state">按状态</option></select>' +
    '<button class="btn tiny" id="mmDir">' + (modState.desc ? "倒序 ↓" : "正序 ↑") + "</button>" +
    "</div>";

  const bar = '<div class="mm-actions">' +
    '<button class="btn tiny" data-batch="enable">启用所选</button>' +
    '<button class="btn tiny" data-batch="disable">停用所选</button>' +
    '<button class="btn tiny danger" data-batch="delete">删除所选</button>' +
    '<span class="mm-dir" title="' + escapeAttr(modState.dir) + '">' + modState.dir + "</span></div>";

  const rows = list.map((it) => {
    const picked = modState.selected.has(it.file);
    const when = it.mtime ? new Date(it.mtime * 1000).toLocaleDateString() : "-";
    return '<tr class="' + (picked ? "picked" : "") + '">' +
      '<td class="c-check"><input type="checkbox" class="mm-pick" data-file="' + escapeAttr(it.file) + '"' +
      (picked ? " checked" : "") + "></td>" +
      '<td><span class="pill ' + (it.enabled ? "on" : "off") + '">' + (it.enabled ? "启用" : "停用") + "</span></td>" +
      '<td class="c-name" title="' + escapeAttr(it.file) + '">' + it.file + "</td>" +
      '<td class="c-size">' + Math.round(it.size / 1024) + " KB</td>" +
      '<td class="c-when">' + when + "</td>" +
      '<td class="c-act"><button class="btn tiny" data-act="toggle" data-file="' + escapeAttr(it.file) + '">' +
      (it.enabled ? "停用" : "启用") + "</button>" +
      '<button class="btn tiny danger" data-act="del" data-file="' + escapeAttr(it.file) + '">删</button></td>' +
      "</tr>";
  }).join("");

  const table = '<div class="mm-table-wrap"><table class="mm-table"><thead><tr>' +
    "<th></th><th>状态</th><th>文件名</th><th>大小</th><th>时间</th><th>操作</th>" +
    "</tr></thead><tbody>" + rows + "</tbody></table></div>" +
    (list.length ? "" : '<div class="mm-empty">没有匹配的。</div>');

  toolModal("mod 管理 · " + (state.chosen || ""), head + bar + table);
  document.getElementById("toolModal")?.classList.add("mods-mode");

  const allBox = document.getElementById("mmAll");
  if (allBox) {
    allBox.checked = list.length > 0 && list.every((i) => modState.selected.has(i.file));
    allBox.addEventListener("change", () => {
      if (allBox.checked) list.forEach((i) => modState.selected.add(i.file));
      else list.forEach((i) => modState.selected.delete(i.file));
      renderMods();
    });
  }
  const search = document.getElementById("mmSearch");
  if (search) {
    search.addEventListener("input", () => { modState.filter = search.value; renderMods(); });
  }
  const sort = document.getElementById("mmSort");
  if (sort) {
    sort.value = modState.sort;
    sort.addEventListener("change", () => { modState.sort = sort.value; renderMods(); });
  }
  document.getElementById("mmDir")?.addEventListener("click", () => {
    modState.desc = !modState.desc; renderMods();
  });
  document.querySelectorAll("#toolBody .mm-pick").forEach((box) => box.addEventListener("change", () => {
    const file = box.getAttribute("data-file");
    if (box.checked) modState.selected.add(file); else modState.selected.delete(file);
    renderMods();
  }));
  document.querySelectorAll("#toolBody [data-act]").forEach((btn) => btn.addEventListener("click", async () => {
    const file = btn.getAttribute("data-file");
    if (btn.getAttribute("data-act") === "toggle") {
      await api("/api/mods/toggle", { version: state.chosen, file: file });
    } else {
      if (!confirm("删掉 " + file + "？会移到 mods-trash")) return;
      await api("/api/mods/delete", { version: state.chosen, file: file });
    }
    await reloadMods();
  }));
  document.querySelectorAll("#toolBody [data-batch]").forEach((btn) => btn.addEventListener("click", async () => {
    const action = btn.getAttribute("data-batch");
    const files = Array.from(modState.selected);
    if (!files.length) { toast("先勾几个 mod"); return; }
    if (action === "delete" && !confirm("删掉选中的 " + files.length + " 个？会移到 mods-trash")) return;
    const r = await api("/api/mods/batch", { version: state.chosen, files: files, action: action });
    if (r.ok) toast("处理了 " + r.done + " 个" + (r.failed && r.failed.length ? "，失败 " + r.failed.length : ""));
    modState.selected = new Set();
    await reloadMods();
  }));
}

function escapeAttr(text) {
  return String(text).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
