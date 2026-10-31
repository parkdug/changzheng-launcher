"""push_api — 不走 git，直接用 GitHub API 把整个目录推上去。

用法：set GH_TOKEN=xxx && python push_api.py <user> <repo>
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
TOKEN = os.environ.get("GH_TOKEN") or ""
ROOT = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {".git", "__pycache__", "node_modules", "dist", "build", "uploads", "exports", "my-mods"}
SKIP_FILES = {"translations.json", "client-errors.log", "app.log"}


def api(method, path, payload=None):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(payload).encode() if payload is not None else None)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "changzheng-publisher")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(body) if body.strip()[:1] in ("{", "[") else body)
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def collect():
    files = []
    for base, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            if name in SKIP_FILES:
                continue
            full = os.path.join(base, name)
            rel = os.path.relpath(full, ROOT).replace("\\", "/")
            files.append((rel, full))
    return files


def main():
    if not TOKEN:
        print("缺 GH_TOKEN")
        return 1
    user = sys.argv[1]
    repo = sys.argv[2]

    files = collect()
    print("要推 %d 个文件" % len(files))

    for rel, full in files:
        with open(full, "rb") as handle:
            data = handle.read()
        payload = {"message": "add " + rel,
                   "content": base64.b64encode(data).decode(), "branch": "main"}
        status, out = api("PUT", "/repos/%s/%s/contents/%s" % (user, repo, rel), payload)
        if status not in (200, 201):
            # 仓库还没 main 分支时，第一个文件不带 branch 建分支
            payload.pop("branch", None)
            status, out = api("PUT", "/repos/%s/%s/contents/%s" % (user, repo, rel), payload)
        print(rel, status)
        if status not in (200, 201):
            print("失败：", out)
            return 1
    print("仓库地址：https://github.com/%s/%s" % (user, repo))
    return 0 if status in (200, 201) else 1


if __name__ == "__main__":
    sys.exit(main())
