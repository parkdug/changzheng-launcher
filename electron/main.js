// 长征启动器 · Electron 外壳
// 起后端（长征引擎.exe）→ 等端口 → 开原生窗口；关窗口时把后端一起收掉。

const { app, BrowserWindow, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const net = require("net");
const fs = require("fs");

const ROOT = path.resolve(__dirname, "..");
const ENGINE = path.join(ROOT, "长征引擎.exe");
const PORT = 8765;
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

function waitPort(port, timeout) {
  const deadline = Date.now() + (timeout || 25000);
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

function startEngine() {
  log("engine=" + ENGINE + " exists=" + fs.existsSync(ENGINE));
  if (!fs.existsSync(ENGINE)) return;
  try {
    engine = spawn(ENGINE, [], { cwd: ROOT, windowsHide: true });
    log("spawn pid=" + engine.pid);
    engine.on("error", function (e) { log("spawn error " + e.message); });
    engine.on("exit", function (code) { log("engine exit " + code); engine = null; });
  } catch (e) {
    log("spawn throw " + e.message);
  }
}

function stopEngine() {
  if (engine) {
    try { engine.kill(); } catch (e) {}
    engine = null;
  }
}

app.whenReady().then(async function () {
  startEngine();
  const ok = await waitPort(PORT);
  log("port ready=" + ok);
  if (!ok) { app.quit(); return; }
  const win = new BrowserWindow({
    width: 1120,
    height: 760,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: "#F7EFE9",
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
  await win.loadURL("http://127.0.0.1:" + PORT + "/?t=" + Date.now());
});

app.on("window-all-closed", function () { stopEngine(); app.quit(); });
app.on("before-quit", stopEngine);
