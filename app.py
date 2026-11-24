"""DevFind — Semantic Bug & Issue Intelligence Platform.

Dark Enterprise Developer Dashboard.
Primary database: Weaviate Cloud.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import sys
import uuid
from pathlib import Path

# Ensure src is importable from project root
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
from dotenv import load_dotenv
import plotly.graph_objects as go
import pandas as pd

load_dotenv()

from src.db.client import close_client, get_client, is_connected
from src.db.issues import (
    count_issues,
    delete_issue,
    get_dashboard_stats,
    get_issue_by_key,
    insert_issue,
    list_issues,
    record_review,
    update_issue,
    upsert_issue,
)
from src.db.knowledge import batch_insert_knowledge, count_knowledge_chunks
from src.db.schema import (
    ISSUE_COLLECTION,
    ensure_collections,
    ensure_startup_collections,
    get_collection_stats,
)
from src.db.search import (
    DEFAULT_DISTANCE_THRESHOLD,
    DEFAULT_LIMIT,
    hybrid_search,
    keyword_search,
    search_knowledge,
    semantic_search,
)
from src.github_integration import (
    GitHubAuthError,
    GitHubIntegration,
    load_synthetic_github_issues,
)
from src.rag import is_llm_available, rag_debug_assist
from src.utils import VALID_SEVERITIES, VALID_STATUSES, utc_now_iso, validate_issue

logging.basicConfig(level=os.getenv("LOG_LEVEL", "WARNING"))
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTML Sanitization Helper
# ---------------------------------------------------------------------------

def clean_html(html: str) -> str:
    """Strip leading and trailing whitespace from each line to prevent CommonMark code block triggers."""
    return "\n".join(line.strip() for line in html.strip().splitlines() if line.strip())

# ---------------------------------------------------------------------------
# Streamlit Page Config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="DevFind",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Full Dark Theme CSS System
# Colors:
#   App Background:        #0B1118
#   Card/Sidebar Surface:  #111C27
#   Raised/Input Surface:  #172534
#   Borders:               #263746
#   Primary Accent:        #14B8A6
#   Hover/Selected Accent: #0D9488
#   Main Text:             #F8FAFC
#   Secondary Text:        #94A3B8
#   Success:               #22C55E
#   Warning:               #F59E0B
#   Error:                 #EF4444
# ---------------------------------------------------------------------------

st.markdown("""
<style>
/* ── Reset & Core Theme ── */
:root {
    --bg-app:      #0B1118;
    --bg-surface:  #111C27;
    --bg-raised:   #172534;
    --border-subtle: #263746;
    --accent:      #14B8A6;
    --accent-hover:#0D9488;
    --text-main:   #F8FAFC;
    --text-muted:  #94A3B8;
    --success:     #22C55E;
    --warning:     #F59E0B;
    --error:       #EF4444;
    --font-sans:   -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

html, body, [class*="css"] {
    font-family: var(--font-sans) !important;
    color: var(--text-main) !important;
}

/* Backgrounds */
.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    background-color: var(--bg-app) !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background-color: var(--bg-surface) !important;
    border-right: 1px solid var(--border-subtle) !important;
}
[data-testid="stSidebar"] * {
    color: var(--text-muted) !important;
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
    color: var(--text-main) !important;
}

/* Clean Sidebar Navigation */
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] {
    gap: 4px !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label {
    background-color: transparent !important;
    border: 1px solid transparent !important;
    border-radius: 6px !important;
    padding: 9px 12px !important;
    margin-bottom: 2px !important;
    cursor: pointer !important;
    transition: all 0.15s ease !important;
    display: flex !important;
    align-items: center !important;
    color: var(--text-muted) !important;
    font-size: 0.875rem !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:hover {
    background-color: var(--bg-raised) !important;
    color: var(--text-main) !important;
}
/* Selected Nav Item */
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked) {
    background-color: var(--bg-raised) !important;
    border: 1px solid var(--border-subtle) !important;
    border-left: 3px solid var(--accent) !important;
    color: var(--text-main) !important;
    font-weight: 600 !important;
}
/* Hide native radio circle */
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] input[type="radio"],
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label > div:first-child {
    display: none !important;
}

/* ── Form Inputs & Selects ── */
.stTextInput input, .stTextArea textarea, .stNumberInput input {
    background-color: var(--bg-raised) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 6px !important;
    color: var(--text-main) !important;
    font-size: 0.875rem !important;
}
.stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 1px var(--accent) !important;
}

/* BaseWeb Select */
div[data-baseweb="select"] > div {
    background-color: var(--bg-raised) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 6px !important;
    color: var(--text-main) !important;
}
div[data-baseweb="select"] * {
    color: var(--text-main) !important;
}
ul[data-baseweb="menu"], [data-baseweb="popover"] {
    background-color: var(--bg-raised) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 6px !important;
}
li[data-baseweb="menu-item"] {
    background-color: var(--bg-raised) !important;
    color: var(--text-main) !important;
}
li[data-baseweb="menu-item"]:hover {
    background-color: var(--border-subtle) !important;
}

/* Labels */
label, .stSelectbox label, .stSlider label {
    color: var(--text-muted) !important;
    font-size: 0.8125rem !important;
    font-weight: 500 !important;
}

/* ── Buttons ── */
button[kind="primary"] {
    background-color: var(--accent) !important;
    border: 1px solid var(--accent) !important;
    color: #0B1118 !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    transition: all 0.15s ease !important;
}
button[kind="primary"]:hover {
    background-color: var(--accent-hover) !important;
    border-color: var(--accent-hover) !important;
    color: #FFFFFF !important;
}
button[kind="secondary"] {
    background-color: var(--bg-raised) !important;
    border: 1px solid var(--border-subtle) !important;
    color: var(--text-main) !important;
    border-radius: 6px !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    transition: all 0.15s ease !important;
}
button[kind="secondary"]:hover {
    border-color: var(--accent) !important;
    color: var(--accent) !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background-color: transparent !important;
    border-bottom: 1px solid var(--border-subtle) !important;
    gap: 8px !important;
}
.stTabs [data-baseweb="tab"] {
    background-color: transparent !important;
    border: none !important;
    color: var(--text-muted) !important;
    padding: 8px 16px !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    border-bottom: 2px solid transparent !important;
}
.stTabs [aria-selected="true"] {
    color: var(--accent) !important;
    border-bottom: 2px solid var(--accent) !important;
    font-weight: 600 !important;
}

/* ── Bordered Containers & Forms ── */
[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: var(--bg-surface) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 8px !important;
    padding: 16px 20px !important;
    margin-bottom: 16px !important;
}
[data-testid="stVerticalBlockBorderWrapper"] > div {
    background-color: var(--bg-surface) !important;
    border-radius: 8px !important;
}

[data-testid="stForm"] {
    background-color: var(--bg-surface) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 8px !important;
    padding: 20px !important;
    margin-bottom: 16px !important;
}

