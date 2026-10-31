// 长征启动器 · Electron 外壳（真正的桌面应用，不是浏览器）
// 起后端 → 等端口 → 开窗口；后端没起来就显示本地引导页，能重试。

const { app, BrowserWindow, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const net = require("net");
const fs = require("fs");

const ROOT = path.resolve(__dirname, "..");
const ENGINE = path.join(ROOT, "长征引擎.exe");
const PORT_FILE = path.join(ROOT, "port.txt");
const BOOT = path.join(ROOT, "web", "boot.html");
const LOG = path.join(__dirname, "app.log");

function log(msg) {
  try {
    fs.appendFileSync(LOG, "[" + new Date().toISOString() + "] " + msg + "\r\n");
  } catch (e) {}
}

try {
  app.setPath("userData", path.join(ROOT, ".userdata"));
} catch (e) {}

let engine = null;
let win = null;

function waitPort(port, timeout) {
  const deadline = Date.now() + (timeout || 20000);
  return new Promise(function (resolve) {
    const tick = function () {
      const sock = net.connect(port, "127.0.0.1");
      sock.once("connect", function () { sock.destroy(); resolve(true); });
      sock.once("error", function () {
        sock.destroy();
        if (Date.now() > deadline) resolve(false);
        else setTimeout(tick, 250);
      });
    };
    tick();
  });
}

function readPort() {
  try {
    const n = parseInt(fs.readFileSync(PORT_FILE, "utf8").trim(), 10);
    if (n > 0) return n;
  } catch (e) {}
  return 8765;
}

function startEngine() {
  if (!fs.existsSync(ENGINE)) {
    log("引擎不存在: " + ENGINE);
    return;
  }
  try {
    engine = spawn(ENGINE, [], { cwd: ROOT, windowsHide: true, detached: false });
    log("引擎启动 pid=" + engine.pid);
    engine.on("exit", function (code) { log("引擎退出 " + code); engine = null; });
  } catch (e) {
    log("引擎起不来: " + e.message);
  }
}

function stopEngine() {
  if (engine) {
    try { engine.kill(); } catch (e) {}
    engine = null;
  }
}

function openBoot() {
  if (win && fs.existsSync(BOOT)) {
    win.loadFile(BOOT, { query: { port: String(readPort()) } });
    return true;
  }
  return false;
}

app.whenReady().then(async function () {
  startEngine();
  let port = 8765;
  let ok = false;
  for (let i = 0; i < 80; i++) {
    port = readPort();
    ok = await waitPort(port, 400);
    if (ok) break;
  }
  log("端口就绪=" + ok + " port=" + port);

  win = new BrowserWindow({
    width: 1180,
    height: 780,
    minWidth: 940,
    minHeight: 620,
    backgroundColor: "#FBF3ED",
    title: "长征启动器",
    autoHideMenuBar: true,
    icon: path.join(ROOT, "icon.ico"),
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  });
  win.setMenuBarVisibility(false);

  win.webContents.setWindowOpenHandler(function (info) {
    shell.openExternal(info.url);
    return { action: "deny" };
  });

  win.webContents.on("did-fail-load", function () {
    log("加载失败，切到引导页");
    setTimeout(openBoot, 300);
  });

  if (ok) {
    win.loadURL("http://127.0.0.1:" + port + "/");
  } else {
    openBoot();
  }
});

app.on("window-all-closed", function () { stopEngine(); app.quit(); });
app.on("before-quit", stopEngine);
