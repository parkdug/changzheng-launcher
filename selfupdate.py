"""selfupdate — 把 updates/new 里的新文件在启动时覆盖进来（此时没有文件被占用）。"""

import os
import shutil


def apply_pending(base):
    stage = os.path.join(base, "updates", "new")
    if not os.path.isdir(stage):
        return False
    moved = 0
    for root, _dirs, files in os.walk(stage):
        for name in files:
            src = os.path.join(root, name)
            rel = os.path.relpath(src, stage)
            dst = os.path.join(base, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                shutil.copyfile(src, dst)
                moved += 1
            except Exception:
                pass
    shutil.rmtree(stage, ignore_errors=True)
    for leftover in ("changzheng-launcher.zip", "自动更新.bat", "应用更新.bat"):
        try:
            os.remove(os.path.join(base, "updates", leftover))
        except Exception:
            pass
    return moved > 0
