# PR Size Score Dashboard

複数リポジトリのPRサイズスコアを可視化するダッシュボード。

## セットアップ

```bash
cd ~/Dev/metrics

# 仮想環境作成
python -m venv .venv
source .venv/bin/activate

# 依存関係インストール
pip install -r requirements.txt
```

## 使い方

### 1. データ取得

```bash
python scripts/fetch_metrics.py
```

各リポジトリの `metrics/pr_size_scores.jsonl` からデータを取得し、`data/pr_size_scores.jsonl` に統合します。

### 2. ダッシュボード起動

```bash
streamlit run app.py
```

ブラウザで http://localhost:8501 を開きます。

## 計測対象リポジトリの追加

`config.yaml` を編集：

```yaml
repositories:
  - org/repo-name
```

## ファイル構成

```
~/Dev/metrics/
├── config.yaml              # 計測対象リポジトリ設定
├── data/
│   └── pr_size_scores.jsonl # 統合データ
├── scripts/
│   └── fetch_metrics.py     # データ取得スクリプト
├── app.py                   # Streamlitダッシュボード
├── requirements.txt
└── README.md
```

## スコア計算式

```
size_score = log(additions + deletions + 1) × √(changed_files)
```

- 小さいPRほどスコアが低い
- 目標ライン: 10.0 以下
