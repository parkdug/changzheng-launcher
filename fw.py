"""fw — 开放 25565 防火墙：能直接加就加，没权限就写个 bat 让人右键以管理员运行。"""

import os
import subprocess
import sys

FLAGS = 0x08000000 if sys.platform == "win32" else 0

BAT_LINES = [
    "@echo off",
    "chcp 65001 >nul",
    "echo 正在开放 25565 ...",
    "netsh advfirewall firewall add rule name=ChangzhengMC dir=in action=allow protocol=TCP localport=25565",
    "netsh advfirewall firewall add rule name=ChangzhengMC-UDP dir=in action=allow protocol=UDP localport=25565",
    "echo 好了，按任意键关闭",
    "pause",
]


def _run(cmd):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", creationflags=FLAGS)
        return proc.returncode == 0, (proc.stdout or proc.stderr or "").strip()[:120]
    except Exception as error:
        return False, str(error)[:120]


def open_port(base):
    results = []
    for proto in ("TCP", "UDP"):
        ok, out = _run(["netsh", "advfirewall", "firewall", "add", "rule",
                        "name=ChangzhengMC-%s" % proto, "dir=in", "action=allow",
                        "protocol=%s" % proto, "localport=25565"])
        results.append({"proto": proto, "ok": ok, "out": out})
    ok_all = all(r["ok"] for r in results)
    bat = ""
    if not ok_all:
        try:
            bat = os.path.join(base, "开放防火墙.bat")
            with open(bat, "w", encoding="utf-8", newline="\r\n") as handle:
                handle.write("\n".join(BAT_LINES))
        except Exception:
            bat = ""
    return {"ok": ok_all, "results": results, "bat": bat}
