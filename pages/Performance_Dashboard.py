from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="RAG Performance Summary",
    page_icon="📊",
    layout="wide",
)


# =========================================================
# CLEAN LIGHT THEME
# =========================================================
st.markdown(
    """
    <style>
        .main {
            background-color: #F8FAFC;
        }

        .page-title {
            font-size: 34px;
            font-weight: 750;
            color: #0F172A;
            margin-bottom: 4px;
        }

        .page-subtitle {
            font-size: 16px;
            color: #64748B;
            margin-bottom: 26px;
        }

        .section-title {
            font-size: 22px;
            font-weight: 700;
            color: #0F172A;
            margin-top: 30px;
            margin-bottom: 12px;
        }

        .metric-card {
            background: white;
            border: 1px solid #E2E8F0;
            border-radius: 16px;
            padding: 18px;
            box-shadow: 0 1px 5px rgba(15, 23, 42, 0.06);
            min-height: 122px;
        }

        .metric-label {
            font-size: 14px;
            color: #64748B;
            margin-bottom: 8px;
        }

        .metric-value {
            font-size: 28px;
            font-weight: 800;
            color: #0F172A;
            line-height: 1.2;
        }

        .metric-note {
            font-size: 13px;
            color: #64748B;
            margin-top: 8px;
        }

        .decision-box {
            background-color: #EFF6FF;
            border-left: 5px solid #60A5FA;
            padding: 16px;
            border-radius: 12px;
            color: #1E3A8A;
            font-size: 15px;
            margin-top: 14px;
        }

        .local-box {
            background-color: #F0F9FF;
            border-left: 5px solid #7DD3FC;
            padding: 14px;
            border-radius: 12px;
            color: #075985;
        }

        .azure-box {
            background-color: #ECFDF5;
            border-left: 5px solid #6EE7B7;
            padding: 14px;
            border-radius: 12px;
            color: #065F46;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


st.markdown(
    '<div class="page-title">📊 Local vs Azure RAG Performance Summary</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="page-subtitle">Simple business view: speed, quality, tool reliability, and deployment fit.</div>',
    unsafe_allow_html=True,
)


# =========================================================
# PATHS
# =========================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"

CSV_FILES = [
    DOCS_DIR / "local-mode-comparison-results-scored.csv",
    DOCS_DIR / "auto-comparison-results.csv",
    DOCS_DIR / "local-mode-comparison-results.csv",
]


# =========================================================
# HELPERS
# =========================================================
@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)

    text_cols = [
        "profile",
        "category",
        "query",
        "tool_called",
        "tool_names",
        "answer",
        "notes",
        "auto_notes",
        "expected_tool",
    ]

    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)

    if "profile" in df.columns:
        df["profile"] = df["profile"].str.lower().str.strip()

    if "category" in df.columns:
        df["category"] = df["category"].str.lower().str.strip()

    numeric_cols = [
        "id",
        "latency_sec",
        "correctness_0_2",
        "citation_0_1",
        "refusal_0_1",
        "tool_correct_0_1",
        "retrieved_chunks",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "tool_called" in df.columns:
        df["tool_called_bool"] = (
            df["tool_called"]
            .str.lower()
            .str.strip()
            .isin(["yes", "true", "1"])
        )
    else:
        df["tool_called_bool"] = False

    return df


def available_csvs() -> list[Path]:
    return [path for path in CSV_FILES if path.exists()]


def profile_label(profile: str) -> str:
    if profile == "local":
        return "Local Ollama"
    if profile == "azure":
        return "Azure Cloud"
    return profile


def expected_tool(row: pd.Series) -> bool:
    category = str(row.get("category", "")).lower()
    query = str(row.get("query", "")).lower()

    if category in {"tool_only", "combined"}:
        return True

    keywords = [
        "latest",
        "current",
        "recent",
        "live",
        "usgs",
        "reading",
        "readings",
        "ph",
        "nitrate",
        "turbidity",
        "dissolved oxygen",
        "temperature",
    ]

    return any(keyword in query for keyword in keywords)


def add_expected_tool(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "expected_tool" in df.columns and df["expected_tool"].str.strip().ne("").any():
        df["expected_tool_bool"] = (
            df["expected_tool"]
            .str.lower()
            .str.strip()
            .isin(["yes", "true", "1"])
        )
    else:
        df["expected_tool_bool"] = df.apply(expected_tool, axis=1)

    df["tool_match"] = df["expected_tool_bool"] == df["tool_called_bool"]

    return df


def score_percent(series: pd.Series, max_score: float) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()

    if values.empty:
        return 0.0

    return round(float(values.mean() / max_score * 100), 1)


def p50(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()

    if values.empty:
        return 0.0

    return round(float(values.median()), 2)


def p95(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()

    if values.empty:
        return 0.0

    return round(float(values.quantile(0.95)), 2)


def avg(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()

    if values.empty:
        return 0.0

    return round(float(values.mean()), 2)


def build_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for profile, group in df.groupby("profile"):
        latency = group["latency_sec"]

        tool_required = group[group["expected_tool_bool"] == True]

        if tool_required.empty:
            tool_reliability = 0.0
        else:
            tool_reliability = round(float(tool_required["tool_match"].mean() * 100), 1)

        correctness = score_percent(group.get("correctness_0_2", pd.Series(dtype=float)), 2)
        citation = score_percent(group.get("citation_0_1", pd.Series(dtype=float)), 1)

        privacy = 100 if profile == "local" else 60
        offline = 100 if profile == "local" else 0
        cost_control = 100 if profile == "local" else 60

        business_score = round(
            correctness * 0.35
            + tool_reliability * 0.20
            + citation * 0.10
            + privacy * 0.15
            + offline * 0.10
            + cost_control * 0.10,
            1,
        )

        rows.append(
            {
                "profile": profile,
                "runtime": profile_label(profile),
                "queries": len(group),
                "avg_latency": avg(latency),
                "p50_latency": p50(latency),
                "p95_latency": p95(latency),
                "correctness": correctness,
                "citation": citation,
                "tool_reliability": tool_reliability,
                "privacy": privacy,
                "offline": offline,
                "cost_control": cost_control,
                "business_score": business_score,
            }
        )

    return pd.DataFrame(rows)


def card(label: str, value: str, note: str = "") -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def style_chart(fig, height: int = 420):
    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(color="#334155"),
        title_font=dict(size=18, color="#0F172A"),
        legend_title_text="",
        margin=dict(l=30, r=30, t=60, b=40),
        height=height,
    )
    fig.update_xaxes(gridcolor="#F1F5F9")
    fig.update_yaxes(gridcolor="#E2E8F0")
    return fig


# =========================================================
# LOAD DATA
# =========================================================
csv_files = available_csvs()

if not csv_files:
    st.error(
        "No comparison CSV found. Run this first:\n\n"
        "`PYTHONPATH=. python scripts/run_comparison.py --profiles local azure`"
    )
    st.stop()

selected_file = st.sidebar.selectbox(
    "Select comparison file",
    csv_files,
    format_func=lambda path: path.name,
)

df = load_data(str(selected_file))
df = add_expected_tool(df)

required = {"profile", "category", "query", "latency_sec"}

missing = required - set(df.columns)

if missing:
    st.error(f"CSV missing required columns: {missing}")
    st.stop()


# =========================================================
# FILTERS
# =========================================================
st.sidebar.header("Filters")

profiles = sorted(df["profile"].dropna().unique().tolist())
categories = sorted(df["category"].dropna().unique().tolist())

selected_profiles = st.sidebar.multiselect(
    "Runtime",
    profiles,
    default=profiles,
    format_func=profile_label,
)

selected_categories = st.sidebar.multiselect(
    "Question type",
    categories,
    default=categories,
)

filtered = df[
    df["profile"].isin(selected_profiles)
    & df["category"].isin(selected_categories)
].copy()

if filtered.empty:
    st.warning("No data available for selected filters.")
    st.stop()

summary = build_summary(filtered)


# =========================================================
# EXECUTIVE VIEW
# =========================================================
st.markdown('<div class="section-title">1. Executive View</div>', unsafe_allow_html=True)

best_profile = summary.sort_values("business_score", ascending=False).iloc[0]

c1, c2, c3, c4 = st.columns(4)

with c1:
    card(
        "Recommended Runtime",
        profile_label(best_profile["profile"]),
        "Based on quality + tool reliability + deployment fit",
    )

with c2:
    card(
        "Business Score",
        f"{best_profile['business_score']}/100",
        "Higher score means better fit for business use",
    )

with c3:
    local_row = summary[summary["profile"] == "local"]
    local_latency = local_row["avg_latency"].iloc[0] if not local_row.empty else 0
    card(
        "Local Avg Speed",
        f"{local_latency:.2f}s",
        "Private and offline, but usually slower",
    )

with c4:
    azure_row = summary[summary["profile"] == "azure"]
    azure_latency = azure_row["avg_latency"].iloc[0] if not azure_row.empty else 0
    card(
        "Azure Avg Speed",
        f"{azure_latency:.2f}s",
        "Cloud-based and usually faster",
    )


st.markdown(
    """
    <div class="decision-box">
        <b>Business conclusion:</b> Local mode is strong for offline/private document Q&A.
        Azure mode is stronger for speed, live tools, and production reliability.
        Keeping both profiles gives the best deployment flexibility.
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# SPEED LINE GRAPH
# =========================================================
st.markdown('<div class="section-title">2. Speed Trend: Local vs Azure</div>', unsafe_allow_html=True)

speed_df = filtered.copy()

if "id" not in speed_df.columns or speed_df["id"].isna().all():
    speed_df["id"] = speed_df.groupby("profile").cumcount() + 1

speed_df["runtime"] = speed_df["profile"].apply(profile_label)

fig_speed = px.line(
    speed_df.sort_values(["runtime", "id"]),
    x="id",
    y="latency_sec",
    color="runtime",
    markers=True,
    color_discrete_map={
        "Local Ollama": "#93C5FD",
        "Azure Cloud": "#A7F3D0",
    },
    title="Response Time Across the 20 Evaluation Queries",
)

fig_speed.update_layout(
    xaxis_title="Question ID",
    yaxis_title="Latency in seconds",
)

style_chart(fig_speed)
st.plotly_chart(fig_speed, use_container_width=True)


# =========================================================
# BUSINESS METRICS
# =========================================================
st.markdown('<div class="section-title">3. Business Metrics Comparison</div>', unsafe_allow_html=True)

business_metrics = summary[
    [
        "runtime",
        "correctness",
        "tool_reliability",
        "privacy",
        "offline",
        "cost_control",
    ]
].copy()

business_long = business_metrics.melt(
    id_vars=["runtime"],
    var_name="metric",
    value_name="score",
)

business_long["metric"] = business_long["metric"].replace(
    {
        "correctness": "Answer Quality",
        "tool_reliability": "Tool Reliability",
        "privacy": "Privacy",
        "offline": "Offline Use",
        "cost_control": "Cost Control",
    }
)

fig_business = px.bar(
    business_long,
    x="metric",
    y="score",
    color="runtime",
    barmode="group",
    text="score",
    color_discrete_map={
        "Local Ollama": "#93C5FD",
        "Azure Cloud": "#A7F3D0",
    },
    title="Business Metrics: Local vs Azure",
)

fig_business.update_traces(textposition="outside")
fig_business.update_layout(
    xaxis_title="Business Metric",
    yaxis_title="Score (%)",
    yaxis_range=[0, 110],
)

style_chart(fig_business)
st.plotly_chart(fig_business, use_container_width=True)


# =========================================================
# SIMPLE DECISION TABLE
# =========================================================
st.markdown('<div class="section-title">4. Simple Decision Table</div>', unsafe_allow_html=True)

decision_table = summary[
    [
        "runtime",
        "business_score",
        "avg_latency",
        "p50_latency",
        "p95_latency",
        "correctness",
        "tool_reliability",
        "privacy",
        "offline",
        "cost_control",
    ]
].copy()

decision_table = decision_table.rename(
    columns={
        "runtime": "Runtime",
        "business_score": "Business Score",
        "avg_latency": "Avg Latency (s)",
        "p50_latency": "p50 Latency (s)",
        "p95_latency": "p95 Latency (s)",
        "correctness": "Answer Quality (%)",
        "tool_reliability": "Tool Reliability (%)",
        "privacy": "Privacy (%)",
        "offline": "Offline Use (%)",
        "cost_control": "Cost Control (%)",
    }
)

st.dataframe(
    decision_table,
    use_container_width=True,
    hide_index=True,
)


# =========================================================
# QUERY RESULTS
# =========================================================
st.markdown('<div class="section-title">5. Query Results</div>', unsafe_allow_html=True)

table_cols = [
    "profile",
    "id",
    "category",
    "query",
    "latency_sec",
    "tool_called",
    "tool_names",
    "correctness_0_2",
    "citation_0_1",
    "tool_correct_0_1",
    "notes",
    "auto_notes",
]

available_cols = [col for col in table_cols if col in filtered.columns]

display_table = filtered[available_cols].copy()

if "profile" in display_table.columns:
    display_table["profile"] = display_table["profile"].apply(profile_label)

st.dataframe(
    display_table,
    use_container_width=True,
    hide_index=True,
)


# =========================================================
# ANSWER VIEWER
# =========================================================
st.markdown('<div class="section-title">6. Answer Viewer</div>', unsafe_allow_html=True)

if "answer" in filtered.columns:
    options = filtered.apply(
        lambda row: (
            f"{profile_label(row.get('profile', ''))} | "
            f"Q{row.get('id', '')} | "
            f"{row.get('category', '')} | "
            f"{str(row.get('query', ''))[:80]}"
        ),
        axis=1,
    ).tolist()

    selected = st.selectbox("Select one answer to inspect", options)

    selected_row = filtered.iloc[options.index(selected)]

    st.markdown("**Question**")
    st.write(selected_row.get("query", ""))

    st.markdown("**Answer**")
    st.write(selected_row.get("answer", ""))

    st.markdown("**Runtime**")
    st.code(
        f"Profile: {profile_label(selected_row.get('profile', ''))}\n"
        f"Latency: {selected_row.get('latency_sec', '')} sec\n"
        f"Tool called: {selected_row.get('tool_called', '')}\n"
        f"Tool names: {selected_row.get('tool_names', '')}",
        language="text",
    )


# =========================================================
# EXPORT
# =========================================================
st.markdown('<div class="section-title">7. Export</div>', unsafe_allow_html=True)

st.download_button(
    "Download filtered CSV",
    data=filtered.to_csv(index=False).encode("utf-8"),
    file_name="rag-business-performance-summary.csv",
    mime="text/csv",
)

st.success("Simple business dashboard loaded successfully.")