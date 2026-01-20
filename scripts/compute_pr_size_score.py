#!/usr/bin/env python3
"""
PRのサイズスコアを計算し、metrics/pr_size_scores.jsonlに追記する。
GitHub Actionsから呼び出される。
"""

import json
import math
import os
import subprocess


def sh(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True).strip()


repo = os.environ["REPO"]
pr_number = os.environ["PR_NUMBER"]

# GitHub APIからPR情報を取得
pr = json.loads(sh(["gh", "api", f"repos/{repo}/pulls/{pr_number}"]))

additions = int(pr["additions"])
deletions = int(pr["deletions"])
changed_files = int(pr["changed_files"])

loc = additions + deletions
files = max(changed_files, 1)

# 規模スコア = log(loc + 1) * sqrt(files)
size_score = math.log(loc + 1) * math.sqrt(files)

record = {
    "repo": repo,
    "pr_number": int(pr_number),
    "merged_at": pr["merged_at"],
    "author": pr["user"]["login"],
    "additions": additions,
    "deletions": deletions,
    "loc": loc,
    "changed_files": changed_files,
    "size_score": round(size_score, 6),
}

os.makedirs("metrics", exist_ok=True)
with open("metrics/pr_size_scores.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps(record, ensure_ascii=False) + "\n")

print("OK:", record)
