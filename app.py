import streamlit as st
import pandas as pd
import os
import re
import math
import json
import time
from datetime import datetime, timezone, timedelta
import plotly.graph_objects as go
from PIL import Image
import google.generativeai as genai
import numpy as np
from supabase import create_client, Client

# ==========================================
# 🛡️ HELPER FUNCTIONS
# ==========================================
def safe_json_loads(text):
    if not text: return {}
    try:
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        if start_idx != -1 and end_idx != -1:
            clean_text = text[start_idx:end_idx+1]
            return json.loads(clean_text)
        return json.loads(text)
    except Exception:
        clean = text.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(clean)
        except:
            return {}

# ต้องเป็น Streamlit call แรกเสมอ
st.set_page_config(
    page_title="GEM System 10.0 · The Oracle",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 🎨 DARK PROFESSIONAL THEME (Bloomberg/TradingView Style)
# ==========================================
GEM_THEME = """
<style>
/* ── Google Fonts ── */
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');

/* ── CSS Variables ── */
:root {
    --bg-base:        #0a0c10;
    --bg-surface:     #111318;
    --bg-card:        #161b24;
    --bg-hover:       #1c2330;
    --border:         #1e2738;
    --border-bright:  #2a3650;

    --accent-cyan:    #00d4ff;
    --accent-green:   #00ff88;
    --accent-amber:   #f5a623;
    --accent-red:     #ff3b5c;
    --accent-purple:  #a78bfa;

    --text-primary:   #e8edf5;
    --text-secondary: #7a8599;
    --text-muted:     #3d4a60;

    --font-mono:   'Space Mono', monospace;
    --font-body:   'DM Sans', sans-serif;

    --radius-sm:  4px;
    --radius-md:  8px;
    --radius-lg:  12px;
    --glow-cyan:  0 0 20px rgba(0,212,255,0.15);
    --glow-green: 0 0 20px rgba(0,255,136,0.15);
}

/* ── Global Reset ── */
html, body, [class*="css"] {
    font-family: var(--font-body) !important;
    background-color: var(--bg-base) !important;
    color: var(--text-primary) !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: var(--bg-base); }
::-webkit-scrollbar-thumb { background: var(--border-bright); border-radius: 2px; }

/* ── Main Container ── */
.main .block-container {
    padding: 1.5rem 2rem 2rem !important;
    max-width: 1400px !important;
    background: var(--bg-base) !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: var(--bg-surface) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] .block-container {
    padding: 1.5rem 1rem !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] label {
    color: var(--text-secondary) !important;
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    font-family: var(--font-mono) !important;
}

/* ── Page Title ── */
h1 {
    font-family: var(--font-mono) !important;
    font-size: 1.4rem !important;
    font-weight: 700 !important;
    color: var(--accent-cyan) !important;
    letter-spacing: 0.05em !important;
    border-bottom: 1px solid var(--border) !important;
    padding-bottom: 0.75rem !important;
    margin-bottom: 1.5rem !important;
}
h1::before {
    content: "▸ ";
    color: var(--accent-green);
}

h2 {
    font-family: var(--font-mono) !important;
    font-size: 0.95rem !important;
    font-weight: 700 !important;
    color: var(--text-secondary) !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
}
h3 {
    font-family: var(--font-mono) !important;
    font-size: 0.85rem !important;
    color: var(--accent-cyan) !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
}
h4, h5 {
    font-family: var(--font-body) !important;
    color: var(--text-secondary) !important;
    font-size: 0.8rem !important;
    letter-spacing: 0.04em !important;
}

/* ── Tabs ── */
[data-testid="stTabs"] [role="tablist"] {
    background: var(--bg-surface) !important;
    border-bottom: 1px solid var(--border) !important;
    gap: 0 !important;
    padding: 0 !important;
}
[data-testid="stTabs"] [role="tab"] {
    font-family: var(--font-mono) !important;
    font-size: 0.7rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: var(--text-muted) !important;
    padding: 0.65rem 1.2rem !important;
    border-radius: 0 !important;
    border-bottom: 2px solid transparent !important;
    transition: all 0.2s ease !important;
}
[data-testid="stTabs"] [role="tab"]:hover {
    color: var(--text-secondary) !important;
    background: var(--bg-hover) !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: var(--accent-cyan) !important;
    background: transparent !important;
    border-bottom: 2px solid var(--accent-cyan) !important;
}
[data-testid="stTabPanel"] {
    padding-top: 1.5rem !important;
    background: var(--bg-base) !important;
}

/* ── Metric Cards ── */
[data-testid="stMetric"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-md) !important;
    padding: 1rem 1.2rem !important;
    transition: border-color 0.2s ease !important;
}
[data-testid="stMetric"]:hover {
    border-color: var(--border-bright) !important;
}
[data-testid="stMetricLabel"] {
    font-family: var(--font-mono) !important;
    font-size: 0.65rem !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: var(--text-muted) !important;
}
[data-testid="stMetricValue"] {
    font-family: var(--font-mono) !important;
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    color: var(--text-primary) !important;
}
[data-testid="stMetricDelta"] {
    font-family: var(--font-mono) !important;
    font-size: 0.7rem !important;
}

/* ── Buttons ── */
[data-testid="stButton"] > button {
    font-family: var(--font-mono) !important;
    font-size: 0.72rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    border-radius: var(--radius-sm) !important;
    border: 1px solid var(--border-bright) !important;
    background: var(--bg-card) !important;
    color: var(--text-secondary) !important;
    padding: 0.5rem 1rem !important;
    transition: all 0.2s ease !important;
    height: 2.4rem !important;
}
[data-testid="stButton"] > button:hover {
    border-color: var(--accent-cyan) !important;
    color: var(--accent-cyan) !important;
    background: rgba(0,212,255,0.05) !important;
    box-shadow: var(--glow-cyan) !important;
}
/* Primary Button */
[data-testid="stButton"] > button[kind="primary"] {
    background: rgba(0,212,255,0.08) !important;
    border: 1px solid var(--accent-cyan) !important;
    color: var(--accent-cyan) !important;
    box-shadow: var(--glow-cyan) !important;
}
[data-testid="stButton"] > button[kind="primary"]:hover {
    background: rgba(0,212,255,0.18) !important;
    box-shadow: 0 0 30px rgba(0,212,255,0.25) !important;
}

/* ── Inputs ── */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea {
    font-family: var(--font-mono) !important;
    font-size: 0.82rem !important;
    background: var(--bg-surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text-primary) !important;
    padding: 0.5rem 0.75rem !important;
    transition: border-color 0.2s ease !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: var(--accent-cyan) !important;
    box-shadow: 0 0 0 1px rgba(0,212,255,0.2) !important;
    outline: none !important;
}
[data-testid="stTextInput"] label,
[data-testid="stNumberInput"] label,
[data-testid="stTextArea"] label,
[data-testid="stSelectbox"] label,
[data-testid="stSlider"] label {
    font-family: var(--font-mono) !important;
    font-size: 0.65rem !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: var(--text-muted) !important;
}

/* NumberInput arrows */
[data-testid="stNumberInput"] [data-testid="stNumberInputStepDown"],
[data-testid="stNumberInput"] [data-testid="stNumberInputStepUp"] {
    background: var(--bg-hover) !important;
    border-color: var(--border) !important;
    color: var(--text-secondary) !important;
}

/* ── Select Box ── */
[data-testid="stSelectbox"] > div > div {
    font-family: var(--font-mono) !important;
    font-size: 0.8rem !important;
    background: var(--bg-surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text-primary) !important;
}

/* ── Slider ── */
[data-testid="stSlider"] [data-testid="stSliderTrack"] {
    background: var(--border-bright) !important;
}
[data-testid="stSlider"] [data-testid="stSliderThumb"] {
    background: var(--accent-cyan) !important;
    border: 2px solid var(--bg-base) !important;
    box-shadow: var(--glow-cyan) !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-md) !important;
    overflow: hidden !important;
}
[data-testid="stExpander"] summary {
    font-family: var(--font-mono) !important;
    font-size: 0.72rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: var(--text-secondary) !important;
    padding: 0.75rem 1rem !important;
    background: var(--bg-surface) !important;
    border-bottom: 1px solid var(--border) !important;
}
[data-testid="stExpander"] summary:hover {
    background: var(--bg-hover) !important;
    color: var(--accent-cyan) !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
    padding: 1rem !important;
    background: var(--bg-card) !important;
}

/* ── Alert Boxes ── */
[data-testid="stSuccess"], .stSuccess {
    background: rgba(0,255,136,0.06) !important;
    border: 1px solid rgba(0,255,136,0.3) !important;
    border-left: 3px solid var(--accent-green) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--accent-green) !important;
    font-family: var(--font-body) !important;
    font-size: 0.85rem !important;
}
[data-testid="stError"], .stError {
    background: rgba(255,59,92,0.06) !important;
    border: 1px solid rgba(255,59,92,0.3) !important;
    border-left: 3px solid var(--accent-red) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--accent-red) !important;
    font-family: var(--font-body) !important;
    font-size: 0.85rem !important;
}
[data-testid="stWarning"], .stWarning {
    background: rgba(245,166,35,0.06) !important;
    border: 1px solid rgba(245,166,35,0.3) !important;
    border-left: 3px solid var(--accent-amber) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--accent-amber) !important;
    font-family: var(--font-body) !important;
    font-size: 0.85rem !important;
}
[data-testid="stInfo"], .stInfo {
    background: rgba(0,212,255,0.06) !important;
    border: 1px solid rgba(0,212,255,0.25) !important;
    border-left: 3px solid var(--accent-cyan) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text-secondary) !important;
    font-family: var(--font-body) !important;
    font-size: 0.85rem !important;
}

/* ── Data Editor / Table ── */
[data-testid="stDataFrame"],
[data-testid="stDataEditor"] {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-md) !important;
    overflow: hidden !important;
}
.dvn-scroller { background: var(--bg-card) !important; }

/* ── Checkbox ── */
[data-testid="stCheckbox"] label {
    font-family: var(--font-body) !important;
    font-size: 0.82rem !important;
    color: var(--text-secondary) !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
}

/* ── Radio ── */
[data-testid="stRadio"] label {
    font-family: var(--font-body) !important;
    font-size: 0.82rem !important;
    color: var(--text-secondary) !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
}

/* ── File Uploader ── */
[data-testid="stFileUploader"] {
    background: var(--bg-card) !important;
    border: 1px dashed var(--border-bright) !important;
    border-radius: var(--radius-md) !important;
    padding: 1rem !important;
}
[data-testid="stFileUploader"] label {
    color: var(--text-secondary) !important;
    font-size: 0.8rem !important;
}

/* ── Sidebar Status badges ── */
[data-testid="stSidebar"] [data-testid="stSuccess"] {
    font-size: 0.72rem !important;
    padding: 0.4rem 0.6rem !important;
}
[data-testid="stSidebar"] [data-testid="stInfo"] {
    font-size: 0.7rem !important;
    padding: 0.35rem 0.6rem !important;
}

/* ── Divider ── */
hr {
    border: none !important;
    border-top: 1px solid var(--border) !important;
    margin: 1.25rem 0 !important;
}

/* ── Custom Section Headers ── */
.gem-section-title {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-muted);
    padding: 0.4rem 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.gem-section-title::before {
    content: "";
    display: inline-block;
    width: 6px;
    height: 6px;
    background: var(--accent-cyan);
    border-radius: 50%;
}

/* ── Stat Cards (custom) ── */
.gem-stat-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
    margin-bottom: 1.25rem;
}
.gem-stat-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 0.9rem 1.1rem;
    transition: border-color 0.25s;
}
.gem-stat-card:hover { border-color: var(--border-bright); }
.gem-stat-card .label {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.35rem;
}
.gem-stat-card .value {
    font-family: var(--font-mono);
    font-size: 1.4rem;
    font-weight: 700;
    color: var(--text-primary);
}
.gem-stat-card .value.up   { color: var(--accent-green); }
.gem-stat-card .value.down { color: var(--accent-red); }
.gem-stat-card .value.warn { color: var(--accent-amber); }

/* ── Live Pulse Indicator ── */
.live-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-family: var(--font-mono);
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: var(--accent-red);
    text-transform: uppercase;
}
.live-dot {
    width: 7px;
    height: 7px;
    background: var(--accent-red);
    border-radius: 50%;
    animation: pulse-dot 1.4s ease-in-out infinite;
}
@keyframes pulse-dot {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(0.75); }
}

/* ── EV Decision Badge ── */
.ev-approve {
    background: rgba(0,255,136,0.08);
    border: 1px solid rgba(0,255,136,0.35);
    border-left: 3px solid var(--accent-green);
    border-radius: var(--radius-sm);
    padding: 0.75rem 1rem;
    font-family: var(--font-mono);
    font-size: 0.8rem;
    color: var(--accent-green);
    letter-spacing: 0.04em;
}
.ev-reject {
    background: rgba(255,59,92,0.08);
    border: 1px solid rgba(255,59,92,0.35);
    border-left: 3px solid var(--accent-red);
    border-radius: var(--radius-sm);
    padding: 0.75rem 1rem;
    font-family: var(--font-mono);
    font-size: 0.8rem;
    color: var(--accent-red);
    letter-spacing: 0.04em;
}

/* ── Spinner ── */
[data-testid="stSpinner"] { color: var(--accent-cyan) !important; }
[data-testid="stSpinner"] p { 
    font-family: var(--font-mono) !important;
    font-size: 0.75rem !important;
    color: var(--text-secondary) !important;
    letter-spacing: 0.06em !important;
}

/* ── Plotly Charts ── */
.js-plotly-plot .plotly .modebar {
    background: var(--bg-card) !important;
}
.js-plotly-plot .plotly .modebar-btn path {
    fill: var(--text-muted) !important;
}

/* ── Sidebar NumberInput ── */
[data-testid="stSidebar"] [data-testid="stNumberInput"] input {
    font-size: 0.8rem !important;
    padding: 0.35rem 0.5rem !important;
}

/* ── Top header bar accent ── */
[data-testid="stHeader"] {
    background: var(--bg-surface) !important;
    border-bottom: 1px solid var(--border) !important;
}

/* ── Paragraph text ── */
p, li {
    font-family: var(--font-body) !important;
    font-size: 0.85rem !important;
    color: var(--text-secondary) !important;
    line-height: 1.6 !important;
}

/* ── Caption ── */
[data-testid="stCaptionContainer"] {
    font-family: var(--font-mono) !important;
    font-size: 0.65rem !important;
    color: var(--text-muted) !important;
    letter-spacing: 0.06em !important;
}

/* ── Sidebar Header Text ── */
[data-testid="stSidebar"] p {
    font-size: 0.78rem !important;
    color: var(--text-secondary) !important;
}

/* ── Hide Streamlit Branding ── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
[data-testid="stToolbar"] { display: none !important; }
</style>
"""

st.markdown(GEM_THEME, unsafe_allow_html=True)

# ==========================================
# DB CONNECTION
# ==========================================
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_connection()

# ==========================================
# 0. SESSION STATE
# ==========================================
def init_session_state():
    defaults = {
        'match_name': "ชื่อคู่แข่งขัน",
        'h1x2_val': 1.0, 'd1x2_val': 1.0, 'a1x2_val': 1.0,
        'hdp_line_val': 0.0, 'hdp_h_w_val': 0.0, 'hdp_a_w_val': 0.0,
        'ou_line_val': 2.5, 'ou_over_w_val': 0.0, 'ou_under_w_val': 0.0,
        'raw_text': "",
        'live_hdp': 0.0, 'live_ou': 2.50,
        'lh_s': 0, 'la_s': 0, 'current_min': 45
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

init_session_state()

def clear_inplay_data():
    inplay_defaults = {
        'lh_s_input': 0, 'la_s_input': 0, 'rc_h': False, 'rc_a': False, 'current_min': 45,
        'pre_h': 2.0, 'pre_d': 3.0, 'pre_a': 3.0, 'pre_ou': 2.5,
        'live_hdp': 0.0, 'live_hdp_h': 0.9, 'live_hdp_a': 0.9,
        'live_ou': 2.5, 'live_ou_over': 0.9, 'live_ou_under': 0.9
    }
    for k, v in inplay_defaults.items(): st.session_state[k] = v

@st.cache_data(ttl=60)
def load_gem_rules():
    if not supabase: return "⚠️ ระบบไม่สามารถเชื่อมต่อฐานข้อมูล Supabase ได้"
    try:
        response = supabase.table("gem_knowledge").select("rule_id, category, rule_text").eq("is_active", True).execute()
        if response.data:
            rules_list = [f"[{item['rule_id']} - หมวด {item['category']}] {item['rule_text']}" for item in response.data]
            return "\n".join(rules_list)
        return "ยังไม่มีข้อมูลกฎในระบบฐานข้อมูล"
    except Exception as e: return f"Error loading rules from Cloud: {e}"

def get_dynamic_rules(target, is_live, raw_rules):
    rules = raw_rules.split('\n')
    dynamic_db = []
    is_ah = target in ["เจ้าบ้าน", "ทีมเยือน"]
    is_ou = target in ["สูง", "ต่ำ"]
    for rule in rules:
        if not rule.strip(): continue
        rule_lower = rule.lower()
        if is_ou and any(w in rule_lower for w in ['เจ้าบ้าน', 'ทีมเยือน', 'ต่อ', 'รอง', 'ah']) and not any(w in rule_lower for w in ['สูง', 'ต่ำ', 'สกอร์', 'o/u']): continue
        if is_ah and any(w in rule_lower for w in ['สูง', 'ต่ำ', 'สกอร์รวม', 'o/u']) and not any(w in rule_lower for w in ['เจ้าบ้าน', 'ทีมเยือน', 'ต่อ', 'รอง', 'ah']): continue
        if not is_live and any(w in rule_lower for w in ['live', 'สด', 'นาที', 'ใบแดง', 'สกอร์ปัจจุบัน']): continue
        if is_live and any(w in rule_lower for w in ['ก่อนเตะ', 'pre-match', 'ราคาเปิด']) and not any(w in rule_lower for w in ['live', 'สด', 'ไหล']): continue
        dynamic_db.append(rule)
    return "\n".join(dynamic_db)

def clear_form_data():
    st.session_state.raw_text = ""
    st.session_state.match_name = "ชื่อคู่แข่งขัน"
    st.session_state.h1x2_val = 1.0; st.session_state.d1x2_val = 1.0; st.session_state.a1x2_val = 1.0
    st.session_state.hdp_line_val = 0.0; st.session_state.hdp_h_w_val = 0.0; st.session_state.hdp_a_w_val = 0.0
    st.session_state.ou_line_val = 2.5; st.session_state.ou_over_w_val = 0.0; st.session_state.ou_under_w_val = 0.0

def parse_line(line_str):
    line_str = str(line_str).replace(' ', '').replace('+', '')
    is_negative = '-' in line_str
    line_str = line_str.replace('-', '')
    try:
        if '/' in line_str or ',' in line_str:
            sep = '/' if '/' in line_str else ','
            return (-1 if is_negative else 1) * ((float(line_str.split(sep)[0]) + float(line_str.split(sep)[1])) / 2.0)
        return float(line_str) * (-1 if is_negative else 1)
    except: return 0.0

# ==========================================
# 🧮 1. QUANT ENGINE
# ==========================================
def shin_devig(o_h, o_d, o_a):
    pi = [1/o_h, 1/o_d, 1/o_a]
    sum_pi = sum(pi)
    if sum_pi <= 1.0: return pi[0]/sum_pi, pi[1]/sum_pi, pi[2]/sum_pi
    low, high = 0.0, 1.0
    for _ in range(100):
        z = (low + high) / 2
        try:
            p = [(math.sqrt(z**2 + 4*(1-z)*pi_i) - z) / (2*(1-z)) for pi_i in pi]
            if sum(p) > 1: low = z
            else: high = z
        except ZeroDivisionError: break
    try: p = [(math.sqrt(z**2 + 4*(1-z)*pi_i) - z) / (2*(1-z)) for pi_i in pi]
    except ZeroDivisionError: p = pi
    sum_p = sum(p)
    return p[0]/sum_p, p[1]/sum_p, p[2]/sum_p

def poisson(k, lam): return (lam**k * math.exp(-lam)) / math.factorial(k)

def calc_dixon_coles_matrix(p_h, p_d, p_a, ou_line, ou_over_w, ou_under_w, rho, current_h=0, current_a=0, minutes_left=90, red_card_h=False, red_card_a=False):
    o_w = ou_over_w + 1.0 if ou_over_w < 1.1 else ou_over_w
    u_w = ou_under_w + 1.0 if ou_under_w < 1.1 else ou_under_w
    o_prob = 1.0 / o_w; u_prob = 1.0 / u_w
    true_o_prob = o_prob / (o_prob + u_prob)
    base_expected_total = ou_line + 0.20 + ((true_o_prob - 0.5) * 2.5)
    draw_divergence = 0.25 - p_d
    total_adjustment = draw_divergence * 8.0
    expected_total = max(0.5, base_expected_total + total_adjustment)
    supremacy = (p_h - p_a) * (expected_total ** 0.60)
    lam_h_base = max(0.15, (expected_total + supremacy) / 2.0)
    lam_a_base = max(0.15, (expected_total - supremacy) / 2.0)
    time_factor = (minutes_left / 90.0) ** 0.75
    lam_h = lam_h_base * time_factor
    lam_a = lam_a_base * time_factor
    if red_card_h: lam_h *= 0.50; lam_a *= 1.30
    if red_card_a: lam_a *= 0.50; lam_h *= 1.30
    matrix = [[0.0 for j in range(10)] for i in range(10)]
    for i in range(10):
        for j in range(10):
            base_prob = poisson(i, lam_h) * poisson(j, lam_a)
            if i == 0 and j == 0: tau = 1 - (lam_h * lam_a * rho)
            elif i == 0 and j == 1: tau = 1 + (lam_h * rho)
            elif i == 1 and j == 0: tau = 1 + (lam_a * rho)
            elif i == 1 and j == 1: tau = 1 - rho
            else: tau = 1.0
            matrix[i][j] = max(0, base_prob * tau)
    total_prob = sum(sum(row) for row in matrix)
    p_h2=0.0; p_h1=0.0; p_draw=0.0; p_a1=0.0; p_a2=0.0; p_ou={}
    for i in range(10):
        for j in range(10):
            prob = matrix[i][j] / total_prob
            final_h = i + current_h; final_a = j + current_a
            diff = final_h - final_a
            if diff >= 2: p_h2 += prob
            elif diff == 1: p_h1 += prob
            elif diff == 0: p_draw += prob
            elif diff == -1: p_a1 += prob
            elif diff <= -2: p_a2 += prob
            total_goals = final_h + final_a
            p_ou[total_goals] = p_ou.get(total_goals, 0.0) + prob
    return (p_h2, p_h1, p_draw, p_a1, p_a2, p_ou)

def calc_advanced_ah_ev(hdp, w2, w1, d, l1, l2, odds, is_fav):
    b = odds - 1; h = abs(hdp)
    if h == 0: return ((w2 + w1) * b) - ((l1 + l2) * 1)
    if is_fav:
        if h == 0.25: return ((w2 + w1) * b) - (d * 0.5) - ((l1 + l2) * 1)
        elif h == 0.5: return ((w2 + w1) * b) - ((d + l1 + l2) * 1)
        elif h == 0.75: return (w2 * b) + (w1 * (b/2)) - ((d + l1 + l2) * 1)
        elif h == 1.0: return (w2 * b) + (w1 * 0) - ((d + l1 + l2) * 1)
        elif h == 1.25: return (w2 * b) - (w1 * 0.5) - ((d + l1 + l2) * 1)
        elif h == 1.5: return (w2 * b) - ((w1 + d + l1 + l2) * 1)
    else:
        if h == 0.25: return ((w2 + w1) * b) + (d * (b/2)) - ((l1 + l2) * 1)
        elif h == 0.5: return ((w2 + w1 + d) * b) - ((l1 + l2) * 1)
        elif h == 0.75: return ((w2 + w1 + d) * b) - (l1 * 0.5) - (l2 * 1)
        elif h == 1.0: return ((w2 + w1 + d) * b) + (l1 * 0) - (l2 * 1)
        elif h == 1.25: return ((w2 + w1 + d) * b) + (l1 * (b/2)) - (l2 * 1)
        elif h == 1.5: return ((w2 + w1 + d + l1) * b) - (l2 * 1)
    return 0.0

def calc_advanced_ou_ev(ou_line, p_total, odds, is_over):
    b = odds - 1; fl = math.floor(ou_line); rm = ou_line - fl
    if is_over:
        if rm == 0.0:
            return (sum(p_total.get(k,0) for k in p_total if k > fl) * b) \
                 - (sum(p_total.get(k,0) for k in p_total if k < fl) * 1)
        elif rm == 0.25:
            return (sum(p_total.get(k,0) for k in p_total if k >= fl+1) * b) \
                 - (p_total.get(fl,0) * 0.5) \
                 - (sum(p_total.get(k,0) for k in p_total if k < fl) * 1)
        elif rm == 0.5:
            return (sum(p_total.get(k,0) for k in p_total if k >= fl+1) * b) \
                 - (sum(p_total.get(k,0) for k in p_total if k <= fl) * 1)
        elif rm == 0.75:
            return (sum(p_total.get(k,0) for k in p_total if k >= fl+2) * b) \
                 + (p_total.get(fl+1,0) * (b/2)) \
                 - (sum(p_total.get(k,0) for k in p_total if k <= fl) * 1)
    else:
        if rm == 0.0:
            return (sum(p_total.get(k,0) for k in p_total if k < fl) * b) \
                 - (sum(p_total.get(k,0) for k in p_total if k > fl) * 1)
        elif rm == 0.25:
            return (sum(p_total.get(k,0) for k in p_total if k < fl) * b) \
                 + (p_total.get(fl,0) * (b/2)) \
                 - (sum(p_total.get(k,0) for k in p_total if k >= fl+1) * 1)
        elif rm == 0.5:
            return (sum(p_total.get(k,0) for k in p_total if k <= fl) * b) \
                 - (sum(p_total.get(k,0) for k in p_total if k >= fl+1) * 1)
        elif rm == 0.75:
            return (sum(p_total.get(k,0) for k in p_total if k <= fl) * b) \
                 - (p_total.get(fl+1,0) * 0.5) \
                 - (sum(p_total.get(k,0) for k in p_total if k >= fl+2) * 1)
    return 0.0

# ==========================================
# 🧠 2. AI DECISION ENGINE
# ==========================================
def ai_quant_decision_engine(match_name, target, base_ev, hdp_line, odds, is_live=False, current_min=0, score="0-0", threshold=0.08, stats_data="", is_target_fav=None):
    raw_database = load_gem_rules()
    try: oracle_database = get_dynamic_rules(target, is_live, raw_database)
    except NameError: oracle_database = raw_database
    if not is_live:
        mode_instruction = (
            "[โหมดการวิเคราะห์: PRE-MATCH]\n"
            "เน้นการหา Mispriced Odds โดยใช้ Math-First Approach (70%) และใช้ GEM Rules เป็น Risk Filter (30%)\n"
            "ตรวจสอบ 'กับดักราคา' หรือ 'เรตแปลกประหลาด' หากไม่ใช่ Fatal Error ให้เน้นยืนยันตาม Base EV"
        )
    else:
        mode_instruction = (
            "[โหมดการวิเคราะห์: IN-PLAY LIVE]\n"
            "ตรวจสอบสถานการณ์ในสนามแบบ Real-time ร่วมกับ GEM RULES อย่างเต็มรูปแบบ\n"
            "หากละเมิดกฎระดับ Fatal ให้ Reject ทันที แต่ถ้า Base EV สูงมาก (+15% ขึ้นไป) และชนกฎระดับ Warning ให้พิจารณาอนุมัติได้"
        )
    role_info = ""
    if is_target_fav is True: role_info = " [สถานะ: ทีมต่อ (Favorite)]"
    elif is_target_fav is False: role_info = " [สถานะ: ทีมรอง (Underdog)]"
    prompt = (
        f"คุณคือ Chief Risk Officer (CRO) ประจำกองทุน Quant Sports Betting\n"
        f"วิสัยทัศน์: ลงทุนเพื่อเอาชนะ Margin ของเจ้ามือด้วยหลักการ Expected Value (EV)\n\n"
        f"[ข้อมูลหน้างาน]\n- คู่: {match_name}\n"
        f"- สถานการณ์: {'Live ' + str(current_min) + ' min (' + score + ')' if is_live else 'Pre-Match'}\n"
        f"- เป้าหมาย: {target}{role_info} (เรต {abs(hdp_line)}, Odds {odds})\n"
        f"- Base EV: {base_ev * 100:.2f}%\n\n"
        f"📊 [ข้อมูลสถิติเชิงลึก (ถ้ามี)]\n{stats_data}\n\n"
        f"{mode_instruction}\n\n"
        f"📖 [คัมภีร์ GEM RULES จาก CLOUD]\n{oracle_database}\n\n"
        "คำสั่งพิเศษ:\n"
        "1. เช็คสถานะ 'ทีมต่อ/ทีมรอง' ในข้อมูลหน้างานให้ดี ห้ามสับสน!\n"
        "2. ⚠️ แยกแยะตลาด (Market Isolation): ห้ามนำกฎคนละตลาดมาปะปน\n"
        "3. หากมีการละเมิดกฎ 'ต้อง' ระบุ [Rule ID] และ [Category] ให้ชัดเจน\n"
        "4. ค่า impact_score ต้องเป็นทศนิยม -1.0 ถึง 1.0 เท่านั้น\n\n"
        "ตอบกลับเป็น JSON Format (ภาษาไทย) เท่านั้น:\n"
        '{"pros_analysis":"...","cons_analysis":"...","rule_triggered":"...","impact_score":0.0,"final_decision":true,"final_comment":"...","confidence_level":3}'
    )
    for attempt in range(3):
        try:
            model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
            response = model.generate_content(prompt)
            data = safe_json_loads(response.text)
            if data:
                impact = float(data.get('impact_score', 0.0))
                if abs(impact) >= 1.0: impact = impact / 100.0
                data['impact_score'] = impact
                return data
        except Exception as e:
            if attempt == 2:
                return {
                    "pros_analysis": "ระบบ AI ขัดข้องชั่วคราว", "cons_analysis": f"Error: {str(e)}",
                    "rule_triggered": "System Fallback Activated", "impact_score": 0.0,
                    "final_decision": True if base_ev >= threshold else False,
                    "final_comment": "⚠️ ยืนยันไม้ด้วยคณิตศาสตร์ (Base EV) เนื่องจาก AI ไม่ตอบสนอง",
                    "confidence_level": 1
                }
            time.sleep(2)

# ==========================================
# 📊 UI COMPONENTS
# ==========================================
def create_ev_gauge(ev_value, title, threshold=8.0):
    ev_pct = ev_value * 100
    if ev_pct >= threshold: color = "#00ff88"
    elif ev_pct > 0: color = "#f5a623"
    else: color = "#ff3b5c"
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=ev_pct,
        number={'suffix': "%", 'font': {'color': color, 'size': 28, 'family': 'Space Mono'}},
        title={'text': title, 'font': {'size': 13, 'color': '#7a8599', 'family': 'Space Mono'}},
        gauge={
            'axis': {'range': [-20, 20], 'tickwidth': 1, 'tickcolor': "#2a3650",
                     'tickfont': {'color': '#3d4a60', 'size': 9, 'family': 'Space Mono'}},
            'bar': {'color': color, 'thickness': 0.25},
            'bgcolor': "rgba(0,0,0,0)", 'borderwidth': 0,
            'steps': [
                {'range': [-20, 0], 'color': "rgba(255,59,92,0.08)"},
                {'range': [0, threshold], 'color': "rgba(245,166,35,0.08)"},
                {'range': [threshold, 20], 'color': "rgba(0,255,136,0.08)"}
            ],
            'threshold': {'line': {'color': color, 'width': 2}, 'thickness': 0.8, 'value': ev_pct}
        }
    ))
    fig.update_layout(
        height=190,
        margin=dict(l=15, r=15, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={'color': '#7a8599'}
    )
    return fig

def render_oracle_result(ai_verdict, base_ev, net_ev):
    """Render AI analysis in styled cards."""
    stars_count = ai_verdict.get('confidence_level', 3)
    star_html = "★" * stars_count + "☆" * (5 - stars_count)

    st.markdown(f"""
    <div style="
        background: #111318;
        border: 1px solid #1e2738;
        border-radius: 8px;
        padding: 1.2rem 1.4rem;
        margin-bottom: 0.75rem;
    ">
        <div style="
            font-family: 'Space Mono', monospace;
            font-size: 0.6rem;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: #3d4a60;
            margin-bottom: 0.6rem;
        ">Confidence Level</div>
        <div style="
            font-family: 'Space Mono', monospace;
            font-size: 1.1rem;
            color: #f5a623;
            letter-spacing: 0.05em;
        ">{star_html} <span style="color:#7a8599; font-size:0.7rem;">({stars_count}/5)</span></div>
    </div>
    """, unsafe_allow_html=True)

    cols = st.columns(3)
    ev_color = "#00ff88" if net_ev > 0 else "#ff3b5c"
    impact = ai_verdict.get('impact_score', 0)
    impact_color = "#00ff88" if impact >= 0 else "#ff3b5c"
    impact_sign = "+" if impact >= 0 else ""

    for col, label, value, color in [
        (cols[0], "BASE EV", f"{base_ev*100:.2f}%", "#7a8599"),
        (cols[1], "ORACLE ADJ", f"{impact_sign}{impact*100:.2f}%", impact_color),
        (cols[2], "NET EV", f"{net_ev*100:.2f}%", ev_color),
    ]:
        col.markdown(f"""
        <div style="background:#161b24;border:1px solid #1e2738;border-radius:6px;padding:0.8rem 1rem;text-align:center;">
            <div style="font-family:'Space Mono',monospace;font-size:0.58rem;letter-spacing:0.12em;text-transform:uppercase;color:#3d4a60;margin-bottom:0.4rem;">{label}</div>
            <div style="font-family:'Space Mono',monospace;font-size:1.3rem;font-weight:700;color:{color};">{value}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

    pros = ai_verdict.get('pros_analysis', 'ไม่มี')
    cons = ai_verdict.get('cons_analysis', 'ไม่มี')
    rules = ai_verdict.get('rule_triggered', 'None')

    st.markdown(f"""
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.6rem;margin-bottom:0.6rem;">
        <div style="background:rgba(0,255,136,0.05);border:1px solid rgba(0,255,136,0.2);border-left:3px solid #00ff88;border-radius:4px;padding:0.8rem 1rem;">
            <div style="font-family:'Space Mono',monospace;font-size:0.58rem;letter-spacing:0.1em;text-transform:uppercase;color:#00ff88;margin-bottom:0.4rem;">✓ Pros</div>
            <div style="font-family:'DM Sans',sans-serif;font-size:0.8rem;color:#e8edf5;line-height:1.5;">{pros}</div>
        </div>
        <div style="background:rgba(255,59,92,0.05);border:1px solid rgba(255,59,92,0.2);border-left:3px solid #ff3b5c;border-radius:4px;padding:0.8rem 1rem;">
            <div style="font-family:'Space Mono',monospace;font-size:0.58rem;letter-spacing:0.1em;text-transform:uppercase;color:#ff3b5c;margin-bottom:0.4rem;">⚠ Risk</div>
            <div style="font-family:'DM Sans',sans-serif;font-size:0.8rem;color:#e8edf5;line-height:1.5;">{cons}</div>
        </div>
    </div>
    <div style="background:rgba(0,212,255,0.04);border:1px solid rgba(0,212,255,0.15);border-radius:4px;padding:0.65rem 1rem;">
        <span style="font-family:'Space Mono',monospace;font-size:0.58rem;letter-spacing:0.1em;text-transform:uppercase;color:#00d4ff;">Rules Triggered: </span>
        <span style="font-family:'DM Sans',sans-serif;font-size:0.8rem;color:#7a8599;">{rules}</span>
    </div>
    """, unsafe_allow_html=True)

def adj_hdp(val): st.session_state['live_hdp'] += val
def adj_ou(val): st.session_state['live_ou'] += val

def save_to_supabase(data_list):
    if not data_list or not supabase: return
    try: supabase.table("investment_logs").insert(data_list).execute()
    except Exception as e: st.error(f"Error saving to Cloud: {e}")

def load_logs():
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table("investment_logs").select("*").order("Time", desc=True).execute()
        if response.data:
            df_logs = pd.DataFrame(response.data)
            df_logs['Time'] = pd.to_datetime(df_logs['Time'], errors='coerce')
            for col in ['EV_Pct', 'Investment', 'Odds', 'Closing_Odds']:
                df_logs[col] = pd.to_numeric(df_logs[col], errors='coerce').fillna(0.0)
            if 'Result' in df_logs.columns: df_logs['Result'] = df_logs['Result'].fillna("")
            return df_logs.dropna(subset=['Time'])
        return pd.DataFrame()
    except: return pd.DataFrame()

def calculate_net_profit(row):
    try:
        if pd.isna(row['Result']) or str(row['Result']).strip() == "" or float(row['Investment']) <= 0: return 0.0
        result_str = str(row['Result']).strip()
        scores = re.findall(r'\d+', result_str)
        if len(scores) < 2: return 0.0
        h_score, a_score = int(scores[0]), int(scores[1])
        hdp, target, odds, invest = float(row['HDP']), str(row['Target']).strip(), float(row['Odds']), float(row['Investment'])
        diff = h_score - a_score
        if target == "เจ้าบ้าน": net_margin = diff - hdp
        elif target == "ทีมเยือน": net_margin = (a_score - h_score) + hdp
        elif target == "สูง": net_margin = (h_score + a_score) - hdp
        elif target == "ต่ำ": net_margin = hdp - (h_score + a_score)
        else: return 0.0
        if net_margin > 0.25: return invest * (odds - 1)
        elif net_margin == 0.25: return (invest * (odds - 1)) / 2
        elif net_margin == 0: return 0.0
        elif net_margin == -0.25: return -(invest / 2)
        else: return -invest
    except: return 0.0

def calculate_clv(row):
    try:
        if pd.isna(row['Closing_Odds']) or float(row['Closing_Odds']) <= 1.0: return 0.0
        return ((float(row['Odds']) / float(row['Closing_Odds'])) - 1.0) * 100.0
    except: return 0.0

# ==========================================
# 🎯 MAIN LAYOUT
# ==========================================
# Header
st.markdown("""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.25rem;">
    <div>
        <div style="font-family:'Space Mono',monospace;font-size:0.6rem;letter-spacing:0.2em;text-transform:uppercase;color:#3d4a60;margin-bottom:0.2rem;">QUANTITATIVE SPORTS INTELLIGENCE</div>
        <h1 style="margin:0 !important;padding:0 !important;border:none !important;">GEM System 10.0 · The Oracle</h1>
    </div>
    <div style="text-align:right;">
        <div style="font-family:'Space Mono',monospace;font-size:0.58rem;color:#3d4a60;letter-spacing:0.08em;">ENGINE v10.0</div>
        <div style="font-family:'Space Mono',monospace;font-size:0.65rem;color:#00d4ff;">DIXON-COLES · SHIN · EV</div>
    </div>
</div>
<div style="height:1px;background:linear-gradient(90deg,#00d4ff22,#00d4ff55,#00d4ff22);margin-bottom:1.5rem;"></div>
""", unsafe_allow_html=True)

# ── Sidebar ──
with st.sidebar:
    st.markdown('<div class="gem-section-title">AI Oracle</div>', unsafe_allow_html=True)
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        st.success("AI Connected")
    else:
        api_key = st.text_input("Gemini API Key", type="password", placeholder="AIza...")
        if api_key:
            genai.configure(api_key=api_key)
            st.success("AI Connected")
        else:
            st.warning("API Key Required")

    st.markdown('<div class="gem-section-title" style="margin-top:1rem;">Database</div>', unsafe_allow_html=True)
    if supabase:
        st.success("Supabase · Connected")
        st.info("Auto cloud sync enabled")
    else:
        st.error("Supabase · Disconnected")

    st.markdown('<div class="gem-section-title" style="margin-top:1rem;">Portfolio</div>', unsafe_allow_html=True)
    total_bankroll = st.number_input("Bankroll (THB)", min_value=0.0, value=10000.0)
    dc_rho = st.slider("Dixon-Coles Rho", -0.30, 0.0, -0.10, step=0.01)
    hdba_val = st.slider("HDBA Penalty %", 0.0, 10.0, 1.5, step=0.5)

    st.markdown('<div class="gem-section-title" style="margin-top:1rem;">EV Thresholds</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-family:\'Space Mono\',monospace;font-size:0.6rem;color:#3d4a60;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:0.4rem;">Pre-Match</div>', unsafe_allow_html=True)
    pre_ah_threshold = st.slider("AH %", 1.0, 15.0, 5.0, step=0.5)
    pre_ou_threshold = st.slider("O/U %", 1.0, 15.0, 5.0, step=0.5)
    st.markdown('<div style="font-family:\'Space Mono\',monospace;font-size:0.6rem;color:#3d4a60;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:0.4rem;margin-top:0.6rem;">In-Play</div>', unsafe_allow_html=True)
    live_ah_threshold = st.slider("AH Live %", 5.0, 50.0, 20.0, step=1.0)
    live_ou_threshold = st.slider("O/U Live %", 5.0, 50.0, 20.0, step=1.0)

pre_ah_limit = pre_ah_threshold / 100.0
pre_ou_limit = pre_ou_threshold / 100.0
live_ah_limit = live_ah_threshold / 100.0
live_ou_limit = live_ou_threshold / 100.0

# ── Tabs ──
tab1, tab2, tab3, tab4 = st.tabs([
    "PRE-MATCH",
    "DASHBOARD",
    "LIVE SNIPER",
    "BACKTEST"
])

# ══════════════════════════════════════════
# TAB 1 · PRE-MATCH TERMINAL
# ══════════════════════════════════════════
with tab1:
    # Input Tools
    with st.expander("AI VISION  ·  สกัดราคาจากภาพ", expanded=False):
        if not api_key:
            st.warning("API Key required")
        else:
            uploaded_file = st.file_uploader("Upload odds screenshot", type=['png', 'jpg'])
            if uploaded_file and st.button("Extract from Image", use_container_width=True):
                with st.spinner("Scanning image..."):
                    try:
                        img = Image.open(uploaded_file)
                        model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
                        prompt_img = 'สกัดข้อมูลจากภาพแปลงเป็น JSON: {"match_name":"","h1x2_val":0,"d1x2_val":0,"a1x2_val":0,"hdp_line_val":0,"hdp_h_w_val":0,"hdp_a_w_val":0,"ou_line_val":0,"ou_over_w_val":0,"ou_under_w_val":0}'
                        res = model.generate_content([prompt_img, img])
                        data = safe_json_loads(res.text)
                        for k, v in data.items(): st.session_state[k] = v
                        st.success("Extracted successfully"); st.rerun()
                    except Exception as e: st.error(f"Error: {e}")

    with st.expander("TEXT PARSER  ·  วางข้อความดิบ", expanded=False):
        st.text_area("Paste raw odds text here...", height=90, key="raw_text")
        cb1, cb2 = st.columns(2)
        with cb1:
            if st.button("Parse Text", use_container_width=True):
                try:
                    raw = st.session_state.raw_text
                    m_vs = re.search(r'(.*VS.*)', raw)
                    if m_vs: st.session_state.match_name = m_vs.group(1).strip()
                    h_matches = re.findall(r'^\s*เหย้า\s+([0-9.]+)', raw, re.MULTILINE)
                    if len(h_matches)>=1: st.session_state.h1x2_val=float(h_matches[0])
                    if len(h_matches)>=2: st.session_state.hdp_h_w_val=float(h_matches[1])
                    d_matches = re.findall(r'^\s*เสมอ\s+([0-9.]+)', raw, re.MULTILINE)
                    if len(d_matches)>=1: st.session_state.d1x2_val=float(d_matches[0])
                    a_matches = re.findall(r'^\s*เยือน\s+([0-9.]+)', raw, re.MULTILINE)
                    if len(a_matches)>=1: st.session_state.a1x2_val=float(a_matches[0])
                    if len(a_matches)>=2: st.session_state.hdp_a_w_val=float(a_matches[1])
                    ah_match = re.search(r'^\s*AH\s+([-+0-9.,/]+)', raw, re.MULTILINE)
                    if ah_match: st.session_state.hdp_line_val = parse_line(ah_match.group(1))
                    ou_match = re.search(r'^\s*สูง/ต่ำ\s+([-+0-9.,/]+)', raw, re.MULTILINE)
                    if ou_match: st.session_state.ou_line_val = parse_line(ou_match.group(1))
                    o_match = re.search(r'^\s*สูง\s+([0-9.]+)', raw, re.MULTILINE)
                    if o_match: st.session_state.ou_over_w_val = float(o_match.group(1))
                    u_match = re.search(r'^\s*ต่ำ\s+([0-9.]+)', raw, re.MULTILINE)
                    if u_match: st.session_state.ou_under_w_val = float(u_match.group(1))
                    st.success("Parsed")
                except Exception as e: st.error(f"Error: {e}")
        with cb2:
            st.button("Clear Form", use_container_width=True, on_click=clear_form_data)

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # Match name
    match_name = st.text_input("Match", key="match_name", placeholder="e.g. Arsenal VS Chelsea")

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # Odds Input Grid
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="gem-section-title">Asian Handicap (AH)</div>', unsafe_allow_html=True)
        r1, r2, r3 = st.columns(3)
        h1x2     = r1.number_input("Home 1X2", format="%.2f", key="h1x2_val")
        d1x2     = r2.number_input("Draw 1X2", format="%.2f", key="d1x2_val")
        a1x2     = r3.number_input("Away 1X2", format="%.2f", key="a1x2_val")
        r4, r5, r6 = st.columns(3)
        hdp_line = r4.number_input("HDP Line", format="%.2f", step=0.25, key="hdp_line_val")
        hdp_h_w  = r5.number_input("Home Odds", format="%.2f", key="hdp_h_w_val")
        hdp_a_w  = r6.number_input("Away Odds", format="%.2f", key="hdp_a_w_val")
    with col2:
        st.markdown('<div class="gem-section-title">Over / Under (O/U)</div>', unsafe_allow_html=True)
        r7, r8, r9 = st.columns(3)
        ou_line   = r7.number_input("O/U Line", format="%.2f", step=0.25, key="ou_line_val")
        ou_over_w = r8.number_input("Over Odds", format="%.2f", key="ou_over_w_val")
        ou_under_w= r9.number_input("Under Odds", format="%.2f", key="ou_under_w_val")

    st.markdown('<div class="gem-section-title" style="margin-top:0.5rem;">Stats & Context (Optional)</div>', unsafe_allow_html=True)
    match_stats = st.text_area("Paste H2H, form, or context for AI analysis...", height=80)

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    analyze_btn = st.button("▸  RUN ANALYSIS", use_container_width=True, type="primary")

    if analyze_btn:
        def fix(o): return o + 1.0 if o < 1.1 else o
        h_o, d_o, a_o = fix(h1x2), fix(d1x2), fix(a1x2)
        hw_o, aw_o, ow_o, uw_o = fix(hdp_h_w), fix(hdp_a_w), fix(ou_over_w), fix(ou_under_w)
        prob_h, prob_d, prob_a = shin_devig(h_o, d_o, a_o)
        hw2, hw1, d_exact, aw1, aw2, p_total = calc_dixon_coles_matrix(prob_h, prob_d, prob_a, ou_line, ow_o, uw_o, dc_rho)
        is_h_fav = prob_h >= prob_a
        ev_h    = calc_advanced_ah_ev(hdp_line, hw2, hw1, d_exact, aw1, aw2, hw_o, is_fav=is_h_fav)
        ev_a    = calc_advanced_ah_ev(hdp_line, aw2, aw1, d_exact, hw1, hw2, aw_o, is_fav=not is_h_fav) - (hdba_val/100)
        ev_over = calc_advanced_ou_ev(ou_line, p_total, ow_o, True)
        ev_under= calc_advanced_ou_ev(ou_line, p_total, uw_o, False)

        best_ah = max([{"n":"เจ้าบ้าน","ev":ev_h,"odds":hw_o,"hdp":hdp_line},{"n":"ทีมเยือน","ev":ev_a,"odds":aw_o,"hdp":hdp_line}], key=lambda x: x['ev'])
        best_ou = max([{"n":"สูง","ev":ev_over,"odds":ow_o,"hdp":ou_line},{"n":"ต่ำ","ev":ev_under,"odds":uw_o,"hdp":ou_line}], key=lambda x: x['ev'])

        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        st.markdown('<div class="gem-section-title">Implied Probabilities</div>', unsafe_allow_html=True)

        pc1, pc2, pc3 = st.columns(3)
        for col, label, val, color in [
            (pc1, "HOME WIN", f"{prob_h*100:.1f}%", "#00d4ff"),
            (pc2, "DRAW", f"{prob_d*100:.1f}%", "#f5a623"),
            (pc3, "AWAY WIN", f"{prob_a*100:.1f}%", "#a78bfa"),
        ]:
            col.markdown(f"""
            <div style="background:#161b24;border:1px solid #1e2738;border-radius:8px;padding:1rem;text-align:center;">
                <div style="font-family:'Space Mono',monospace;font-size:0.58rem;letter-spacing:0.12em;text-transform:uppercase;color:#3d4a60;margin-bottom:0.4rem;">{label}</div>
                <div style="font-family:'Space Mono',monospace;font-size:1.6rem;font-weight:700;color:{color};">{val}</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        st.markdown('<div class="gem-section-title">EV Analysis</div>', unsafe_allow_html=True)

        g1, g2 = st.columns(2)
        with g1:
            st.markdown(f'<div style="font-family:\'Space Mono\',monospace;font-size:0.6rem;letter-spacing:0.1em;text-transform:uppercase;color:#00d4ff;margin-bottom:0.4rem;">▸ AH MARKET · {best_ah["n"]}</div>', unsafe_allow_html=True)
            st.plotly_chart(create_ev_gauge(best_ah['ev'], f"Best: {best_ah['n']}", pre_ah_threshold), use_container_width=True)
        with g2:
            st.markdown(f'<div style="font-family:\'Space Mono\',monospace;font-size:0.6rem;letter-spacing:0.1em;text-transform:uppercase;color:#f5a623;margin-bottom:0.4rem;">▸ O/U MARKET · {best_ou["n"]}</div>', unsafe_allow_html=True)
            st.plotly_chart(create_ev_gauge(best_ou['ev'], f"Best: {best_ou['n']}", pre_ou_threshold), use_container_width=True)

        ah_passed = best_ah['ev'] >= pre_ah_limit
        ou_passed = best_ou['ev'] >= pre_ou_limit

        if ah_passed or ou_passed:
            target_to_check = best_ah if best_ah['ev'] > best_ou['ev'] else best_ou
            if not api_key:
                st.warning("API Key required for Oracle analysis")
            else:
                with st.spinner("Oracle processing..."):
                    t_fav = None
                    if target_to_check['n'] == "เจ้าบ้าน": t_fav = is_h_fav
                    elif target_to_check['n'] == "ทีมเยือน": t_fav = not is_h_fav
                    ai_verdict = ai_quant_decision_engine(
                        match_name, target_to_check['n'], target_to_check['ev'],
                        target_to_check['hdp'], target_to_check['odds'],
                        is_live=False, threshold=pre_ah_limit,
                        stats_data=match_stats, is_target_fav=t_fav
                    )
                    net_ev = target_to_check['ev'] + ai_verdict.get('impact_score', 0)

                st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
                st.markdown('<div class="gem-section-title">Oracle Verdict</div>', unsafe_allow_html=True)
                render_oracle_result(ai_verdict, target_to_check['ev'], net_ev)

                if ai_verdict.get('final_decision', False) and net_ev > 0:
                    st.balloons()
                    inv = min(
                        (((target_to_check['odds']-1) * ((net_ev+1)/target_to_check['odds']) - (1-((net_ev+1)/target_to_check['odds']))) / (target_to_check['odds']-1)) * 0.25,
                        0.05
                    ) * total_bankroll
                    st.markdown(f"""
                    <div class="ev-approve">
                        ▸ ORACLE APPROVED  ·  Stake: <strong>฿{inv:,.2f}</strong><br>
                        <span style="opacity:0.7;font-size:0.72rem;">{ai_verdict.get('final_comment','')}</span>
                    </div>
                    """, unsafe_allow_html=True)
                    tz_th = timezone(timedelta(hours=7))
                    save_to_supabase([{"Time": datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S"), "Match": match_name, "HDP": target_to_check['hdp'], "Target": target_to_check['n'], "EV_Pct": round(net_ev*100,2), "Investment": round(inv,2), "Odds": target_to_check['odds'], "Closing_Odds": 0.0, "Result": ""}])
                else:
                    st.markdown(f"""
                    <div class="ev-reject">
                        ✕ ORACLE REJECTED<br>
                        <span style="opacity:0.7;font-size:0.72rem;">{ai_verdict.get('final_comment','')}</span>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background:rgba(61,74,96,0.15);border:1px solid #1e2738;border-radius:4px;padding:0.8rem 1rem;font-family:'Space Mono',monospace;font-size:0.75rem;color:#3d4a60;letter-spacing:0.06em;">
                BELOW THRESHOLD  ·  AH: {pre_ah_threshold}%  ·  O/U: {pre_ou_threshold}%
            </div>
            """, unsafe_allow_html=True)


# ══════════════════════════════════════════
# TAB 2 · DASHBOARD
# ══════════════════════════════════════════
with tab2:
    tab2_logs = load_logs()
    if not tab2_logs.empty:
        st.markdown('<div class="gem-section-title">Edit Results & Closing Odds</div>', unsafe_allow_html=True)

        col_edit1, _ = st.columns([1, 2])
        with col_edit1:
            edit_filter = st.selectbox("Filter:", ["Today Only", "Pending Results", "All Records"], index=0)

        df_to_edit = tab2_logs.copy()
        tz_th = timezone(timedelta(hours=7))
        today_str = datetime.now(tz_th).strftime("%Y-%m-%d")

        if edit_filter == "Today Only":
            df_to_edit = df_to_edit[df_to_edit['Time'].astype(str).str.contains(today_str, na=False)]
        elif edit_filter == "Pending Results":
            df_to_edit = df_to_edit[df_to_edit['Result'].astype(str).str.strip() == ""]

        df_to_edit = df_to_edit.sort_values(by='Time', ascending=False).reset_index(drop=True)
        edited_df = st.data_editor(
            df_to_edit,
            column_config={
                "id": None,
                "Result": st.column_config.TextColumn("Result"),
                "Closing_Odds": st.column_config.NumberColumn("Closing Odds", min_value=0.0, format="%.2f")
            },
            use_container_width=True, num_rows="dynamic"
        )

        cb1, cb2 = st.columns(2)
        if cb1.button("Save to Cloud", use_container_width=True, type="primary"):
            with st.spinner("Syncing..."):
                for _, row in edited_df.iterrows():
                    supabase.table("investment_logs").update({"Closing_Odds": float(row['Closing_Odds']), "Result": str(row['Result'])}).eq("id", row['id']).execute()
            st.success("Synced"); st.rerun()
        if cb2.button("Refresh", use_container_width=True): st.rerun()

        tab2_logs['Net_Profit'] = tab2_logs.apply(calculate_net_profit, axis=1)
        tab2_logs['CLV_Pct']    = tab2_logs.apply(calculate_clv, axis=1)

        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
        st.markdown('<div class="gem-section-title">Performance Dashboard</div>', unsafe_allow_html=True)

        f1, f2 = st.columns(2)
        with f1: time_filter = st.radio("Period:", ["All Time", "Today"], horizontal=True)
        with f2: view_mode   = st.radio("View:",   ["All", "Pre-Match", "In-Play"], horizontal=True)

        if time_filter == "Today":
            time_filtered_logs = tab2_logs[tab2_logs['Time'].astype(str).str.contains(today_str, na=False)].copy()
        else:
            time_filtered_logs = tab2_logs.copy()

        if view_mode == "In-Play":
            filtered_logs = time_filtered_logs[time_filtered_logs['Match'].str.contains(r'\[LIVE\]', na=False, case=False)]
        elif view_mode == "Pre-Match":
            filtered_logs = time_filtered_logs[~time_filtered_logs['Match'].str.contains(r'\[LIVE\]', na=False, case=False)]
        else:
            filtered_logs = time_filtered_logs

        inv_logs = filtered_logs[filtered_logs['Investment'] > 0]

        net_profit = filtered_logs['Net_Profit'].sum()
        total_inv  = inv_logs['Investment'].sum()
        win_rate   = (len(inv_logs[inv_logs['Net_Profit']>0])/len(inv_logs)*100) if not inv_logs.empty else 0
        roi        = (net_profit/total_inv*100) if (not inv_logs.empty and total_inv > 0) else 0
        clv_logs   = inv_logs[inv_logs['Closing_Odds']>1.0]
        avg_clv    = clv_logs['CLV_Pct'].mean() if not clv_logs.empty else 0

        profit_color = "up" if net_profit >= 0 else "down"
        roi_color    = "up" if roi >= 0 else "down"

        m1, m2, m3, m4, m5 = st.columns(5)
        for col, lbl, val, cls in [
            (m1, "NET P&L",    f"฿{net_profit:,.2f}", profit_color),
            (m2, "INVESTED",   f"฿{total_inv:,.2f}",  ""),
            (m3, "WIN RATE",   f"{win_rate:.1f}%",    "up" if win_rate >= 50 else "down"),
            (m4, "ROI",        f"{roi:.2f}%",         roi_color),
            (m5, "AVG CLV",    f"{avg_clv:.2f}%",     "up" if avg_clv >= 0 else "down"),
        ]:
            col.markdown(f"""
            <div style="background:#161b24;border:1px solid #1e2738;border-radius:8px;padding:0.85rem 1rem;">
                <div style="font-family:'Space Mono',monospace;font-size:0.55rem;letter-spacing:0.14em;text-transform:uppercase;color:#3d4a60;margin-bottom:0.4rem;">{lbl}</div>
                <div class="value {cls}" style="font-family:'Space Mono',monospace;font-size:1.15rem;font-weight:700;">{val}</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

        if not filtered_logs.empty:
            logs_s = filtered_logs.sort_values(by='Time').copy()
            logs_s['Cumulative_Profit'] = logs_s['Net_Profit'].cumsum()
            line_color = '#ff3b5c' if "In-Play" in view_mode else ('#00d4ff' if "Pre-Match" in view_mode else '#00ff88')

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=logs_s['Time'], y=logs_s['Cumulative_Profit'],
                mode='lines', fill='tozeroy',
                line=dict(color=line_color, width=2),
                fillcolor=f"rgba({','.join(str(int(line_color.lstrip('#')[i:i+2],16)) for i in (0,2,4))},0.07)"
            ))
            fig.update_layout(
                title=dict(text=f"Equity Curve · {view_mode}", font=dict(size=11, color='#7a8599', family='Space Mono'), x=0),
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(gridcolor='#1e2738', tickfont=dict(color='#3d4a60', size=9, family='Space Mono'), showline=False),
                yaxis=dict(gridcolor='#1e2738', tickfont=dict(color='#3d4a60', size=9, family='Space Mono'), showline=False),
                margin=dict(l=0, r=0, t=40, b=0), height=260
            )
            st.plotly_chart(fig, use_container_width=True)

            st.markdown('<div class="gem-section-title">Performance Breakdown</div>', unsafe_allow_html=True)
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown('<div style="font-family:\'Space Mono\',monospace;font-size:0.6rem;color:#3d4a60;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:0.5rem;">P&L by Target</div>', unsafe_allow_html=True)
                target_stats = logs_s.groupby('Target')['Net_Profit'].sum()
                st.bar_chart(target_stats, color=line_color)
            with col_b:
                st.markdown('<div style="font-family:\'Space Mono\',monospace;font-size:0.6rem;color:#3d4a60;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:0.5rem;">Win Rate by Odds Range</div>', unsafe_allow_html=True)
                logs_s['Odds_Bin'] = pd.cut(logs_s['Odds'], bins=[0,1.8,2.0,2.2,5.0], labels=['<1.8','1.8-2.0','2.0-2.2','>2.2'])
                wins   = logs_s[logs_s['Net_Profit']>0].groupby('Odds_Bin', observed=False).size()
                totals = logs_s.groupby('Odds_Bin', observed=False).size()
                st.bar_chart((wins/totals*100).fillna(0), color=line_color)

        # AI Oracle Learning
        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
        st.markdown('<div class="gem-section-title">Oracle Learning Engine</div>', unsafe_allow_html=True)

        if 'Net_Profit' in tab2_logs.columns:
            completed_logs = tab2_logs[tab2_logs['Result'].astype(str).str.strip() != ""].copy()
        else:
            completed_logs = pd.DataFrame()

        if len(completed_logs) > 0:
            debrief_type = st.radio(
                "Analysis Mode:",
                ["Loss Analysis (Defensive Rules)", "Win Analysis (Offensive Rules)", "Mixed Analysis"],
                horizontal=True
            )
            if "Loss" in debrief_type:
                target_logs = completed_logs[completed_logs['Net_Profit'] < 0].copy()
                ai_task = "ทำ 'Post-Mortem Analysis' จากข้อมูลที่ขาดทุน ค้นหาจุดอ่อน และสร้างกฎเพื่อป้องกันความผิดพลาดเดิม (Defensive Rules)"
                prefix_id = "GEM_DEF_"
            elif "Win" in debrief_type:
                target_logs = completed_logs[completed_logs['Net_Profit'] > 0].copy()
                ai_task = "ทำ 'Success Analysis' จากข้อมูลที่ได้กำไร ค้นหารูปแบบที่ชนะตลาด และสร้างกฎเชิงบวก (Offensive Rules)"
                prefix_id = "GEM_OFF_"
            else:
                target_logs = completed_logs.copy()
                ai_task = "วิเคราะห์เปรียบเทียบทั้งไม้ที่ชนะและแพ้ สร้างหรือปรับปรุงกฎในคัมภีร์"
                prefix_id = "GEM_MIX_"

            if len(target_logs) > 0:
                st.caption(f"{len(target_logs)} records available · select cases for analysis")
                target_logs.insert(0, "Analyze", False)
                debrief_selection = st.data_editor(
                    target_logs[['Analyze','Time','Match','HDP','Target','Odds','Result','Net_Profit']],
                    column_config={
                        "Analyze": st.column_config.CheckboxColumn("Select", default=False),
                        "Net_Profit": st.column_config.NumberColumn("P&L", format="%.2f")
                    },
                    hide_index=True, use_container_width=True, key="debrief_editor"
                )
                selected_for_debrief = debrief_selection[debrief_selection['Analyze'] == True]

                if st.button("Run Oracle Learning", use_container_width=True, type="primary"):
                    if selected_for_debrief.empty:
                        st.warning("Select at least one record above")
                    else:
                        with st.spinner(f"Oracle learning from {len(selected_for_debrief)} cases..."):
                            loss_data_str = selected_for_debrief[['Time','Match','HDP','Target','Odds','Result']].to_csv(index=False)
                            try:
                                rules_res = supabase.table("gem_knowledge").select("rule_id, category, rule_text").eq("is_active", True).execute()
                                rules_str = "\n".join([f"[{r['rule_id']} - หมวด {r['category']}] {r['rule_text']}" for r in (rules_res.data or [])])
                            except: rules_str = ""
                            prompt_debrief = (
                                f"คุณคือ Chief Risk Officer และ Quant Analyst ของกองทุนกีฬา\nหน้าที่: {ai_task}\n\n"
                                f"📋 [ข้อมูล Case Study (CSV)]\n{loss_data_str}\n\n"
                                f"📖 [คัมภีร์ปัจจุบัน]\n{rules_str}\n\n"
                                "คำสั่ง:\n1. วิเคราะห์เจาะลึกสาเหตุ\n2. สร้างกฎเชิงเทคนิค ห้ามเจาะจงชื่อทีม\n"
                                "3. ระบุ Category: [AH], [OU], หรือ [ALL]\n"
                                "ตอบกลับ JSON เท่านั้น:\n"
                                '{"analysis_summary":"...","new_rules_to_add":[{"rule_text":"...","category":"..."}]}'
                            )
                            try:
                                if "GEMINI_API_KEY" not in st.secrets and not api_key:
                                    st.error("API Key required")
                                else:
                                    model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
                                    res_debrief = model.generate_content(prompt_debrief)
                                    data = safe_json_loads(res_debrief.text)
                                    if data:
                                        st.info(f"**Analysis:**\n{data.get('analysis_summary','')}")
                                        new_rules = data.get("new_rules_to_add", [])
                                        if new_rules:
                                            insert_payload = []
                                            base_id = datetime.now(timezone(timedelta(hours=7))).strftime("%Y%m%d_%H%M")
                                            st.markdown('<div class="gem-section-title">New Rules Generated</div>', unsafe_allow_html=True)
                                            for idx, rule in enumerate(new_rules):
                                                rule_id = f"{prefix_id}{base_id}_{idx+1}"
                                                insert_payload.append({"rule_id": rule_id, "rule_text": rule.get("rule_text",""), "category": rule.get("category","AI Learning")})
                                                color = "#ff3b5c" if "DEF" in prefix_id else ("#00ff88" if "OFF" in prefix_id else "#f5a623")
                                                st.markdown(f"""
                                                <div style="background:rgba(0,0,0,0.2);border:1px solid #1e2738;border-left:3px solid {color};border-radius:4px;padding:0.7rem 1rem;margin-bottom:0.4rem;">
                                                    <span style="font-family:'Space Mono',monospace;font-size:0.6rem;color:{color};">[{rule_id}]</span>
                                                    <span style="font-family:'DM Sans',sans-serif;font-size:0.82rem;color:#e8edf5;margin-left:0.5rem;">{rule.get('rule_text','')}</span>
                                                </div>
                                                """, unsafe_allow_html=True)
                                            supabase.table("gem_knowledge").insert(insert_payload).execute()
                                            load_gem_rules.clear()
                                            st.balloons()
                                            st.success(f"Saved {len(insert_payload)} new rules to cloud")
                                        else:
                                            st.info("No new rules needed — variance within normal range")
                                    else:
                                        st.error("AI response format error")
                            except Exception as e:
                                st.error(f"Error: {e}")
            else:
                st.caption("No records in this category yet")
        else:
            st.caption("No completed records available for analysis")
    else:
        st.markdown("""
        <div style="text-align:center;padding:3rem;color:#3d4a60;font-family:'Space Mono',monospace;font-size:0.75rem;letter-spacing:0.1em;">
            NO RECORDS FOUND · Run your first analysis in Pre-Match tab
        </div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════
# TAB 3 · LIVE SNIPER
# ══════════════════════════════════════════
with tab3:
    st.markdown("""
    <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:1rem;">
        <div class="live-dot"></div>
        <span class="live-badge">LIVE SNIPER</span>
        <span style="font-family:'Space Mono',monospace;font-size:0.6rem;color:#3d4a60;letter-spacing:0.08em;">· IN-PLAY COMMAND CENTER</span>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("AI LIVE VISION  ·  Upload Screenshots", expanded=False):
        if not api_key: st.warning("API Key required")
        else:
            live_images = st.file_uploader("Upload up to 3 screenshots", type=['png','jpg'], accept_multiple_files=True)
            if live_images and st.button("Extract Live Data", use_container_width=True):
                with st.spinner("Scanning..."):
                    try:
                        imgs = [Image.open(f) for f in live_images]
                        model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
                        prompt_live = 'สกัดเป็น JSON: {"current_min":0,"current_score_h":0,"current_score_a":0,"pre_h":2.0,"pre_d":3.0,"pre_a":3.0,"pre_ou":2.5,"live_hdp":0.0,"live_hdp_h":0.9,"live_hdp_a":0.9,"live_ou":2.5,"live_ou_over":0.9,"live_ou_under":0.9}'
                        res = model.generate_content([prompt_live] + imgs)
                        data = safe_json_loads(res.text)
                        for k, v in data.items(): st.session_state[k] = float(v) if 'score' not in k and 'min' not in k else int(v)
                        st.success("Extracted"); st.rerun()
                    except Exception as e: st.error(f"Error: {e}")

    col_l1, col_l2 = st.columns(2)
    with col_l1:
        st.markdown('<div class="gem-section-title">Match State</div>', unsafe_allow_html=True)
        c_h1, c_h2 = st.columns(2)
        current_score_h = c_h1.number_input("Home Score", min_value=0, value=st.session_state.get('lh_s_input',0), key="lh_s_input")
        red_card_h = c_h2.checkbox("🟥 Home Red Card", key="rc_h")
        c_a1, c_a2 = st.columns(2)
        current_score_a = c_a1.number_input("Away Score", min_value=0, value=st.session_state.get('la_s_input',0), key="la_s_input")
        red_card_a = c_a2.checkbox("🟥 Away Red Card", key="rc_a")
        current_min = st.slider("Minute", 0, 120, st.session_state.get('current_min',45))
    with col_l2:
        st.markdown('<div class="gem-section-title">Pre-Match Odds</div>', unsafe_allow_html=True)
        pre_h  = st.number_input("Home (Open)", value=st.session_state.get('pre_h',2.0), format="%.2f", key="pre_h")
        pre_d  = st.number_input("Draw (Open)", value=st.session_state.get('pre_d',3.0), format="%.2f", key="pre_d")
        pre_a  = st.number_input("Away (Open)", value=st.session_state.get('pre_a',3.0), format="%.2f", key="pre_a")
        pre_ou = st.number_input("O/U (Open)",  value=st.session_state.get('pre_ou',2.5), format="%.2f", step=0.25, key="pre_ou")

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    st.markdown('<div class="gem-section-title">Live Odds</div>', unsafe_allow_html=True)

    col_live1, col_live2 = st.columns(2)
    with col_live1:
        st.markdown('<div style="font-family:\'Space Mono\',monospace;font-size:0.6rem;color:#00d4ff;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:0.4rem;">AH Market</div>', unsafe_allow_html=True)
        bh1, bh2, bh3 = st.columns([1,2,1])
        bh1.button("−", key="h_sub", on_click=adj_hdp, args=(-0.25,), use_container_width=True)
        live_hdp = bh2.number_input("HDP", value=st.session_state['live_hdp'], step=0.25, key="live_hdp", label_visibility="collapsed", format="%.2f")
        bh3.button("+", key="h_add", on_click=adj_hdp, args=(0.25,), use_container_width=True)
        cw1, cw2 = st.columns(2)
        live_hdp_h = cw1.number_input("Home Odds", value=st.session_state.get('live_hdp_h',0.9), format="%.2f", key="live_hdp_h")
        live_hdp_a = cw2.number_input("Away Odds", value=st.session_state.get('live_hdp_a',0.9), format="%.2f", key="live_hdp_a")

    with col_live2:
        st.markdown('<div style="font-family:\'Space Mono\',monospace;font-size:0.6rem;color:#f5a623;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:0.4rem;">O/U Market</div>', unsafe_allow_html=True)
        bo1, bo2, bo3 = st.columns([1,2,1])
        bo1.button("−", key="o_sub", on_click=adj_ou, args=(-0.25,), use_container_width=True)
        live_ou = bo2.number_input("O/U", value=st.session_state['live_ou'], step=0.25, key="live_ou", label_visibility="collapsed", format="%.2f")
        bo3.button("+", key="o_add", on_click=adj_ou, args=(0.25,), use_container_width=True)
        cw3, cw4 = st.columns(2)
        live_ou_over  = cw3.number_input("Over Odds",  value=st.session_state.get('live_ou_over',0.9),  format="%.2f", key="live_ou_over")
        live_ou_under = cw4.number_input("Under Odds", value=st.session_state.get('live_ou_under',0.9), format="%.2f", key="live_ou_under")

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    sb1, sb2 = st.columns([4,1])
    submit_live = sb1.button("▸  ENGAGE SNIPER", use_container_width=True, type="primary")
    sb2.button("Reset", use_container_width=True, on_click=clear_inplay_data)

    if submit_live:
        def fix(o): return o + 1.0 if o < 1.1 else o
        p_h, p_d, p_a = shin_devig(fix(pre_h), fix(pre_d), fix(pre_a))
        m_left = max(90 - current_min, 1)
        hw2, hw1, d_ex, aw1, aw2, p_tot = calc_dixon_coles_matrix(
            p_h, p_d, p_a, live_ou, fix(live_ou_over), fix(live_ou_under),
            dc_rho, current_score_h, current_score_a, m_left, red_card_h, red_card_a
        )
        is_fav = p_h >= p_a
        ev_h = calc_advanced_ah_ev(live_hdp, hw2, hw1, d_ex, aw1, aw2, fix(live_hdp_h), is_fav)
        ev_a = calc_advanced_ah_ev(live_hdp, aw2, aw1, d_ex, hw1, hw2, fix(live_hdp_a), not is_fav) - (hdba_val/100)
        ev_o = calc_advanced_ou_ev(live_ou, p_tot, fix(live_ou_over), True)
        ev_u = calc_advanced_ou_ev(live_ou, p_tot, fix(live_ou_under), False)

        b_ah_v = max(ev_h, ev_a); t_ah = "เจ้าบ้าน" if ev_h > ev_a else "ทีมเยือน"
        b_ou_v = max(ev_o, ev_u); t_ou = "สูง" if ev_o > ev_u else "ต่ำ"

        g1, g2 = st.columns(2)
        with g1:
            st.markdown(f'<div style="font-family:\'Space Mono\',monospace;font-size:0.6rem;color:#00d4ff;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:0.3rem;">AH · {t_ah}</div>', unsafe_allow_html=True)
            st.plotly_chart(create_ev_gauge(b_ah_v, f"AH: {t_ah}", live_ah_threshold), use_container_width=True)
        with g2:
            st.markdown(f'<div style="font-family:\'Space Mono\',monospace;font-size:0.6rem;color:#f5a623;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:0.3rem;">O/U · {t_ou}</div>', unsafe_allow_html=True)
            st.plotly_chart(create_ev_gauge(b_ou_v, f"O/U: {t_ou}", live_ou_threshold), use_container_width=True)

        ah_live_passed = b_ah_v >= live_ah_limit
        ou_live_passed = b_ou_v >= live_ou_limit

        if ah_live_passed or ou_live_passed:
            t_live = (
                {"n": t_ah, "ev": b_ah_v, "hdp": live_hdp, "odds": fix(live_hdp_h) if t_ah=="เจ้าบ้าน" else fix(live_hdp_a)}
                if b_ah_v > b_ou_v else
                {"n": t_ou, "ev": b_ou_v, "hdp": live_ou, "odds": fix(live_ou_over) if t_ou=="สูง" else fix(live_ou_under)}
            )
            if not api_key:
                st.warning("API Key required")
            else:
                with st.spinner("Oracle targeting..."):
                    t_fav = None
                    if t_live['n'] == "เจ้าบ้าน": t_fav = is_fav
                    elif t_live['n'] == "ทีมเยือน": t_fav = not is_fav
                    ai_live = ai_quant_decision_engine(
                        "Live", t_live['n'], t_live['ev'], t_live['hdp'], t_live['odds'],
                        True, current_min, f"{current_score_h}-{current_score_a}",
                        threshold=live_ah_limit, stats_data="", is_target_fav=t_fav
                    )
                    net_l_ev = t_live['ev'] + ai_live.get('impact_score', 0)

                st.markdown('<div class="gem-section-title">Oracle Verdict</div>', unsafe_allow_html=True)
                render_oracle_result(ai_live, t_live['ev'], net_l_ev)

                limit_to_use = live_ah_limit if t_live['n'] in ["เจ้าบ้าน","ทีมเยือน"] else live_ou_limit
                if ai_live.get('final_decision', False) and net_l_ev >= limit_to_use:
                    st.balloons()
                    inv = min(
                        (((t_live['odds']-1) * ((net_l_ev+1)/t_live['odds']) - (1-((net_l_ev+1)/t_live['odds']))) / (t_live['odds']-1)) * 0.25,
                        0.05
                    ) * total_bankroll
                    st.markdown(f"""
                    <div style="background:rgba(255,59,92,0.08);border:1px solid rgba(255,59,92,0.4);border-radius:6px;padding:1rem 1.2rem;margin-top:0.5rem;">
                        <div style="font-family:'Space Mono',monospace;font-size:0.65rem;letter-spacing:0.12em;color:#ff3b5c;margin-bottom:0.4rem;">🚨 SNIPER LOCK — TARGET ACQUIRED</div>
                        <div style="font-family:'Space Mono',monospace;font-size:1.1rem;font-weight:700;color:#ff3b5c;">
                            {t_live['n']}  ·  EV {net_l_ev*100:.1f}%  ·  Stake ฿{inv:,.2f}
                        </div>
                        <div style="font-family:'DM Sans',sans-serif;font-size:0.78rem;color:#7a8599;margin-top:0.3rem;">{ai_live.get('final_comment','')}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    tz_th = timezone(timedelta(hours=7))
                    save_to_supabase([{"Time": datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S"), "Match": f"[LIVE] {st.session_state.get('match_name','Live Match')}", "HDP": t_live['hdp'], "Target": t_live['n'], "EV_Pct": round(net_l_ev*100,2), "Investment": round(inv,2), "Odds": t_live['odds'], "Closing_Odds": 0.0, "Result": ""}])
                else:
                    st.markdown(f"""
                    <div class="ev-reject">
                        ✕ ORACLE REJECTED · {ai_live.get('final_comment','')}
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background:rgba(61,74,96,0.1);border:1px solid #1e2738;border-radius:4px;padding:0.75rem 1rem;font-family:'Space Mono',monospace;font-size:0.72rem;color:#3d4a60;letter-spacing:0.06em;">
                BELOW THRESHOLD  ·  AH: {live_ah_threshold}%  ·  O/U: {live_ou_threshold}%
            </div>
            """, unsafe_allow_html=True)


# ══════════════════════════════════════════
# TAB 4 · BACKTEST ENGINE
# ══════════════════════════════════════════
with tab4:
    st.markdown('<div class="gem-section-title">Brier Score Evaluation</div>', unsafe_allow_html=True)
    st.caption("Compares GEM probability estimates vs bookmaker implied odds using Brier Score (lower = more accurate)")

    tab4_logs = load_logs()
    if tab4_logs is not None and not tab4_logs.empty:
        tab4_logs['Net_Profit'] = tab4_logs.apply(calculate_net_profit, axis=1)
        finished_logs = tab4_logs[tab4_logs['Result'].astype(str).str.strip() != ""].copy()

        if not finished_logs.empty:
            def map_net_profit_to_score(row):
                try:
                    inv, net, odds = float(row['Investment']), float(row['Net_Profit']), float(row['Odds'])
                    if inv <= 0: return np.nan
                    max_win = inv * (odds - 1)
                    if net >= max_win * 0.95: return 1.0
                    elif net > 0: return 0.75
                    elif net == 0: return 0.50
                    elif net <= -inv * 0.95: return 0.0
                    elif net < 0: return 0.25
                    return np.nan
                except: return np.nan

            finished_logs['Actual_Score'] = finished_logs.apply(map_net_profit_to_score, axis=1)
            finished_logs = finished_logs.dropna(subset=['Actual_Score'])

            if not finished_logs.empty:
                finished_logs['Bookie_Prob'] = (1 / finished_logs['Odds']).clip(lower=0.0, upper=1.0)
                raw_our_prob = (((finished_logs['EV_Pct'] / 100) + 1) / finished_logs['Odds']).clip(lower=0.0, upper=1.0)
                finished_logs['Our_Prob'] = ((raw_our_prob * 0.85) + (finished_logs['Bookie_Prob'] * 0.15)).clip(lower=0.0, upper=1.0)
                finished_logs['Our_Error']    = (finished_logs['Our_Prob']    - finished_logs['Actual_Score'])**2
                finished_logs['Bookie_Error'] = (finished_logs['Bookie_Prob'] - finished_logs['Actual_Score'])**2

                avg_our_error    = finished_logs['Our_Error'].mean()
                avg_bookie_error = finished_logs['Bookie_Error'].mean()
                error_diff       = avg_bookie_error - avg_our_error
                we_win           = avg_our_error < avg_bookie_error

                st.markdown(f'<div style="font-family:\'Space Mono\',monospace;font-size:0.6rem;color:#3d4a60;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:0.75rem;">Sample: {len(finished_logs)} bets</div>', unsafe_allow_html=True)

                bc1, bc2, bc3 = st.columns(3)
                result_color = "#00ff88" if we_win else "#ff3b5c"
                for col, lbl, val, color in [
                    (bc1, "GEM BRIER SCORE",      f"{avg_our_error:.4f}",    "#00d4ff"),
                    (bc2, "BOOKMAKER SCORE",       f"{avg_bookie_error:.4f}", "#7a8599"),
                    (bc3, "EDGE vs MARKET",        f"{error_diff:+.4f}",      result_color),
                ]:
                    col.markdown(f"""
                    <div style="background:#161b24;border:1px solid #1e2738;border-radius:8px;padding:1rem;text-align:center;">
                        <div style="font-family:'Space Mono',monospace;font-size:0.55rem;letter-spacing:0.12em;text-transform:uppercase;color:#3d4a60;margin-bottom:0.4rem;">{lbl}</div>
                        <div style="font-family:'Space Mono',monospace;font-size:1.4rem;font-weight:700;color:{color};">{val}</div>
                    </div>
                    """, unsafe_allow_html=True)

                verdict_text = "GEM SYSTEM BEATS THE MARKET" if we_win else "BOOKMAKER MORE ACCURATE · RECALIBRATE"
                verdict_color = "#00ff88" if we_win else "#ff3b5c"
                st.markdown(f"""
                <div style="margin-top:0.75rem;background:rgba(0,0,0,0.2);border:1px solid {verdict_color}33;border-left:3px solid {verdict_color};border-radius:4px;padding:0.7rem 1rem;font-family:'Space Mono',monospace;font-size:0.72rem;color:{verdict_color};letter-spacing:0.08em;">
                    {"▸" if we_win else "✕"} {verdict_text}
                </div>
                """, unsafe_allow_html=True)

                st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
                st.markdown('<div class="gem-section-title">Cumulative Error Comparison</div>', unsafe_allow_html=True)
                st.caption("Lower line = fewer cumulative errors")

                finished_logs = finished_logs.sort_values(by='Time').reset_index(drop=True)
                finished_logs['Cum_Our_Error']    = finished_logs['Our_Error'].cumsum()
                finished_logs['Cum_Bookie_Error'] = finished_logs['Bookie_Error'].cumsum()

                fig_bt = go.Figure()
                fig_bt.add_trace(go.Scatter(
                    x=finished_logs.index, y=finished_logs['Cum_Our_Error'],
                    mode='lines', name='GEM System',
                    line=dict(color='#00ff88', width=2)
                ))
                fig_bt.add_trace(go.Scatter(
                    x=finished_logs.index, y=finished_logs['Cum_Bookie_Error'],
                    mode='lines', name='Bookmaker',
                    line=dict(color='#ff3b5c', width=2, dash='dot')
                ))
                fig_bt.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(title=dict(text="Bets", font=dict(size=9, color='#3d4a60', family='Space Mono')), gridcolor='#1e2738', tickfont=dict(color='#3d4a60', size=8)),
                    yaxis=dict(title=dict(text="Cumulative Error", font=dict(size=9, color='#3d4a60', family='Space Mono')), gridcolor='#1e2738', tickfont=dict(color='#3d4a60', size=8)),
                    legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(color='#7a8599', size=9, family='Space Mono')),
                    margin=dict(l=0, r=0, t=10, b=0), height=280
                )
                st.plotly_chart(fig_bt, use_container_width=True)

                with st.expander("RAW DATA · Probability Comparison", expanded=False):
                    st.dataframe(
                        finished_logs[['Time','Match','Target','Odds','Result','Net_Profit','Actual_Score','Bookie_Prob','Our_Prob']],
                        use_container_width=True
                    )
            else:
                st.info("No computable results yet")
        else:
            st.markdown("""
            <div style="text-align:center;padding:3rem;color:#3d4a60;font-family:'Space Mono',monospace;font-size:0.75rem;letter-spacing:0.1em;">
                NO RESULTS RECORDED · Update results in Dashboard tab first
            </div>
            """, unsafe_allow_html=True)
    else:
        st.warning("No investment database found")
