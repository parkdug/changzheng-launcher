"""main — 纯应用窗口：本地服务 + WebView2 原生窗口（不是浏览器）。

pythonnet 在这台机器上要走 coreclr，所以先把环境变量设好再 import webview。
"""

import os
import socket
import sys
import threading
import time

# 必须在 import webview 之前设好
os.environ.setdefault("PYTHONNET_RUNTIME", "coreclr")
os.environ.setdefault("DOTNET_ROOT", r"C:\Program Files\dotnet")

import server  # noqa: E402


def wait_port(port, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.5):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def open_edge_app(url):
    import subprocess

    for path in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if os.path.isfile(path):
            profile = os.path.join(os.path.expanduser("~"), ".changzheng-launcher-window")
            subprocess.Popen([path, "--app=%s" % url, "--window-size=1120,760",
                              "--user-data-dir=%s" % profile, "--no-first-run"],
                             creationflags=0x08000000)
            return True
    return False


def run_window(url):
    """优先用 WebView2 原生窗口；失败再退 Edge 应用模式。"""
    try:
        import webview

        webview.create_window("长征启动器", url, width=1120, height=760,
                              min_size=(900, 600), background_color="#F7EFE9")
        webview.start()
        return True
    except Exception as error:
        print("WebView2 窗口没起来：%s" % error, flush=True)
        return open_edge_app(url)


def main():
    threading.Thread(target=lambda: server.main(False), daemon=True).start()
    url = "http://127.0.0.1:%d/" % server.PORT
    wait_port(server.PORT)
    if not run_window(url):
        import webbrowser
        webbrowser.open(url)
        while True:
            time.sleep(3600)


if __name__ == "__main__":
    main()