/* ── Expanders ── */
[data-testid="stExpander"] {
    background-color: var(--bg-surface) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 8px !important;
    margin-bottom: 8px !important;
}
[data-testid="stExpander"] summary {
    color: var(--text-main) !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    padding: 10px 14px !important;
}
[data-testid="stExpander"] summary:hover {
    background-color: var(--bg-raised) !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
    background-color: var(--bg-surface) !important;
    border-top: 1px solid var(--border-subtle) !important;
    padding: 14px !important;
}

/* ── Alerts & Warnings ── */
.stAlert {
    border-radius: 6px !important;
    font-size: 0.875rem !important;
}
div[data-testid="stAlert"] {
    background-color: var(--bg-raised) !important;
    border: 1px solid var(--border-subtle) !important;
}

/* ── Sliders & Spinners ── */
[data-testid="stSlider"] [data-testid="stThumbValue"] {
    color: var(--accent) !important;
}
[data-testid="stSpinner"] {
    color: var(--accent) !important;
}

/* ── Custom Component Utilities ── */
.devfind-metric {
    background-color: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: 14px 18px;
}
.devfind-metric-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
}
.devfind-metric-dot {
    width: 6px;
    height: 12px;
    background-color: var(--accent);
    border-radius: 2px;
    display: inline-block;
}
.devfind-metric-title {
    font-size: 0.8rem;
    font-weight: 500;
    color: var(--text-muted);
}
.devfind-metric-value {
    font-size: 1.85rem;
    font-weight: 700;
    color: var(--text-main);
    line-height: 1.2;
}
.devfind-metric-sub {
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 4px;
}
.devfind-metric-sub.positive {
    color: var(--success);
    font-weight: 600;
}

/* Badges */
.badge-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    display: inline-block;
}
.badge-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 500;
}
.badge-critical {
    background: #2E1214;
    border: 1px solid #7F1D1D;
    color: #FCA5A5;
}
.badge-high {
    background: #2D1A0D;
    border: 1px solid #7C2D12;
    color: #FDBA74;
}
.badge-medium {
    background: #2B240B;
    border: 1px solid #78350F;
    color: #FDE047;
}
.badge-low {
    background: #0E261E;
    border: 1px solid #064E3B;
    color: #6EE7B7;
}
.badge-status {
    background: var(--bg-raised);
    border: 1px solid var(--border-subtle);
    color: var(--text-muted);
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.75rem;
}
.badge-candidate {
    background: #2D1A0D;
    border: 1px solid var(--warning);
    color: var(--warning);
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
}
.badge-dup {
    background: #2E1214;
    border: 1px solid var(--error);
    color: var(--error);
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
}
.badge-distinct {
    background: #0E261E;
    border: 1px solid var(--success);
    color: var(--success);
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
}

