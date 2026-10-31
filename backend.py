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


if __name__ == "__main__":
    main()
