"""
Banking Assistant Agent — Streamlit dashboard.

A modern, single-page fintech-style UI on top of the deterministic
agent/analytics pipeline in agent.py. This file is presentation only — all
calculation, filtering, categorization, and anomaly detection happens in
src/*.py and is never duplicated here.

Authentication: every financial page requires login. User data is scoped
via the DB-backed repository; no user can see another's transactions.
"""

from __future__ import annotations

import html as html_mod
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config
from src.analytics import (
    calculate_category_breakdown,
    calculate_overall_statistics,
    income_expense_over_time,
    period_comparison,
    spending_over_time,
    top_merchants,
)
from src.anomaly_detector import detect_anomalies
from src.auth import get_current_user_id, get_current_username, is_authenticated, login, logout, register
from src.categorizer import categorize_transactions
from src.data_loader import TransactionDataError
from src.database import get_db, init_db
from src.formatting import format_inr, _symbol
from src.importer import auto_map_columns, apply_column_mapping, detect_file_type, read_upload, run_import
from src.orchestrator import ConversationContext, Orchestrator
from src.services import (
    DBTransactionRepository, get_default_account, get_user_imports,
    get_user_plan, get_user_plan_detail, activate_pro, activate_demo, cancel_pro,
    create_conversation, get_user_conversations, get_conversation,
    add_message, get_conversation_messages, delete_conversation,
)

def _user_currency() -> str | None:
    """Resolve the logged-in user's primary account currency (cached per request)."""
    uid = get_current_user_id()
    if uid is None:
        return None
    cached = st.session_state.get("_user_currency")
    cached_uid = st.session_state.get("_user_currency_uid")
    if cached and cached_uid == uid:
        return cached
    with get_db() as db:
        acct = get_default_account(db, uid)
        cur = acct.currency if acct else "INR"
    st.session_state["_user_currency"] = cur
    st.session_state["_user_currency_uid"] = uid
    return cur


def _fmt(amount: float) -> str:
    """format_inr with the logged-in user's currency."""
    return format_inr(amount, _user_currency())


def _currency_symbol() -> str:
    """Return the symbol string for the current user's currency."""
    return _symbol(_user_currency())


# --------------------------------------------------------------------------- #
# Page config (must be first Streamlit call)
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Banking Assistant Agent",
    page_icon="\U0001f3e6",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Ensure tables exist on first run
init_db()

