"""backend — 只跑本地服务，不开窗口；给 Electron 外壳用。"""

import threading

import server


def main():
    threading.Thread(target=server.auto_update_worker, args=(True,), daemon=True).start()
    server.main(False)


if __name__ == "__main__":
    main()
