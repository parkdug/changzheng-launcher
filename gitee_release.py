"""gitee_release — 把更新包发到 Gitee，给国内用户走国内直链。

用法：
    set GITEE_TOKEN=xxxx
    python gitee_release.py            # 用已有仓库
    python gitee_release.py --create   # 没有仓库就先建一个

需要 token 权限：projects（读写仓库）。
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TOKEN = os.environ.get("GITEE_TOKEN") or ""
API = "https://gitee.com/api/v5"
REPO = os.environ.get("GITEE_REPO") or "changzheng-launcher"
ZIP = os.environ.get("GITEE_ZIP") or os.path.join(os.getcwd(), "changzheng-launcher.zip")


def api(method, path, payload=None, raw=None, ctype="application/json"):
    url = API + path
    data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("User-Agent", "changzheng-publisher")
    if data is not None:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(body) if body.strip()[:1] in ("{", "[") else body)
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")[:300]


def me():
    return api("GET", "/user?access_token=" + TOKEN)


def create_repo(name, private=False):
    return api("POST", "/user/repos", {
        "access_token": TOKEN, "name": name,
        "description": "长征启动器 更新包", "private": private,
        "has_issues": "false", "has_wiki": "false",
    })


def create_release(owner, repo, tag, name, body):
    return api("POST", "/repos/%s/%s/releases" % (owner, repo), {
        "access_token": TOKEN, "tag_name": tag, "name": name, "body": body,
        "target_commitish": "main",
    })


def upload_asset(owner, repo, release_id, path):
    boundary = "----changzheng" + os.urandom(8).hex()
    with open(path, "rb") as handle:
        data = handle.read()
    name = os.path.basename(path)
    parts = []
    parts.append(("--" + boundary).encode())
    parts.append(('Content-Disposition: form-data; name="access_token"').encode())
    parts.append(b"")
    parts.append(TOKEN.encode())
    parts.append(("--" + boundary).encode())
    parts.append(('Content-Disposition: form-data; name="file"; filename="%s"' % name).encode())
    parts.append(b"Content-Type: application/zip")
    parts.append(b"")
    parts.append(data)
    parts.append(("--" + boundary + "--").encode())
    payload = b"\r\n".join(parts)
    return api("POST", "/repos/%s/%s/releases/%s/attach_files" % (owner, repo, release_id),
               raw=payload, ctype="multipart/form-data; boundary=" + boundary)


def update_version_json(owner, repo, tag, filename, version):
    """把仓库里的 version.json 改成指向 Gitee 附件。"""
    path = "version.json"
    status, info = api("GET", "/repos/%s/%s/contents/%s?access_token=%s&ref=main"
                       % (owner, repo, path, TOKEN))
    payload = {
        "access_token": TOKEN,
        "content": __import__("base64").b64encode(
            json.dumps(version, ensure_ascii=False, indent=2).encode()).decode(),
        "message": "chore: 更新到 " + version.get("version", ""),
        "branch": "main",
    }
    if status == 200 and isinstance(info, dict):
        payload["sha"] = info.get("sha", "")
    return api("PUT", "/repos/%s/%s/contents/%s" % (owner, repo, path), payload)


def main():
    if not TOKEN:
        print("没配 GITEE_TOKEN，跳过 Gitee 发布")
        return 0
    status, info = me()
    if status != 200:
        print("token 不对：", info)
        return 1
    owner = info.get("login")
    print("登录为", owner)

    status, repo = api("GET", "/repos/%s/%s?access_token=%s" % (owner, REPO, TOKEN))
    if status == 404 and "--create" in sys.argv:
        status, repo = create_repo(REPO)
        print("建仓库：", status)
    if status != 200:
        print("仓库读不到，加 --create 试试：", str(repo)[:160])
        return 1

    tag = os.environ.get("GITEE_TAG") or "app-latest"
    status, rel = api("GET", "/repos/%s/%s/releases/tags/%s?access_token=%s" % (owner, REPO, tag, TOKEN))
    if status != 200 or not isinstance(rel, dict):
        status, rel = create_release(owner, REPO, tag, "长征启动器（最新构建）",
                                     "自动发布，跟着 GitHub 的最新构建走。")
        print("建 release:", status, str(rel)[:160])
    if not isinstance(rel, dict):
        print("Release 拿不到，跳过")
        return 0
    print("Release:", rel.get("html_url"))

    if os.path.isfile(ZIP):
        for asset in rel.get("assets") or []:
            if asset.get("name") == os.path.basename(ZIP):
                api("DELETE", "/repos/%s/%s/releases/%s/attach_files/%s?access_token=%s"
                    % (owner, REPO, rel["id"], asset["id"], TOKEN))
        status, asset = upload_asset(owner, REPO, rel["id"], ZIP)
        print("上传附件：", status)
        if status in (200, 201):
            print("下载地址：", asset.get("browser_download_url"))

    version = {
        "version": "1.1." + os.environ.get("BUILD_NUMBER", "0"),
        "download": "https://gitee.com/%s/%s/releases/download/%s/changzheng-launcher.zip"
                    % (owner, REPO, tag),
        "notes": "Gitee 国内直链",
    }
    st3, out3 = update_version_json(owner, REPO, tag, "changzheng-launcher.zip", version)
    print("version.json 更新：", st3)
    return 0


if __name__ == "__main__":
    sys.exit(main())
