"""pack_tools — 导出整合包（给小助手一句话调用）。"""

import json
import os
import zipfile


def export_bundle(mc_dir, version_id, mc_version, loader, out_dir, name="长征整合包",
                  include_game=True, include_launcher=True, cfg=None):
    ver_dir = os.path.join(mc_dir, "versions", version_id)
    if not os.path.isdir(ver_dir):
        raise RuntimeError("找不到版本目录")
    os.makedirs(out_dir, exist_ok=True)
    safe = "".join(ch for ch in name if ch not in '\\/:*?"<>|') or "长征整合包"
    target = os.path.join(out_dir, safe + ".zip")
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        mods = os.path.join(ver_dir, "mods")
        if os.path.isdir(mods):
            for name_ in os.listdir(mods):
                if name_.endswith(".jar"):
                    zf.write(os.path.join(mods, name_), "mods/" + name_)
                    count += 1
        if include_game:
            for item in ("options.txt", "optionsof.txt", "servers.dat", "config",
                         "shaderpacks", "resourcepacks", "defaultconfigs", "kubejs"):
                src = os.path.join(ver_dir, item)
                if os.path.isfile(src):
                    zf.write(src, item)
                elif os.path.isdir(src):
                    for base, _dirs, files in os.walk(src):
                        for f in files:
                            full = os.path.join(base, f)
                            zf.write(full, os.path.relpath(full, ver_dir))
        manifest = {
            "name": name, "version": version_id, "mc": mc_version, "loader": loader,
            "mods": count, "include_game": include_game,
            "include_launcher": include_launcher, "made_by": "长征启动器",
        }
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        if include_launcher and cfg:
            keep = {k: cfg.get(k) for k in ("ram_mb", "jvm_args", "theme", "isolation",
                                            "win_size", "window_title", "priority")}
            zf.writestr("launcher.json", json.dumps(keep, ensure_ascii=False, indent=2))
    return target, count
