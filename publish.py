"""publish — 用 token 建仓库、推代码、发 Release。

用法：
    set GH_TOKEN=ghp_xxx
    python publish.py [仓库名] [--zip 打包文件]
"""

import json
import os
import subprocess
import sys
import urllib.request

API = "https://api.github.com"
TOKEN = os.environ.get("GH_TOKEN") or ""
REPO_DIR = os.path.dirname(os.path.abspath(__file__))


def api(method, path, payload=None, raw=None, ctype="application/json"):
    url = API + path
    data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "changzheng-publisher")
    if data is not None:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(body) if body.strip().startswith(("{", "[")) else body)
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def main():
    if not TOKEN:
        print("先把 GH_TOKEN 设上")
        return 1
    name = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "changzheng-launcher"

    status, me = api("GET", "/user")
    if status != 200:
        print("token 无效：", me)
        return 1
    user = me["login"]
    print("登录为", user)

    status, repo = api("GET", "/repos/%s/%s" % (user, name))
    if status == 404:
        status, repo = api("POST", "/user/repos", {
            "name": name,
            "description": "长征启动器 — 一个能自己修自己的 Minecraft 启动器",
            "private": False,
            "has_issues": True,
            "has_wiki": False,
        })
        print("建仓库：", status)
        if status not in (200, 201):
            print(repo)
            return 1
    else:
        print("仓库已存在")

    remote = "https://%s@github.com/%s/%s.git" % (TOKEN, user, name)
    for cmd in (["git", "remote", "remove", "origin"],):
        subprocess.run(cmd, cwd=REPO_DIR, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", remote], cwd=REPO_DIR, check=True)
    subprocess.run(["git", "push", "-u", "origin", "HEAD:main", "--force"], cwd=REPO_DIR, check=True)
    print("代码推上去了：https://github.com/%s/%s" % (user, name))

    zip_path = None
    if "--zip" in sys.argv:
        zip_path = sys.argv[sys.argv.index("--zip") + 1]

    status, rel = api("POST", "/repos/%s/%s/releases" % (user, name), {
        "tag_name": "v1.0.0",
        "name": "长征启动器 1.0.0",
        "body": "第一个公开版本：版本安装、模组中文名、崩溃自动修复、三步开服、整合包导入导出。",
    })
    if status in (200, 201) and zip_path and os.path.isfile(zip_path):
        with open(zip_path, "rb") as handle:
            data = handle.read()
        status2, info = api(
            "POST",
            "/repos/%s/%s/releases/%s/assets?name=%s" % (user, name, rel["id"], os.path.basename(zip_path)),
            raw=data, ctype="application/zip")
        print("发布包：", status2)
    print("Release:", rel.get("html_url") if isinstance(rel, dict) else rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
