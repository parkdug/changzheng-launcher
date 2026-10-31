"""publish_app — 把 Electron 版打成 zip，按 60MB 分卷上传到 Gitee（单文件不超 100MB）。

用法：set GITEE_TOKEN=xxx && python publish_app.py 1.2.1
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile

TOKEN = os.environ.get("GITEE_TOKEN") or ""
OWNER, REPO = "parkty", "changzheng-launcher"
ROOT = r"D:\长征启动器"
OUT = r"D:\DSH work\changzheng-app.zip"
PART_MB = 60
TAG = "app-latest"


def api(method, path, payload=None, raw=None, ctype="application/json"):
    url = "https://gitee.com/api/v5" + path
    data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("User-Agent", "cz")
    if data is not None:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(body) if body.strip()[:1] in "{[" else body)
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")[:200]


def build_zip():
    files = []
    electron = os.path.join(ROOT, "electron")
    dist = os.path.join(electron, "node_modules", "electron", "dist")
    for base, _d, fs in os.walk(dist):
        for f in fs:
            full = os.path.join(base, f)
            files.append((full, "electron/" + os.path.relpath(full, dist).replace("\\", "/")))
    for name in ("main.js", "package.json"):
        p = os.path.join(electron, name)
        if os.path.isfile(p):
            files.append((p, "electron/" + name))
    engine = os.path.join(ROOT, "长征引擎")
    for base, _d, fs in os.walk(engine):
        for f in fs:
            full = os.path.join(base, f)
            files.append((full, "长征引擎/" + os.path.relpath(full, engine).replace("\\", "/")))
    ver_file = os.path.join(ROOT, "version.txt")
    files.append((ver_file, "version.txt")) if os.path.isfile(ver_file) else None
    icon = os.path.join(ROOT, "icon.ico")
    if os.path.isfile(icon):
        files.append((icon, "icon.ico"))
    web = os.path.join(ROOT, "web")
    for base, _d, fs in os.walk(web):
        for f in fs:
            full = os.path.join(base, f)
            files.append((full, "web/" + os.path.relpath(full, web).replace("\\", "/")))
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for full, rel in files:
            z.write(full, rel)
    return OUT


def split_zip(path, size_mb=PART_MB, version="x"):
    parts = []
    size = size_mb * 1024 * 1024
    idx = 1
    with open(path, "rb") as src:
        while True:
            chunk = src.read(size)
            if not chunk:
                break
            part = "%s-%s.%03d" % (path, version, idx)
            with open(part, "wb") as out:
                out.write(chunk)
            parts.append(part)
            idx += 1
    return parts


def ensure_release():
    st, rel = api("GET", "/repos/%s/%s/releases/tags/%s?access_token=%s" % (OWNER, REPO, TAG, TOKEN))
    if st != 200 or not isinstance(rel, dict):
        st, rel = api("POST", "/repos/%s/%s/releases" % (OWNER, REPO), {
            "access_token": TOKEN, "tag_name": TAG, "name": "长征启动器（最新版）",
            "body": "自动发布", "target_commitish": "main",
        })
    return rel


def upload(rel, path):
    boundary = "----cz" + os.urandom(6).hex()
    name = os.path.basename(path)
    data = open(path, "rb").read()
    body = b""
    for k, v in (("access_token", TOKEN),):
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, k, v)).encode()
    body += ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\nContent-Type: application/octet-stream\r\n\r\n" % (boundary, name)).encode()
    body += data
    body += ("\r\n--%s--" % boundary).encode()
    st, out = api("POST", "/repos/%s/%s/releases/%s/attach_files" % (OWNER, REPO, rel["id"]),
                  raw=body, ctype="multipart/form-data; boundary=" + boundary)
    return st, out


def main():
    if not TOKEN:
        print("缺 GITEE_TOKEN")
        return 1
    version = sys.argv[1] if len(sys.argv) > 1 else "1.2.1"
    print("打包…")
    with open(os.path.join(ROOT, "version.txt"), "w", encoding="utf-8") as fh:
        fh.write(version)
    path = build_zip()
    print("体积", round(os.path.getsize(path) / 1024 / 1024, 1), "MB")
    parts = split_zip(path, PART_MB, version)
    print("分卷", [os.path.basename(p) for p in parts])
    rel = ensure_release()
    if not isinstance(rel, dict):
        print("Release 拿不到", rel)
        return 1
    existing = {a.get("name") for a in (rel.get("assets") or rel.get("attach_files") or [])}
    urls = []
    for part in parts:
        name = os.path.basename(part)
        if name in existing:
            print("已存在，跳过", name)
        else:
            st, out = upload(rel, part)
            print("上传", name, st)
            if st not in (200, 201):
                print(str(out)[:200])
                return 1
        urls.append("https://gitee.com/%s/%s/releases/download/%s/%s" % (OWNER, REPO, TAG, name))
    manifest = {"version": version, "parts": urls, "size": os.path.getsize(path),
                "notes": "Electron 版，分卷下载后自动合并"}
    content = base64.b64encode(json.dumps(manifest, ensure_ascii=False, indent=2).encode()).decode()
    st, info = api("GET", "/repos/%s/%s/contents/version.json?ref=main&access_token=%s" % (OWNER, REPO, TOKEN))
    payload = {"access_token": TOKEN, "content": content, "message": "release " + version, "branch": "main"}
    if st == 200 and isinstance(info, dict):
        payload["sha"] = info.get("sha", "")
    st2, _ = api("PUT", "/repos/%s/%s/contents/version.json" % (OWNER, REPO), payload)
    print("version.json", st2)
    print("下载地址:", urls)
    return 0


if __name__ == "__main__":
    sys.exit(main())
