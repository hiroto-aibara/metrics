#!/usr/bin/env python3
"""
各リポジトリからPR Size Scoreデータを取得し、統合JSONLに保存する。
GitHub CLIを使用（事前にgh auth loginが必要）
"""

import json
import subprocess
import sys
from pathlib import Path

import yaml


def sh(cmd: list[str]) -> str:
    """シェルコマンドを実行して出力を返す"""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {' '.join(cmd)}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return ""
    return result.stdout.strip()


def fetch_metrics_file(repo: str) -> str | None:
    """リポジトリからmetrics/pr_size_scores.jsonlの内容を取得"""
    print(f"Fetching from {repo}...")
    content = sh([
        "gh", "api",
        f"repos/{repo}/contents/metrics/pr_size_scores.jsonl",
        "--jq", ".content"
    ])
    if not content:
        print(f"  -> No metrics file found in {repo}")
        return None

    # Base64デコード
    import base64
    try:
        decoded = base64.b64decode(content).decode("utf-8")
        lines = [line for line in decoded.strip().split("\n") if line]
        print(f"  -> Found {len(lines)} records")
        return decoded
    except Exception as e:
        print(f"  -> Error decoding: {e}")
        return None


def main():
    # パス設定
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent
    config_path = project_dir / "config.yaml"
    output_path = project_dir / "data" / "pr_size_scores.jsonl"

    # 設定読み込み
    with open(config_path) as f:
        config = yaml.safe_load(f)

    repositories = config.get("repositories", [])
    if not repositories:
        print("No repositories configured in config.yaml")
        sys.exit(1)

    print(f"Target repositories: {repositories}\n")

    # 各リポジトリからデータ取得
    all_records: dict[str, dict] = {}  # キー: "repo:pr_number" で重複排除

    for repo in repositories:
        content = fetch_metrics_file(repo)
        if content:
            for line in content.strip().split("\n"):
                if line:
                    try:
                        record = json.loads(line)
                        key = f"{record['repo']}:{record['pr_number']}"
                        all_records[key] = record
                    except json.JSONDecodeError:
                        continue

    # 統合ファイルに書き出し
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # merged_atでソート
    sorted_records = sorted(
        all_records.values(),
        key=lambda r: r.get("merged_at", "")
    )

    with open(output_path, "w", encoding="utf-8") as f:
        for record in sorted_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\nTotal: {len(sorted_records)} records saved to {output_path}")


if __name__ == "__main__":
    main()
