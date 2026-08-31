"""
SpacePoint - Branding & Styling Helpers
Author: Kommal
"""

from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

LOGO_PATH = Path("assets/spacepoint_logo.png")

# App identity shown as a small overline in the page header - kept
# separate from each page's own title so headings read as just
# "Mission Map", not "SpacePoint Mission Map".
APP_NAME = "SpacePoint"
APP_TAGLINE = "Drone Remote Sensing"

# Design tokens - single source of truth for color/type
TOKENS = {
    "bg": "#0A0C12",
    "panel": "#10131C",
    "panel_raised": "#161A26",
    "border": "#262B3B",
    "border_strong": "#363C52",
    "accent": "#8B5CF6",
    "accent_soft": "#BFA7FF",
    "accent_dim": "rgba(139, 92, 246, 0.14)",
    "text": "#E8EAF0",
    "text_secondary": "#B4B8C6",
    "muted": "#7C8194",
    "success": "#6EE7B7",
    "warning": "#F5C97A",
    "danger": "#F28B8B",
    "font_sans": "'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    "font_mono": "'IBM Plex Mono', ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace",
}

# Sequential ramp for sensor/data values, kept separate from the accent color
DATA_RAMP = ["#3E5872", "#4FD1C5", "#F5C97A"]  # cool -> mid -> warm

STATE_COLORS = {
    "ok": TOKENS["success"],
    "warning": TOKENS["warning"],
    "danger": TOKENS["danger"],
    "neutral": TOKENS["muted"],
}
STATE_LABELS = {
    "ok": "NOMINAL",
    "warning": "FLAGGED",
    "danger": "CRITICAL",
    "neutral": "N/A",
}


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


def _utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def apply_page_config(page_title: str):
    """Sets browser tab title and favicon - call first on every page."""
    st.set_page_config(
        page_title=f"SpacePoint | {page_title}",
        page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else None,
        layout="wide",
    )


def render_sidebar_logo():
    """Shows the logo above the page nav list in the sidebar."""
    if LOGO_PATH.exists():
        st.logo(str(LOGO_PATH), icon_image=str(LOGO_PATH))


