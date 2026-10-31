// 项目详情：点卡片看介绍，按版本挑下载
let pjCurrent = null;

function pjEscape(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function mdToHtml(text) {
  let html = pjEscape(text || "");
  const lines = html.split(/\r?\n/);
  const out = lines.map(function (line) {
    if (/^#{1,3}\s+/.test(line)) return "<p><b>" + line.replace(/^#{1,3}\s+/, "") + "</b></p>";
    if (!line.trim()) return "";
    return "<p>" + line + "</p>";
  });
  html = out.join("");
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
  html = html.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  html = html.replace(/`([^`]+)`/g, "$1");
  return html || "<p class='tiny'>作者没写介绍。</p>";
}

async function openProject(id, type) {
  var tool = document.getElementById("toolModal");
  if (tool) tool.classList.add("hidden");
  var modal = document.getElementById("projectModal");
  if (!modal) return;
  modal.classList.remove("hidden");
  document.getElementById("pjTitle").textContent = "读取中…";
  document.getElementById("pjBody").innerHTML = "";
  document.getElementById("pjVersions").innerHTML = "";
  const r = await api("/api/project?id=" + encodeURIComponent(id));
  if (!r.ok) {
    document.getElementById("pjTitle").textContent = "打不开：" + r.error;
    return;
  }
  pjCurrent = { project: r.project, mc: r.mc, type: type || "mod" };
  renderProject();
}

function renderProject() {
  if (!pjCurrent) return;
  const p = pjCurrent.project;
  const icon = document.getElementById("pjIcon");
  if (icon) icon.src = p.icon || "";
  document.getElementById("pjTitle").textContent = p.title || "";
  document.getElementById("pjDesc").textContent = p.desc || "";
  document.getElementById("pjStats").textContent =
    (p.downloads || 0).toLocaleString() + " 次下载 · " +
    (p.followers || 0).toLocaleString() + " 关注 · 更新于 " + (p.updated || "未知");
  const tags = (p.categories || []).slice(0, 8).map(function (c) {
    return '<span class="pj-tag">' + pjEscape(c) + "</span>";
  }).concat((p.mc || []).slice(-6).map(function (v) {
    return '<span class="pj-tag">' + pjEscape(v) + "</span>";
  }));
  document.getElementById("pjTags").innerHTML = tags.join("");
  document.getElementById("pjBody").innerHTML = mdToHtml(p.body || p.desc || "");

  const onlyEl = document.getElementById("pjOnlyCompat");
  const only = onlyEl ? onlyEl.checked : true;
  const rows = (p.versions || []).filter(function (v) { return !only || v.compatible; });
  const box = document.getElementById("pjVersions");
  if (!rows.length) {
    box.innerHTML = '<p class="tiny">没有匹配当前版本的，取消勾选看看全部。</p>';
    return;
  }
  box.innerHTML = rows.map(function (v) {
    return '<div class="pj-row ' + (v.compatible ? "ok" : "no") + '">' +
      '<span class="nm">' + pjEscape(v.name || v.number) + "</span>" +
      '<span class="mc">' + pjEscape((v.mc || []).slice(-4).join(", ")) + "</span>" +
      '<span class="mc">' + pjEscape(v.date) + "</span>" +
      '<button class="btn tiny primary" data-url="' + pjEscape(v.url) + '" data-file="' +
      pjEscape(v.filename) + '">装这个</button></div>';
  }).join("");

  box.querySelectorAll("[data-url]").forEach(function (btn) {
    btn.addEventListener("click", async function () {
      const url = btn.getAttribute("data-url");
      if (!url) return;
      btn.disabled = true;
      btn.textContent = "下载中…";
      const r = await api("/api/mod/version", {
        version: state.chosen,
        url: url,
        filename: btn.getAttribute("data-file"),
        type: pjCurrent.type,
      });
      toast(r.ok ? "开始下载（看底部进度）" : "失败：" + r.error);
      setTimeout(function () { btn.disabled = false; btn.textContent = "装这个"; }, 2500);
    });
  });
}

document.addEventListener("DOMContentLoaded", function () {
  const close = document.getElementById("pjClose");
  if (close) close.addEventListener("click", function () {
    document.getElementById("projectModal").classList.add("hidden");
  });
  const only = document.getElementById("pjOnlyCompat");
  if (only) only.addEventListener("change", renderProject);
});

document.addEventListener("click", function (e) {
  const card = e.target.closest ? e.target.closest(".mod-card") : null;
  if (!card) return;
  if (e.target.closest("button")) return;
  const pid = card.getAttribute("data-pid");
  if (pid) openProject(pid, card.getAttribute("data-kind") || "mod");
});
