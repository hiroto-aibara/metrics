"""
PR Size Score Dashboard - Streamlit App
"""

import base64
import json
import subprocess
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
    df["merged_at"] = pd.to_datetime(df["merged_at"]).dt.tz_convert("Asia/Tokyo")
    df["date"] = df["merged_at"].dt.date
    df["week"] = df["merged_at"].dt.tz_localize(None).dt.to_period("W").astype(str)
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

    # メトリクス
    st.header("サマリー")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("総PR数", len(filtered_df))
    with col2:
        avg_score = filtered_df["size_score"].mean() if len(filtered_df) > 0 else 0
        st.metric("平均スコア", f"{avg_score:.2f}")
    with col3:
        avg_loc = filtered_df["loc"].mean() if len(filtered_df) > 0 else 0
        st.metric("平均LOC", f"{avg_loc:.0f}")
    with col4:
        small_pr_ratio = (
            len(filtered_df[filtered_df["size_score"] <= SCORE_TARGET]) / len(filtered_df) * 100
            if len(filtered_df) > 0 else 0
        )
        st.metric("小規模PR率", f"{small_pr_ratio:.1f}%", help=f"スコア{SCORE_TARGET}以下のPR割合")

    # スコア推移グラフ
    st.header("スコア推移")

    if len(filtered_df) > 0:
        fig = px.scatter(
            filtered_df,
            x="merged_at",
            y="size_score",
            color="repo",
            hover_data=["pr_number", "author", "loc", "changed_files"],
            title="PR Size Score (時系列)",
        )
        fig.add_hline(
            y=SCORE_TARGET,
            line_dash="dash",
            line_color="green",
            annotation_text=f"目標: {SCORE_TARGET}",
        )
        st.plotly_chart(fig, use_container_width=True)

    # 週次平均
    st.header("週次平均スコア")

    if len(filtered_df) > 0:
        weekly = filtered_df.groupby("week").agg({
            "size_score": "mean",
            "pr_number": "count"
        }).reset_index()
        weekly.columns = ["week", "avg_score", "pr_count"]

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=weekly["week"],
            y=weekly["avg_score"],
            name="平均スコア",
            text=weekly["pr_count"].apply(lambda x: f"{x} PRs"),
            textposition="outside",
        ))
        fig2.add_hline(y=SCORE_TARGET, line_dash="dash", line_color="green")
        fig2.update_layout(title="週次平均スコア")
        st.plotly_chart(fig2, use_container_width=True)

    # リポジトリ別比較
    st.header("リポジトリ別比較")

    if len(df) > 0 and selected_repo == "All":
        repo_stats = df.groupby("repo").agg({
            "size_score": ["mean", "median", "count"],
            "loc": "mean",
        }).reset_index()
        repo_stats.columns = ["repo", "avg_score", "median_score", "pr_count", "avg_loc"]

        fig3 = px.bar(
            repo_stats,
            x="repo",
            y="avg_score",
            color="repo",
            title="リポジトリ別 平均スコア",
            text="pr_count",
        )
        fig3.add_hline(y=SCORE_TARGET, line_dash="dash", line_color="green")
        st.plotly_chart(fig3, use_container_width=True)

    # 著者別統計
    st.header("著者別統計")

    if len(filtered_df) > 0:
        author_stats = filtered_df.groupby("author").agg({
            "size_score": ["mean", "count"],
            "loc": "mean",
        }).reset_index()
        author_stats.columns = ["author", "avg_score", "pr_count", "avg_loc"]
        author_stats = author_stats.sort_values("avg_score")

        fig4 = px.bar(
            author_stats,
            x="author",
            y="avg_score",
            color="avg_score",
            color_continuous_scale="RdYlGn_r",
            title="著者別 平均スコア",
            text="pr_count",
        )
        fig4.add_hline(y=SCORE_TARGET, line_dash="dash", line_color="green")
        st.plotly_chart(fig4, use_container_width=True)

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