def render_sidebar_status(state: str = "ok", label: str = "OPERATIONAL"):
    """Small system-status readout at the bottom of the sidebar nav."""
    color = STATE_COLORS.get(state, STATE_COLORS["neutral"])
    st.sidebar.markdown(
        f"""
        <div class="sp-sidebar-status">
            <div class="sp-sidebar-status-label">SYSTEM STATUS</div>
            <div class="sp-sidebar-status-row">
                <span class="sp-status-dot" style="background:{color};"></span>
                <span class="sp-mono">{label}</span>
            </div>
            <div class="sp-sidebar-status-time sp-mono">{_utc_timestamp()}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_header(subtitle: str, meta: dict | None = None):
    """Mission-console header used on every page.

    subtitle: this page's own name (e.g. "Mission Map") - rendered as
    the main heading, on its own, with nothing prepended to it. The
    app's own name/tagline is shown above it as a small overline
    instead, so the brand appears once per page without merging into
    the page's actual title text.
    meta: optional ordered dict of small metadata fields under the title.
    """
    meta = meta or {}
    meta_html = "".join(
        f'<span class="sp-header-meta-item"><span class="sp-header-meta-key">{k}</span>'
        f'<span class="sp-header-meta-val sp-mono">{v}</span></span>'
        for k, v in meta.items()
    )

    st.markdown(
        f"""
        <div class="sp-header">
            <div class="sp-header-top">
                <div class="sp-header-titleblock">
                    <span class="sp-header-brand">{APP_NAME}<span class="sp-header-brand-divider">·</span>{APP_TAGLINE}</span>
                    <span class="sp-header-subtitle">{subtitle}</span>
                </div>
                <div class="sp-header-status">
                    <span class="sp-status-dot sp-status-dot-ok"></span>
                    <span class="sp-mono sp-header-status-text">OPERATIONAL</span>
                    <span class="sp-header-divider">/</span>
                    <span class="sp-mono sp-header-status-text">{_utc_timestamp()}</span>
                </div>
            </div>
            {f'<div class="sp-header-meta">{meta_html}</div>' if meta else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(title: str, caption: str | None = None):
    """Technical section label with an uppercase title and thin rule."""
    st.markdown(
        f"""
        <div class="sp-section-header">
            <span class="sp-section-title">{title.upper()}</span>
            {f'<span class="sp-section-caption">{caption}</span>' if caption else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_bar(fields: dict):
    """Horizontal strip of label/value pairs, e.g.
    render_status_bar({"MISSION": "vineyard_survey_04", "SAMPLES": 812})."""
    items = "".join(
        f'<div class="sp-statusbar-item"><span class="sp-statusbar-label">{k}</span>'
        f'<span class="sp-statusbar-value sp-mono">{v}</span></div>'
        for k, v in fields.items()
    )
    st.markdown(f'<div class="sp-statusbar">{items}</div>', unsafe_allow_html=True)


def render_technical_metadata(rows: dict, columns: int = 1):
    """Compact label:value monospace list for coordinates, IDs, etc."""
    items = "".join(
        f'<div class="sp-meta-row"><span class="sp-meta-key">{k}</span>'
        f'<span class="sp-meta-val sp-mono">{v}</span></div>'
        for k, v in rows.items()
    )
    st.markdown(
        f'<div class="sp-meta-grid" style="--sp-meta-cols:{columns};">{items}</div>',
        unsafe_allow_html=True,
    )


def render_metric_panel(label: str, value, sublabel: str | None = None, tone: str = "neutral"):
    """Instrument-style metric block, for layouts where st.metric doesn't fit."""
    color = STATE_COLORS.get(tone, TOKENS["text"]) if tone != "neutral" else TOKENS["text"]
    st.markdown(
        f"""
        <div class="sp-metric-panel">
            <div class="sp-metric-label">{label.upper()}</div>
            <div class="sp-metric-value sp-mono" style="color:{color};">{value}</div>
            {f'<div class="sp-metric-sublabel">{sublabel}</div>' if sublabel else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_state_indicator(label: str, state: str = "neutral", detail: str | None = None):
    """Status row with both a colored dot and a text label (never color alone)."""
    color = STATE_COLORS.get(state, STATE_COLORS["neutral"])
    state_text = STATE_LABELS.get(state, state.upper())
    st.markdown(
        f"""
        <div class="sp-state-row">
            <span class="sp-status-dot" style="background:{color};"></span>
            <span class="sp-state-label">{label}</span>
            <span class="sp-state-value sp-mono" style="color:{color};">{state_text}</span>
            {f'<span class="sp-state-detail sp-mono">{detail}</span>' if detail else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_data_source(name: str, description: str):
    """One row in a data-provenance list."""
    st.markdown(
        f"""
        <div class="sp-source-row">
            <span class="sp-source-name sp-mono">{name}</span>
            <span class="sp-source-desc">{description}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_pipeline_status(stages: list[tuple[str, str]]):
    """Numbered pipeline list. stages: list of (name, state) tuples,
    state one of "ok", "warning", "neutral", "danger"."""
    rows = ""
    for i, (name, state) in enumerate(stages, start=1):
        color = STATE_COLORS.get(state, STATE_COLORS["neutral"])
        state_text = {"ok": "COMPLETE", "warning": "RUNNING", "neutral": "QUEUED", "danger": "FAILED"}.get(state, state.upper())
        rows += (
            f'<div class="sp-pipeline-row">'
            f'<span class="sp-pipeline-index sp-mono">{i:02d}</span>'
            f'<span class="sp-pipeline-name">{name}</span>'
            f'<span class="sp-pipeline-state sp-mono" style="color:{color};">{state_text}</span>'
            f'</div>'
        )
    st.markdown(f'<div class="sp-pipeline">{rows}</div>', unsafe_allow_html=True)


def apply_custom_css():
    """Fonts, chrome removal, and instrument-style theming for native
    widgets plus the custom components above."""
    t = TOKENS
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

        :root {{
            --sp-bg: {t['bg']};
            --sp-panel: {t['panel']};
            --sp-panel-raised: {t['panel_raised']};
            --sp-border: {t['border']};
            --sp-border-strong: {t['border_strong']};
            --sp-accent: {t['accent']};
            --sp-accent-soft: {t['accent_soft']};
            --sp-accent-dim: {t['accent_dim']};
            --sp-text: {t['text']};
            --sp-text-secondary: {t['text_secondary']};
            --sp-muted: {t['muted']};
            --sp-success: {t['success']};
            --sp-warning: {t['warning']};
            --sp-danger: {t['danger']};
            --sp-font-sans: {t['font_sans']};
            --sp-font-mono: {t['font_mono']};
        }}

        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}

        html, body, [class*="css"] {{
            font-family: var(--sp-font-sans);
            color: var(--sp-text);
        }}

        .stApp {{
            background: var(--sp-bg);
        }}

        .sp-mono {{ font-family: var(--sp-font-mono); }}

        p, span, div, label {{
            color: var(--sp-text-secondary);
        }}
        h1, h2, h3, h4 {{
            color: var(--sp-text);
            font-weight: 600;
            letter-spacing: -0.01em;
        }}

        .sp-header {{
            border-bottom: 1px solid var(--sp-border);
            padding-bottom: 14px;
            margin-bottom: 22px;
        }}
        .sp-header-top {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .sp-header-titleblock {{
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}
        .sp-header-brand {{
            font-family: var(--sp-font-mono);
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: var(--sp-muted);
        }}
        .sp-header-brand-divider {{
            margin: 0 6px;
            color: var(--sp-border-strong);
        }}
        .sp-header-subtitle {{
            font-size: 26px;
            font-weight: 600;
            color: var(--sp-text);
        }}
        .sp-header-status {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .sp-header-status-text {{
            font-size: 12px;
            color: var(--sp-muted);
            letter-spacing: 0.04em;
        }}
        .sp-header-divider {{ color: var(--sp-border-strong); }}
        .sp-header-meta {{
            display: flex;
            gap: 24px;
            margin-top: 10px;
            flex-wrap: wrap;
        }}
        .sp-header-meta-item {{
            display: flex;
            gap: 6px;
            align-items: baseline;
        }}
        .sp-header-meta-key {{
            font-size: 10px;
            letter-spacing: 0.08em;
            color: var(--sp-muted);
        }}
        .sp-header-meta-val {{
            font-size: 12px;
            color: var(--sp-text-secondary);
        }}

        .sp-status-dot {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
            display: inline-block;
            background: var(--sp-success);
        }}
        .sp-status-dot-ok {{ background: var(--sp-success); }}

        .sp-section-header {{
            display: flex;
            align-items: baseline;
            gap: 10px;
            border-bottom: 1px solid var(--sp-border);
            padding-bottom: 8px;
            margin: 22px 0 14px 0;
        }}
        .sp-section-title {{
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.1em;
            color: var(--sp-text-secondary);
        }}
        .sp-section-caption {{
            font-size: 12px;
            color: var(--sp-muted);
        }}

        .sp-statusbar {{
            display: flex;
            flex-wrap: wrap;
            gap: 28px;
            background: var(--sp-panel);
            border: 1px solid var(--sp-border);
            border-radius: 4px;
            padding: 12px 18px;
            margin-bottom: 16px;
        }}
        .sp-statusbar-item {{
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}
        .sp-statusbar-label {{
            font-size: 10px;
            letter-spacing: 0.08em;
            color: var(--sp-muted);
        }}
        .sp-statusbar-value {{
            font-size: 13px;
            color: var(--sp-text);
        }}

        .sp-meta-grid {{
            display: grid;
            grid-template-columns: repeat(var(--sp-meta-cols, 1), minmax(160px, 1fr));
            gap: 4px 24px;
            background: var(--sp-panel);
            border: 1px solid var(--sp-border);
            border-radius: 4px;
            padding: 12px 16px;
            margin-bottom: 14px;
        }}
        .sp-meta-row {{
            display: flex;
            justify-content: space-between;
            gap: 12px;
            padding: 3px 0;
        }}
        .sp-meta-key {{
            font-size: 11px;
            letter-spacing: 0.06em;
            color: var(--sp-muted);
        }}
        .sp-meta-val {{
            font-size: 12px;
            color: var(--sp-text);
        }}

        .sp-metric-panel {{
            border: 1px solid var(--sp-border);
            background: var(--sp-panel);
            border-radius: 4px;
            padding: 12px 14px;
        }}
        .sp-metric-label {{
            font-size: 10px;
            letter-spacing: 0.08em;
            color: var(--sp-muted);
            margin-bottom: 4px;
        }}
        .sp-metric-value {{
            font-size: 28px;
            font-weight: 600;
            line-height: 1.1;
        }}
        .sp-metric-sublabel {{
            font-size: 11px;
            color: var(--sp-muted);
            margin-top: 4px;
        }}

        .sp-state-row {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 7px 0;
            border-bottom: 1px solid var(--sp-border);
        }}
        .sp-state-label {{
            font-size: 13px;
            color: var(--sp-text-secondary);
            flex: 1;
        }}
        .sp-state-value {{
            font-size: 11px;
            letter-spacing: 0.06em;
        }}
        .sp-state-detail {{
            font-size: 11px;
            color: var(--sp-muted);
        }}

        .sp-source-row {{
            display: flex;
            gap: 14px;
            padding: 8px 0;
            border-bottom: 1px solid var(--sp-border);
            align-items: baseline;
        }}
        .sp-source-name {{
            font-size: 12px;
            color: var(--sp-text);
            min-width: 160px;
        }}
        .sp-source-desc {{
            font-size: 12px;
            color: var(--sp-muted);
        }}

        .sp-pipeline {{
            border: 1px solid var(--sp-border);
            background: var(--sp-panel);
            border-radius: 4px;
            overflow: hidden;
        }}
        .sp-pipeline-row {{
            display: flex;
            align-items: center;
            gap: 14px;
            padding: 9px 14px;
            border-bottom: 1px solid var(--sp-border);
        }}
        .sp-pipeline-row:last-child {{ border-bottom: none; }}
        .sp-pipeline-index {{
            font-size: 11px;
            color: var(--sp-muted);
            width: 20px;
        }}
        .sp-pipeline-name {{
            flex: 1;
            font-size: 13px;
            color: var(--sp-text-secondary);
        }}
        .sp-pipeline-state {{
            font-size: 11px;
            letter-spacing: 0.06em;
        }}

        section[data-testid="stSidebar"] {{
            background: var(--sp-panel);
            border-right: 1px solid var(--sp-border);
        }}
        .sp-sidebar-status {{
            border-top: 1px solid var(--sp-border);
            margin-top: 16px;
            padding-top: 12px;
        }}
        .sp-sidebar-status-label {{
            font-size: 10px;
            letter-spacing: 0.08em;
            color: var(--sp-muted);
            margin-bottom: 6px;
        }}
        .sp-sidebar-status-row {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            color: var(--sp-text-secondary);
        }}
        .sp-sidebar-status-time {{
            font-size: 11px;
            color: var(--sp-muted);
            margin-top: 4px;
        }}

        [data-testid="stMetric"] {{
            background: var(--sp-panel);
            border: 1px solid var(--sp-border);
            border-radius: 4px;
            padding: 12px 14px;
        }}
        [data-testid="stMetricLabel"] {{
            font-size: 10px !important;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--sp-muted) !important;
        }}
        [data-testid="stMetricValue"] {{
            font-family: var(--sp-font-mono);
            font-size: 24px !important;
            color: var(--sp-text) !important;
        }}

        .stTabs [data-baseweb="tab-list"] {{
            border-bottom: 1px solid var(--sp-border);
            gap: 4px;
        }}
        .stTabs [data-baseweb="tab"] {{
            color: var(--sp-muted);
            font-size: 13px;
        }}
        .stTabs [aria-selected="true"] {{
            color: var(--sp-text) !important;
            border-bottom-color: var(--sp-accent) !important;
        }}

        button {{
            border-radius: 4px !important;
            font-family: var(--sp-font-sans) !important;
        }}
        .stButton > button, .stDownloadButton > button {{
            background: var(--sp-panel-raised);
            border: 1px solid var(--sp-border-strong);
            color: var(--sp-text);
        }}
        .stButton > button:hover, .stDownloadButton > button:hover {{
            border-color: var(--sp-accent);
            color: var(--sp-text);
        }}
        .stButton > button[kind="primary"] {{
            background: var(--sp-accent);
            border-color: var(--sp-accent);
            color: var(--sp-bg);
        }}

        [data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {{
            background: var(--sp-panel) !important;
            border-color: var(--sp-border-strong) !important;
            border-radius: 4px !important;
            color: var(--sp-text) !important;
        }}

        div[role="radiogroup"] label, .stCheckbox label {{
            color: var(--sp-text-secondary);
            font-size: 13px;
        }}

        [data-testid="stDataFrame"] {{
            border: 1px solid var(--sp-border);
            border-radius: 4px;
        }}

        .stExpander {{
            border: 1px solid var(--sp-border) !important;
            border-radius: 4px !important;
            background: var(--sp-panel);
        }}

        hr {{ border-color: var(--sp-border) !important; }}

        ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
        ::-webkit-scrollbar-track {{ background: var(--sp-bg); }}
        ::-webkit-scrollbar-thumb {{ background: var(--sp-border-strong); border-radius: 5px; }}
        </style>
        """,
        unsafe_allow_html=True,
    )