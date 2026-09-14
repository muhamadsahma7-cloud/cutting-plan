"""Visual theme matching the original web app's palette (web/styles.css),
applied on top of Streamlit's default components via CSS injection.
"""

import streamlit as st

PRIMARY = "#2563eb"
PRIMARY_LIGHT = "#3b82f6"
SUCCESS = "#10b981"
WARNING = "#f59e0b"
DANGER = "#ef4444"
INFO = "#06b6d4"
DARK = "#1e293b"
LIGHT = "#f8fafc"
BORDER = "#e2e8f0"

CSS = f"""
<style>
:root {{
    --primary: {PRIMARY};
    --primary-light: {PRIMARY_LIGHT};
    --success: {SUCCESS};
    --warning: {WARNING};
    --danger: {DANGER};
    --info: {INFO};
    --dark: {DARK};
    --light: {LIGHT};
    --border: {BORDER};
}}

/* Page background */
[data-testid="stAppViewContainer"] {{
    background-color: var(--light);
}}
[data-testid="stHeader"] {{
    background-color: transparent;
}}

/* Sidebar */
[data-testid="stSidebar"] {{
    background-color: #ffffff;
    border-right: 1px solid var(--border);
}}

/* Buttons */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
    border-radius: 8px;
    font-weight: 600;
    border: 1px solid var(--border);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {{
    transform: translateY(-1px);
    box-shadow: 0 4px 10px rgba(37, 99, 235, 0.18);
}}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
    background: linear-gradient(135deg, var(--primary), var(--primary-light));
    border: none;
    color: white;
}}

/* Tabs styled as pill navigation */
.stTabs [data-baseweb="tab-list"] {{
    gap: 4px;
    border-bottom: 2px solid var(--border);
}}
.stTabs [data-baseweb="tab"] {{
    border-radius: 8px 8px 0 0;
    padding: 8px 18px;
    font-weight: 600;
    color: var(--dark);
}}
.stTabs [aria-selected="true"] {{
    background: linear-gradient(135deg, var(--primary), var(--primary-light));
    color: white !important;
}}

/* Metric cards */
[data-testid="stMetric"] {{
    background: linear-gradient(135deg, #f8fafc, #e2e8f0);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1rem 1rem 0.75rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}}
[data-testid="stMetricValue"] {{
    color: var(--primary);
    font-weight: 700;
}}
[data-testid="stMetricLabel"] {{
    color: #64748b;
    font-weight: 600;
    text-transform: uppercase;
    font-size: 0.72rem !important;
    letter-spacing: 0.03em;
}}

/* Bordered containers used as "cards" */
[data-testid="stVerticalBlockBorderWrapper"] {{
    border-radius: 12px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    background: #ffffff;
}}

/* Data editor / dataframe wrapper */
[data-testid="stDataFrame"], [data-testid="stElementContainer"] div[data-testid="stDataFrameResizable"] {{
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid var(--border);
}}

/* Inputs focus ring */
input:focus, textarea:focus {{
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15) !important;
}}

/* Success/warning/error alert boxes: rounder corners */
[data-testid="stAlert"] {{
    border-radius: 10px;
}}

.app-banner {{
    background: linear-gradient(135deg, var(--primary), var(--primary-light));
    color: white;
    padding: 1.1rem 1.5rem;
    border-radius: 12px;
    margin-bottom: 1.25rem;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.15);
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.5rem;
}}
.app-banner h1 {{
    font-size: 1.5rem;
    margin: 0;
    font-weight: 700;
    color: white;
}}
.app-banner .subtitle {{
    font-size: 0.85rem;
    opacity: 0.9;
}}
.app-banner .badge {{
    background: rgba(255,255,255,0.2);
    padding: 0.25rem 0.6rem;
    border-radius: 8px;
    font-size: 0.75rem;
    font-weight: 600;
}}
</style>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)


def banner(title: str, subtitle: str = "", badge: str = ""):
    badge_html = f'<span class="badge">{badge}</span>' if badge else ""
    st.markdown(
        f"""
        <div class="app-banner">
            <div>
                <h1>📐 {title}</h1>
                <div class="subtitle">{subtitle}</div>
            </div>
            {badge_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