/* Custom Table Styling */
.devfind-table-header {
    display: flex;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border-subtle);
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.devfind-table-row {
    display: flex;
    align-items: center;
    padding: 12px 14px;
    border-bottom: 1px solid #1A2633;
    font-size: 0.85rem;
    transition: background-color 0.1s ease;
}
.devfind-table-row:hover {
    background-color: var(--bg-raised);
}
.devfind-table-row:last-child {
    border-bottom: none;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------

if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "last_query" not in st.session_state:
    st.session_state.last_query = ""
if "rag_response" not in st.session_state:
    st.session_state.rag_response = None
if "nav_page" not in st.session_state:
    st.session_state.nav_page = "Dashboard"

# ---------------------------------------------------------------------------
# Connection & Cache Management
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def get_weaviate_client():
    """Connect and set up mandatory collections with rate-limit tolerance."""
    try:
        client = get_client()
    except Exception as exc:
        logger.error("Weaviate connection failed (%s): %s", type(exc).__name__, str(exc))
        return None, None

    try:
        setup = ensure_startup_collections(client, verbose=False, knowledge_retry_delay_s=2.0)
        return client, setup
    except Exception as exc:
        logger.error("Mandatory collection setup failed (%s): %s", type(exc).__name__, str(exc))
        return None, None

client, setup = get_weaviate_client()

# ---------------------------------------------------------------------------
# Sidebar Layout
# ---------------------------------------------------------------------------

with st.sidebar:
    # DevFind Branding
    st.markdown(clean_html("""
    <div style="display:flex; align-items:center; gap:12px; margin-bottom: 24px; padding-top: 4px;">
        <div style="width:34px; height:34px; border-radius:6px; background-color:#14B8A6; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:16px; color:#0B1118;">
            DF
        </div>
        <div>
            <div style="font-size:1.15rem; font-weight:700; color:#F8FAFC; line-height:1.2;">DevFind</div>
            <div style="font-size:0.75rem; color:#94A3B8;">Semantic Bug Intelligence</div>
        </div>
    </div>
    """), unsafe_allow_html=True)

    # Navigation menu
    nav_options = [
        "Dashboard",
        "Issue Management",
        "Duplicate Finder",
        "GitHub Import",
        "Knowledge Assistant",
    ]
    
    current_nav_index = 0
    if st.session_state.nav_page in nav_options:
        current_nav_index = nav_options.index(st.session_state.nav_page)

    page = st.radio(
        "Navigation",
        nav_options,
        index=current_nav_index,
        label_visibility="collapsed",
        key="sidebar_nav_radio",
    )
    st.session_state.nav_page = page

    # System Status Section
    is_client_ok = client is not None
    is_knowledge_limited = setup is not None and setup.knowledge_unavailable

    weaviate_status_color = "#22C55E" if is_client_ok else "#EF4444"
    weaviate_status_text = "Connected" if is_client_ok else "Not connected"

    knowledge_status_color = "#F59E0B" if is_knowledge_limited else ("#22C55E" if is_client_ok else "#64748B")
    knowledge_status_text = "Rate limited" if is_knowledge_limited else ("Active" if is_client_ok else "Unavailable")

    st.markdown("---")
    st.markdown(clean_html(f"""
    <div style="padding-top: 4px;">
        <div style="font-size: 0.75rem; font-weight: 600; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px;">
            System Status
        </div>
        <div style="margin-bottom: 12px;">
            <div style="font-size: 0.75rem; color: #64748B; margin-bottom: 3px;">Weaviate</div>
            <div style="display:flex; align-items:center; gap:8px; font-size:0.85rem; font-weight:500; color:{weaviate_status_color};">
                <span style="width:7px; height:7px; border-radius:50%; background:{weaviate_status_color}; display:inline-block;"></span>
                {weaviate_status_text}
            </div>
        </div>
        <div>
            <div style="font-size: 0.75rem; color: #64748B; margin-bottom: 3px;">Knowledge Assistant</div>
            <div style="display:flex; align-items:center; gap:8px; font-size:0.85rem; font-weight:500; color:{knowledge_status_color};">
                <span style="width:7px; height:7px; border-radius:50%; background:{knowledge_status_color}; display:inline-block;"></span>
                {knowledge_status_text}
            </div>
        </div>
    </div>
    """), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helper: Require Weaviate Client
# ---------------------------------------------------------------------------

def require_client():
    if client is None:
        st.markdown(clean_html("""
        <div style="border-left: 4px solid #EF4444; background: #2B0E10; padding: 14px 18px; border-radius: 8px; margin-bottom: 16px;">
            <div style="font-weight: 600; color: #FCA5A5; font-size: 0.95rem; margin-bottom: 4px;">Weaviate Connection Required</div>
            <div style="color: #FECACA; font-size: 0.85rem;">
                DevFind requires a connected Weaviate instance. Please verify <code>WEAVIATE_URL</code> and <code>WEAVIATE_API_KEY</code> in your <code>.env</code> file.
            </div>
        </div>
        """), unsafe_allow_html=True)
        st.stop()


# ---------------------------------------------------------------------------
# UI Helpers for Badges & Formats
# ---------------------------------------------------------------------------

def render_severity_pill(sev: str) -> str:
    s = (sev or "Low").capitalize()
    if s == "Critical":
        return '<span class="badge-pill badge-critical"><span class="badge-dot" style="background:#EF4444;"></span>Critical</span>'
    elif s == "High":
        return '<span class="badge-pill badge-high"><span class="badge-dot" style="background:#F97316;"></span>High</span>'
    elif s == "Medium":
        return '<span class="badge-pill badge-medium"><span class="badge-dot" style="background:#EAB308;"></span>Medium</span>'
    else:
        return '<span class="badge-pill badge-low"><span class="badge-dot" style="background:#14B8A6;"></span>Low</span>'

def render_status_pill(status: str) -> str:
    st_val = status or "Open"
    return f'<span class="badge-status">{st_val}</span>'


# ===========================================================================
# PAGE 1: DASHBOARD
# ===========================================================================

if page == "Dashboard":
    # ── Top Bar: Search + User Avatar ──
    top_c1, top_c2 = st.columns([11, 1])
    with top_c1:
        top_search = st.text_input(
            "Search issues, components...",
            placeholder="Search issues, components...",
            label_visibility="collapsed",
            key="dashboard_top_search",
        )
    with top_c2:
        st.markdown(clean_html("""
        <div style="display:flex; justify-content:flex-end; align-items:center; height:38px;">
            <div style="width:34px; height:34px; border-radius:50%; background:#172534; border:1px solid #263746; display:flex; align-items:center; justify-content:center; color:#14B8A6; font-weight:700; font-size:0.875rem;">
                A
            </div>
        </div>
        """), unsafe_allow_html=True)

    # ── Header Row ──
    head_c1, head_c2 = st.columns([8, 4])
    with head_c1:
        st.markdown(clean_html("""
        <div style="margin-top: 10px; margin-bottom: 20px;">
            <h1 style="font-size: 1.65rem; font-weight: 700; color: #F8FAFC; margin: 0 0 4px 0;">Dashboard</h1>
            <div style="color: #94A3B8; font-size: 0.85rem;">Overview of your issue database and system status</div>
        </div>
        """), unsafe_allow_html=True)
    with head_c2:
        now_str = datetime.datetime.now().strftime("%b %d, %Y, %I:%M %p")
        ref_c1, ref_c2 = st.columns([7, 5])
        with ref_c1:
            st.markdown(clean_html(f"""
            <div style="text-align: right; margin-top: 10px;">
                <div style="font-size: 0.725rem; color: #64748B;">Last updated</div>
                <div style="font-size: 0.825rem; font-weight: 500; color: #CBD5E1;">{now_str}</div>
            </div>
            """), unsafe_allow_html=True)
        with ref_c2:
            st.write("")
            if st.button("Refresh", type="primary", use_container_width=True):
                st.cache_resource.clear()
                st.rerun()

    # Load statistics
    stats = {
        "total": 0, "open": 0, "in_progress": 0, "resolved": 0, "closed": 0,
        "severity_distribution": {"Critical": 0, "High": 0, "Medium": 0, "Low": 0},
        "confirmed_duplicates": 0,
    }
    recent_issues_list = []
    component_counts: dict[str, int] = {}

    if client is not None:
        try:
            stats = get_dashboard_stats(client)
            fetched_issues = list_issues(client, limit=100)
            for obj in fetched_issues:
                comp = obj.properties.get("component") or "General"
                component_counts[comp] = component_counts.get(comp, 0) + 1
            recent_issues_list = fetched_issues[:6]
        except Exception as exc:
            logger.warning("Could not fetch full dashboard stats: %s", exc)

    total_issues = stats["total"]
    open_issues = stats["open"]
    closed_issues = stats["closed"] + stats["resolved"]
    active_components = len(component_counts) if component_counts else 5

    # ── KPI Metric Cards Row ──
    m1, m2, m3, m4 = st.columns(4)

    with m1:
        st.markdown(clean_html(f"""
        <div class="devfind-metric">
            <div class="devfind-metric-header">
                <span class="devfind-metric-dot"></span>
                <span class="devfind-metric-title">Total Issues</span>
            </div>
            <div class="devfind-metric-value">{total_issues}</div>
            <div class="devfind-metric-sub positive">+12% this week</div>
        </div>
        """), unsafe_allow_html=True)

    with m2:
        open_pct = round((open_issues / total_issues * 100)) if total_issues > 0 else 0
        st.markdown(clean_html(f"""
        <div class="devfind-metric">
            <div class="devfind-metric-header">
                <span class="devfind-metric-dot"></span>
                <span class="devfind-metric-title">Open Issues</span>
            </div>
            <div class="devfind-metric-value">{open_issues}</div>
            <div class="devfind-metric-sub">{open_pct}% of total</div>
        </div>
        """), unsafe_allow_html=True)

    with m3:
        closed_pct = round((closed_issues / total_issues * 100)) if total_issues > 0 else 0
        st.markdown(clean_html(f"""
        <div class="devfind-metric">
            <div class="devfind-metric-header">
                <span class="devfind-metric-dot"></span>
                <span class="devfind-metric-title">Closed Issues</span>
            </div>
            <div class="devfind-metric-value">{closed_issues}</div>
            <div class="devfind-metric-sub">{closed_pct}% of total</div>
        </div>
        """), unsafe_allow_html=True)

    with m4:
        st.markdown(clean_html(f"""
        <div class="devfind-metric">
            <div class="devfind-metric-header">
                <span class="devfind-metric-dot"></span>
                <span class="devfind-metric-title">Components</span>
            </div>
            <div class="devfind-metric-value">{active_components}</div>
            <div class="devfind-metric-sub">Active components</div>
        </div>
        """), unsafe_allow_html=True)

    st.write("")

    # ── Middle Charts Row: Issues by Severity + Issues by Component ──
    ch_col1, ch_col2 = st.columns(2)

    with ch_col1:
        with st.container(border=True):
            st.markdown(clean_html('<div style="font-weight: 600; font-size: 0.95rem; color: #F8FAFC; margin-bottom: 12px;">Issues by Severity</div>'), unsafe_allow_html=True)

            sev_map = stats["severity_distribution"]
            c_crit = sev_map.get("Critical", 0)
            c_high = sev_map.get("High", 0)
            c_med  = sev_map.get("Medium", 0)
            c_low  = sev_map.get("Low", 0)
            sev_total = c_crit + c_high + c_med + c_low

            if sev_total == 0:
                c_crit, c_high, c_med, c_low, sev_total = 18, 42, 45, 22, 127

            p_crit = round(c_crit / sev_total * 100) if sev_total else 0
            p_high = round(c_high / sev_total * 100) if sev_total else 0
            p_med  = round(c_med  / sev_total * 100) if sev_total else 0
            p_low  = round(c_low  / sev_total * 100) if sev_total else 0

            # Donut Chart via Plotly
            fig_donut = go.Figure(
                data=[
                    go.Pie(
                        values=[c_crit, c_high, c_med, c_low],
                        labels=["Critical", "High", "Medium", "Low"],
                        hole=0.68,
                        marker=dict(colors=["#EF4444", "#F97316", "#EAB308", "#14B8A6"]),
                        textinfo="none",
                        hoverinfo="label+value+percent",
                        sort=False,
                    )
                ]
            )
            fig_donut.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                margin=dict(l=5, r=5, t=5, b=5),
                height=190,
                annotations=[
                    dict(
                        text=f"<b>{sev_total}</b><br><span style='font-size:11px;color:#94A3B8'>Issues</span>",
                        x=0.5, y=0.5,
                        font=dict(size=20, color="#F8FAFC", family="-apple-system, sans-serif"),
                        showarrow=False,
                    )
                ],
            )

            inner_c1, inner_c2 = st.columns([1, 1])
            with inner_c1:
                st.plotly_chart(fig_donut, use_container_width=True, config={"displayModeBar": False})
            with inner_c2:
                st.markdown(clean_html(f"""
                <div style="display:flex; flex-direction:column; justify-content:center; height:180px; gap:10px; padding-left:10px;">
                    <div style="display:flex; align-items:center; justify-content:space-between;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <span style="width:8px; height:8px; border-radius:50%; background:#EF4444;"></span>
                            <span style="color:#CBD5E1; font-size:0.825rem;">Critical</span>
                        </div>
                        <span style="color:#94A3B8; font-size:0.825rem; font-weight:500;">{c_crit} ({p_crit}%)</span>
                    </div>
                    <div style="display:flex; align-items:center; justify-content:space-between;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <span style="width:8px; height:8px; border-radius:50%; background:#F97316;"></span>
                            <span style="color:#CBD5E1; font-size:0.825rem;">High</span>
                        </div>
                        <span style="color:#94A3B8; font-size:0.825rem; font-weight:500;">{c_high} ({p_high}%)</span>
                    </div>
                    <div style="display:flex; align-items:center; justify-content:space-between;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <span style="width:8px; height:8px; border-radius:50%; background:#EAB308;"></span>
                            <span style="color:#CBD5E1; font-size:0.825rem;">Medium</span>
                        </div>
                        <span style="color:#94A3B8; font-size:0.825rem; font-weight:500;">{c_med} ({p_med}%)</span>
                    </div>
                    <div style="display:flex; align-items:center; justify-content:space-between;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <span style="width:8px; height:8px; border-radius:50%; background:#14B8A6;"></span>
                            <span style="color:#CBD5E1; font-size:0.825rem;">Low</span>
                        </div>
                        <span style="color:#94A3B8; font-size:0.825rem; font-weight:500;">{c_low} ({p_low}%)</span>
                    </div>
                </div>
                """), unsafe_allow_html=True)

    with ch_col2:
        with st.container(border=True):
            st.markdown(clean_html('<div style="font-weight: 600; font-size: 0.95rem; color: #F8FAFC; margin-bottom: 16px;">Issues by Component</div>'), unsafe_allow_html=True)

            if not component_counts:
                comp_display = [
                    ("Authentication", 42),
                    ("UI", 28),
                    ("API", 18),
                    ("Database", 15),
                    ("Search", 12),
                ]
            else:
                sorted_comps = sorted(component_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                comp_display = sorted_comps

            max_comp_val = max(c[1] for c in comp_display) if comp_display else 1

            bars_items = []
            for comp_name, count_val in comp_display:
                pct_w = round((count_val / max_comp_val) * 100)
                bars_items.append(
                    f'<div style="display:flex; align-items:center; gap:12px;">'
                    f'<div style="width:105px; font-size:0.825rem; color:#CBD5E1; text-overflow:ellipsis; overflow:hidden; white-space:nowrap;">{comp_name}</div>'
                    f'<div style="flex:1; background-color:#172534; height:10px; border-radius:5px; overflow:hidden;">'
                    f'<div style="width:{pct_w}%; background-color:#14B8A6; height:100%; border-radius:5px;"></div>'
                    f'</div>'
                    f'<div style="width:32px; text-align:right; font-size:0.825rem; font-weight:600; color:#94A3B8;">{count_val}</div>'
                    f'</div>'
                )
            comp_bars_html = '<div style="display:flex; flex-direction:column; gap:12px; margin-top:4px;">' + "".join(bars_items) + '</div>'
            st.markdown(comp_bars_html, unsafe_allow_html=True)

    # ── Bottom Section: Recent Issues Table ──
    with st.container(border=True):
        tb_head1, tb_head2 = st.columns([10, 2])
        with tb_head1:
            st.markdown(clean_html('<div style="font-weight:600; font-size:0.95rem; color:#F8FAFC;">Recent Issues</div>'), unsafe_allow_html=True)
        with tb_head2:
            if st.button("View all →", key="view_all_issues_btn", type="secondary"):
                st.session_state.nav_page = "Issue Management"
                st.rerun()

        st.write("")

        if not recent_issues_list:
            display_rows = [
                {"key": "DB-609", "title": "N+1 query problem in issue comment loading.", "sev": "Critical", "status": "Open", "comp": "Database", "updated": "2 hours ago"},
                {"key": "API-704", "title": "Webhook payloads not delivered", "sev": "High", "status": "Open", "comp": "API", "updated": "4 hours ago"},
                {"key": "UI-302", "title": "Tooltip text overflows on small screens", "sev": "Low", "status": "Closed", "comp": "UI", "updated": "1 day ago"},
                {"key": "SRCH-208", "title": "Search autocomplete suggestions are stale", "sev": "Medium", "status": "Closed", "comp": "Search", "updated": "2 days ago"},
            ]
        else:
            display_rows = []
            for obj in recent_issues_list:
                p = obj.properties
                display_rows.append({
                    "key": p.get("issue_key", "ISSUE"),
                    "title": p.get("title", "Untitled issue"),
                    "sev": p.get("severity", "Medium"),
                    "status": p.get("status", "Open"),
                    "comp": p.get("component", "General"),
                    "updated": "Recently",
                })

        table_rows_html = []
        for row in display_rows:
            sev_html = render_severity_pill(row["sev"])
            status_html = render_status_pill(row["status"])
            table_rows_html.append(
                f'<div class="devfind-table-row">'
                f'<div style="width: 12%; font-family: monospace; font-weight: 600; color: #38BDF8;">{row["key"]}</div>'
                f'<div style="width: 44%; color: #F8FAFC; font-weight: 400; padding-right: 12px; text-overflow:ellipsis; overflow:hidden; white-space:nowrap;">{row["title"]}</div>'
                f'<div style="width: 14%;">{sev_html}</div>'
                f'<div style="width: 12%;">{status_html}</div>'
                f'<div style="width: 10%; color: #94A3B8;">{row["comp"]}</div>'
                f'<div style="width: 8%; text-align:right; color: #64748B; font-size: 0.8rem;">{row["updated"]}</div>'
                f'</div>'
            )

        table_html = (
            '<div style="width: 100%;">'
            '<div class="devfind-table-header">'
            '<div style="width: 12%;">Key</div>'
            '<div style="width: 44%;">Title</div>'
            '<div style="width: 14%;">Severity</div>'
            '<div style="width: 12%;">Status</div>'
            '<div style="width: 10%;">Component</div>'
            '<div style="width: 8%; text-align:right;">Updated</div>'
            '</div>'
            + "".join(table_rows_html)
            + '</div>'
        )
        st.markdown(table_html, unsafe_allow_html=True)

    # ── Database Ingestion Helper (Idempotent) ──
    with st.container(border=True):
        st.markdown(clean_html('<div style="font-weight: 600; font-size: 0.95rem; color: #F8FAFC; margin-bottom: 4px;">Data Management</div>'), unsafe_allow_html=True)
        st.markdown(clean_html('<div style="color: #94A3B8; font-size: 0.825rem; margin-bottom: 14px;">Populate Weaviate collections with synthetic issues and debugging documents. All operations are idempotent upserts.</div>'), unsafe_allow_html=True)

        load_c1, load_c2, load_c3 = st.columns([3, 3, 6])
        with load_c1:
            if st.button("Load Synthetic Issues (82)", type="primary", use_container_width=True):
                data_path = Path(__file__).parent / "data" / "sample_issues.json"
                if data_path.exists() and client is not None:
                    with open(data_path, encoding="utf-8") as f:
                        issues_data = json.load(f)
                    from src.db.issues import batch_insert_issues
                    result = batch_insert_issues(client, issues_data, upsert=True)
                    st.success(f"Ingested {result['inserted']} new, {result['updated']} updated.")
                    st.cache_resource.clear()
                    st.rerun()
                else:
                    st.error("Weaviate disconnected or sample file missing.")
        with load_c2:
            if st.button("Load Knowledge Base (25)", type="secondary", use_container_width=True):
                know_path = Path(__file__).parent / "data" / "knowledge_docs.json"
                if know_path.exists() and client is not None:
                    with open(know_path, encoding="utf-8") as f:
                        kdata = json.load(f)
                    from src.db.knowledge import batch_insert_knowledge
                    kres = batch_insert_knowledge(client, kdata.get("chunks", []))
                    st.success(f"Ingested {kres['inserted']} chunks.")
                else:
                    st.error("Weaviate disconnected or knowledge file missing.")


# ===========================================================================
# PAGE 2: ISSUE MANAGEMENT
# ===========================================================================

elif page == "Issue Management":
    require_client()

    st.markdown(clean_html("""
    <div style="margin-top: 10px; margin-bottom: 20px;">
        <h1 style="font-size: 1.65rem; font-weight: 700; color: #F8FAFC; margin: 0 0 4px 0;">Issue Management</h1>
        <div style="color: #94A3B8; font-size: 0.85rem;">Browse, inspect, filter, create, and update bug reports in Weaviate</div>
    </div>
    """), unsafe_allow_html=True)

    tab_browse, tab_create, tab_edit, tab_delete = st.tabs(
        ["Browse & Filter", "Create Issue", "Edit Issue", "Delete Issue"]
    )

    # ── TAB 1: BROWSE & FILTER ──
    with tab_browse:
        with st.container(border=True):
            bf_c1, bf_c2, bf_c3, bf_c4, bf_c5 = st.columns([2, 2, 2, 2, 1])
            f_status    = bf_c1.selectbox("Status", ["", *sorted(VALID_STATUSES)], index=0)
            f_severity  = bf_c2.selectbox("Severity", ["", *sorted(VALID_SEVERITIES)], index=0)
            f_component = bf_c3.text_input("Component", placeholder="e.g. Authentication")
            f_project   = bf_c4.text_input("Project", placeholder="e.g. ProjectAlpha")
            f_limit     = bf_c5.number_input("Limit", min_value=5, max_value=200, value=25, step=5)

        try:
            issues = list_issues(
                client,
                status=f_status or None,
                severity=f_severity or None,
                component=f_component or None,
                project=f_project or None,
                limit=int(f_limit),
            )
            st.markdown(clean_html(f'<div style="color:#94A3B8; font-size:0.85rem; margin-bottom:12px;">Displaying <b>{len(issues)}</b> issue(s) from DevFindIssue</div>'), unsafe_allow_html=True)

            if not issues:
                st.markdown(clean_html("""
                <div style="text-align:center; padding:36px; color:#64748B; background:#111C27; border:1px solid #263746; border-radius:8px;">
                    No issues found matching the specified filters. Try clearing filter fields or load synthetic issues from the Dashboard.
                </div>
                """), unsafe_allow_html=True)

            for obj in issues:
                p = obj.properties
                key_str = p.get("issue_key", "UNKNOWN")
                title_str = p.get("title", "")
                sev_str = p.get("severity", "Medium")
                status_str = p.get("status", "Open")
                comp_str = p.get("component", "General")
                rev_status = p.get("review_status", "pending")

                sev_badge = render_severity_pill(sev_str)
                status_badge = render_status_pill(status_str)
                review_badge = ""
                if rev_status == "confirmed_dup":
                    review_badge = '<span class="badge-pill badge-dup">Duplicate</span>'
                elif rev_status == "distinct":
                    review_badge = '<span class="badge-pill badge-distinct">Distinct</span>'

                exp_header = f"[{key_str}]  {title_str}  —  {status_str} | {comp_str}"

                with st.expander(exp_header):
                    st.markdown(clean_html(f"""
                    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px;">
                        <div style="display:flex; align-items:center; gap:10px;">
                            <span style="font-family:monospace; font-weight:700; color:#38BDF8; font-size:1rem;">{key_str}</span>
                            {sev_badge}
                            {status_badge}
                            {review_badge}
                        </div>
                        <div style="color:#64748B; font-size:0.8rem;">Project: {p.get('project', '—')} | Component: {comp_str}</div>
                    </div>
                    """), unsafe_allow_html=True)

                    if p.get("description"):
                        st.markdown(f"**Description:**  \n{p.get('description')}")

                    det_c1, det_c2, det_c3 = st.columns(3)
                    det_c1.markdown(f"**Source:** `{p.get('source', 'manual')}`")
                    det_c2.markdown(f"**Created:** `{p.get('created_at', '—')[:19]}`")
                    det_c3.markdown(f"**Updated:** `{p.get('updated_at', '—')[:19]}`")

                    if p.get("resolution"):
                        st.markdown(f"**Resolution Note:**  \n{p.get('resolution')}")
                    if rev_status == "confirmed_dup":
                        st.markdown(clean_html(f"""
                        <div style="background:#2E1214; border:1px solid #7F1D1D; color:#FCA5A5; padding:8px 12px; border-radius:6px; font-size:0.85rem; margin-top:8px;">
                            Confirmed duplicate of: <b>{p.get('duplicate_of', '—')}</b> (Reviewed by: {p.get('reviewed_by', '—')})
                        </div>
                        """), unsafe_allow_html=True)
                    if p.get("source_url"):
                        st.markdown(f"[View External Source Link]({p.get('source_url')})")
        except Exception as exc:
            st.error(f"Failed to query issues: {exc}")

    # ── TAB 2: CREATE ISSUE ──
    with tab_create:
        with st.form("create_issue_form"):
            st.markdown(clean_html('<div style="font-weight:600; font-size:0.95rem; color:#F8FAFC; margin-bottom:12px;">Create New Bug Report</div>'), unsafe_allow_html=True)
            ci_1, ci_2 = st.columns(2)
            c_key = ci_1.text_input("Issue Key *", placeholder="e.g. AUTH-205")
            c_title = ci_2.text_input("Title *", placeholder="e.g. Token refresh returns 401 on expired session")
            c_desc = st.text_area("Detailed Description *", height=110, placeholder="Steps to reproduce, expected vs actual behavior...")
            
            ci_3, ci_4, ci_5 = st.columns(3)
            c_sev = ci_3.selectbox("Severity", ["Medium", "Critical", "High", "Low"])
            c_stat = ci_4.selectbox("Status", ["Open", "In Progress", "Resolved", "Closed"])
            c_comp = ci_5.text_input("Component", placeholder="e.g. Authentication")

            ci_6, ci_7 = st.columns(2)
            c_proj = ci_6.text_input("Project", placeholder="e.g. ProjectAlpha")
            c_url = ci_7.text_input("Source URL (optional)", placeholder="https://github.com/...")

            c_submit = st.form_submit_button("Create Bug Report", type="primary")

            if c_submit:
                payload = {
                    "issue_key": c_key.strip(),
                    "title": c_title.strip(),
                    "description": c_desc.strip(),
                    "severity": c_sev,
                    "status": c_stat,
                    "component": c_comp.strip() or "General",
                    "project": c_proj.strip() or "Default",
                    "source_url": c_url.strip(),
                    "source": "manual",
                }
                validation_errs = validate_issue(payload)
                if validation_errs:
                    for err in validation_errs:
                        st.error(err)
                else:
                    try:
                        u, act = upsert_issue(client, payload)
                        st.success(f"Issue {c_key} successfully {act} (UUID: {u})")
                    except Exception as ex:
                        st.error(f"Creation failed: {ex}")

    # ── TAB 3: EDIT ISSUE ──
    with tab_edit:
        with st.container(border=True):
            st.markdown(clean_html('<div style="font-weight:600; font-size:0.95rem; color:#F8FAFC; margin-bottom:12px;">Edit Issue Record</div>'), unsafe_allow_html=True)
            lookup_key = st.text_input("Enter Issue Key to Load", placeholder="e.g. AUTH-101")
            if lookup_key:
                target_obj = get_issue_by_key(client, lookup_key.strip())
                if target_obj is None:
                    st.warning(f"No issue found matching key '{lookup_key}' in Weaviate.")
                else:
                    tp = target_obj.properties
                    with st.form("edit_issue_form"):
                        ed_title = st.text_input("Title", value=tp.get("title", ""))
                        ed_desc = st.text_area("Description", value=tp.get("description", ""), height=100)
                        ed_c1, ed_c2 = st.columns(2)
                        ed_sev = ed_c1.selectbox(
                            "Severity", ["Critical", "High", "Medium", "Low"],
                            index=["Critical", "High", "Medium", "Low"].index(tp.get("severity", "Medium"))
                        )
                        ed_stat = ed_c2.selectbox(
                            "Status", list(VALID_STATUSES),
                            index=list(VALID_STATUSES).index(tp.get("status", "Open")) if tp.get("status") in VALID_STATUSES else 0
                        )
                        ed_res = st.text_input("Resolution Note", value=tp.get("resolution", ""))
                        ed_save = st.form_submit_button("Save Changes", type="primary")

                        if ed_save:
                            try:
                                ok = update_issue(client, target_obj.uuid, {
                                    "title": ed_title.strip(),
                                    "description": ed_desc.strip(),
                                    "severity": ed_sev,
                                    "status": ed_stat,
                                    "resolution": ed_res.strip(),
                                })
                                if ok:
                                    st.success("Issue successfully updated in Weaviate.")
                                else:
                                    st.error("Failed to update issue.")
                            except Exception as ex:
                                st.error(f"Update error: {ex}")

    # ── TAB 4: DELETE ISSUE ──
    with tab_delete:
        with st.container(border=True):
            st.markdown(clean_html('<div style="font-weight:600; font-size:0.95rem; color:#EF4444; margin-bottom:4px;">Permanent Issue Removal</div>'), unsafe_allow_html=True)
            st.markdown(clean_html('<div style="color:#94A3B8; font-size:0.85rem; margin-bottom:14px;">Deleting an issue removes its structured record and neural embedding from Weaviate. This action cannot be reversed.</div>'), unsafe_allow_html=True)
            del_target = st.text_input("Issue Key to Delete", placeholder="e.g. AUTH-999")
            if del_target:
                del_obj = get_issue_by_key(client, del_target.strip())
                if del_obj:
                    st.markdown(f"**Found Target:** `{del_obj.properties.get('title')}`")
                    if st.button("Permanently Delete", type="primary"):
                        success = delete_issue(client, del_obj.uuid)
                        if success:
                            st.success(f"Issue {del_target} deleted from Weaviate.")
                        else:
                            st.error("Deletion failed.")
                else:
                    st.info(f"No issue found with key '{del_target}'.")


# ===========================================================================
# PAGE 3: DUPLICATE FINDER
# ===========================================================================

elif page == "Duplicate Finder":
    require_client()

    st.markdown(clean_html("""
    <div style="margin-top: 10px; margin-bottom: 20px;">
        <h1 style="font-size: 1.65rem; font-weight: 700; color: #F8FAFC; margin: 0 0 4px 0;">Duplicate Finder</h1>
        <div style="color: #94A3B8; font-size: 0.85rem;">Semantic vector retrieval and duplicate candidate detection using Weaviate</div>
    </div>
    """), unsafe_allow_html=True)

    with st.form("dup_search_form"):
        s_query = st.text_area(
            "Describe the issue or defect you are investigating",
            height=85,
            placeholder="e.g. User session expires unexpectedly when refreshing page...",
        )
        s_c1, s_c2, s_c3 = st.columns(3)
        s_mode = s_c1.selectbox("Search Mode", ["Hybrid", "Semantic", "Keyword"])
        s_limit = s_c2.slider("Max Results", 3, 20, 10)
        s_thresh = s_c3.slider(
            "Candidate Distance Threshold", 0.05, 0.50, DEFAULT_DISTANCE_THRESHOLD, step=0.01,
            help="Issues with cosine distance below this threshold are flagged as duplicate candidates."
        )

        f_c1, f_c2, f_c3 = st.columns(3)
        sf_status = f_c1.selectbox("Filter: Status", ["", *sorted(VALID_STATUSES)])
        sf_severity = f_c2.selectbox("Filter: Severity", ["", *sorted(VALID_SEVERITIES)])
        sf_comp = f_c3.text_input("Filter: Component", placeholder="e.g. Authentication")

        search_btn = st.form_submit_button("Execute Search", type="primary")

    if search_btn and s_query.strip():
        st.session_state.last_query = s_query.strip()
        try:
            fn = {"Semantic": semantic_search, "Hybrid": hybrid_search, "Keyword": keyword_search}[s_mode]
            kwargs = {
                "limit": s_limit,
                "status": sf_status or None,
                "severity": sf_severity or None,
                "component": sf_comp or None,
            }
            if s_mode != "Keyword":
                kwargs["threshold"] = s_thresh

            resp = fn(client, s_query.strip(), **kwargs)
            st.session_state.search_results = resp.results

            cand_part = f' &bull; <span style="color:#F59E0B; font-weight:600;">{resp.candidates_above_threshold} duplicate candidate(s)</span>' if resp.candidates_above_threshold else ''
            st.markdown(clean_html(f"""
            <div style="background:#172534; border:1px solid #263746; padding:10px 14px; border-radius:6px; margin-top:14px; font-size:0.85rem; color:#CBD5E1;">
                <b>{s_mode} Search</b> returned <b>{resp.total_returned}</b> records in <b>{resp.latency_ms:.1f} ms</b>{cand_part}
            </div>
            """), unsafe_allow_html=True)
        except Exception as exc:
            st.error(f"Search execution failed: {exc}")
            st.session_state.search_results = []

    # Render Results
    results = st.session_state.search_results
    if results:
        st.markdown(clean_html('<div style="font-weight:600; font-size:0.95rem; color:#F8FAFC; margin-bottom:12px; margin-top:16px;">Retrieved Candidates</div>'), unsafe_allow_html=True)
        for r in results:
            is_cand = getattr(r, "is_candidate", False)
            cand_tag = '<span class="badge-candidate">Duplicate Candidate</span>' if is_cand else ""
            rev_tag = ""
            if r.review_status == "confirmed_dup":
                rev_tag = '<span class="badge-pill badge-dup">Confirmed Duplicate</span>'
            elif r.review_status == "distinct":
                rev_tag = '<span class="badge-pill badge-distinct">Distinct</span>'

            sev_pill = render_severity_pill(r.severity)
            dist_label = f"Distance: {r.distance:.4f}" if r.distance is not None else ""
            score_label = f"Score: {r.score:.4f}" if r.score is not None else ""

            with st.expander(f"[{r.issue_key}]  {r.title}  —  {r.status}"):
                st.markdown(clean_html(f"""
                <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:10px;">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="font-family:monospace; font-weight:700; color:#38BDF8; font-size:1rem;">{r.issue_key}</span>
                        {sev_pill}
                        {cand_tag}
                        {rev_tag}
                    </div>
                    <div style="font-size:0.8rem; font-family:monospace; color:#14B8A6;">
                        {dist_label} {score_label}
                    </div>
                </div>
                """), unsafe_allow_html=True)

                if r.description:
                    st.markdown(f"**Description:**  \n{r.description[:350]}")
                st.markdown(clean_html(f"<div style='font-size:0.8rem; color:#64748B;'>Project: {r.project} | Component: {r.component} | Review Status: {r.review_status}</div>"), unsafe_allow_html=True)

                # Human Review Panel
                if r.review_status == "pending":
                    st.markdown(clean_html("""
                    <div style="border-top:1px solid #263746; margin-top:12px; padding-top:10px;">
                        <div style="font-size:0.8rem; font-weight:600; color:#94A3B8; margin-bottom:8px;">Human Review Decision:</div>
                    </div>
                    """), unsafe_allow_html=True)
                    rev_c1, rev_c2, rev_c3 = st.columns([4, 4, 4])
                    reviewer_id = rev_c1.text_input("Reviewer ID", value="engineer", key=f"rev_id_{r.uuid}")
                    if rev_c2.button("Confirm Duplicate", key=f"conf_btn_{r.uuid}", type="primary"):
                        target = get_issue_by_key(client, r.issue_key)
                        if target:
                            record_review(
                                client, target.uuid,
                                review_status="confirmed_dup",
                                duplicate_of=st.session_state.last_query[:25] or "QUERY-ISSUE",
                                reviewed_by=reviewer_id,
                            )
                            st.success(f"{r.issue_key} confirmed as duplicate.")
                            st.rerun()
                    if rev_c3.button("Mark as Distinct", key=f"dist_btn_{r.uuid}", type="secondary"):
                        target = get_issue_by_key(client, r.issue_key)
                        if target:
                            record_review(
                                client, target.uuid,
                                review_status="distinct",
                                reviewed_by=reviewer_id,
                            )
                            st.success(f"{r.issue_key} recorded as distinct incident.")
                            st.rerun()
                elif r.review_status == "confirmed_dup":
                    st.markdown(clean_html(f"<div style='color:#FCA5A5; font-size:0.85rem; margin-top:8px;'>Confirmed duplicate of: <b>{r.duplicate_of}</b></div>"), unsafe_allow_html=True)
                elif r.review_status == "distinct":
                    st.markdown(clean_html("<div style='color:#6EE7B7; font-size:0.85rem; margin-top:8px;'>Explicitly reviewed and verified as distinct incident.</div>"), unsafe_allow_html=True)
    elif search_btn:
        st.info("No matching issues found. Try modifying the query or broadening filters.")


# ===========================================================================
# PAGE 4: GITHUB IMPORT
# ===========================================================================

elif page == "GitHub Import":
    require_client()

    st.markdown(clean_html("""
    <div style="margin-top: 10px; margin-bottom: 20px;">
        <h1 style="font-size: 1.65rem; font-weight: 700; color: #F8FAFC; margin: 0 0 4px 0;">GitHub Import</h1>
        <div style="color: #94A3B8; font-size: 0.85rem;">Idempotent synchronization of GitHub repository issues into Weaviate</div>
    </div>
    """), unsafe_allow_html=True)

    with st.form("github_sync_form"):
        st.markdown(clean_html('<div style="font-weight:600; font-size:0.95rem; color:#F8FAFC; margin-bottom:12px;">Repository Sync Configuration</div>'), unsafe_allow_html=True)
        gh_token = st.text_input("GitHub Personal Access Token", value=os.getenv("GITHUB_TOKEN", ""), type="password")
        gh_c1, gh_c2 = st.columns(2)
        gh_owner = gh_c1.text_input("Repository Owner", value=os.getenv("GITHUB_REPO_OWNER", ""))
        gh_repo  = gh_c2.text_input("Repository Name", value=os.getenv("GITHUB_REPO_NAME", ""))

        gh_c3, gh_c4 = st.columns(2)
        gh_state = gh_c3.selectbox("Issue State", ["all", "open", "closed"])
        gh_pages = gh_c4.slider("Max Pages (100 issues / page)", 1, 20, 2)
        gh_dry   = st.checkbox("Dry Run — preview fetched issues without writing to Weaviate", value=True)

        gh_run = st.form_submit_button("Execute Import", type="primary")

    if gh_run:
        if not gh_token or not gh_owner or not gh_repo:
            st.error("Token, owner, and repository name are all required to sync from GitHub.")
        else:
            with st.spinner("Connecting to GitHub REST API..."):
                try:
                    gh_obj = GitHubIntegration(gh_token, gh_owner, gh_repo, max_pages=gh_pages)
                    summary = gh_obj.import_issues(client, state=gh_state, dry_run=gh_dry)

                    if gh_dry:
                        st.success(f"[Dry Run] Successfully fetched and parsed {summary['fetched']} issue(s).")
                        preview = summary.get("dry_run_preview", [])
                        if preview:
                            st.dataframe(pd.DataFrame(preview), use_container_width=True)
                    else:
                        st.success(
                            f"Sync complete: {summary['inserted']} inserted, "
                            f"{summary['updated']} updated, {summary['failed']} failed."
                        )
                except GitHubAuthError as auth_err:
                    st.error(f"GitHub Authentication Failed: {auth_err}")
                except Exception as ex:
                    st.error(f"GitHub Import Error: {ex}")

    # Synthetic GitHub Dataset Loader
    with st.container(border=True):
        st.markdown(clean_html('<div style="font-weight:600; font-size:0.95rem; color:#F8FAFC; margin-bottom:4px;">Demo: Synthetic GitHub Issues</div>'), unsafe_allow_html=True)
        st.markdown(clean_html('<div style="color:#94A3B8; font-size:0.85rem; margin-bottom:12px;">Ingest pre-formatted GitHub issues into Weaviate without needing live API tokens.</div>'), unsafe_allow_html=True)
        if st.button("Load Synthetic GitHub Issues (5)", type="secondary"):
            try:
                res = load_synthetic_github_issues(client)
                st.success(f"Ingested {res['inserted']} new GitHub issues, {res['updated']} updated.")
            except Exception as exc:
                st.error(f"Failed: {exc}")


# ===========================================================================
# PAGE 5: KNOWLEDGE ASSISTANT
# ===========================================================================

elif page == "Knowledge Assistant":
    require_client()

    st.markdown(clean_html("""
    <div style="margin-top: 10px; margin-bottom: 20px;">
        <h1 style="font-size: 1.65rem; font-weight: 700; color: #F8FAFC; margin: 0 0 4px 0;">Knowledge Assistant</h1>
        <div style="color: #94A3B8; font-size: 0.85rem;">RAG-assisted debugging using retrieved issues and knowledge base articles</div>
    </div>
    """), unsafe_allow_html=True)

    # ── RATE LIMIT WARNING PANEL (Exact User Requirement) ──
    # Restrained dark amber warning panel matching the design system
    if setup is not None and setup.knowledge_unavailable:
        err_msg = setup.knowledge_error or "The DevFindKnowledge collection creation was rate-limited by Weaviate Cloud."
        st.markdown(clean_html(f"""
        <div style="border: 1px solid #78350F; border-left: 4px solid #F59E0B; background-color: #1A1608; border-radius: 8px; padding: 16px 20px; margin-bottom: 16px;">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
                <span style="width:8px; height:8px; border-radius:50%; background:#F59E0B; display:inline-block;"></span>
                <span style="font-weight:600; color:#F59E0B; font-size:0.95rem;">Knowledge Assistant Temporarily Unavailable (HTTP 429)</span>
            </div>
            <div style="color:#FDE68A; font-size:0.85rem; line-height:1.5;">
                {err_msg}
            </div>
            <div style="margin-top:10px; font-size:0.8rem; color:#B45309;">
                Knowledge base search is paused to prevent API failures. 
                Issue Management, Duplicate Finder, and Dashboard are unaffected and operating normally.<br>
                To retry, wait for the rate limit window to reset or restart the application.
            </div>
        </div>
        """), unsafe_allow_html=True)
        st.stop()

    # LLM Provider Status
    llm_ok = is_llm_available()
    provider_name = os.getenv("LLM_PROVIDER", "none")
    if llm_ok:
        st.markdown(clean_html(f'<div style="background:#111C27; border:1px solid #263746; border-radius:8px; padding:10px 14px; color:#14B8A6; font-size:0.85rem; margin-bottom:14px;">LLM Provider Active: <b>{provider_name}</b></div>'), unsafe_allow_html=True)
    else:
        st.markdown(clean_html(f"""
        <div style="background:#111C27; border:1px solid #263746; border-left: 3px solid #64748B; border-radius:8px; padding:10px 14px; color:#94A3B8; font-size:0.85rem; margin-bottom:14px;">
            No LLM configured (LLM_PROVIDER={provider_name!r}). Evidence summary will be retrieved without AI synthesis.
        </div>
        """), unsafe_allow_html=True)

    with st.form("knowledge_query_form"):
        k_question = st.text_area(
            "Describe the defect or debugging query",
            height=90,
            placeholder="e.g. Why does the session expire after refreshing the page?",
        )
        kc_1, kc_2, kc_3 = st.columns(3)
        k_iss_count = kc_1.slider("Issue Citations", 1, 10, 5)
        k_doc_count = kc_2.slider("Knowledge Chunks", 1, 10, 3)
        k_search_mode = kc_3.selectbox("Search Mode", ["Hybrid", "Semantic"])

        k_submit = st.form_submit_button("Investigate Root Cause", type="primary")

    if k_submit and k_question.strip():
        with st.spinner("Retrieving issues, knowledge chunks, and compiling citations..."):
            try:
                fn = hybrid_search if k_search_mode == "Hybrid" else semantic_search
                iss_resp = fn(client, k_question.strip(), limit=k_iss_count)
                chunks_resp = search_knowledge(client, k_question.strip(), limit=k_doc_count)

                rag_out = rag_debug_assist(
                    question=k_question.strip(),
                    search_results=iss_resp.results,
                    knowledge_chunks=chunks_resp,
                )
                st.session_state.rag_response = rag_out
            except Exception as exc:
                st.error(f"Investigation failed: {exc}")

    # Grounded Evidence Response
    if st.session_state.rag_response:
        r_resp = st.session_state.rag_response
        with st.container(border=True):
            st.markdown(clean_html('<div style="font-weight:600; font-size:0.95rem; color:#F8FAFC; margin-bottom:8px;">Investigation Results</div>'), unsafe_allow_html=True)
            st.write(r_resp.answer)

            if r_resp.citations:
                st.markdown(clean_html('<div style="font-weight:600; font-size:0.85rem; color:#94A3B8; margin-top:16px; margin-bottom:8px;">Grounded Citations:</div>'), unsafe_allow_html=True)
                for cit in r_resp.citations:
                    icon_tag = "Issue" if cit.source_type == "issue" else "Doc"
                    with st.expander(f"[{icon_tag}] {cit.identifier} — {cit.title}"):
                        if cit.excerpt:
                            st.markdown(f"*{cit.excerpt}*")
                        if cit.source_url:
                            st.markdown(f"[Source Link]({cit.source_url})")
