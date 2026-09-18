"""通过 GitHub Git Data API 部署 dist 目录（github.com 不可达时的备用通道）。"""
import base64
import os
import subprocess
import sys

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = "Jintaokasumi/Jintaokasumi.github.io"
API = "https://api.github.com"

# 从本机 git 凭据取令牌（不打印）
out = subprocess.run(
    ["git", "credential", "fill"],
    input="protocol=https\nhost=github.com\n\n",
    capture_output=True, text=True,
).stdout
TOKEN = next(l[len("password="):] for l in out.splitlines() if l.startswith("password="))
H = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}

def must(r, what):
    if r.status_code >= 300:
        print(f"FAIL {what}: {r.status_code} {r.text[:200]}")
        sys.exit(1)
    return r.json()

# 1. 当前 main 指向
ref = must(requests.get(f"{API}/repos/{REPO}/git/ref/heads/main", headers=H, timeout=20), "get ref")
base_sha = ref["object"]["sha"]
print("base:", base_sha[:7])

# 2. 收集文件并逐个创建 blob
files = []
for dirpath, _, names in os.walk(ROOT):
    if ".git" in dirpath.split(os.sep):
        continue
    for n in names:
        p = os.path.join(dirpath, n)
        rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
        files.append((rel, p))
files.sort()
print(f"{len(files)} 个文件待上传")

tree_items = []
for rel, p in files:
    data = base64.b64encode(open(p, "rb").read()).decode()
    blob = must(
        requests.post(f"{API}/repos/{REPO}/git/blobs", headers=H, timeout=60,
                      json={"content": data, "encoding": "base64"}),
        f"blob {rel}",
    )
    tree_items.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    print("blob:", rel)

# 3. 创建 tree / commit / 更新 ref
tree = must(requests.post(f"{API}/repos/{REPO}/git/trees", headers=H, timeout=30,
                          json={"base_tree": base_sha, "tree": tree_items}), "tree")
commit = must(requests.post(f"{API}/repos/{REPO}/git/commits", headers=H, timeout=30,
                            json={"message": "全面升级：AI 定制插画、作品卡真实链接、精简随笔",
                                  "tree": tree["sha"], "parents": [base_sha]}), "commit")
must(requests.patch(f"{API}/repos/{REPO}/git/refs/heads/main", headers=H, timeout=20,
                    json={"sha": commit["sha"]}), "update ref")
print("DEPLOYED:", commit["sha"][:7])
