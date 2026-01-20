"""
PR Size Score Dashboard - Streamlit App
"""

import base64
import json
import subprocess
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import yaml

# ページ設定
st.set_page_config(
    page_title="PR Size Score Dashboard",
    page_icon="📊",
    layout="wide",
)

# パス設定
PROJECT_DIR = Path(__file__).parent
DATA_PATH = PROJECT_DIR / "data" / "pr_size_scores.jsonl"
CONFIG_PATH = PROJECT_DIR / "config.yaml"

# 目標ライン（小さいPRの目安）
SCORE_TARGET = 10.0


def fetch_metrics() -> tuple[bool, str]:
    """GitHub APIからデータを取得"""
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    repositories = config.get("repositories", [])
    all_records: dict[str, dict] = {}
    messages = []

    for repo in repositories:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/contents/metrics/pr_size_scores.jsonl", "--jq", ".content"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            messages.append(f"- {repo}: データなし")
            continue

        try:
            decoded = base64.b64decode(result.stdout.strip()).decode("utf-8")
            count = 0
            for line in decoded.strip().split("\n"):
                if line:
                    record = json.loads(line)
                    key = f"{record['repo']}:{record['pr_number']}"
                    all_records[key] = record
                    count += 1
            messages.append(f"- {repo}: {count}件")
        except Exception as e:
            messages.append(f"- {repo}: エラー ({e})")

    # 保存
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    sorted_records = sorted(all_records.values(), key=lambda r: r.get("merged_at", ""))

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        for record in sorted_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return True, f"取得完了: {len(sorted_records)}件\n" + "\n".join(messages)


def load_data() -> pd.DataFrame:
    """JSONLからデータを読み込む"""
    if not DATA_PATH.exists():
        return pd.DataFrame()

    records = []
    with open(DATA_PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["merged_at"] = pd.to_datetime(df["merged_at"])
    df["date"] = df["merged_at"].dt.date
    df["week"] = df["merged_at"].dt.to_period("W").astype(str)
    return df


def main():
    st.title("📊 PR Size Score Dashboard")

    # サイドバー: データ更新
    st.sidebar.header("データ更新")
    if st.sidebar.button("データを取得", type="primary", use_container_width=True):
        with st.spinner("GitHub APIからデータを取得中..."):
            success, message = fetch_metrics()
            if success:
                st.sidebar.success(message)
                st.cache_data.clear()
                st.rerun()
            else:
                st.sidebar.error(message)

    # データ読み込み
    df = load_data()

    if df.empty:
        st.warning("データがありません。サイドバーの「データを取得」ボタンをクリックしてください。")
        return

    # サイドバー: フィルタ
    st.sidebar.header("フィルタ")

    repos = ["All"] + sorted(df["repo"].unique().tolist())
    selected_repo = st.sidebar.selectbox("リポジトリ", repos)

    authors = ["All"] + sorted(df["author"].unique().tolist())
    selected_author = st.sidebar.selectbox("著者", authors)

    # フィルタ適用
    filtered_df = df.copy()
    if selected_repo != "All":
        filtered_df = filtered_df[filtered_df["repo"] == selected_repo]
    if selected_author != "All":
        filtered_df = filtered_df[filtered_df["author"] == selected_author]

    # 過去7日間と前週のデータを抽出
    today = pd.Timestamp.now(tz="UTC").normalize()
    last_7_days = filtered_df[filtered_df["merged_at"] >= today - pd.Timedelta(days=7)]
    prev_7_days = filtered_df[
        (filtered_df["merged_at"] >= today - pd.Timedelta(days=14)) &
        (filtered_df["merged_at"] < today - pd.Timedelta(days=7))
    ]

    # メトリクス（過去7日間実績・前週比）
    st.header("サマリー（過去7日間）")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        current_count = len(last_7_days)
        prev_count = len(prev_7_days)
        delta_count = current_count - prev_count if prev_count > 0 else None
        st.metric("PR数", current_count, delta=delta_count)
    with col2:
        current_sum = last_7_days["size_score"].sum() if len(last_7_days) > 0 else 0
        prev_sum = prev_7_days["size_score"].sum() if len(prev_7_days) > 0 else None
        delta_sum = f"{current_sum - prev_sum:.2f}" if prev_sum is not None else None
        st.metric("合計スコア", f"{current_sum:.2f}", delta=delta_sum, delta_color="inverse")
    with col3:
        current_loc = last_7_days["loc"].mean() if len(last_7_days) > 0 else 0
        prev_loc = prev_7_days["loc"].mean() if len(prev_7_days) > 0 else None
        delta_loc = f"{current_loc - prev_loc:.0f}" if prev_loc is not None else None
        st.metric("平均LOC", f"{current_loc:.0f}", delta=delta_loc, delta_color="inverse")
    with col4:
        current_small = (
            len(last_7_days[last_7_days["size_score"] <= SCORE_TARGET]) / len(last_7_days) * 100
            if len(last_7_days) > 0 else 0
        )
        prev_small = (
            len(prev_7_days[prev_7_days["size_score"] <= SCORE_TARGET]) / len(prev_7_days) * 100
            if len(prev_7_days) > 0 else None
        )
        delta_small = f"{current_small - prev_small:.1f}%" if prev_small is not None else None
        st.metric("小規模PR率", f"{current_small:.1f}%", delta=delta_small, help=f"スコア{SCORE_TARGET}以下のPR割合")

    # スコア推移グラフ（日次合計・リポジトリ別積み上げ）
    st.header("スコア推移")

    if len(filtered_df) > 0:
        daily_scores = filtered_df.groupby(["date", "repo"])["size_score"].sum().reset_index()
        daily_scores["date"] = pd.to_datetime(daily_scores["date"])

        fig = px.bar(
            daily_scores,
            x="date",
            y="size_score",
            color="repo",
            title="日次合計スコア（リポジトリ別積み上げ）",
            labels={"size_score": "合計スコア", "date": "日付", "repo": "リポジトリ"},
        )
        fig.update_layout(barmode="stack")
        st.plotly_chart(fig, use_container_width=True)

    # リポジトリ別比較（過去7日間・円グラフ）
    st.header("リポジトリ別比較（過去7日間）")

    if len(last_7_days) > 0 and selected_repo == "All":
        repo_scores = last_7_days.groupby("repo")["size_score"].sum().reset_index()

        fig3 = px.pie(
            repo_scores,
            values="size_score",
            names="repo",
            title="リポジトリ別 合計スコア割合（過去7日間）",
        )
        fig3.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig3, use_container_width=True)

    # PR一覧
    st.header("PR一覧")

    if len(filtered_df) > 0:
        display_df = filtered_df[[
            "repo", "pr_number", "merged_at", "author",
            "additions", "deletions", "loc", "changed_files", "size_score"
        ]].sort_values("merged_at", ascending=False)

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "pr_number": st.column_config.NumberColumn("PR#", format="%d"),
                "merged_at": st.column_config.DatetimeColumn("マージ日時", format="YYYY-MM-DD HH:mm"),
                "size_score": st.column_config.NumberColumn("スコア", format="%.2f"),
            }
        )


if __name__ == "__main__":
    main()
