"""
Banking Assistant Agent — Streamlit dashboard.

A modern, single-page fintech-style UI on top of the deterministic
agent/analytics pipeline in agent.py. This file is presentation only — all
calculation, filtering, categorization, and anomaly detection happens in
src/*.py and is never duplicated here.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config
from agent import AgentResult, BankingAssistantAgent
from src.analytics import calculate_category_breakdown, calculate_overall_statistics, spending_over_time
from src.anomaly_detector import detect_anomalies
from src.categorizer import categorize_transactions
from src.data_loader import TransactionDataError, TransactionRepository

# --------------------------------------------------------------------------- #
# Page config (must be first Streamlit call)
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Banking Assistant Agent",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
# Custom CSS — fintech dashboard styling
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"]  {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }

    :root {
        --bank-navy: #0f1b3d;
        --bank-navy-light: #16234f;
        --bank-accent: #4f6df5;
        --bank-accent-2: #22c3a6;
        --bank-red: #e5484d;
        --bank-amber: #f5a524;
        --bank-bg: #f6f7fb;
        --bank-card: #ffffff;
        --bank-border: #e7e9f3;
        --bank-text: #1a1f36;
        --bank-muted: #6b7280;
    }

    .stApp {
        background: var(--bank-bg);
    }

    /* Header banner */
    .bank-header {
        background: linear-gradient(120deg, var(--bank-navy) 0%, #1e2f6b 60%, #2c3f8f 100%);
        border-radius: 18px;
        padding: 28px 32px;
        margin-bottom: 22px;
        color: white;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 10px 30px rgba(15, 27, 61, 0.25);
    }
    .bank-header h1 {
        font-size: 26px;
        font-weight: 800;
        margin: 0;
        color: #ffffff;
    }
    .bank-header p {
        margin: 4px 0 0 0;
        color: #c7d0f5;
        font-size: 14px;
    }
    .bank-badge {
        background: rgba(34, 195, 166, 0.18);
        border: 1px solid rgba(34, 195, 166, 0.5);
        color: #5eead4;
        padding: 6px 14px;
        border-radius: 999px;
        font-size: 12.5px;
        font-weight: 600;
        white-space: nowrap;
    }

    /* KPI cards */
    .kpi-card {
        background: var(--bank-card);
        border: 1px solid var(--bank-border);
        border-radius: 14px;
        padding: 18px 20px;
        box-shadow: 0 2px 10px rgba(15, 27, 61, 0.04);
        height: 100%;
    }
    .kpi-label {
        font-size: 12.5px;
        font-weight: 600;
        color: var(--bank-muted);
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 6px;
    }
    .kpi-value {
        font-size: 26px;
        font-weight: 800;
        color: var(--bank-text);
    }
    .kpi-sub {
        font-size: 12.5px;
        color: var(--bank-muted);
        margin-top: 4px;
    }

    /* Generic section card */
    .bank-card {
        background: var(--bank-card);
        border: 1px solid var(--bank-border);
        border-radius: 14px;
        padding: 20px 22px;
        box-shadow: 0 2px 10px rgba(15, 27, 61, 0.04);
        margin-bottom: 18px;
    }
    .bank-card h3 {
        margin-top: 0;
        font-size: 16px;
        font-weight: 700;
        color: var(--bank-text);
    }

    /* AI summary card */
    .ai-summary-card {
        background: linear-gradient(135deg, #eef1ff 0%, #e8fbf6 100%);
        border: 1px solid #d7defc;
        border-radius: 14px;
        padding: 20px 22px;
        margin-bottom: 18px;
    }
    .ai-summary-card h3 {
        margin-top: 0;
        font-size: 16px;
        font-weight: 700;
        color: var(--bank-navy);
    }
    .ai-summary-card p {
        font-size: 14.5px;
        line-height: 1.6;
        color: #26315e;
        margin-bottom: 0;
    }
    .ai-method-tag {
        display: inline-block;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.03em;
        text-transform: uppercase;
        padding: 3px 10px;
        border-radius: 999px;
        margin-bottom: 10px;
    }
    .ai-method-tag.ai { background: #dcfce7; color: #166534; }
    .ai-method-tag.template { background: #fef3c7; color: #92400e; }

    /* Anomaly cards */
    .anomaly-card {
        border: 1px solid #fbd5d5;
        background: #fff6f6;
        border-radius: 12px;
        padding: 14px 16px;
        margin-bottom: 10px;
    }
    .anomaly-card.moderate {
        border-color: #fde3b4;
        background: #fffaf0;
    }
    .anomaly-title {
        font-weight: 700;
        color: var(--bank-text);
        font-size: 14.5px;
    }
    .anomaly-reason {
        color: var(--bank-muted);
        font-size: 13px;
        margin-top: 4px;
    }
    .severity-pill {
        font-size: 10.5px;
        font-weight: 700;
        text-transform: uppercase;
        padding: 2px 9px;
        border-radius: 999px;
        margin-left: 8px;
    }
    .severity-pill.high { background: #fee2e2; color: #991b1b; }
    .severity-pill.moderate { background: #fef3c7; color: #92400e; }

    /* Quick query buttons */
    div[data-testid="stButton"] > button {
        border-radius: 10px;
        border: 1px solid var(--bank-border);
        font-weight: 600;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: var(--bank-navy);
    }
    section[data-testid="stSidebar"] * {
        color: #e5e9ff !important;
    }
    section[data-testid="stSidebar"] .stRadio label {
        font-weight: 500;
    }
    .sidebar-section-title {
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #8b96d1 !important;
        margin: 18px 0 6px 0;
    }
    .status-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 6px;
    }
    .status-dot.green { background: #22c3a6; }
    .status-dot.amber { background: #f5a524; }

    .disclaimer-box {
        background: #fff8e6;
        border: 1px solid #f5d98b;
        border-radius: 10px;
        padding: 10px 14px;
        font-size: 12.5px;
        color: #7a5b00;
        margin-bottom: 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def format_inr(amount: float) -> str:
    """Format a number using Indian digit grouping, e.g. 125000 -> '₹1,25,000'."""
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return f"{config.CURRENCY_SYMBOL}0"
    negative = amount < 0
    amount = abs(amount)
    int_part = f"{amount:,.0f}".replace(",", "")  # plain digit string
    if len(int_part) <= 3:
        formatted = int_part
    else:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted = ",".join(groups) + "," + last3
    sign = "-" if negative else ""
    return f"{sign}{config.CURRENCY_SYMBOL}{formatted}"


@st.cache_resource(show_spinner=False)
def get_agent() -> BankingAssistantAgent:
    return BankingAssistantAgent()


@st.cache_data(show_spinner=False, ttl=60)
def load_full_dataset():
    """Load + categorize the full dataset once (cached), for the
    Transactions / Analytics / Anomalies browser pages.
    """
    repo = TransactionRepository()
    df, report = repo.load()
    df = categorize_transactions(df)
    return df, report


def kpi_card(label: str, value: str, sub: str = "") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {sub_html}
    </div>
    """


