"""backend — 只跑本地服务，不开窗口；给 Electron 外壳用。"""

import server

if __name__ == "__main__":
    server.main(False)
