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
            base_abs = os.path.abspath(base)
            if not os.path.abspath(dst).startswith(base_abs + os.sep):
                continue
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


def cleanup_mei(base):
    """清掉上次残留的 _MEI 解包目录（exe 从 run 目录解包时留下的）。"""
    import shutil
    import sys
    areas = [os.path.join(base, "run"), os.path.join(base, "updates")]
    keep = getattr(sys, "_MEIPASS", "")
    removed = 0
    for area in areas:
        if not os.path.isdir(area):
            continue
        for name in os.listdir(area):
            full = os.path.join(area, name)
            if not os.path.isdir(full):
                continue
            if keep and os.path.abspath(full) in os.path.abspath(keep):
                continue
            try:
                shutil.rmtree(full, ignore_errors=True)
                removed += 1
            except Exception:
                pass
    return removed