def render_header():
    provider = config.active_llm_provider()
    status_label = f"AI: {provider.upper()}" if provider else "AI: Fallback Mode"
    st.markdown(
        f"""
        <div class="bank-header">
            <div>
                <h1>🏦 {config.APP_NAME}</h1>
                <p>{config.APP_TAGLINE}</p>
            </div>
            <div style="text-align:right;">
                <div class="bank-badge">● Secure Demo &nbsp;|&nbsp; {status_label}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> str:
    with st.sidebar:
        st.markdown("### 🏦 BANKING ASSISTANT")
        page = st.radio(
            "Navigate",
            ["Dashboard", "Transactions", "Analytics", "Anomalies"],
            label_visibility="collapsed",
        )

        st.markdown('<div class="sidebar-section-title">Data Source</div>', unsafe_allow_html=True)
        st.markdown(f"📄 `{config.TRANSACTIONS_CSV_PATH}`")

        st.markdown('<div class="sidebar-section-title">AI Status</div>', unsafe_allow_html=True)
        provider = config.active_llm_provider()
        if provider:
            st.markdown(f'<span class="status-dot green"></span> Available ({provider.upper()})', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-dot amber"></span> Fallback Mode (no API key)', unsafe_allow_html=True)

        st.markdown('<div class="sidebar-section-title">Demo Mode</div>', unsafe_allow_html=True)
        st.markdown('<span class="status-dot green"></span> Enabled — synthetic data only', unsafe_allow_html=True)

        st.markdown('<div class="sidebar-section-title">About</div>', unsafe_allow_html=True)
        with st.expander("What is this?"):
            st.write(
                "The Banking Assistant Agent is a demo transaction-analysis tool. "
                "It answers natural-language questions about a synthetic transaction "
                "dataset using deterministic Python/Pandas calculations, with an "
                "optional LLM used only for language understanding and prose "
                "summaries — never for the underlying math. "
                "**This app does not connect to any real bank account.**"
            )

    return page


def render_data_quality_notice(load_report):
    if load_report and load_report.has_issues():
        with st.expander(f"⚠️ Data quality notice — {load_report.total_rows_skipped} row(s) excluded", expanded=False):
            for w in load_report.warnings:
                st.write(f"- {w}")


def render_kpis(result: AgentResult):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card("Total Spending", format_inr(result.matching_stats.matching_total_amount)), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("Transactions Found", str(result.matching_stats.matching_transaction_count)), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("Average Transaction", format_inr(result.matching_stats.matching_average_amount)), unsafe_allow_html=True)
    with c4:
        st.markdown(kpi_card("Largest Transaction", format_inr(result.matching_stats.matching_largest_amount)), unsafe_allow_html=True)


def render_category_chart(category_breakdown):
    if not category_breakdown:
        st.info("No category data to chart for this selection.")
        return
    df = pd.DataFrame([c.model_dump() for c in category_breakdown])
    fig = px.pie(
        df,
        names="category",
        values="total_amount",
        hole=0.55,
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_traces(textinfo="percent+label", textposition="outside")
    fig.update_layout(
        showlegend=False,
        margin=dict(t=10, b=10, l=10, r=10),
        height=340,
        font=dict(family="Inter, sans-serif", size=12.5),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_time_series_chart(time_series: pd.DataFrame):
    if time_series is None or time_series.empty:
        st.info("No time-series data to chart for this selection.")
        return
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=time_series["period"],
            y=time_series["amount"],
            marker_color="#4f6df5",
            hovertemplate="%{x}<br>₹%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        margin=dict(t=10, b=10, l=10, r=10),
        height=340,
        font=dict(family="Inter, sans-serif", size=12.5),
        yaxis_title="Amount (₹)",
        xaxis_title=None,
        plot_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_anomalies(anomalies):
    if not anomalies:
        st.success("✅ No anomalies detected for this selection — spending looks consistent with the normal pattern.")
        return

    type_labels = {
        "statistical_outlier": "📈 Statistical Outlier",
        "duplicate_like": "🔁 Possible Duplicate",
        "rapid_repeated_large": "⚡ Rapid Large Spending Burst",
    }
    for a in anomalies:
        severity_class = "high" if a.severity == "high" else "moderate"
        card_class = "anomaly-card" if a.severity == "high" else "anomaly-card moderate"
        label = type_labels.get(a.anomaly_type, "⚠️ Potential Anomaly")
        st.markdown(
            f"""
            <div class="{card_class}">
                <div class="anomaly-title">{label}: {a.merchant} — {format_inr(a.amount)}
                    <span class="severity-pill {severity_class}">{a.severity}</span>
                </div>
                <div class="anomaly-reason">{a.date.strftime('%b %d, %Y')} · {a.category} · {a.reason}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.caption(
        "⚠️ These transactions are flagged as **potentially unusual** based on statistical patterns and simple "
        "rules — this is not a fraud determination."
    )


def render_summary_card(result: AgentResult):
    tag_class = "ai" if result.summary_method == "ai" else "template"
    tag_label = "AI-Generated Summary" if result.summary_method == "ai" else "Template Summary (deterministic)"
    st.markdown(
        f"""
        <div class="ai-summary-card">
            <span class="ai-method-tag {tag_class}">{tag_label}</span>
            <h3>💡 Spending Summary</h3>
            <p>{result.summary_text}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_transaction_table(df: pd.DataFrame, anomaly_ids: set[str] | None = None):
    if df.empty:
        st.markdown(
            '<div class="bank-card">No transactions to display for this selection.</div>',
            unsafe_allow_html=True,
        )
        return
    anomaly_ids = anomaly_ids or set()
    display_df = df.copy()
    display_df["Anomaly"] = display_df["transaction_id"].apply(lambda x: "⚠️ Flagged" if x in anomaly_ids else "—")
    display_df["Amount"] = display_df["amount"].apply(format_inr)
    display_df["Date"] = display_df["date"].dt.strftime("%b %d, %Y")
    display_df = display_df.rename(
        columns={
            "merchant": "Merchant",
            "description": "Description",
            "category": "Category",
            "type": "Type",
        }
    )
    st.dataframe(
        display_df[["Date", "Merchant", "Description", "Category", "Amount", "Type", "Anomaly"]],
        use_container_width=True,
        hide_index=True,
        height=min(440, 46 + 35 * len(display_df)),
    )


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #

QUICK_QUERIES = {
    "💰 High-value transactions": "Show all transactions above ₹50,000 from last month and summarize my spending.",
    "📊 Last month's spending": "What did I spend last month?",
    "⚠️ Find unusual transactions": "Find unusual transactions.",
    "🛒 Shopping spending": "How much did I spend on shopping last month?",
}


def page_dashboard():
    if "query_text" not in st.session_state:
        st.session_state.query_text = ""
    if "trigger_analysis" not in st.session_state:
        st.session_state.trigger_analysis = False

    st.markdown('<div class="bank-card">', unsafe_allow_html=True)
    st.markdown("#### Ask your banking question")
    query_text = st.text_area(
        "query_input",
        value=st.session_state.query_text,
        placeholder="Show transactions above ₹50,000 from last month and summarize my spending.",
        label_visibility="collapsed",
        height=80,
    )

    st.markdown("###### Quick queries")
    qc = st.columns(len(QUICK_QUERIES))
    for i, (label, q) in enumerate(QUICK_QUERIES.items()):
        if qc[i].button(label, use_container_width=True, key=f"quick_{i}"):
            st.session_state.query_text = q
            st.session_state.trigger_analysis = True
            st.rerun()

    _, mid, _ = st.columns([1, 1, 1])
    analyze_clicked = mid.button("🔍 Analyze Transactions", use_container_width=True, type="primary")
    st.markdown("</div>", unsafe_allow_html=True)

    should_run = analyze_clicked or st.session_state.trigger_analysis
    st.session_state.trigger_analysis = False

    if not should_run:
        st.info(
            "👋 Enter a question above (or click a quick query) and press **Analyze Transactions** to get started. "
            "Try: *\"Show all transactions above ₹50,000 from last month and summarize my spending.\"*"
        )
        return

    if not query_text or not query_text.strip():
        st.warning("Please enter a question first, or click one of the quick queries above.")
        return

    st.session_state.query_text = query_text

    with st.spinner("Analyzing your transactions..."):
        agent = get_agent()
        result = agent.analyze(query_text)

    if not result.success:
        st.error(f"❌ {result.error_message}")
        return

    render_data_quality_notice(result.load_report)

    st.markdown(
        f"""
        <div class="bank-card">
            <strong>Analysis Period:</strong> {result.period_label}
            &nbsp;·&nbsp; <strong>Query understood as:</strong> {result.structured_query.intent.replace('_', ' ').title()}
            &nbsp;·&nbsp; <span style="color:#6b7280;">(parsed via {result.parse_method})</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if result.matching_stats.matching_transaction_count == 0:
        st.warning(
            f"No transactions matched your criteria during **{result.period_label}**. "
            f"Try widening the date range or lowering the amount threshold."
        )
        render_summary_card(result)
        return

    render_kpis(result)
    st.write("")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="bank-card"><h3>📊 Spending by Category</h3>', unsafe_allow_html=True)
        render_category_chart(result.category_breakdown)
        st.markdown("</div>", unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="bank-card"><h3>📈 Spending Overview</h3>', unsafe_allow_html=True)
        render_time_series_chart(result.time_series)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="bank-card"><h3>⚠️ Potential Anomalies</h3>', unsafe_allow_html=True)
    render_anomalies(result.anomalies)
    st.markdown("</div>", unsafe_allow_html=True)

    render_summary_card(result)

    st.markdown('<div class="bank-card"><h3>📋 Matching Transactions</h3>', unsafe_allow_html=True)
    anomaly_ids = {a.transaction_id for a in result.anomalies}
    render_transaction_table(result.matching_df, anomaly_ids)
    st.markdown("</div>", unsafe_allow_html=True)

    if result.category_breakdown:
        with st.expander("📑 Category Breakdown (table)"):
            cat_df = pd.DataFrame([c.model_dump() for c in result.category_breakdown])
            cat_df["total_amount"] = cat_df["total_amount"].apply(format_inr)
            cat_df["percentage_of_spending"] = cat_df["percentage_of_spending"].apply(lambda v: f"{v:.1f}%")
            cat_df = cat_df.rename(
                columns={
                    "category": "Category",
                    "transaction_count": "Transaction Count",
                    "total_amount": "Total Amount",
                    "percentage_of_spending": "% of Spending",
                }
            )
            st.dataframe(cat_df, use_container_width=True, hide_index=True)


def page_transactions():
    st.markdown('<div class="bank-card"><h3>📋 All Transactions</h3>', unsafe_allow_html=True)
    try:
        df, load_report = load_full_dataset()
    except TransactionDataError as exc:
        st.error(f"❌ {exc.user_message}")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    render_data_quality_notice(load_report)

    col1, col2, col3 = st.columns([2, 2, 3])
    with col1:
        categories = sorted(df["category"].unique())
        selected_categories = st.multiselect("Category", categories, default=[])
    with col2:
        types = sorted(df["type"].unique())
        selected_types = st.multiselect("Type", types, default=[])
    with col3:
        search = st.text_input("Search merchant / description", "")

    filtered = df.copy()
    if selected_categories:
        filtered = filtered[filtered["category"].isin(selected_categories)]
    if selected_types:
        filtered = filtered[filtered["type"].isin(selected_types)]
    if search.strip():
        mask = (
            filtered["merchant"].str.contains(search, case=False, na=False)
            | filtered["description"].str.contains(search, case=False, na=False)
        )
        filtered = filtered[mask]

    filtered = filtered.sort_values("date", ascending=False)
    st.caption(f"Showing {len(filtered)} of {len(df)} transactions")
    render_transaction_table(filtered)
    st.markdown("</div>", unsafe_allow_html=True)


def page_analytics():
    try:
        df, load_report = load_full_dataset()
    except TransactionDataError as exc:
        st.error(f"❌ {exc.user_message}")
        return

    render_data_quality_notice(load_report)

    stats = calculate_overall_statistics(df)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card("Total Spending (All Time)", format_inr(stats.total_spending)), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("Total Income (All Time)", format_inr(stats.total_income)), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("Net Cash Flow", format_inr(stats.net_cash_flow)), unsafe_allow_html=True)
    with c4:
        st.markdown(kpi_card("Total Transactions", str(stats.total_transactions)), unsafe_allow_html=True)

    st.write("")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="bank-card"><h3>📊 Spending by Category (All Time)</h3>', unsafe_allow_html=True)
        breakdown = calculate_category_breakdown(df)
        render_category_chart(breakdown)
        st.markdown("</div>", unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="bank-card"><h3>📈 Monthly Spending Trend</h3>', unsafe_allow_html=True)
        ts = spending_over_time(df, freq="MS")
        render_time_series_chart(ts)
        st.markdown("</div>", unsafe_allow_html=True)


def page_anomalies():
    try:
        df, load_report = load_full_dataset()
    except TransactionDataError as exc:
        st.error(f"❌ {exc.user_message}")
        return

    render_data_quality_notice(load_report)

    anomalies = detect_anomalies(df)
    st.markdown(
        f'<div class="bank-card"><h3>⚠️ All Potential Anomalies (All Time) — {len(anomalies)} flagged</h3>',
        unsafe_allow_html=True,
    )
    render_anomalies(anomalies)
    st.markdown("</div>", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main():
    render_header()
    page = render_sidebar()

    st.markdown(
        '<div class="disclaimer-box">⚠️ This is a demo application using 100% synthetic, fictional transaction '
        'data. It does not connect to any real bank account, and it is not a financial advisor.</div>',
        unsafe_allow_html=True,
    )

    if page == "Dashboard":
        page_dashboard()
    elif page == "Transactions":
        page_transactions()
    elif page == "Analytics":
        page_analytics()
    elif page == "Anomalies":
        page_anomalies()


if __name__ == "__main__":
    main()