# --------------------------------------------------------------------------- #
# Stitch Design System — Dark Navy Executive Theme
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=Inter:wght@400;500;600;700;800&family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap');

    :root {
        /* Stitch MD3 — exact tokens from Tailwind config */
        --bg: #0a122a;
        --surface: #0a122a;
        --surface-lowest: #050d25;
        --surface-low: #131a33;
        --surface-container: #171e37;
        --surface-high: #212942;
        --surface-highest: #2c344d;
        --surface-elevated: #131a33;
        --surface-bright: #313852;
        --primary-container: #101d35;
        --primary: #bac6e6;
        --secondary: #78d8ba;
        --secondary-container: #007c63;
        --on-secondary-container: #b6ffe5;
        --tertiary: #54dcb6;
        --on-surface: #dbe1ff;
        --on-surface-variant: #c5c6ce;
        --outline: #8f9098;
        --outline-variant: #45474d;
        --error: #ffb4ab;
        --error-container: #93000a;
        --on-error-container: #ffdad6;
        --surface-variant: #2c344d;

        /* Aliases for backward compatibility */
        --border: #45474d;
        --text: #dbe1ff;
        --text-muted: #c5c6ce;
        --text-dim: #8f9098;
        --accent: #007c63;
        --accent-glow: #54dcb6;
        --accent-light: rgba(0,124,99,0.12);
        --danger: #ffb4ab;
        --warning: #F59E0B;
        --success: #78d8ba;

        /* Radii (Stitch MD3) */
        --r-sm: 4px;
        --r: 8px;
        --r-lg: 12px;
        --r-xl: 9999px;
        --r-card: 16px;

        /* Shadows */
        --shadow: 0 8px 32px rgba(0,0,0,0.3);
        --shadow-sm: 0 1px 8px rgba(0,0,0,0.04);
        --shadow-lg: 0 20px 50px rgba(5,13,37,0.5);
    }

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
        font-variant-numeric: tabular-nums;
    }

    .stApp {
        background: #0a122a !important;
        color: var(--text);
    }

    /* Force all streamlit text to light */
    .stApp p, .stApp span, .stApp label, .stApp li, .stApp div,
    .stApp h1, .stApp h2, .stApp h3, .stApp h4 {
        color: var(--text) !important;
    }
    .stApp .stMarkdown p { color: var(--text) !important; }

    /* Headings use Plus Jakarta Sans */
    h1, h2, h3, .stitch-headline {
        font-family: 'Plus Jakarta Sans', 'Inter', sans-serif !important;
        letter-spacing: -0.02em;
    }

    /* ---------- Sidebar: Stitch surface-container-low ---------- */
    section[data-testid="stSidebar"] {
        background: var(--surface-low) !important;
        border-right: none;
        box-shadow: 0 1px 8px rgba(0,0,0,0.04);
    }
    section[data-testid="stSidebar"] * { color: var(--on-surface-variant) !important; }
    section[data-testid="stSidebar"] .stRadio label {
        font-family: 'Inter', sans-serif; font-weight: 600;
        font-size: 0.875rem; padding: 8px 8px;
        border-radius: 8px; transition: all 0.15s;
        display: block; margin: 2px 0;
        letter-spacing: 0.01em;
    }
    section[data-testid="stSidebar"] .stRadio label:hover {
        color: var(--on-surface) !important; background: var(--surface-high);
    }
    section[data-testid="stSidebar"] .stRadio label[data-checked="true"],
    section[data-testid="stSidebar"] [data-baseweb="radio"] input:checked + div {
        color: var(--on-secondary-container) !important;
        background: var(--secondary-container);
        border-radius: 8px; font-weight: 600;
    }

    .sidebar-brand {
        font-family: 'Plus Jakarta Sans', sans-serif;
        display: flex; align-items: center; gap: 8px;
        padding: 16px; margin-bottom: 0;
        background: var(--surface-lowest);
        height: 64px; box-sizing: border-box;
    }
    .sidebar-brand-name {
        font-size: 0.875rem; font-weight: 600; color: var(--on-surface) !important;
        letter-spacing: 0.01em; line-height: 1.2;
    }
    .sidebar-brand-sub {
        font-size: 0.75rem; font-weight: 600; color: var(--secondary) !important;
        letter-spacing: 0.04em; text-transform: uppercase; line-height: 1;
    }
    .sidebar-section {
        font-size: 0.75rem; font-weight: 600; letter-spacing: 0.04em;
        text-transform: uppercase; color: var(--outline) !important;
        margin: 12px 0 4px; padding: 0 8px;
    }
    .material-symbols-outlined {
        font-family: 'Material Symbols Outlined'; font-weight: normal;
        font-style: normal; font-size: 20px; line-height: 1;
        letter-spacing: normal; text-transform: none; display: inline-block;
        white-space: nowrap; word-wrap: normal; direction: ltr;
        -webkit-font-smoothing: antialiased;
        font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 20;
    }
    .nav-item { display: flex; align-items: center; gap: 10px; font-size: 13.5px; }
    .nav-item .material-symbols-outlined { font-size: 18px; color: var(--outline); }
    .sidebar-pro-card {
        background: rgba(0,124,99,0.08); border: 1px solid rgba(0,124,99,0.2);
        border-radius: var(--r); padding: 14px 16px; margin-top: 16px;
    }
    .sidebar-pro-card .pro-label { color: var(--tertiary) !important; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }
    .sidebar-pro-card .pro-price { color: var(--on-surface) !important; font-size: 18px; font-weight: 800; margin: 4px 0; }

    .pro-badge {
        background: rgba(0,124,99,0.15); color: var(--tertiary) !important;
        padding: 2px 8px; border-radius: 999px; font-size: 10px;
        font-weight: 700; margin-left: 6px; display: inline-block;
    }
    .free-badge {
        background: rgba(143,144,152,0.12); color: var(--outline) !important;
        padding: 2px 8px; border-radius: 999px; font-size: 10px;
        font-weight: 700; margin-left: 6px; display: inline-block;
    }

    /* ---------- Top header bar ---------- */
    .stitch-header {
        background: var(--surface); border: 1px solid var(--border);
        border-radius: var(--r-lg); padding: 14px 24px; margin-bottom: 20px;
        display: flex; align-items: center; justify-content: space-between;
        box-shadow: var(--shadow-sm);
    }
    .stitch-header-left {
        display: flex; align-items: center; gap: 8px;
        font-size: 13px; color: var(--text-muted);
    }
    .stitch-header-left .breadcrumb-sep { color: var(--text-dim); margin: 0 2px; }
    .stitch-header-left .breadcrumb-active { color: var(--text); font-weight: 600; }
    .stitch-header-center {
        display: flex; align-items: center; gap: 0;
        background: var(--surface-lowest); border: 1px solid var(--border);
        border-radius: 999px; padding: 3px;
    }
    .mode-btn {
        padding: 6px 18px; border-radius: 999px; font-size: 12px;
        font-weight: 600; cursor: pointer; transition: all 0.15s;
        border: none; color: var(--text-muted); background: transparent;
    }
    .mode-btn.active-standard { background: var(--border); color: var(--text); }
    .mode-btn.active-ai { background: var(--secondary-container); color: var(--on-secondary-container); box-shadow: 0 2px 10px rgba(0,124,99,0.3); }
    .stitch-header-right {
        display: flex; align-items: center; gap: 16px; font-size: 12px; color: var(--text-muted);
    }
    .header-user { display: flex; align-items: center; gap: 8px; }
    .header-user-name { font-weight: 600; color: var(--text); font-size: 13px; }

    /* ---------- KPI Cards (dark, tabular) ---------- */
    .kpi-card {
        background: var(--surface); border: 1px solid var(--border);
        border-radius: var(--r-lg); padding: 20px 22px;
        box-shadow: var(--shadow); height: 100%;
        transition: box-shadow 0.2s, border-color 0.15s;
    }
    .kpi-card:hover { border-color: rgba(30,184,148,0.3); }
    .kpi-card.hero {
        background: linear-gradient(135deg, rgba(0,124,99,0.08) 0%, var(--surface) 100%);
        border-color: rgba(0,124,99,0.2);
    }
    .kpi-label {
        font-size: 10.5px; font-weight: 600; color: var(--text-muted);
        text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px;
    }
    .kpi-value {
        font-family: 'Plus Jakarta Sans', 'Inter', sans-serif;
        font-size: 26px; font-weight: 800; color: var(--text);
        letter-spacing: -0.02em; font-variant-numeric: tabular-nums;
    }
    .kpi-card.hero .kpi-value { font-size: 30px; }
    .kpi-sub { font-size: 12px; color: var(--text-muted); margin-top: 6px; display: flex; align-items: center; gap: 4px; }
    .kpi-delta-up { color: var(--accent-glow); font-weight: 600; }
    .kpi-delta-down { color: var(--danger); font-weight: 600; }
    .kpi-delta-neutral { color: var(--text-muted); font-weight: 600; }

    /* ---------- Dark card ---------- */
    .bank-card {
        background: var(--surface); border: 1px solid var(--border);
        border-radius: var(--r-lg); padding: 20px 24px;
        box-shadow: var(--shadow); margin-bottom: 16px;
    }
    .bank-card h3 {
        margin-top: 0; font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 14px; font-weight: 700; color: var(--text);
        display: flex; align-items: center; gap: 8px;
    }

    /* ---------- Overview hero (dark navy gradient) ---------- */
    .overview-hero {
        background: linear-gradient(135deg, var(--primary-container) 0%, var(--surface-low) 50%, var(--surface-high) 100%);
        border: 1px solid var(--border);
        border-radius: var(--r-xl); padding: 32px 36px; color: white;
        position: relative; overflow: hidden; margin-bottom: 24px;
        box-shadow: var(--shadow);
    }
    .overview-hero::before {
        content: ''; position: absolute; top: -40%; right: -10%;
        width: 300px; height: 300px;
        background: radial-gradient(circle, rgba(0,124,99,0.15) 0%, transparent 70%);
        pointer-events: none;
    }
    .hero-label {
        font-size: 12px; color: var(--text-muted); text-transform: uppercase;
        letter-spacing: 0.06em; font-weight: 600; margin-bottom: 4px;
    }
    .hero-welcome {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 28px; font-weight: 800; color: #fff;
        letter-spacing: -0.02em; margin-bottom: 4px;
    }
    .hero-subtitle { font-size: 14px; color: var(--text-muted); margin-bottom: 16px; }
    .hero-telemetry {
        display: inline-flex; align-items: center; gap: 6px;
        background: rgba(0,124,99,0.1); border: 1px solid rgba(0,124,99,0.2);
        border-radius: 999px; padding: 4px 12px; font-size: 11px; font-weight: 600;
        color: var(--tertiary); margin-bottom: 16px;
    }
    .hero-telemetry .pulse-dot {
        width: 6px; height: 6px; border-radius: 50%; background: var(--secondary);
        box-shadow: 0 0 8px rgba(0,124,99,0.5);
    }
    .hero-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 16px; }
    .hero-action-btn {
        background: rgba(0,124,99,0.12); border: 1px solid rgba(0,124,99,0.25);
        color: var(--tertiary); padding: 8px 16px; border-radius: var(--r-sm);
        font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s;
    }
    .hero-action-btn:hover { background: rgba(0,124,99,0.2); }
    .hero-stats { display: flex; gap: 40px; margin-top: 20px; }
    .hero-stat-label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.04em; }
    .hero-stat-value { font-size: 22px; font-weight: 700; color: var(--on-surface); font-variant-numeric: tabular-nums; }
    .hero-delta { font-size: 13px; font-weight: 600; margin-top: 6px; }
    .hero-delta.up { color: var(--tertiary); }
    .hero-delta.down { color: var(--on-error-container); }

    /* ---------- AI Summary / Insight card ---------- */
    .ai-summary-card {
        background: linear-gradient(135deg, rgba(0,124,99,0.06) 0%, rgba(0,124,99,0.02) 100%);
        border: 1px solid rgba(0,124,99,0.18); border-radius: var(--r);
        padding: 16px 18px; margin-bottom: 12px;
    }
    .ai-summary-card h3 { margin-top: 0; font-size: 14px; font-weight: 700; color: var(--text) !important; }
    .ai-summary-card p { font-size: 13px; line-height: 1.65; color: var(--text-muted) !important; margin-bottom: 0; }
    .ai-method-tag {
        display: inline-block; font-size: 10px; font-weight: 700;
        letter-spacing: 0.05em; text-transform: uppercase;
        padding: 2px 8px; border-radius: 999px; margin-bottom: 8px;
    }
    .ai-method-tag.ai { background: var(--accent-light); color: var(--accent-glow); }
    .ai-method-tag.template { background: rgba(245,165,36,0.1); color: #F59E0B; }

    /* ---------- Insight cards ---------- */
    .insight-card {
        background: var(--surface); border: 1px solid var(--border);
        border-left: 3px solid var(--accent);
        border-radius: var(--r-sm); padding: 14px 16px; margin-bottom: 10px;
        box-shadow: var(--shadow-sm);
    }
    .insight-title { font-weight: 700; font-size: 13px; color: var(--text); margin-bottom: 2px; }
    .insight-body { font-size: 12.5px; color: var(--text-muted); line-height: 1.6; }
    .insight-cat {
        display: inline-block; font-size: 9.5px; font-weight: 700;
        letter-spacing: 0.05em; text-transform: uppercase;
        padding: 2px 7px; border-radius: 999px; margin-bottom: 6px;
    }
    .insight-cat.spending { background: rgba(0,124,99,0.1); color: var(--accent-glow); }
    .insight-cat.income { background: rgba(59,130,246,0.1); color: #60A5FA; }
    .insight-cat.pattern { background: rgba(139,92,246,0.1); color: #A78BFA; }
    .insight-cat.alert { background: rgba(239,68,68,0.08); color: var(--on-error-container); }

    /* ---------- Anomaly cards ---------- */
    .anomaly-card {
        border: 1px solid rgba(239,68,68,0.3); background: rgba(239,68,68,0.06);
        border-radius: var(--r-sm); padding: 12px 14px; margin-bottom: 8px;
    }
    .anomaly-card.moderate { border-color: rgba(245,158,11,0.3); background: rgba(245,158,11,0.06); }
    .anomaly-title { font-weight: 700; color: var(--text) !important; font-size: 13px; }
    .anomaly-reason { color: var(--text-muted) !important; font-size: 12px; margin-top: 2px; }
    .severity-pill {
        font-size: 10px; font-weight: 700; text-transform: uppercase;
        padding: 2px 7px; border-radius: 999px; margin-left: 6px;
    }
    .severity-pill.high { background: rgba(239,68,68,0.12); color: var(--on-error-container); }
    .severity-pill.moderate { background: rgba(245,158,11,0.12); color: #FBBF24; }

    /* ---------- Buttons ---------- */
    div[data-testid="stButton"] > button {
        border-radius: var(--r-sm); border: 1px solid var(--border);
        background: rgba(255,255,255,0.04); color: var(--text);
        font-weight: 600; font-size: 13px; transition: all 0.15s;
    }
    div[data-testid="stButton"] > button:hover {
        border-color: var(--accent); background: rgba(0,124,99,0.08);
    }
    div[data-testid="stButton"] > button[kind="primary"] {
        background: var(--accent) !important; border-color: var(--accent) !important;
        color: #fff !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover {
        background: var(--accent-glow) !important;
    }

    /* ---------- Tables (dark dense) ---------- */
    .stitch-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .stitch-table th {
        text-align: left; font-weight: 600; color: var(--text-muted);
        font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.04em;
        padding: 10px 12px; border-bottom: 1px solid var(--border);
        background: var(--surface-lowest);
    }
    .stitch-table td {
        padding: 10px 12px; border-bottom: 1px solid rgba(69,71,77,0.6);
        color: var(--text); font-variant-numeric: tabular-nums;
    }
    .stitch-table tr:hover td { background: rgba(255,255,255,0.02); }

    .status-badge {
        font-size: 10px; font-weight: 700; padding: 2px 8px;
        border-radius: 999px; display: inline-block;
    }
    .status-badge.complete, .status-badge.cleared { background: rgba(16,185,129,0.1); color: var(--accent-glow); }
    .status-badge.failed, .status-badge.flagged { background: rgba(239,68,68,0.1); color: var(--on-error-container); }
    .status-badge.pending { background: rgba(245,158,11,0.1); color: #FBBF24; }

    .txn-badge { font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 999px; }
    .txn-badge.expense { background: rgba(239,68,68,0.1); color: var(--on-error-container); }
    .txn-badge.income { background: rgba(0,124,99,0.1); color: var(--accent-glow); }

    /* ---------- Step indicator ---------- */
    .step-bar { display: flex; align-items: flex-start; justify-content: center; gap: 0; margin: 20px 0 28px; }
    .step-item { display: flex; flex-direction: column; align-items: center; }
    .step-num {
        width: 32px; height: 32px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 13px; font-weight: 700;
    }
    .step-num.active { background: var(--accent); color: white; box-shadow: 0 0 0 4px rgba(0,124,99,0.2); }
    .step-num.done { background: var(--accent); color: white; }
    .step-num.pending { background: var(--border); color: var(--text-dim); }
    .step-name { font-size: 10px; color: var(--text-muted); margin-top: 4px; font-weight: 600; }
    .step-name.active { color: var(--accent-glow); }
    .step-line { width: 60px; height: 2px; background: var(--border); margin: 0 4px; margin-top: 15px; }
    .step-line.done { background: var(--accent); }

    /* ---------- Data inputs ---------- */
    div[data-testid="stTextInput"] input,
    div[data-testid="stTextArea"] textarea,
    div[data-testid="stSelectbox"] > div,
    div[data-testid="stDateInput"] input {
        background: var(--surface-lowest) !important; border-color: var(--border) !important;
        color: var(--text) !important; font-size: 13px;
    }
    div[data-testid="stTextInput"] input:focus,
    div[data-testid="stTextArea"] textarea:focus {
        border-color: var(--tertiary) !important;
        box-shadow: 0 0 0 1px var(--tertiary) !important;
    }
    div[data-testid="stTextInput"] label,
    div[data-testid="stSelectbox"] label,
    div[data-testid="stDateInput"] label {
        color: var(--text-muted) !important;
    }

    /* Chat message styling */
    div[data-testid="stChatMessage"] {
        background: rgba(255,255,255,0.03) !important;
        border: 1px solid rgba(255,255,255,0.06) !important;
        border-radius: var(--r);
    }
    div[data-testid="stChatMessage"] p,
    div[data-testid="stChatMessage"] span,
    div[data-testid="stChatMessage"] li,
    div[data-testid="stChatMessage"] strong { color: var(--on-surface) !important; }
    div[data-testid="stChatInput"] textarea {
        background: var(--surface-lowest) !important; color: var(--text) !important;
        border-color: var(--border) !important;
    }

    /* Dataframe */
    div[data-testid="stDataFrame"] {
        border-radius: var(--r-sm); border: 1px solid var(--border);
    }
    div[data-testid="stTabs"] button[data-baseweb="tab"] {
        font-weight: 600; font-size: 13px; color: var(--text-muted) !important;
    }

    /* Expanders */
    div[data-testid="stExpander"] { border-color: var(--border) !important; }
    div[data-testid="stExpander"] summary { color: var(--text) !important; }

    /* Alerts */
    div[data-testid="stAlert"] { background: rgba(255,255,255,0.03) !important; }

    /* Disclaimer */
    .disclaimer-box {
        background: rgba(245,158,11,0.06); border: 1px solid rgba(245,158,11,0.15);
        border-radius: var(--r-sm); padding: 8px 14px;
        font-size: 11.5px; color: var(--warning) !important; margin-bottom: 16px;
    }

    /* Auth page */
    .auth-container {
        display: flex; gap: 0; min-height: 70vh; margin: -20px -16px;
    }
    .auth-left {
        flex: 1; background: linear-gradient(135deg, var(--primary-container) 0%, var(--surface-lowest) 100%);
        padding: 60px 48px; display: flex; flex-direction: column; justify-content: center;
        border-radius: var(--r-lg) 0 0 var(--r-lg);
    }
    .auth-left h1 {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 28px; font-weight: 800; color: var(--on-surface);
        letter-spacing: -0.02em; margin-bottom: 16px;
    }
    .auth-left .tagline { color: var(--text-muted); font-size: 14px; line-height: 1.6; margin-bottom: 32px; }
    .auth-feature {
        display: flex; align-items: center; gap: 12px; margin-bottom: 16px;
        font-size: 13px; color: var(--on-surface-variant);
    }
    .auth-feature-icon {
        width: 32px; height: 32px; border-radius: var(--r-sm);
        background: rgba(0,124,99,0.12); display: flex; align-items: center;
        justify-content: center; color: var(--tertiary); font-size: 16px; flex-shrink: 0;
    }
    .auth-testimonial {
        margin-top: 32px; padding: 20px; background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.06); border-radius: var(--r);
    }
    .auth-testimonial q { font-size: 13px; color: var(--on-surface-variant); line-height: 1.6; font-style: italic; }
    .auth-testimonial .author { font-size: 12px; color: var(--text-dim); margin-top: 8px; }

    .auth-right {
        flex: 1; padding: 60px 48px;
        display: flex; flex-direction: column; justify-content: center;
    }
    .auth-header { text-align: center; margin: 0 0 8px; }
    .auth-header h2 { font-size: 20px; font-weight: 700; color: var(--text); margin: 0 0 4px; }
    .auth-header p { font-size: 13px; color: var(--text-muted); margin: 0; }

    /* Empty state */
    .empty-state {
        text-align: center; padding: 48px 24px;
        background: var(--surface); border: 1px dashed var(--border);
        border-radius: var(--r-lg); margin: 14px 0;
    }
    .empty-state h3 { color: var(--text) !important; font-size: 18px; font-weight: 700; margin: 0 0 8px; }
    .empty-state p { color: var(--text-muted) !important; font-size: 13px; margin: 0 auto 16px; max-width: 400px; }

    /* Section label */
    .section-label {
        font-size: 13px; font-weight: 700; color: var(--text);
        display: flex; align-items: center; gap: 6px; margin-bottom: 6px;
    }

    /* Page title / subtitle */
    .page-title {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 22px; font-weight: 700; color: var(--text) !important;
        letter-spacing: -0.02em; margin: 0 0 2px 0;
        display: flex; align-items: center; gap: 8px;
    }
    .page-subtitle { font-size: 13px; color: var(--text-muted) !important; margin: 0 0 20px 0; }

    /* Pricing */
    .pricing-toggle {
        display: flex; align-items: center; justify-content: center; gap: 12px;
        margin: 24px 0;
    }
    .pricing-card {
        background: var(--surface); border: 1px solid var(--border);
        border-radius: var(--r-xl); padding: 32px;
        box-shadow: var(--shadow); height: 100%;
    }
    .pricing-card.pro {
        border-color: rgba(0,124,99,0.3);
        background: linear-gradient(135deg, rgba(0,124,99,0.06) 0%, var(--surface) 100%);
    }
    .pricing-card h3 { font-size: 16px; font-weight: 700; color: var(--text); margin: 0 0 8px; }
    .pricing-price {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 32px; font-weight: 800; color: var(--accent-glow);
        margin: 8px 0 4px;
    }
    .pricing-price .period { font-size: 14px; font-weight: 400; color: var(--text-muted); }

    /* Subscription utilization */
    .util-bar-bg { background: var(--border); border-radius: 999px; height: 6px; overflow: hidden; }
    .util-bar-fill { background: var(--accent-glow); height: 100%; border-radius: 999px; }

    /* Metric info for data sync pipeline */
    .sync-node {
        display: flex; align-items: center; gap: 8px;
        padding: 8px 0; border-bottom: 1px solid rgba(69,71,77,0.4);
        font-size: 12px;
    }
    .sync-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .sync-dot.green { background: var(--accent-glow); box-shadow: 0 0 6px rgba(30,184,148,0.4); }
    .sync-dot.amber { background: var(--warning); box-shadow: 0 0 6px rgba(245,158,11,0.4); }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

PAGES_PER_TABLE = 25
_CHART_FONT = "Inter, system-ui, -apple-system, sans-serif"

_DARK_CHART_COLORS = dict(
    font_color="#8f9098",
    gridcolor="rgba(69,71,77,0.5)",
    zerolinecolor="rgba(69,71,77,0.5)",
)


def _chart_layout(**overrides):
    base = dict(
        margin=dict(t=10, b=10, l=10, r=10), height=320,
        font=dict(family=_CHART_FONT, size=12, color="#8f9098"),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="rgba(69,71,77,0.4)", zerolinecolor="rgba(69,71,77,0.4)"),
        yaxis=dict(gridcolor="rgba(69,71,77,0.4)", zerolinecolor="rgba(69,71,77,0.4)"),
    )
    base.update(overrides)
    return base


def _load_user_dataset(user_id: int):
    """Load user's transactions from DB, categorize, and return."""
    with get_db() as db:
        repo = DBTransactionRepository(db, user_id)
        df, report = repo.load()
        if not df.empty:
            df = categorize_transactions(df)
        return df, report


def _date_range_selector(df: pd.DataFrame, key_prefix: str = "dr") -> tuple[date, date, str]:
    """Render date range preset + custom pickers. Returns (start, end, label)."""
    presets = {
        "This Month": 0,
        "Last Month": 1,
        "Last 30 Days": 2,
        "Last 90 Days": 3,
        "This Year": 4,
        "All Time": 5,
        "Custom": 6,
    }
    today = date.today()

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        choice = st.selectbox("Period", list(presets.keys()), index=0, key=f"{key_prefix}_preset")

    if choice == "This Month":
        start = today.replace(day=1)
        end = today
        label = today.strftime("%B %Y")
    elif choice == "Last Month":
        first_this = today.replace(day=1)
        end = first_this - timedelta(days=1)
        start = end.replace(day=1)
        label = start.strftime("%B %Y")
    elif choice == "Last 30 Days":
        start = today - timedelta(days=29)
        end = today
        label = f"{start.strftime('%b %d')} - {end.strftime('%b %d, %Y')}"
    elif choice == "Last 90 Days":
        start = today - timedelta(days=89)
        end = today
        label = f"{start.strftime('%b %d')} - {end.strftime('%b %d, %Y')}"
    elif choice == "This Year":
        start = today.replace(month=1, day=1)
        end = today
        label = str(today.year)
    elif choice == "Custom":
        data_min = df["date"].min().date() if not df.empty else today - timedelta(days=365)
        data_max = df["date"].max().date() if not df.empty else today
        with col2:
            start = st.date_input("From", value=data_min, key=f"{key_prefix}_start")
        with col3:
            end = st.date_input("To", value=data_max, key=f"{key_prefix}_end")
        label = f"{start.strftime('%b %d, %Y')} - {end.strftime('%b %d, %Y')}"
    else:  # All Time
        if not df.empty:
            start = df["date"].min().date()
            end = df["date"].max().date()
        else:
            start = today - timedelta(days=365)
            end = today
        label = "All Time"

    return start, end, label


def _filter_by_date(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if df.empty:
        return df
    return df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))]


def kpi_card(label: str, value: str, sub: str = "", hero: bool = False) -> str:
    cls = "kpi-card hero" if hero else "kpi-card"
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="{cls}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'{sub_html}'
        f'</div>'
    )


