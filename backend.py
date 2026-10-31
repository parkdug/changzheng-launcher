"""backend — 只跑本地服务，不开窗口；给 Electron 外壳用。"""

import threading

import os
import sys

import server

try:
    import selfupdate
    selfupdate.cleanup_mei(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__)))
    if selfupdate.apply_pending(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))):
        try:
            server.VERSION = server._read_version()
        except Exception:
            pass
except Exception:
    pass


def main():
    threading.Thread(target=server.auto_update_worker, args=(True,), daemon=True).start()
    server.main(False)


def apply_update_mode():
    """Electron 版专用：等老进程退出→覆盖→重新拉起外壳。"""
    import subprocess
    import time
    base = os.environ.get("CZ_BASE") or os.path.dirname(sys.executable)
    time.sleep(5)
    try:
        import selfupdate
        selfupdate.apply_pending(base)
    except Exception:
        pass
    electron = os.path.join(base, "electron", "node_modules", "electron", "dist", "electron.exe")
    exe = os.path.join(base, "长征启动器.exe")
    try:
        if os.path.isfile(exe):
            subprocess.Popen([exe], cwd=base, close_fds=True, creationflags=0x08000000)
        elif os.path.isfile(electron):
            subprocess.Popen([electron, os.path.join(base, "electron")], cwd=base,
                             close_fds=True, creationflags=0x08000000)
    except Exception:
        pass


if __name__ == "__main__":
    if "--apply-update" in sys.argv:
        apply_update_mode()
        raise SystemExit(0)
    main()