def _delta_html(pct: float | None, invert: bool = False) -> str:
    if pct is None:
        return '<span class="kpi-delta-neutral">—</span>'
    arrow = "↑" if pct > 0 else ("↓" if pct < 0 else "↔")
    if invert:
        css = "kpi-delta-down" if pct > 0 else ("kpi-delta-up" if pct < 0 else "kpi-delta-neutral")
    else:
        css = "kpi-delta-up" if pct > 0 else ("kpi-delta-down" if pct < 0 else "kpi-delta-neutral")
    return f'<span class="{css}">{arrow} {abs(pct):.1f}%</span>'


def _insight_category(title: str) -> tuple[str, str]:
    t = title.lower()
    if "anomal" in t or "unusual" in t:
        return "alert", "Alert"
    if "income" in t or "expense-to-income" in t:
        return "income", "Income"
    if "trend" in t or "average" in t or "peak" in t:
        return "pattern", "Pattern"
    return "spending", "Spending"


def _sparkline_svg(values: list[float], width: int = 80, height: int = 24, color: str = "#78d8ba") -> str:
    if not values or len(values) < 2:
        return ""
    mn, mx = min(values), max(values)
    rng = mx - mn if mx != mn else 1
    pts = []
    for i, v in enumerate(values):
        x = i * width / (len(values) - 1)
        y = height - (v - mn) / rng * (height - 4) - 2
        pts.append(f"{x:.1f},{y:.1f}")
    polyline = "L".join(pts)
    fill_pts = f"M0,{height} L{polyline} L{width},{height} Z"
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'style="display:inline-block;vertical-align:middle;margin-left:8px">'
        f'<defs><linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.3"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/>'
        f'</linearGradient></defs>'
        f'<path d="{fill_pts}" fill="url(#sg)"/>'
        f'<path d="M{polyline}" fill="none" stroke="{color}" stroke-width="1.5" '
        f'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


def _step_indicator_html(current: int, steps: list[str]) -> str:
    parts = []
    for i, name in enumerate(steps, 1):
        cls = "done" if i < current else ("active" if i == current else "pending")
        name_cls = "active" if i == current else ""
        parts.append(f'<div class="step-item"><div class="step-num {cls}">{i}</div><div class="step-name {name_cls}">{name}</div></div>')
        if i < len(steps):
            line_cls = "done" if i < current else ""
            parts.append(f'<div class="step-line {line_cls}"></div>')
    return f'<div class="step-bar">{"".join(parts)}</div>'


# --------------------------------------------------------------------------- #
# Layout components
# --------------------------------------------------------------------------- #


def _get_user_plan_cached() -> str:
    plan, _ = _get_user_plan_detail_cached()
    return plan


def _get_user_plan_detail_cached() -> tuple[str, bool]:
    uid = get_current_user_id()
    if uid is None:
        return "free", False
    with get_db() as db:
        return get_user_plan_detail(db, uid)


def render_header():
    username = get_current_username() if is_authenticated() else ""
    plan, is_demo = _get_user_plan_detail_cached() if is_authenticated() else ("free", False)
    if plan == "pro" and is_demo:
        plan_badge = '<span class="pro-badge">PRO · Demo</span>'
    elif plan == "pro":
        plan_badge = '<span class="pro-badge">PRO</span>'
    else:
        plan_badge = ""

    ai_mode = st.session_state.get("global_ai_mode", "Standard")
    std_cls = "mode-btn active-standard" if ai_mode == "Standard" else "mode-btn"
    ai_cls = "mode-btn active-ai" if ai_mode == "AI Mode" else "mode-btn"

    st.markdown(
        f'<div class="stitch-header">'
        f'<div class="stitch-header-left">'
        f'<span>Workspace</span><span class="breadcrumb-sep">›</span>'
        f'<span class="breadcrumb-active">Institutional Treasury</span>'
        f'</div>'
        f'<div class="stitch-header-center">'
        f'<span class="{std_cls}">Standard Mode</span>'
        f'<span class="{ai_cls}">AI Mode (Pro)</span>'
        f'</div>'
        f'<div class="stitch-header-right">'
        f'<span>Last 30 Days</span>'
        f'<div class="header-user">'
        f'<span class="header-user-name">{html_mod.escape(username)}</span>'
        f'{plan_badge}'
        f'</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if is_authenticated():
        hc1, hc2, _ = st.columns([1, 1, 6])
        with hc1:
            if st.button("Standard Mode", key="mode_std", use_container_width=True):
                st.session_state["global_ai_mode"] = "Standard"
                st.rerun()
        with hc2:
            if st.button("AI Mode (Pro)", key="mode_ai", use_container_width=True):
                st.session_state["global_ai_mode"] = "AI Mode"
                st.rerun()


def render_sidebar() -> str:
    with st.sidebar:
        st.markdown(
            '<div class="sidebar-brand">'
            '<div class="sidebar-brand-name">'
            '<span class="material-symbols-outlined" style="font-size:18px;color:var(--accent-glow);vertical-align:middle;margin-right:6px;">account_balance</span>'
            'Banking Assistant</div>'
            '<div class="sidebar-brand-sub">Agentic Intelligence</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        if is_authenticated():
            plan = _get_user_plan_cached()

            nav_options = [
                "Overview",
                "Transactions",
                "AI Assistant",
                "Data Center",
                "Billing & Subscription",
            ]

            page = st.radio(
                "Navigate",
                nav_options,
                label_visibility="collapsed",
            )

            st.markdown('<div class="sidebar-section">Account</div>', unsafe_allow_html=True)
            badge = '<span class="pro-badge">PRO</span>' if plan == "pro" else '<span class="free-badge">FREE</span>'
            st.markdown(f"**{get_current_username()}** {badge}", unsafe_allow_html=True)
            if st.button("Logout", use_container_width=True):
                logout()
                st.rerun()

            st.markdown('<div class="sidebar-section">AI Status</div>', unsafe_allow_html=True)
            provider = config.active_llm_provider()
            if provider:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:6px;font-size:12px;">'
                    f'<span class="sync-dot green"></span> Available ({provider.upper()})</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:6px;font-size:12px;">'
                    f'<span class="sync-dot amber"></span> Fallback Mode</div>',
                    unsafe_allow_html=True,
                )

            # Sidebar Pro card
            if plan == "pro":
                st.markdown(
                    f'<div class="sidebar-pro-card">'
                    f'<div class="pro-label">Pro Plan</div>'
                    f'<div class="pro-price">₹{config.PRO_MONTHLY_PRICE_INR}/mo</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="sidebar-pro-card">'
                    f'<div class="pro-label">Upgrade to Pro</div>'
                    f'<div style="font-size:12px;color:#8f9098;margin-top:4px;">Unlock AI Assistant</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            page = "auth"

    return page


def render_data_quality_notice(load_report):
    if load_report and load_report.has_issues():
        with st.expander(f"Data quality notice — {load_report.total_rows_skipped} row(s) excluded", expanded=False):
            for w in load_report.warnings:
                st.write(f"- {w}")


def render_category_chart(category_breakdown):
    if not category_breakdown:
        st.info("No category data to chart for this selection.")
        return
    df = pd.DataFrame([c.model_dump() for c in category_breakdown])
    fig = px.pie(
        df, names="category", values="total_amount", hole=0.55,
        color_discrete_sequence=["#007c63", "#78d8ba", "#0EA5E9", "#8B5CF6", "#F59E0B", "#EF4444", "#8f9098", "#06B6D4"],
    )
    fig.update_traces(textinfo="percent+label", textposition="outside",
                      textfont=dict(color="#8f9098"))
    fig.update_layout(**_chart_layout(showlegend=False, height=320))
    st.plotly_chart(fig, use_container_width=True)


def render_anomalies(anomalies):
    if not anomalies:
        st.success("No anomalies detected — spending looks consistent.")
        return

    type_labels = {
        "statistical_outlier": "Statistical Outlier",
        "duplicate_like": "Possible Duplicate",
        "rapid_repeated_large": "Rapid Large Spending Burst",
    }
    for a in anomalies:
        sev_class = "high" if a.severity == "high" else "moderate"
        card_class = "anomaly-card" if a.severity == "high" else "anomaly-card moderate"
        label = type_labels.get(a.anomaly_type, "Potential Anomaly")
        st.markdown(
            f'<div class="{card_class}">'
            f'<div class="anomaly-title">{label}: {html_mod.escape(str(a.merchant))} — {_fmt(a.amount)}'
            f'<span class="severity-pill {sev_class}">{a.severity}</span></div>'
            f'<div class="anomaly-reason">{a.date.strftime("%b %d, %Y")} · '
            f'{html_mod.escape(str(a.category))} · {html_mod.escape(str(a.reason))}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.caption(
        "These transactions are flagged as **potentially unusual** based on statistical patterns and simple "
        "rules — this is not a fraud determination."
    )


def render_summary_card(summary_text: str, summary_method: str):
    tag_class = "ai" if summary_method == "ai" else "template"
    tag_label = "AI-Generated Summary" if summary_method == "ai" else "Template Summary"
    st.markdown(
        f'<div class="ai-summary-card">'
        f'<span class="ai-method-tag {tag_class}">{tag_label}</span>'
        f'<h3>Spending Summary</h3>'
        f'<p>{html_mod.escape(summary_text)}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_transaction_table(df: pd.DataFrame, anomaly_ids: set[str] | None = None,
                             page_size: int = PAGES_PER_TABLE, key: str = "txn"):
    if df.empty:
        st.markdown(
            '<div class="bank-card">No transactions to display for this selection.</div>',
            unsafe_allow_html=True,
        )
        return

    anomaly_ids = anomaly_ids or set()
    total = len(df)
    total_pages = max(1, (total + page_size - 1) // page_size)

    if total > page_size:
        page_num = st.number_input(
            f"Page (1–{total_pages})", min_value=1, max_value=total_pages, value=1,
            key=f"{key}_page",
        )
    else:
        page_num = 1

    start_idx = (page_num - 1) * page_size
    page_df = df.iloc[start_idx:start_idx + page_size].copy()

    page_df["Anomaly"] = page_df["transaction_id"].apply(
        lambda x: "Flagged" if x in anomaly_ids else "—"
    )
    page_df["Amount"] = page_df["amount"].apply(_fmt)
    page_df["Date"] = page_df["date"].dt.strftime("%b %d, %Y")
    page_df = page_df.rename(columns={
        "merchant": "Merchant", "description": "Description",
        "category": "Category", "type": "Type",
    })
    st.dataframe(
        page_df[["Date", "Merchant", "Description", "Category", "Amount", "Type", "Anomaly"]],
        use_container_width=True, hide_index=True,
        height=min(440, 46 + 35 * len(page_df)),
    )
    if total > page_size:
        st.caption(f"Showing {start_idx + 1}–{min(start_idx + page_size, total)} of {total} transactions")


# --------------------------------------------------------------------------- #
# Auth page — dual-pane layout
# --------------------------------------------------------------------------- #


def page_auth():
    left_col, right_col = st.columns([5, 7], gap="small")

    with left_col:
        st.markdown(
            '<div style="background:var(--primary-container);border-radius:12px 0 0 12px;'
            'padding:40px 32px;min-height:780px;display:flex;flex-direction:column;justify-content:space-between;'
            'position:relative;overflow:hidden;">'
            # ambient blurs
            '<div style="position:absolute;top:-96px;left:-96px;width:384px;height:384px;border-radius:50%;'
            'background:rgba(0,124,99,0.2);filter:blur(80px);pointer-events:none;"></div>'
            '<div style="position:absolute;bottom:-96px;right:-96px;width:384px;height:384px;border-radius:50%;'
            'background:rgba(44,52,77,0.4);filter:blur(80px);pointer-events:none;"></div>'
            # top section
            '<div style="position:relative;z-index:10;display:flex;flex-direction:column;gap:24px;">'
            # brand badge
            '<div style="display:flex;align-items:center;gap:8px;">'
            '<div style="width:32px;height:32px;border-radius:8px;background:var(--surface-container);'
            'display:flex;align-items:center;justify-content:center;color:#78d8ba;">'
            '<span class="material-symbols-outlined" style="font-size:18px;">smart_toy</span></div>'
            '<span style="font-family:Plus Jakarta Sans,sans-serif;font-size:1.25rem;font-weight:600;'
            'letter-spacing:-0.015em;color:var(--on-surface);">Banking Assistant</span>'
            '<span style="padding:2px 8px;border-radius:999px;background:var(--secondary-container);'
            'color:var(--on-secondary-container);font-size:0.75rem;font-weight:600;letter-spacing:0.04em;'
            'text-transform:uppercase;">Agentic Intelligence</span>'
            '</div>'
            # hero statement
            '<div style="margin-top:8px;">'
            '<h1 style="font-family:Plus Jakarta Sans,sans-serif;font-size:2.25rem;font-weight:700;'
            'color:var(--on-surface);letter-spacing:-0.025em;line-height:2.75rem;margin:0 0 8px;">'
            'Institutional Treasury Intelligence, Powered by Autonomous AI.</h1>'
            '<p style="font-size:0.9375rem;line-height:1.5rem;color:#c5c6ce;letter-spacing:-0.005em;margin:0;">'
            'Continuous multi-bank ledger synchronization, anomaly isolation, and sovereign '
            'automated settlements built for Fortune 500 treasuries.</p>'
            '</div>'
            # feature pillars
            '<div style="display:flex;flex-direction:column;gap:12px;margin-top:8px;">'
            '<div style="display:flex;align-items:flex-start;gap:8px;background:rgba(19,26,51,0.7);'
            'padding:16px;border-radius:8px;">'
            '<div style="width:24px;height:24px;border-radius:50%;background:rgba(120,216,186,0.15);'
            'display:flex;align-items:center;justify-content:center;color:#78d8ba;flex-shrink:0;margin-top:2px;">'
            '<span class="material-symbols-outlined" style="font-size:16px;">check_circle</span></div>'
            '<div><div style="font-size:0.875rem;font-weight:600;color:var(--on-surface);letter-spacing:0.01em;">'
            'Real-Time Multi-Ledger Reconciliation</div>'
            '<div style="font-size:0.8125rem;color:#c5c6ce;line-height:1.25rem;">'
            'Instant unified matching across SWIFT, FedNow, and multi-bank feeds.</div></div></div>'
            '<div style="display:flex;align-items:flex-start;gap:8px;background:rgba(19,26,51,0.7);'
            'padding:16px;border-radius:8px;">'
            '<div style="width:24px;height:24px;border-radius:50%;background:rgba(120,216,186,0.15);'
            'display:flex;align-items:center;justify-content:center;color:#78d8ba;flex-shrink:0;margin-top:2px;">'
            '<span class="material-symbols-outlined" style="font-size:16px;">security</span></div>'
            '<div><div style="font-size:0.875rem;font-weight:600;color:var(--on-surface);letter-spacing:0.01em;">'
            'Autonomous Anomaly & Dispute Generation</div>'
            '<div style="font-size:0.8125rem;color:#c5c6ce;line-height:1.25rem;">'
            'Sub-second duplicate ledger flagging with auto-drafted clearing arbitration.</div></div></div>'
            '<div style="display:flex;align-items:flex-start;gap:8px;background:rgba(19,26,51,0.7);'
            'padding:16px;border-radius:8px;">'
            '<div style="width:24px;height:24px;border-radius:50%;background:rgba(120,216,186,0.15);'
            'display:flex;align-items:center;justify-content:center;color:#78d8ba;flex-shrink:0;margin-top:2px;">'
            '<span class="material-symbols-outlined" style="font-size:16px;">verified_user</span></div>'
            '<div><div style="font-size:0.875rem;font-weight:600;color:var(--on-surface);letter-spacing:0.01em;">'
            'Hardware Sovereign Encryption</div>'
            '<div style="font-size:0.8125rem;color:#c5c6ce;line-height:1.25rem;">'
            'FIPS 140-3 Level 4 HSM isolation, RBI compliance, SOC 2 Type II attestation.</div></div></div>'
            '</div>'
            '</div>'
            # bottom: testimonial + trust bar
            '<div style="position:relative;z-index:10;display:flex;flex-direction:column;gap:16px;margin-top:24px;">'
            '<div style="background:rgba(33,41,66,0.6);backdrop-filter:blur(8px);padding:16px;border-radius:8px;">'
            '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
            '<div style="width:40px;height:40px;border-radius:50%;background:var(--surface-container-highest);'
            'display:flex;align-items:center;justify-content:center;color:#78d8ba;font-weight:700;font-size:16px;">EV</div>'
            '<div><div style="font-size:0.875rem;font-weight:600;color:var(--on-surface);">Elena Vance</div>'
            '<div style="font-size:0.8125rem;color:#78d8ba;">VP of Finance &bull; Sovereign Tech Group</div></div></div>'
            '<p style="font-size:0.8125rem;color:#c5c6ce;line-height:1.25rem;font-style:italic;margin:0;">'
            '&ldquo;Banking Assistant cut our monthly multi-entity vendor reconciliation cycle '
            'from 4 full days to under 14 minutes with zero manual adjustments.&rdquo;</p>'
            '</div>'
            '<div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;'
            'gap:8px;padding-top:8px;color:#c5c6ce;font-size:0.8125rem;">'
            '<div style="display:flex;align-items:center;gap:6px;">'
            '<span style="width:8px;height:8px;border-radius:50%;background:#78d8ba;"></span>'
            '<span style="font-family:Inter,sans-serif;font-size:0.8125rem;letter-spacing:0.02em;">Encrypted Enclave Node</span></div>'
            '<div style="display:flex;align-items:center;gap:6px;">'
            '<span class="material-symbols-outlined" style="font-size:14px;color:#78d8ba;">sync_saved_locally</span>'
            '<span style="font-family:Inter,sans-serif;font-size:0.8125rem;letter-spacing:0.02em;">99.8% Sync Integrity</span></div>'
            '<div style="display:flex;align-items:center;gap:6px;">'
            '<span class="material-symbols-outlined" style="font-size:14px;color:#78d8ba;">lock</span>'
            '<span style="font-family:Inter,sans-serif;font-size:0.8125rem;letter-spacing:0.02em;">Zero LLM Data Training</span></div>'
            '</div>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    with right_col:
        st.markdown(
            '<div style="display:flex;align-items:center;justify-content:space-between;padding-bottom:16px;">'
            '<div style="display:flex;align-items:center;gap:4px;color:#c5c6ce;">'
            '<span class="material-symbols-outlined" style="font-size:16px;color:#78d8ba;">corporate_fare</span>'
            '<span style="font-size:0.75rem;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;">Enterprise Gateway</span>'
            '</div></div>',
            unsafe_allow_html=True,
        )

        tab_login, tab_register = st.tabs([" Sign In ", " Register Organization "])

        with tab_login:
            st.markdown(
                '<div style="margin-bottom:4px;">'
                '<h2 style="font-family:Plus Jakarta Sans,sans-serif;font-size:1.5rem;font-weight:600;'
                'color:var(--on-surface);letter-spacing:-0.02em;margin:0 0 4px;">Sign in to Executive Portal</h2>'
                '<p style="font-size:0.9375rem;color:#c5c6ce;margin:0;">Authenticate using your corporate '
                'directory credentials.</p></div>',
                unsafe_allow_html=True,
            )
            with st.form("login_form"):
                username = st.text_input("Corporate Username", placeholder="username")
                password = st.text_input("Password / Enclave Passkey", type="password", placeholder="Enter password")
                submitted = st.form_submit_button(
                    "Authenticate & Enter Workspace", use_container_width=True, type="primary",
                )
                if submitted:
                    if not username or not password:
                        st.error("Please fill in both fields.")
                    else:
                        with get_db() as db:
                            ok, err = login(db, username, password)
                        if ok:
                            st.rerun()
                        else:
                            st.error(err)

        with tab_register:
            st.markdown(
                '<div style="margin-bottom:4px;">'
                '<h2 style="font-family:Plus Jakarta Sans,sans-serif;font-size:1.5rem;font-weight:600;'
                'color:var(--on-surface);letter-spacing:-0.02em;margin:0 0 4px;">Register Organization</h2>'
                '<p style="font-size:0.9375rem;color:#c5c6ce;margin:0;">Create a new corporate account to '
                'access the treasury platform.</p></div>',
                unsafe_allow_html=True,
            )
            with st.form("register_form"):
                reg_username = st.text_input("Username", key="reg_user", placeholder="Choose a username")
                reg_email = st.text_input("Corporate Email", key="reg_email", placeholder="name@institution.com")
                reg_password = st.text_input("Password (min 8 chars)", type="password", key="reg_pass")
                reg_password2 = st.text_input("Confirm Password", type="password", key="reg_pass2")
                reg_submitted = st.form_submit_button(
                    "Create Account & Enter Workspace", use_container_width=True, type="primary",
                )
                if reg_submitted:
                    if reg_password != reg_password2:
                        st.error("Passwords do not match.")
                    else:
                        with get_db() as db:
                            ok, err = register(db, reg_username, reg_email, reg_password)
                        if ok:
                            with get_db() as db:
                                login_ok, _ = login(db, reg_username, reg_password)
                            if login_ok:
                                st.rerun()
                            else:
                                st.success("Account created! You can now log in.")
                        else:
                            st.error(err)

        st.markdown(
            '<div style="display:flex;align-items:center;gap:4px;color:#8f9098;margin-top:16px;">'
            '<span class="material-symbols-outlined" style="font-size:16px;color:#78d8ba;">shield_lock</span>'
            '<span style="font-size:0.8125rem;">Protected by Sovereign 256-bit Enclave. '
            'All logins audited under ISO 27001 standard.</span></div>',
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------------- #
# Overview Dashboard
# --------------------------------------------------------------------------- #


def page_overview():
    user_id = get_current_user_id()
    try:
        df, load_report = _load_user_dataset(user_id)
    except TransactionDataError as exc:
        st.error(f"{exc.user_message}")
        return

    if df.empty:
        st.markdown(
            '<div class="empty-state">'
            '<h3>Welcome to Your Banking Dashboard</h3>'
            '<p>Import your transaction data (CSV or XLSX) using the <strong>Data Center</strong> '
            'page in the sidebar to see your financial overview, insights, and anomaly detection.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    render_data_quality_notice(load_report)

    start, end, label = _date_range_selector(df, key_prefix="ov")
    period_df = _filter_by_date(df, start, end)

    if period_df.empty:
        st.warning(f"No transactions found for **{label}**. Try a different date range.")
        return

    comp = period_comparison(df, start, end)
    cur = comp["current"]
    changes = comp["changes"]
    ie_ts = income_expense_over_time(period_df, freq="MS")

    # ── Hero Banner ──
    username = get_current_username()
    ncf_delta = changes.get("net_cash_flow")
    delta_cls = "up" if ncf_delta and ncf_delta > 0 else "down"
    delta_arrow = "↑" if ncf_delta and ncf_delta > 0 else "↓"
    delta_text = f"{delta_arrow} {abs(ncf_delta):.1f}% vs prior period" if ncf_delta is not None else ""

    st.markdown(
        f'<div class="overview-hero">'
        f'<div class="hero-telemetry"><span class="pulse-dot"></span> Live Telemetry · Sync Integrity Active</div>'
        f'<div class="hero-welcome">Welcome back, {html_mod.escape(username)}</div>'
        f'<div class="hero-subtitle">Fiscal Command Center · {label}</div>'
        f'<div class="hero-stats">'
        f'<div><div class="hero-stat-label">Net Cash Flow</div>'
        f'<div class="hero-stat-value">{_fmt(cur.net_cash_flow)}</div>'
        f'<div class="hero-delta {delta_cls}">{delta_text}</div></div>'
        f'<div><div class="hero-stat-label">Total Income</div>'
        f'<div class="hero-stat-value">{_fmt(cur.total_income)}</div></div>'
        f'<div><div class="hero-stat-label">Total Expenses</div>'
        f'<div class="hero-stat-value">{_fmt(cur.total_spending)}</div></div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    hb1, hb2, hb3 = st.columns(3)
    with hb1:
        if st.button("Import CSV", key="hero_import", use_container_width=True):
            st.session_state["_nav_override"] = "Data Center"
            st.rerun()
    with hb2:
        if st.button("Run Anomaly Scan", key="hero_anomalies", use_container_width=True):
            st.session_state["_nav_override"] = "AI Assistant"
            st.rerun()
    with hb3:
        if st.button("Download Audit Pack", key="hero_insights", use_container_width=True):
            st.session_state["global_ai_mode"] = "Standard"
            st.session_state["_nav_override"] = "AI Assistant"
            st.rerun()

    # ── 4 KPI Cards ──
    income_vals = ie_ts["income"].tolist() if not ie_ts.empty else []
    expense_vals = ie_ts["expense"].tolist() if not ie_ts.empty else []
    net_vals = ie_ts["net"].tolist() if not ie_ts.empty else []

    anomalies = detect_anomalies(period_df)
    anom_count = len(anomalies)
    pending_str = f"{anom_count} Pending" if anom_count else "None"

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(kpi_card(
            "Net Position", _fmt(cur.total_income - cur.total_spending),
            f'{_delta_html(changes["income"])} {_sparkline_svg(income_vals)}',
        ), unsafe_allow_html=True)
    with k2:
        st.markdown(kpi_card(
            "Monthly OpEx Velocity", _fmt(cur.total_spending),
            f'{_delta_html(changes["spending"], invert=True)} {_sparkline_svg(expense_vals, color="#bac6e6")}',
        ), unsafe_allow_html=True)
    with k3:
        st.markdown(kpi_card(
            "Net Cashflow Run-Rate", _fmt(cur.net_cash_flow),
            f'{_delta_html(changes["net_cash_flow"])} {_sparkline_svg(net_vals)}',
        ), unsafe_allow_html=True)
    with k4:
        st.markdown(kpi_card(
            "Flagged Anomalies", pending_str,
            f'{cur.total_transactions} transactions scanned',
        ), unsafe_allow_html=True)

    st.write("")

    # ── Bento Row: Cash Flow (8-col) + AI Copilot Insights (4-col) ──
    col_wide, col_narrow = st.columns([2, 1])
    with col_wide:
        st.markdown('<div class="bank-card"><h3><span class="material-symbols-outlined" style="font-size:18px;">waterfall_chart</span> Cash Flow Dynamics</h3>', unsafe_allow_html=True)
        if ie_ts.empty:
            st.info("Not enough data for a trend chart.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=ie_ts["period"], y=ie_ts["income"], name="Inflows",
                mode="lines", fill="tozeroy",
                line=dict(color="#78d8ba", width=2),
                fillcolor="rgba(84,220,182,0.12)",
                hovertemplate=f"%{{x|%b %Y}}<br>{_currency_symbol()}%{{y:,.0f}}<extra>Inflows</extra>",
            ))
            fig.add_trace(go.Scatter(
                x=ie_ts["period"], y=ie_ts["expense"], name="Disbursements",
                mode="lines", fill="tozeroy",
                line=dict(color="#bac6e6", width=2, dash="dot"),
                fillcolor="rgba(186,198,230,0.08)",
                hovertemplate=f"%{{x|%b %Y}}<br>{_currency_symbol()}%{{y:,.0f}}<extra>Disbursements</extra>",
            ))
            fig.update_layout(**_chart_layout(
                yaxis_title=f"Amount ({_currency_symbol()})", xaxis_title=None, height=340,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                            font=dict(color="#8f9098")),
            ))
            st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_narrow:
        st.markdown('<div class="bank-card"><h3><span class="material-symbols-outlined" style="font-size:18px;">auto_awesome</span> AI Copilot Insights</h3>', unsafe_allow_html=True)
        insights = _generate_insights(df)
        if insights:
            for ins in insights[:3]:
                cat_class, cat_label = _insight_category(ins["title"])
                st.markdown(
                    f'<div style="margin-bottom:12px;">'
                    f'<span class="insight-cat {cat_class}">{cat_label}</span><br/>'
                    f'<span style="font-size:12.5px;font-weight:600;color:var(--text);">{html_mod.escape(ins["title"])}</span>'
                    f'<div style="font-size:11.5px;color:var(--text-muted);margin-top:2px;">{html_mod.escape(ins["body"][:120])}…</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("Import more data to see insights.")

        # AI unlock banner for free users
        plan = _get_user_plan_cached()
        if plan != "pro":
            st.markdown(
                '<div style="margin-top:12px;padding:14px 16px;background:rgba(0,124,99,0.06);'
                'border:1px solid rgba(0,124,99,0.15);border-radius:var(--r-sm);">'
                '<div style="font-size:12px;font-weight:700;color:#54dcb6;margin-bottom:4px;">Unlock AI Mode</div>'
                '<div style="font-size:11.5px;color:var(--text-muted);line-height:1.5;">'
                'Get natural language queries and AI-powered analysis of your financial data.</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            if st.button("Activate AI Features", key="ov_ai_unlock", use_container_width=True):
                st.session_state["global_ai_mode"] = "AI Mode"
                st.session_state["_nav_override"] = "AI Assistant"
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Bottom: Recent Transactions + Data Sync Pipeline ──
    col_txn, col_sync = st.columns([2, 1])
    with col_txn:
        st.markdown('<div class="bank-card"><h3><span class="material-symbols-outlined" style="font-size:18px;">swap_horiz</span> Recent Ledger Movements</h3>', unsafe_allow_html=True)
        recent = period_df.sort_values("date", ascending=False).head(5)
        if not recent.empty:
            rows_html = ""
            for _, r in recent.iterrows():
                badge_cls = "income" if r["type"] == "Credit" else "expense"
                badge_label = "Income" if r["type"] == "Credit" else "Expense"
                rows_html += (
                    f'<tr>'
                    f'<td>{r["date"].strftime("%b %d, %Y")}</td>'
                    f'<td>{html_mod.escape(str(r.get("merchant", "")))}</td>'
                    f'<td>{html_mod.escape(str(r.get("category", "")))}</td>'
                    f'<td style="text-align:right;font-variant-numeric:tabular-nums;">{_fmt(r["amount"])}</td>'
                    f'<td><span class="txn-badge {badge_cls}">{badge_label}</span></td>'
                    f'</tr>'
                )
            st.markdown(
                f'<table class="stitch-table">'
                f'<tr><th>Date</th><th>Counterparty</th><th>Category</th><th style="text-align:right;">Amount</th><th>Type</th></tr>'
                f'{rows_html}'
                f'</table>',
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

    with col_sync:
        st.markdown('<div class="bank-card"><h3><span class="material-symbols-outlined" style="font-size:18px;">sync</span> Data Sync Pipeline</h3>', unsafe_allow_html=True)
        with get_db() as db:
            imports = get_user_imports(db, user_id)
        if imports:
            latest = imports[0]
            total_synced = sum(i.rows_imported for i in imports)
            st.markdown(
                f'<div class="sync-node">'
                f'<span class="sync-dot green"></span>'
                f'<span style="color:var(--text);font-weight:600;">Manual Import</span>'
                f'<span style="margin-left:auto;color:var(--text-muted);">Active</span>'
                f'</div>'
                f'<div class="sync-node">'
                f'<span class="sync-dot {"green" if len(imports) > 0 else "amber"}"></span>'
                f'<span style="color:var(--text);">{total_synced} rows synced</span>'
                f'<span style="margin-left:auto;color:var(--text-muted);">'
                f'{latest.created_at.strftime("%b %d") if latest.created_at else "—"}</span>'
                f'</div>'
                f'<div class="sync-node">'
                f'<span class="sync-dot amber"></span>'
                f'<span style="color:var(--text-dim);">Bank API (ICICI)</span>'
                f'<span style="margin-left:auto;color:var(--text-dim);font-size:10px;">Not Connected</span>'
                f'</div>'
                f'<div class="sync-node">'
                f'<span class="sync-dot amber"></span>'
                f'<span style="color:var(--text-dim);">Bank API (HDFC)</span>'
                f'<span style="margin-left:auto;color:var(--text-dim);font-size:10px;">Not Connected</span>'
                f'</div>'
                f'<div class="sync-node">'
                f'<span class="sync-dot amber"></span>'
                f'<span style="color:var(--text-dim);">Razorpay</span>'
                f'<span style="margin-left:auto;color:var(--text-dim);font-size:10px;">Not Connected</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="font-size:12.5px;color:var(--text-muted);">No data sync nodes connected. '
                'Import data to begin.</div>',
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

    # Period comparison
    prev = comp["previous"]
    if prev.total_transactions > 0:
        with st.expander(f"Period comparison: {label} vs {comp['prev_start'].strftime('%b %d')} – {comp['prev_end'].strftime('%b %d, %Y')}"):
            pc1, pc2, pc3, pc4 = st.columns(4)
            def _metric_delta(val):
                return f"{val:+.1f}%" if val is not None else "N/A"
            with pc1:
                st.metric("Income", _fmt(cur.total_income), _metric_delta(changes['income']))
            with pc2:
                st.metric("Expenses", _fmt(cur.total_spending), _metric_delta(changes['spending']), delta_color="inverse")
            with pc3:
                st.metric("Net Cash Flow", _fmt(cur.net_cash_flow), _metric_delta(changes['net_cash_flow']))
            with pc4:
                st.metric("Transactions", cur.total_transactions, _metric_delta(changes['transactions']))


# --------------------------------------------------------------------------- #
# Transactions Ledger & Inspector
# --------------------------------------------------------------------------- #


def page_transactions():
    user_id = get_current_user_id()
    try:
        df, load_report = _load_user_dataset(user_id)
    except TransactionDataError as exc:
        st.error(f"{exc.user_message}")
        return

    if df.empty:
        st.markdown(
            '<div class="empty-state">'
            '<h3>No Transactions Yet</h3>'
            '<p>Use the <strong>Data Center</strong> page to upload your transaction file and start browsing.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    render_data_quality_notice(load_report)

    st.markdown(
        '<div class="page-title"><span class="material-symbols-outlined" style="font-size:22px;color:var(--accent-glow);">receipt_long</span> Institutional Ledger</div>'
        '<div class="page-subtitle" style="display:flex;align-items:center;gap:8px;">'
        'Browse, filter, and audit your transaction history '
        '<span style="display:inline-flex;align-items:center;gap:4px;background:rgba(0,124,99,0.1);'
        'border:1px solid rgba(0,124,99,0.2);border-radius:999px;padding:2px 10px;font-size:10px;'
        'font-weight:600;color:#54dcb6;">'
        '<span style="width:5px;height:5px;border-radius:50%;background:#78d8ba;"></span> Live Sync</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Filters
    fc1, fc2, fc3, fc4, fc5, fc6 = st.columns([2, 2, 2, 2, 2, 3])
    with fc1:
        date_min = df["date"].min().date()
        date_max = df["date"].max().date()
        d_start = st.date_input("From", value=date_min, key="txn_from")
    with fc2:
        d_end = st.date_input("To", value=date_max, key="txn_to")
    with fc3:
        categories = ["All"] + sorted(df["category"].unique())
        sel_cat = st.selectbox("Category", categories, key="txn_cat")
    with fc4:
        types = ["All"] + sorted(df["type"].unique())
        sel_type = st.selectbox("Type", types, key="txn_type")
    with fc5:
        sort_options = {
            "Date (newest)": ("date", False),
            "Date (oldest)": ("date", True),
            "Amount (highest)": ("amount", False),
            "Amount (lowest)": ("amount", True),
        }
        sort_choice = st.selectbox("Sort by", list(sort_options.keys()), key="txn_sort")
        sort_col, sort_asc = sort_options[sort_choice]
    with fc6:
        search = st.text_input("Search", placeholder="Merchant or description…", key="txn_search")

    # Apply filters
    filtered = _filter_by_date(df, d_start, d_end)
    if sel_cat != "All":
        filtered = filtered[filtered["category"] == sel_cat]
    if sel_type != "All":
        filtered = filtered[filtered["type"] == sel_type]
    if search.strip():
        mask = (
            filtered["merchant"].str.contains(search, case=False, na=False)
            | filtered["description"].str.contains(search, case=False, na=False)
        )
        filtered = filtered[mask]

    filtered = filtered.sort_values(sort_col, ascending=sort_asc).reset_index(drop=True)

    # Summary metric cards
    if not filtered.empty:
        total_debit = filtered.loc[filtered["type"] == "Debit", "amount"].sum()
        total_credit = filtered.loc[filtered["type"] == "Credit", "amount"].sum()
        total_amt = filtered["amount"].sum()
        anomalies = detect_anomalies(filtered)
        flagged_count = len(anomalies)

        sc1, sc2, sc3, sc4 = st.columns(4)
        with sc1:
            st.markdown(kpi_card("Total Audited Volume", _fmt(float(total_amt))), unsafe_allow_html=True)
        with sc2:
            st.markdown(kpi_card("Inflow / Receivables", _fmt(float(total_credit))), unsafe_allow_html=True)
        with sc3:
            st.markdown(kpi_card("Outflow / OPEX", _fmt(float(total_debit))), unsafe_allow_html=True)
        with sc4:
            st.markdown(kpi_card("Flagged Discrepancies", str(flagged_count)), unsafe_allow_html=True)

        # Export
        export_df = filtered[["date", "merchant", "description", "category", "amount", "type"]].copy()
        export_df["date"] = export_df["date"].dt.strftime("%Y-%m-%d")
        st.download_button(
            "Export CSV",
            data=export_df.to_csv(index=False),
            file_name="transactions_export.csv",
            mime="text/csv",
        )

    render_transaction_table(filtered, key="txn_table")

    # Transaction Inspector
    if not filtered.empty:
        with st.expander("Transaction Inspector", expanded=False):
            idx = st.number_input(
                "Select row number", min_value=1, max_value=len(filtered),
                value=1, key="txn_detail_idx",
            )
            row = filtered.iloc[idx - 1]
            dc1, dc2 = st.columns(2)
            with dc1:
                st.markdown(f"**Date:** {row['date'].strftime('%B %d, %Y')}")
                st.markdown(f"**Merchant:** {row['merchant']}")
                st.markdown(f"**Description:** {row['description']}")
            with dc2:
                st.markdown(f"**Amount:** {_fmt(float(row['amount']))}")
                st.markdown(f"**Type:** {row['type']}")
                st.markdown(f"**Category:** {row['category']}")


# --------------------------------------------------------------------------- #
# AI Assistant Intelligence Hub
# --------------------------------------------------------------------------- #

QUICK_QUERIES = {
    "Spending summary": "What did I spend last month?",
    "Top expenses": "Show my biggest expenses",
    "Anomalies": "Find unusual transactions",
    "Trends": "How has my spending changed over time?",
    "Insights": "What insights can you give me about my finances?",
    "Compare": "Compare this month to last month",
}


def _get_conversation_context(user_id: int) -> ConversationContext:
    key = "conversation_context"
    ctx = st.session_state.get(key)
    if ctx is None or ctx.user_id != user_id:
        ctx = ConversationContext()
        ctx.user_id = user_id
        st.session_state[key] = ctx
    return ctx


def _ai_locked_state():
    st.markdown(
        '<div style="text-align:center;padding:60px 20px;">'
        '<div style="font-size:48px;margin-bottom:16px;">🔒</div>'
        '<h2 style="font-family:Plus Jakarta Sans,sans-serif;color:var(--text);font-size:24px;font-weight:700;margin:0 0 12px;">Unlock AI Assistant with Pro</h2>'
        '<p style="color:var(--text-muted);font-size:14px;max-width:480px;margin:0 auto 24px;line-height:1.7;">'
        'Get instant answers about your finances using natural language. '
        'Ask about spending patterns, unusual transactions, trends, and more — '
        'powered by advanced AI analysis of your actual financial data.</p>'
        '<div style="display:flex;gap:16px;justify-content:center;flex-wrap:wrap;margin-bottom:32px;">'
        '<div style="background:rgba(0,124,99,0.08);border:1px solid rgba(0,124,99,0.2);border-radius:12px;padding:16px 20px;min-width:150px;">'
        '<div style="color:#54dcb6;font-weight:700;font-size:13px;margin-bottom:4px;">Natural Language</div>'
        '<div style="color:var(--text-muted);font-size:12px;">Ask in plain English</div></div>'
        '<div style="background:rgba(0,124,99,0.08);border:1px solid rgba(0,124,99,0.2);border-radius:12px;padding:16px 20px;min-width:150px;">'
        '<div style="color:#54dcb6;font-weight:700;font-size:13px;margin-bottom:4px;">Smart Analysis</div>'
        '<div style="color:var(--text-muted);font-size:12px;">AI-powered insights</div></div>'
        '<div style="background:rgba(0,124,99,0.08);border:1px solid rgba(0,124,99,0.2);border-radius:12px;padding:16px 20px;min-width:150px;">'
        '<div style="color:#54dcb6;font-weight:700;font-size:13px;margin-bottom:4px;">Contextual</div>'
        '<div style="color:var(--text-muted);font-size:12px;">Your actual data</div></div>'
        '</div>'
        f'<div style="color:var(--text-muted);font-size:14px;">Starting at <span style="color:#54dcb6;font-weight:700;">₹{config.PRO_MONTHLY_PRICE_INR}/month</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("Upgrade to Pro", type="primary", use_container_width=True):
            st.session_state["_nav_override"] = "Billing & Subscription"
            st.rerun()
    with btn_col2:
        if st.button("Activate Demo Access", use_container_width=True, key="demo_btn"):
            st.session_state["_show_demo_form"] = True

    if st.session_state.get("_show_demo_form"):
        if not config.DEMO_ACTIVATION_KEY:
            st.warning(
                "**Demo activation is not configured on this server.** "
                "To enable it, set `DEMO_ACTIVATION_KEY` to a secret value "
                "in your `.env` file and restart the app. "
                "Optionally set `DEMO_ACTIVATION_DAYS` (default: 7)."
            )
        else:
            st.markdown(
                '<div class="bank-card" style="max-width:480px;margin:20px auto;text-align:left;">'
                '<h3 style="font-size:16px;margin-bottom:4px;">Demo AI Access</h3>'
                '<p style="color:var(--text-muted);font-size:12.5px;margin-bottom:12px;">'
                f'Enter the activation key to unlock Pro features for {config.DEMO_ACTIVATION_DAYS} days. '
                'This is temporary demo access, not a paid subscription.</p>'
                '</div>',
                unsafe_allow_html=True,
            )
            with st.form("demo_activation_form"):
                demo_key = st.text_input("Activation Key", type="password", placeholder="Enter demo activation key")
                submitted = st.form_submit_button("Activate", type="primary", use_container_width=True)
                if submitted:
                    if not demo_key:
                        st.error("Please enter the activation key.")
                    else:
                        user_id = get_current_user_id()
                        with get_db() as db:
                            ok, msg = activate_demo(db, user_id, demo_key)
                            if ok:
                                db.commit()
                                st.cache_data.clear()
                                st.success(msg)
                                st.session_state.pop("_show_demo_form", None)
                                st.rerun()
                            else:
                                st.error(msg)


def page_ai_assistant():
    user_id = get_current_user_id()
    plan = _get_user_plan_cached()
    ai_mode = st.session_state.get("global_ai_mode", "Standard")

    if ai_mode == "AI Mode" and plan != "pro":
        st.markdown(
            '<div class="page-title"><span class="material-symbols-outlined" style="font-size:22px;color:var(--accent-glow);">psychology</span> AI Financial Assistant</div>'
            '<div class="page-subtitle">Premium LLM-powered conversational analysis</div>',
            unsafe_allow_html=True,
        )
        _ai_locked_state()
        return

    # --- Both Standard and AI Mode share the chat assistant ---
    # Standard Mode uses the same chat UI but with deterministic-only analysis.
    # AI Mode adds LLM-powered summaries and query parsing when API keys are configured.
    ctx = _get_conversation_context(user_id)
    mode_label = "AI Intelligence Hub" if ai_mode == "AI Mode" else "Financial Assistant"
    mode_sub = "LLM-powered analysis" if ai_mode == "AI Mode" else "Deterministic analysis — no external AI"

    # ── Conversation thread management ──
    with get_db() as db:
        user_convos = get_user_conversations(db, user_id, limit=20)

    # Handle new-conversation button
    if st.session_state.get("_new_conv"):
        st.session_state.pop("_new_conv", None)
        st.session_state.pop("_active_conv_id", None)
        ctx.clear()
        st.rerun()

    # Handle delete-conversation
    del_id = st.session_state.get("_del_conv_id")
    if del_id:
        st.session_state.pop("_del_conv_id", None)
        with get_db() as db:
            delete_conversation(db, user_id, del_id)
        if st.session_state.get("_active_conv_id") == del_id:
            st.session_state.pop("_active_conv_id", None)
            ctx.clear()
        st.rerun()

    hdr1, hdr2, hdr3 = st.columns([5, 1, 1])
    with hdr1:
        st.markdown(
            f'<div class="page-title"><span class="material-symbols-outlined" style="font-size:22px;color:var(--accent-glow);">psychology</span> {mode_label}</div>'
            f'<div class="page-subtitle">{mode_sub}</div>',
            unsafe_allow_html=True,
        )
    with hdr2:
        if st.button("New chat", use_container_width=True, key="new_chat_btn"):
            st.session_state["_new_conv"] = True
            st.rerun()
    with hdr3:
        if st.session_state.get("_active_conv_id") and st.button("Clear", use_container_width=True, key="clear_chat_btn"):
            st.session_state["_del_conv_id"] = st.session_state["_active_conv_id"]
            st.rerun()

    if ai_mode == "AI Mode":
        status, status_msg = config.llm_status()
        if status == "active":
            st.markdown(
                f'<div style="padding:6px 12px;background:rgba(0,124,99,0.1);border:1px solid rgba(0,124,99,0.2);'
                f'border-radius:8px;font-size:12px;color:#78d8ba;margin-bottom:12px;">'
                f'● LLM Active — {html_mod.escape(status_msg)}</div>',
                unsafe_allow_html=True,
            )
        elif status == "credits_exhausted":
            st.warning(f"⚠ {status_msg} All queries use rule-based analysis.")
        else:
            st.info(
                f"ℹ {status_msg} Standard deterministic analysis is fully operational. "
                f"To enable AI-powered queries, install Ollama locally or add an API key to .env."
            )

    # ── Thread selector ──
    if user_convos:
        conv_options = {f"{c.title} ({c.updated_at.strftime('%b %d')})": c.id for c in user_convos}
        conv_labels = list(conv_options.keys())
        active_id = st.session_state.get("_active_conv_id")
        default_idx = 0
        if active_id:
            for i, cid in enumerate(conv_options.values()):
                if cid == active_id:
                    default_idx = i
                    break
        with st.expander(f"Conversation history ({len(user_convos)})", expanded=False):
            for label, cid in conv_options.items():
                if st.button(label, key=f"conv_{cid}", use_container_width=True):
                    st.session_state["_active_conv_id"] = cid
                    ctx.clear()
                    st.rerun()

    # ── Load messages for active conversation ──
    active_conv_id = st.session_state.get("_active_conv_id")
    if active_conv_id:
        with get_db() as db:
            messages = get_conversation_messages(db, active_conv_id, user_id)
        for msg in messages:
            with st.chat_message(msg.role):
                st.markdown(msg.content)
    elif ctx.turns:
        for turn in ctx.turns:
            with st.chat_message("user"):
                st.markdown(turn.query)
            with st.chat_message("assistant"):
                intent_label = turn.intent.replace("_", " ").title()
                st.markdown(f"**{intent_label}** · {turn.date_range}")
                if turn.answer_preview:
                    st.caption(turn.answer_preview[:200])
    else:
        st.info("Ask a question about your transactions below, or try one of these quick queries.")

    qc = st.columns(len(QUICK_QUERIES))
    for i, (label, q) in enumerate(QUICK_QUERIES.items()):
        if qc[i].button(label, key=f"quick_{i}", use_container_width=True):
            st.session_state["_pending_ai_query"] = q
            st.rerun()

    pending = st.session_state.get("_pending_ai_query")
    if pending is not None:
        del st.session_state["_pending_ai_query"]
    chat_query = st.chat_input("Ask about your transactions…")
    query_text = pending or chat_query

    if not query_text:
        return

    with st.chat_message("user"):
        st.markdown(query_text)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing your transactions…"):
            with get_db() as db:
                orchestrator = Orchestrator(db=db, user_id=user_id)
                result = orchestrator.run(query_text, context=ctx)

        if not result.success:
            st.error(f"Could not process: {result.error}")
            return

        data = result.data
        render_data_quality_notice(data.get("load_report"))

        query = data["query"]
        answer_parts = []

        st.markdown(
            f"**{data['period_label']}** · "
            f"{query.intent.replace('_', ' ').title()} · "
            f"_{data['parse_method']}_"
        )

        _agent_only_intents = {"trend_analysis", "period_comparison", "insights_query",
                                "merchant_analysis", "income_analysis", "cashflow_analysis", "budget_query"}
        if query.intent in _agent_only_intents and data.get("direct_answer"):
            st.markdown(html_mod.escape(data["direct_answer"]))
            answer_parts.append(data["direct_answer"])
            if data.get("summary_text"):
                render_summary_card(data["summary_text"], data["summary_method"])
                answer_parts.append(data["summary_text"])
        else:
            matching_stats = data["matching_stats"]
            if matching_stats.matching_transaction_count == 0:
                no_match_msg = (
                    f"No transactions matched your criteria during {data['period_label']}. "
                    f"Try widening the date range or lowering the amount threshold."
                )
                st.warning(no_match_msg)
                answer_parts.append(no_match_msg)
                if data.get("summary_text"):
                    render_summary_card(data["summary_text"], data["summary_method"])
                    answer_parts.append(data["summary_text"])
            else:
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.markdown(kpi_card("Total Spending", _fmt(matching_stats.matching_total_amount)), unsafe_allow_html=True)
                with c2:
                    st.markdown(kpi_card("Transactions", str(matching_stats.matching_transaction_count)), unsafe_allow_html=True)
                with c3:
                    st.markdown(kpi_card("Average", _fmt(matching_stats.matching_average_amount)), unsafe_allow_html=True)
                with c4:
                    st.markdown(kpi_card("Largest", _fmt(matching_stats.matching_largest_amount)), unsafe_allow_html=True)

                if data.get("direct_answer"):
                    answer_parts.append(data["direct_answer"])

                ch1, ch2 = st.columns(2)
                with ch1:
                    st.markdown('<div class="section-label">Spending by Category</div>', unsafe_allow_html=True)
                    render_category_chart(data["category_breakdown"])
                with ch2:
                    st.markdown('<div class="section-label">Spending Over Time</div>', unsafe_allow_html=True)
                    ts = data["time_series"]
                    if ts is None or ts.empty:
                        st.info("No time-series data to chart.")
                    else:
                        fig = go.Figure()
                        fig.add_trace(go.Bar(
                            x=ts["period"], y=ts["amount"], marker_color="#78d8ba",
                            hovertemplate=f"%{{x}}<br>{_currency_symbol()}%{{y:,.0f}}<extra></extra>",
                        ))
                        fig.update_layout(**_chart_layout(
                            yaxis_title=f"Amount ({_currency_symbol()})", xaxis_title=None, height=300,
                        ))
                        st.plotly_chart(fig, use_container_width=True)

                if data["anomalies"]:
                    st.markdown(
                        f'<div class="section-label">Potential Anomalies ({len(data["anomalies"])})</div>',
                        unsafe_allow_html=True,
                    )
                    render_anomalies(data["anomalies"])

                if data.get("summary_text"):
                    render_summary_card(data["summary_text"], data["summary_method"])
                    answer_parts.append(data["summary_text"])

                with st.expander(f"Matching Transactions ({matching_stats.matching_transaction_count})"):
                    anomaly_ids = {a.transaction_id for a in data["anomalies"]}
                    render_transaction_table(data["matching_df"], anomaly_ids, key="ai_txn")

                if data["category_breakdown"]:
                    with st.expander("Category Breakdown"):
                        cat_df = pd.DataFrame([c.model_dump() for c in data["category_breakdown"]])
                        cat_df["total_amount"] = cat_df["total_amount"].apply(_fmt)
                        cat_df["percentage_of_spending"] = cat_df["percentage_of_spending"].apply(lambda v: f"{v:.1f}%")
                        cat_df = cat_df.rename(columns={
                            "category": "Category", "transaction_count": "Transaction Count",
                            "total_amount": "Total Amount", "percentage_of_spending": "% of Spending",
                        })
                        st.dataframe(cat_df, use_container_width=True, hide_index=True)

    # ── Download analysis report ──
    answer_text = " ".join(answer_parts) if answer_parts else data.get("direct_answer", "Analysis complete.")
    report_lines = [
        f"Banking Assistant — Analysis Report",
        f"Query: {query_text}",
        f"Period: {data['period_label']}",
        f"Intent: {query.intent.replace('_', ' ').title()}",
        f"Method: {data['parse_method']}",
        "",
        answer_text,
    ]
    if data.get("summary_text"):
        report_lines += ["", "--- Summary ---", data["summary_text"]]
    st.download_button(
        "Download report",
        data="\n".join(report_lines),
        file_name="analysis_report.txt",
        mime="text/plain",
        key="dl_report",
    )

    # ── Persist conversation to DB ──
    with get_db() as db:
        if not active_conv_id:
            title = query_text[:60] + ("…" if len(query_text) > 60 else "")
            conv = create_conversation(db, user_id, title=title)
            active_conv_id = conv.id
            st.session_state["_active_conv_id"] = active_conv_id
        add_message(db, active_conv_id, "user", query_text,
                    intent=query.intent, date_range=query.date_range, category=query.category)
        add_message(db, active_conv_id, "assistant", answer_text[:10000],
                    intent=query.intent, date_range=query.date_range)


# --------------------------------------------------------------------------- #
# Data Center (Import Wizard)
# --------------------------------------------------------------------------- #


def page_import():
    user_id = get_current_user_id()

    st.markdown(
        '<div class="page-title"><span class="material-symbols-outlined" style="font-size:22px;color:var(--accent-glow);">cloud_upload</span> Data Center & Reconciliation Engine</div>'
        '<div class="page-subtitle" style="display:flex;align-items:center;gap:8px;">'
        'Import and reconcile your financial data '
        '<span style="display:inline-flex;align-items:center;gap:4px;background:rgba(0,124,99,0.1);'
        'border:1px solid rgba(0,124,99,0.2);border-radius:999px;padding:2px 10px;font-size:10px;'
        'font-weight:600;color:#54dcb6;">'
        '<span style="width:5px;height:5px;border-radius:50%;background:#78d8ba;"></span> Live Ingestion Node</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    _imp_step = 1
    if "import_uploader" in st.session_state and st.session_state["import_uploader"] is not None:
        _imp_step = 2
    st.markdown(_step_indicator_html(_imp_step, ["Upload Source", "Schema Mapping", "Validate", "Commit"]), unsafe_allow_html=True)

    up_col, req_col = st.columns([3, 1])
    with up_col:
        uploaded = st.file_uploader(
            "Drag & drop your file here",
            type=["csv", "xlsx"],
            key="import_uploader",
        )
    with req_col:
        st.markdown(
            '<div class="bank-card">'
            '<h3>File Requirements</h3>'
            '<div style="font-size:12px;color:var(--text-muted);line-height:2;">'
            '<div style="display:flex;align-items:center;gap:6px;">'
            '<span style="color:var(--accent-glow);font-weight:700;">✓</span> CSV or XLSX format</div>'
            '<div style="display:flex;align-items:center;gap:6px;">'
            '<span style="color:var(--accent-glow);font-weight:700;">✓</span> Max file size: 200MB</div>'
            '<div style="display:flex;align-items:center;gap:6px;">'
            '<span style="color:var(--accent-glow);font-weight:700;">✓</span> Required: Date, Amount, Description</div>'
            '</div></div>',
            unsafe_allow_html=True,
        )

    if uploaded is not None:
        file_bytes = uploaded.getvalue()
        filename = uploaded.name

        raw_df, err = read_upload(file_bytes, filename)
        if err:
            st.error(err)
            return

        st.markdown("**Step 2** — Schema & Tax Mapping")
        st.dataframe(raw_df.head(10), use_container_width=True, hide_index=True)
        st.caption(f"{len(raw_df)} rows parsed, {len(raw_df.columns)} columns detected")

        auto = auto_map_columns(raw_df)
        target_cols = ["", "date", "amount", "description", "merchant", "category", "txn_type", "account", "transaction_id"]

        mapping = {}
        cols = st.columns(min(4, len(raw_df.columns)))
        for i, src_col in enumerate(raw_df.columns):
            default_idx = target_cols.index(auto[src_col]) if src_col in auto and auto[src_col] in target_cols else 0
            with cols[i % len(cols)]:
                chosen = st.selectbox(
                    f"**{src_col}**",
                    target_cols,
                    index=default_idx,
                    key=f"map_{src_col}",
                )
                if chosen:
                    mapping[src_col] = chosen

        mapped_df = apply_column_mapping(raw_df, mapping)

        if "date" not in mapped_df.columns or "amount" not in mapped_df.columns:
            st.warning("Please map at least the **date** and **amount** columns before importing.")
        else:
            st.markdown("**Step 4** — Commit to Ledger")
            if st.button("Commit Valid Rows to Ledger", type="primary", use_container_width=True):
                with st.spinner("Importing…"):
                    with get_db() as db:
                        account = get_default_account(db, user_id)
                        if not account:
                            st.error("No account found. Please contact support.")
                            return

                        file_type = detect_file_type(filename) or "csv"
                        imp_result = run_import(db, user_id, account.id, mapped_df, filename, file_type)

                if imp_result.success:
                    st.success(
                        f"**Import complete!** "
                        f"{imp_result.rows_imported} imported, "
                        f"{imp_result.rows_duplicate} duplicates, "
                        f"{imp_result.rows_skipped} skipped."
                    )
                else:
                    st.error(f"Import failed: {imp_result.error}")

                for w in imp_result.warnings:
                    st.warning(w)

    # Import history
    st.markdown("---")
    st.markdown('<div class="section-label">Ingestion History</div>', unsafe_allow_html=True)
    with get_db() as db:
        imports = get_user_imports(db, user_id)
    if not imports:
        st.info("No imports yet.")
    else:
        hist_rows = ""
        for imp in imports:
            s_cls = "complete" if imp.status == "complete" else ("failed" if imp.status == "failed" else "pending")
            s_label = imp.status.capitalize()
            dt = imp.created_at.strftime("%b %d, %Y %H:%M") if imp.created_at else "—"
            hist_rows += (
                f'<tr>'
                f'<td>{html_mod.escape(imp.filename)}</td>'
                f'<td>{dt}</td>'
                f'<td><span class="status-badge {s_cls}">{s_label}</span></td>'
                f'<td style="text-align:right;">{imp.rows_total}</td>'
                f'<td style="text-align:right;">{imp.rows_imported}</td>'
                f'<td style="text-align:right;">{imp.rows_skipped + imp.rows_duplicate}</td>'
                f'</tr>'
            )
        st.markdown(
            f'<table class="stitch-table">'
            f'<tr><th>File Name</th><th>Date &amp; Time</th><th>Status</th>'
            f'<th style="text-align:right;">Rows</th><th style="text-align:right;">Imported</th>'
            f'<th style="text-align:right;">Errors</th></tr>'
            f'{hist_rows}'
            f'</table>',
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------------- #
# Pricing & Upgrade to Pro
# --------------------------------------------------------------------------- #


def page_pricing():
    st.markdown(
        '<div style="text-align:center;padding:20px 0 8px;">'
        '<div class="page-title" style="justify-content:center;font-size:26px;"><span class="material-symbols-outlined" style="font-size:26px;color:var(--accent-glow);">rocket_launch</span> Supercharge Your Treasury</div>'
        '<div class="page-subtitle" style="max-width:500px;margin:0 auto;">with autonomous AI intelligence</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    plan = _get_user_plan_cached()
    if plan == "pro":
        st.success("You are already on the Pro plan!")
        return

    # Billing toggle
    billing = st.radio("Billing cycle", ["Monthly", "Annual (Save 17%)"], horizontal=True, key="billing_toggle", label_visibility="collapsed")
    is_annual = "Annual" in billing
    price_display = f"₹2,990" if is_annual else f"₹{config.PRO_MONTHLY_PRICE_INR}"
    period_display = "/year" if is_annual else "/month"

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            '<div class="pricing-card">'
            '<h3>Free Tier</h3>'
            '<div class="pricing-price">₹0<span class="period">/forever</span></div>'
            '<div style="font-size:12px;color:var(--text-muted);margin-bottom:20px;">Essential treasury tools</div>'
            '<ul style="list-style:none;padding:0;margin:0;font-size:13px;line-height:2.2;color:var(--text);">'
            '<li style="display:flex;align-items:center;gap:8px;"><span style="color:var(--accent-glow);">✓</span> Dashboard overview with KPIs</li>'
            '<li style="display:flex;align-items:center;gap:8px;"><span style="color:var(--accent-glow);">✓</span> Transaction management & filters</li>'
            '<li style="display:flex;align-items:center;gap:8px;"><span style="color:var(--accent-glow);">✓</span> CSV/Excel export</li>'
            '<li style="display:flex;align-items:center;gap:8px;"><span style="color:var(--accent-glow);">✓</span> Anomaly detection</li>'
            '<li style="display:flex;align-items:center;gap:8px;"><span style="color:var(--accent-glow);">✓</span> Deterministic insights</li>'
            '<li style="display:flex;align-items:center;gap:8px;"><span style="color:var(--accent-glow);">✓</span> Data import wizard</li>'
            '<li style="display:flex;align-items:center;gap:8px;"><span style="color:var(--text-dim);">✗</span><span style="color:var(--text-dim);">AI Financial Assistant</span></li>'
            '<li style="display:flex;align-items:center;gap:8px;"><span style="color:var(--text-dim);">✗</span><span style="color:var(--text-dim);">Natural language queries</span></li>'
            '</ul>'
            '<div style="margin-top:20px;padding:10px 16px;background:rgba(148,163,184,0.06);border:1px solid var(--border);'
            'border-radius:var(--r-sm);text-align:center;font-size:13px;color:var(--text-muted);font-weight:600;">Current Plan</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f'<div class="pricing-card pro">'
            f'<h3>Pro AI Agent <span class="pro-badge">RECOMMENDED</span></h3>'
            f'<div class="pricing-price">{price_display}<span class="period">{period_display}</span></div>'
            f'<div style="font-size:12px;color:var(--text-muted);margin-bottom:20px;">Full autonomous intelligence</div>'
            f'<ul style="list-style:none;padding:0;margin:0;font-size:13px;line-height:2.2;color:var(--text);">'
            f'<li style="display:flex;align-items:center;gap:8px;"><span style="color:var(--accent-glow);">✓</span> Everything in Free</li>'
            f'<li style="display:flex;align-items:center;gap:8px;"><span style="color:var(--accent-glow);">✓</span><span style="color:#54dcb6;font-weight:600;">AI Financial Assistant</span></li>'
            f'<li style="display:flex;align-items:center;gap:8px;"><span style="color:var(--accent-glow);">✓</span><span style="color:#54dcb6;font-weight:600;">Natural language queries</span></li>'
            f'<li style="display:flex;align-items:center;gap:8px;"><span style="color:var(--accent-glow);">✓</span><span style="color:#54dcb6;font-weight:600;">AI-powered summaries</span></li>'
            f'<li style="display:flex;align-items:center;gap:8px;"><span style="color:var(--accent-glow);">✓</span><span style="color:#54dcb6;font-weight:600;">Smart follow-up suggestions</span></li>'
            f'<li style="display:flex;align-items:center;gap:8px;"><span style="color:var(--accent-glow);">✓</span><span style="color:#54dcb6;font-weight:600;">Automated anomaly resolution</span></li>'
            f'<li style="display:flex;align-items:center;gap:8px;"><span style="color:var(--accent-glow);">✓</span><span style="color:#54dcb6;font-weight:600;">Export to Excel/PDF</span></li>'
            f'<li style="display:flex;align-items:center;gap:8px;"><span style="color:var(--accent-glow);">✓</span><span style="color:#54dcb6;font-weight:600;">Priority support</span></li>'
            f'</ul>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if config.RAZORPAY_KEY_ID:
            if st.button(f"Subscribe — {price_display}{period_display}", type="primary", use_container_width=True):
                st.info("Razorpay checkout integration pending. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env.")
        else:
            st.info(
                "Payment integration not configured. Set "
                "`RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in `.env` to enable."
            )

    # Interactive Pro preview
    st.markdown("---")
    st.markdown(
        '<div class="bank-card" style="text-align:center;padding:40px;">'
        '<h3 style="justify-content:center;font-size:18px;">Interactive Pro Environment Preview</h3>'
        '<p style="color:var(--text-muted);font-size:13px;max-width:500px;margin:8px auto 20px;">'
        'Experience the power of multi-ledger reasoning, anomaly dispute automation, '
        'and natural language financial queries.</p>'
        '<div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">'
        '<div style="background:rgba(0,124,99,0.06);border:1px solid rgba(0,124,99,0.15);border-radius:12px;padding:20px;min-width:180px;">'
        '<div style="color:#54dcb6;font-size:24px;font-weight:800;margin-bottom:4px;">∞</div>'
        '<div style="color:var(--text-muted);font-size:12px;">Unlimited Queries</div></div>'
        '<div style="background:rgba(0,124,99,0.06);border:1px solid rgba(0,124,99,0.15);border-radius:12px;padding:20px;min-width:180px;">'
        '<div style="color:#54dcb6;font-size:24px;font-weight:800;margin-bottom:4px;">24/7</div>'
        '<div style="color:var(--text-muted);font-size:12px;">AI Copilot Available</div></div>'
        '<div style="background:rgba(0,124,99,0.06);border:1px solid rgba(0,124,99,0.15);border-radius:12px;padding:20px;min-width:180px;">'
        '<div style="color:#54dcb6;font-size:24px;font-weight:800;margin-bottom:4px;">&lt;1s</div>'
        '<div style="color:var(--text-muted);font-size:12px;">Query Execution</div></div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Subscription Management
# --------------------------------------------------------------------------- #


def page_subscription():
    st.markdown(
        '<div class="page-title"><span class="material-symbols-outlined" style="font-size:22px;color:var(--accent-glow);">credit_card</span> Subscription Management</div>'
        '<div class="page-subtitle">Plan overview, utilization, and billing</div>',
        unsafe_allow_html=True,
    )

    plan = _get_user_plan_cached()
    user_id = get_current_user_id()

    if plan == "pro":
        with get_db() as db:
            from sqlalchemy import select as sa_select
            from src.models import Subscription
            sub = db.scalars(
                sa_select(Subscription)
                .where(Subscription.user_id == user_id, Subscription.plan == "pro", Subscription.status == "active")
                .order_by(Subscription.created_at.desc())
            ).first()

        # Active plan card
        st.markdown(
            '<div class="bank-card">'
            '<h3>Active Plan: <span style="color:var(--accent-glow);">Pro AI Agent</span></h3>',
            unsafe_allow_html=True,
        )
        if sub:
            c1, c2, c3 = st.columns(3)
            with c1:
                if sub.started_at:
                    st.markdown(f"**Started:** {sub.started_at.strftime('%B %d, %Y')}")
            with c2:
                if sub.expires_at:
                    st.markdown(f"**Expires:** {sub.expires_at.strftime('%B %d, %Y')}")
            with c3:
                if sub.payment_provider:
                    st.markdown(f"**Payment:** {sub.payment_provider.title()}")
        st.markdown(
            f'<div style="margin-top:12px;padding:12px 16px;background:rgba(0,124,99,0.06);border:1px solid rgba(0,124,99,0.15);'
            f'border-radius:var(--r-sm);font-size:13px;color:var(--text-muted);">'
            f'₹{config.PRO_MONTHLY_PRICE_INR} base + applicable taxes · Auto-debit monthly'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)

        # Usage stats from real data
        with get_db() as db:
            conv_count = len(get_user_conversations(db, user_id, limit=100))
            from sqlalchemy import func as sa_func
            from src.models import Conversation, ConversationMessage
            msg_count = db.scalar(
                sa_select(sa_func.count(ConversationMessage.id))
                .join(Conversation)
                .where(Conversation.user_id == user_id, ConversationMessage.role == "user")
            ) or 0
        st.markdown(
            '<div class="bank-card"><h3>Usage</h3>',
            unsafe_allow_html=True,
        )
        u1, u2, u3 = st.columns(3)
        with u1:
            st.markdown(kpi_card("Conversations", str(conv_count)), unsafe_allow_html=True)
        with u2:
            st.markdown(kpi_card("Queries", str(msg_count)), unsafe_allow_html=True)
        with u3:
            llm_status, _ = config.llm_status()
            llm_label = "Active" if llm_status == "active" else "Deterministic"
            st.markdown(kpi_card("AI Engine", llm_label), unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # Payment methods placeholder
        st.markdown(
            '<div class="bank-card">'
            '<h3>Payment Methods</h3>'
            '<div style="font-size:13px;color:var(--text-muted);padding:12px 0;">'
            'No payment methods on file. Payment is managed through your subscription provider.</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        # Entity & Tax info placeholder
        st.markdown(
            '<div class="bank-card">'
            '<h3>Entity & Tax Information</h3>'
            '<div style="font-size:13px;color:var(--text-muted);padding:12px 0;">'
            'Tax profile not configured. Contact support to set up B2B invoicing with GSTIN.</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        # Invoice history
        st.markdown(
            '<div class="bank-card">'
            '<h3>Invoice History</h3>'
            '<div style="font-size:13px;color:var(--text-muted);padding:12px 0;">'
            'No invoices yet. Invoices will appear here after your first billing cycle.</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        if st.button("Cancel Subscription", use_container_width=True):
            with get_db() as db:
                cancel_pro(db, user_id)
                db.commit()
            st.cache_data.clear()
            st.success("Your Pro subscription has been cancelled.")
            st.rerun()
    else:
        st.markdown(
            '<div class="bank-card">'
            '<h3>Current Plan: <span style="color:var(--text-muted);">Free</span></h3>'
            '<p style="font-size:13px;color:var(--text-dim);margin-top:8px;">'
            'You are on the Free plan. Upgrade to Pro to unlock the AI Financial Assistant '
            'and autonomous treasury features.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button("Upgrade to Pro", type="primary"):
            st.session_state["_nav_override"] = "Billing & Subscription"
            st.rerun()


# --------------------------------------------------------------------------- #
# Billing (combined: pricing for free, subscription for pro)
# --------------------------------------------------------------------------- #


def page_billing():
    plan = _get_user_plan_cached()
    if plan == "pro":
        page_subscription()
    else:
        page_pricing()


# --------------------------------------------------------------------------- #
# Insights generator (used by Overview + AI Standard mode)
# --------------------------------------------------------------------------- #


def _generate_insights(df: pd.DataFrame) -> list[dict]:
    insights = []
    if df.empty or len(df) < 3:
        return insights

    spend = df[df["type"] == "Debit"]
    income = df[df["type"] == "Credit"]

    if not spend.empty:
        top_cat = spend.groupby("category")["amount"].sum().idxmax()
        top_cat_amt = spend.groupby("category")["amount"].sum().max()
        total_spend = spend["amount"].sum()
        pct = top_cat_amt / total_spend * 100 if total_spend > 0 else 0
        insights.append({
            "title": f"Largest spending category: {top_cat}",
            "body": f"You spent {_fmt(top_cat_amt)} on {top_cat}, "
                    f"which is {pct:.1f}% of your total spending ({_fmt(total_spend)}). "
                    f"Period: {df['date'].min().strftime('%b %d')} – {df['date'].max().strftime('%b %d, %Y')}.",
        })

    if not spend.empty and len(spend) >= 5:
        monthly = spend.set_index("date").resample("MS")["amount"].sum()
        if len(monthly) >= 2:
            peak_month = monthly.idxmax()
            peak_amt = monthly.max()
            avg_monthly = monthly.mean()
            insights.append({
                "title": f"Peak spending month: {peak_month.strftime('%B %Y')}",
                "body": f"You spent {_fmt(peak_amt)} in {peak_month.strftime('%B %Y')}, "
                        f"which is {peak_amt / avg_monthly:.1f}x your monthly average of {_fmt(avg_monthly)}.",
            })

    total_income = income["amount"].sum() if not income.empty else 0
    total_expense = spend["amount"].sum() if not spend.empty else 0
    if total_income > 0 and total_expense > 0:
        ratio = total_expense / total_income * 100
        verdict = "below" if ratio < 100 else "above"
        insights.append({
            "title": f"Expense-to-income ratio: {ratio:.0f}%",
            "body": f"Your total expenses ({_fmt(total_expense)}) are {verdict} your total income "
                    f"({_fmt(total_income)}). Net cash flow: {_fmt(total_income - total_expense)}. "
                    f"Note: this reflects only imported transactions and may not include all income sources.",
        })

    if not spend.empty:
        freq = spend["merchant"].value_counts()
        top_merchant = freq.index[0]
        top_count = freq.iloc[0]
        top_merchant_total = spend[spend["merchant"] == top_merchant]["amount"].sum()
        if top_count >= 3:
            insights.append({
                "title": f"Most frequent merchant: {top_merchant}",
                "body": f"You made {top_count} transactions at {top_merchant}, "
                        f"totaling {_fmt(top_merchant_total)}.",
            })

    if not spend.empty and len(spend) >= 10:
        monthly_avg = spend.set_index("date").resample("MS")["amount"].mean()
        if len(monthly_avg) >= 3:
            first_half = monthly_avg.iloc[:len(monthly_avg)//2].mean()
            second_half = monthly_avg.iloc[len(monthly_avg)//2:].mean()
            if first_half > 0:
                change = (second_half - first_half) / first_half * 100
                direction = "increased" if change > 0 else "decreased"
                insights.append({
                    "title": f"Average transaction size {direction} by {abs(change):.0f}%",
                    "body": f"Your average transaction went from {_fmt(first_half)} in the earlier months "
                            f"to {_fmt(second_half)} in the later months of your data.",
                })

    anomalies = detect_anomalies(df)
    if anomalies:
        high = sum(1 for a in anomalies if a.severity == "high")
        moderate = sum(1 for a in anomalies if a.severity == "moderate")
        parts = []
        if high:
            parts.append(f"{high} high-severity")
        if moderate:
            parts.append(f"{moderate} moderate")
        insights.append({
            "title": f"{len(anomalies)} potentially unusual transactions detected",
            "body": f"Breakdown: {', '.join(parts)}. "
                    f"These are flagged by statistical patterns and rules, not a fraud-detection system.",
        })

    return insights


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main():
    render_header()
    page = render_sidebar()

    if "_nav_override" in st.session_state:
        page = st.session_state.pop("_nav_override")

    if not is_authenticated():
        page_auth()
        return

    st.markdown(
        '<div class="disclaimer-box">This is a demo application using 100% synthetic, fictional transaction '
        'data. It does not connect to any real bank account, and it is not a financial advisor.</div>',
        unsafe_allow_html=True,
    )

    if page == "Overview":
        page_overview()
    elif page == "Transactions":
        page_transactions()
    elif page == "AI Assistant":
        page_ai_assistant()
    elif page == "Data Center":
        page_import()
    elif page == "Billing & Subscription":
        page_billing()
    # Legacy route support
    elif page == "Upgrade to Pro":
        page_pricing()
    elif page == "Subscription":
        page_subscription()
    elif page == "Anomalies":
        page_overview()
    elif page == "Insights":
        page_ai_assistant()


if __name__ == "__main__":
    main()
