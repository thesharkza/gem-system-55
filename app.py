import streamlit as st
import pandas as pd
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

# ── must be the very first Streamlit call ──
st.set_page_config(
    page_title="GEM System 10.0 · The Oracle",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="🎯"
)

# ==========================================
# 🛡️ HELPER FUNCTIONS
# ==========================================
def safe_json_loads(text):
    if not text: return {}
    try:
        start_idx = text.find('{')
        end_idx   = text.rfind('}')
        if start_idx != -1 and end_idx != -1:
            return json.loads(text[start_idx:end_idx+1])
        return json.loads(text)
    except Exception:
        clean = text.replace("```json", "").replace("```", "").strip()
        try:    return json.loads(clean)
        except: return {}

# ==========================================
# 🎨  NEON QUANT THEME
# ==========================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;500;600;700&family=Exo+2:wght@300;400;600;800&display=swap');

:root {
    --bg-primary:  #050a0e;
    --bg-panel:    #0a1520;
    --bg-card:     #0d1e2e;
    --bg-card2:    #091520;
    --neon-green:  #00ff88;
    --neon-green2: #00cc6a;
    --neon-dim:    #00ff8820;
    --neon-glow:   0 0 8px #00ff8870, 0 0 24px #00ff8828;
    --neon-red:    #ff3b5c;
    --neon-yellow: #ffd600;
    --neon-blue:   #00b4ff;
    --border:      #0f2535;
    --border-neon: #00ff8835;
    --text-main:   #c8e6d4;
    --text-dim:    #4a7a60;
    --text-label:  #2a5040;
    --font-mono:   'Share Tech Mono', monospace;
    --font-ui:     'Rajdhani', sans-serif;
    --font-head:   'Exo 2', sans-serif;
}

html, body, [data-testid="stAppViewContainer"] {
    background-color: var(--bg-primary) !important;
    color: var(--text-main) !important;
    font-family: var(--font-ui) !important;
}
[data-testid="stAppViewContainer"]::before {
    content: "";
    position: fixed;
    inset: 0;
    background:
        radial-gradient(ellipse 80% 40% at 50% -10%, #00ff8810 0%, transparent 70%),
        repeating-linear-gradient(0deg, transparent, transparent 39px, #0f253508 40px),
        repeating-linear-gradient(90deg, transparent, transparent 39px, #0f253508 40px);
    pointer-events: none;
    z-index: 0;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg,#060d14 0%,#050a0e 100%) !important;
    border-right: 1px solid var(--border-neon) !important;
}
[data-testid="stSidebar"] * { font-family: var(--font-ui) !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: var(--neon-green) !important;
    font-family: var(--font-head) !important;
    font-size: 0.82rem !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
}
[data-testid="stSidebar"] label {
    color: var(--text-dim) !important;
    font-size: 0.76rem !important;
    letter-spacing: 0.05em !important;
    text-transform: uppercase !important;
}
h1 {
    font-family: var(--font-head) !important;
    font-weight: 800 !important;
    font-size: 2rem !important;
    letter-spacing: 0.04em !important;
    color: var(--neon-green) !important;
    text-shadow: var(--neon-glow) !important;
}
h2 {
    font-family: var(--font-head) !important;
    font-weight: 600 !important;
    color: #88ffcc !important;
    font-size: 1.1rem !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
}
h3, h4, h5 { font-family: var(--font-ui) !important; color: var(--text-main) !important; }

[data-testid="stTabs"] [role="tablist"] {
    background: var(--bg-panel) !important;
    border-bottom: 1px solid var(--border-neon) !important;
    gap: 2px !important; padding: 4px 8px 0 !important;
    border-radius: 6px 6px 0 0 !important;
}
[data-testid="stTabs"] button[role="tab"] {
    font-family: var(--font-ui) !important; font-weight: 600 !important;
    font-size: 0.8rem !important; letter-spacing: 0.1em !important;
    text-transform: uppercase !important; color: var(--text-dim) !important;
    background: transparent !important; border: none !important;
    border-bottom: 2px solid transparent !important; padding: 8px 16px !important;
    transition: all 0.2s !important;
}
[data-testid="stTabs"] button[role="tab"]:hover {
    color: var(--neon-green) !important; background: var(--neon-dim) !important;
}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: var(--neon-green) !important;
    border-bottom: 2px solid var(--neon-green) !important;
    text-shadow: 0 0 12px #00ff88 !important;
}
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    background: var(--bg-card2) !important; color: var(--neon-green) !important;
    font-family: var(--font-mono) !important; font-size: 1rem !important;
    border: 1px solid var(--border) !important; border-radius: 4px !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: var(--neon-green2) !important;
    box-shadow: 0 0 0 2px #00ff8818 !important; outline: none !important;
}
[data-testid="stSelectbox"] > div {
    background: var(--bg-card2) !important;
    border-color: var(--border) !important; color: var(--neon-green) !important;
}
label[data-testid="stWidgetLabel"] {
    color: var(--text-dim) !important; font-size: 0.75rem !important;
    letter-spacing: 0.07em !important; text-transform: uppercase !important;
    font-family: var(--font-ui) !important;
}
.stButton > button {
    font-family: var(--font-head) !important; font-weight: 700 !important;
    font-size: 0.8rem !important; letter-spacing: 0.14em !important;
    text-transform: uppercase !important; background: transparent !important;
    color: var(--neon-green) !important; border: 1px solid var(--neon-green2) !important;
    border-radius: 3px !important; padding: 8px 18px !important;
    transition: all 0.15s ease !important;
}
.stButton > button:hover {
    background: var(--neon-dim) !important; box-shadow: var(--neon-glow) !important;
    border-color: var(--neon-green) !important; color: #fff !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg,#00ff8815,#00cc6a10) !important;
    border-color: var(--neon-green) !important; box-shadow: 0 0 10px #00ff8835 !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg,#00ff8828,#00cc6a20) !important;
    box-shadow: var(--neon-glow) !important;
}
[data-testid="stMetric"] {
    background: var(--bg-card) !important; border: 1px solid var(--border) !important;
    border-top: 2px solid var(--neon-green2) !important; border-radius: 4px !important;
    padding: 14px 16px !important; position: relative !important;
}
[data-testid="stMetric"]::before {
    content: ""; position: absolute; top: 0; left: 0; right: 0; height: 1px;
    background: linear-gradient(90deg,transparent,var(--neon-green2),transparent);
}
[data-testid="stMetricLabel"] {
    color: var(--text-dim) !important; font-size: 0.7rem !important;
    letter-spacing: 0.1em !important; text-transform: uppercase !important;
    font-family: var(--font-ui) !important;
}
[data-testid="stMetricValue"] {
    color: var(--neon-green) !important; font-family: var(--font-mono) !important;
    font-size: 1.45rem !important; text-shadow: 0 0 8px #00ff8855 !important;
}
[data-testid="stMetricDelta"] { font-family: var(--font-mono) !important; font-size: 0.76rem !important; }
[data-testid="stExpander"] {
    border: 1px solid var(--border) !important; border-radius: 4px !important;
    background: var(--bg-card2) !important;
}
[data-testid="stExpander"] summary {
    color: var(--text-main) !important; font-family: var(--font-ui) !important;
    font-size: 0.83rem !important; letter-spacing: 0.07em !important; padding: 10px 14px !important;
}
[data-testid="stExpander"] summary:hover { color: var(--neon-green) !important; }
[data-testid="stRadio"] label { color: var(--text-main) !important; font-family: var(--font-ui) !important; font-size: 0.83rem !important; }
hr { border-color: var(--border-neon) !important; }
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: var(--bg-primary); }
::-webkit-scrollbar-thumb { background: var(--text-label); border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: var(--neon-green2); }

.gem-panel {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 6px; padding: 18px 20px; margin-bottom: 14px; position: relative;
}
.gem-panel::before {
    content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg,var(--neon-green2),transparent);
    border-radius: 6px 6px 0 0;
}
.gem-label {
    font-family: var(--font-mono); font-size: 0.65rem; letter-spacing: 0.2em;
    color: var(--text-label); text-transform: uppercase; margin-bottom: 10px;
    border-left: 2px solid var(--neon-green2); padding-left: 8px;
}
.gem-badge {
    display: inline-block; background: var(--neon-dim); color: var(--neon-green);
    font-family: var(--font-mono); font-size: 0.68rem; padding: 2px 10px;
    border-radius: 2px; border: 1px solid var(--neon-green2); letter-spacing: 0.08em;
}
.gem-ok   { color:#00ff88 !important; font-family:'Share Tech Mono',monospace !important; font-size:0.78rem !important; }
.gem-warn { color:#ffd600 !important; font-family:'Share Tech Mono',monospace !important; font-size:0.78rem !important; }
.gem-err  { color:#ff3b5c !important; font-family:'Share Tech Mono',monospace !important; font-size:0.78rem !important; }
.gem-dim  { color:#2a5040 !important; font-family:'Share Tech Mono',monospace !important; font-size:0.68rem !important; }
.gem-divider {
    height: 1px;
    background: linear-gradient(90deg,transparent,#00cc6a25,transparent);
    margin: 16px 0;
}
[data-testid="stNumberInput"] button {
    background: var(--bg-card) !important; color: var(--neon-green) !important;
    border-color: var(--border) !important;
}
[data-testid="stNumberInput"] button:hover { background: var(--neon-dim) !important; }
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
[data-testid="stHeader"] { background-color: transparent; }
</style>
""", unsafe_allow_html=True)


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
        'raw_text': "", 'live_hdp': 0.0, 'live_ou': 2.50,
        'lh_s_input': 0, 'la_s_input': 0, 'current_min': 45,
        'rc_h_chk': False, 'rc_a_chk': False,
        'xg_h_val': 0.0, 'xg_a_val': 0.0,
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

init_session_state()

def clear_inplay_data():
    for k, v in {
        'lh_s_input': 0, 'la_s_input': 0,
        'rc_h_chk': False, 'rc_a_chk': False, 'current_min': 45,
        'pre_h': 2.0, 'pre_d': 3.0, 'pre_a': 3.0, 'pre_ou': 2.5,
        'live_hdp': 0.0, 'live_hdp_h': 0.9, 'live_hdp_a': 0.9,
        'live_ou': 2.5, 'live_ou_over': 0.9, 'live_ou_under': 0.9,
    }.items():
        st.session_state[k] = v
    if 'match_name_live' in st.session_state:
        del st.session_state['match_name_live']

@st.cache_data(ttl=60)
def load_gem_rules():
    if not supabase: return "⚠️ ไม่สามารถเชื่อมต่อ Supabase"
    try:
        # [แก้ไข #1] เปลี่ยนชื่อตัวแปร response เพื่อไม่ให้ชนกับ loop variable
        response = supabase.table("gem_knowledge").select(
            "rule_id,category,rule_text").eq("is_active", True).execute()
        if response.data:
            return "\n".join([
                f"[{item['rule_id']} - หมวด {item['category']}] {item['rule_text']}"
                for item in response.data
            ])
        return "ยังไม่มีข้อมูลกฎ"
    except Exception as e:
        return f"Error: {e}"

def get_dynamic_rules(target, is_live, raw_rules):
    rules = raw_rules.split('\n')
    out = []
    is_ah = target in ["เจ้าบ้าน", "ทีมเยือน"]
    is_ou = target in ["สูง", "ต่ำ"]
    for rule in rules:
        if not rule.strip(): continue
        rl = rule.lower()
        if is_ou and any(w in rl for w in ['เจ้าบ้าน','ทีมเยือน','ต่อ','รอง','ah']) \
                and not any(w in rl for w in ['สูง','ต่ำ','สกอร์','o/u']): continue
        if is_ah and any(w in rl for w in ['สูง','ต่ำ','สกอร์รวม','o/u']) \
                and not any(w in rl for w in ['เจ้าบ้าน','ทีมเยือน','ต่อ','รอง','ah']): continue
        if not is_live and any(w in rl for w in ['live','สด','นาที','ใบแดง','สกอร์ปัจจุบัน']): continue
        if is_live and any(w in rl for w in ['ก่อนเตะ','pre-match','ราคาเปิด']) \
                and not any(w in rl for w in ['live','สด','ไหล']): continue
        out.append(rule)
    return "\n".join(out)

def clear_form_data():
    st.session_state.raw_text = ""
    st.session_state.match_name = "ชื่อคู่แข่งขัน"
    for k, v in {
        'h1x2_val': 1.0, 'd1x2_val': 1.0, 'a1x2_val': 1.0,
        'hdp_line_val': 0.0, 'hdp_h_w_val': 0.0, 'hdp_a_w_val': 0.0,
        'ou_line_val': 2.5, 'ou_over_w_val': 0.0, 'ou_under_w_val': 0.0,
        'xg_h_val': 0.0, 'xg_a_val': 0.0,
    }.items():
        st.session_state[k] = v

def parse_line(s):
    s = str(s).replace(' ', '').replace('+', '')
    neg = '-' in s
    s = s.replace('-', '')
    try:
        if '/' in s or ',' in s:
            sep = '/' if '/' in s else ','
            return (-1 if neg else 1) * ((float(s.split(sep)[0]) + float(s.split(sep)[1])) / 2)
        return float(s) * (-1 if neg else 1)
    except:
        return 0.0

# ==========================================
# 🧮 MATH ENGINE
# ==========================================
def shin_devig(oh, od, oa):
    pi = [1/oh, 1/od, 1/oa]
    sp = sum(pi)
    if sp <= 1.0: return pi[0]/sp, pi[1]/sp, pi[2]/sp
    lo, hi = 0.0, 1.0
    z = 0.0
    for _ in range(100):
        z = (lo + hi) / 2
        try:
            p = [(math.sqrt(z**2 + 4*(1-z)*pi_i) - z) / (2*(1-z)) for pi_i in pi]
            if sum(p) > 1: lo = z
            else: hi = z
        except ZeroDivisionError:
            break
    try:
        p = [(math.sqrt(z**2 + 4*(1-z)*pi_i) - z) / (2*(1-z)) for pi_i in pi]
    except:
        p = pi
    sp = sum(p)
    # [แก้ไข #5] guard หาก sp = 0 เพื่อหลีกเลี่ยง ZeroDivisionError
    if sp == 0:
        return 1/3, 1/3, 1/3
    return p[0]/sp, p[1]/sp, p[2]/sp


def poisson(k, lam):
    return (lam**k * math.exp(-lam)) / math.factorial(k)


def calc_dixon_coles_matrix(ph, pd, pa, ou, oow, uuw,
                             ch=0, ca=0, ml=90,
                             rch=False, rca=False,
                             xg_h=0.0, xg_a=0.0, xg_weight=0.0):
    ow  = oow + 1 if oow < 1.1 else oow
    uw  = uuw + 1 if uuw < 1.1 else uuw
    op  = 1/ow; up = 1/uw
    top = op / (op + up)

    # [Calibration v2] ลด baseline bias และ draw multiplier เพื่อให้ et
    # ใกล้เคียง implied goal ที่ตลาดสะท้อน มากกว่าเดิม
    # baseline: 0.20 → 0.05  (ลด Under bias จากการดัน et สูงเกิน)
    # draw_mult: 8.0 → 4.0   (ลดการขยายเกินจริงในเกมที่เต็งชัด)
    bet = ou + 0.05 + ((top - 0.5) * 2.5)
    et  = max(0.5, bet + (0.25 - pd) * 4.0)
    sup = (ph - pa) * (et ** 0.60)

    lh = max(0.15, (et + sup) / 2) * (ml / 90) ** 0.75
    la = max(0.15, (et - sup) / 2) * (ml / 90) ** 0.75

    # [แก้ไข #6] ใช้ if block แยกบรรทัด ป้องกัน semicolon bug
    # Python อ่าน `if cond: a; b` ว่า b อยู่นอก if เสมอ
    if rch:
        lh *= 0.50
        la *= 1.30
    if rca:
        la *= 0.50
        lh *= 1.30

    # xG Blending — จำกัด xG input ก่อนเบลนด์เพื่อป้องกัน Lambda สูงเกินจริง
    # [แก้ไข ข้อจำกัด #2] ค่า xG ปกติอยู่ที่ 0.5–3.0 ต่อเกม จำกัดที่ 4.0 เป็น hard cap
    if xg_h > 0.0 or xg_a > 0.0:
        xg_h_safe = min(xg_h, 4.0)
        xg_a_safe = min(xg_a, 4.0)
        lh = lh * (1 - xg_weight) + xg_h_safe * (ml / 90) ** 0.75 * xg_weight
        la = la * (1 - xg_weight) + xg_a_safe * (ml / 90) ** 0.75 * xg_weight

    # Dynamic Rho — คำนวณอัตโนมัติจากเรตประตูรวม ไม่ต้องใช้ Slider
    dyn_rho = max(-0.25, min(0.0, -0.15 + (et - 2.5) * 0.05))

    mx = [[0.0] * 10 for _ in range(10)]
    for i in range(10):
        for j in range(10):
            bp = poisson(i, lh) * poisson(j, la)
            if   i == 0 and j == 0: tau = 1 - (lh * la * dyn_rho)
            elif i == 0 and j == 1: tau = 1 + (lh * dyn_rho)
            elif i == 1 and j == 0: tau = 1 + (la * dyn_rho)
            elif i == 1 and j == 1: tau = 1 - dyn_rho
            else: tau = 1.0
            mx[i][j] = max(0, bp * tau)

    tp = sum(sum(r) for r in mx)
    h2 = h1 = dr = a1 = a2 = 0.0
    pou = {}
    for i in range(10):
        for j in range(10):
            p  = mx[i][j] / tp
            fh = i + ch; fa = j + ca; d = fh - fa
            if   d >= 2:  h2 += p
            elif d == 1:  h1 += p
            elif d == 0:  dr += p
            elif d == -1: a1 += p
            elif d <= -2: a2 += p
            tg = fh + fa
            pou[tg] = pou.get(tg, 0) + p
    return (h2, h1, dr, a1, a2, pou)


# [แก้ไข #4] เปลี่ยน flat penalty เป็น relative (สัดส่วน) และ
# แยกออกจาก ev_ah/ev_ou เป็น utility function ที่สะอาด
def _quant_penalty(ev, line, odds):
    """Relative penalty สำหรับ quarter-ball line และ extreme odds."""
    rm = abs(line) - math.floor(abs(line))
    if rm in (0.25, 0.75):
        ev *= 0.985          # หัก 1.5% สัดส่วน แทน flat -0.015
    if odds < 1.30 or odds > 4.00:
        ev *= 0.970          # หัก 3.0% สัดส่วน แทน flat -0.030
    return ev


def ev_ah(hdp, w2, w1, d, l1, l2, odds, fav):
    """
    คำนวณ Expected Value สำหรับตลาด Asian Handicap
    ครอบคลุมเส้น 0.0 – 2.5 ทั้ง Fav และ Dog

    Bucket probability จาก Dixon-Coles (5 ช่อง):
      w2 = ชนะห่าง ≥ 2 ประตู  (margin ≥ 2)
      w1 = ชนะ 1 ประตู         (margin = 1)
      d  = เสมอ                 (margin = 0)
      l1 = แพ้ 1 ประตู          (margin = -1)
      l2 = แพ้ห่าง ≥ 2 ประตู   (margin ≤ -2)

    Settlement rules (Pinnacle / SBO standard):
      เส้นจำนวนเต็ม (.0): ชนะเต็ม / คืนทุน / แพ้เต็ม
      เส้น .5          : ชนะเต็ม / แพ้เต็ม (ไม่มีคืนทุน)
      เส้น .25 / .75   : ตัดครึ่ง — ครึ่งหนึ่งเล่น .0, ครึ่งหนึ่งเล่น .5
        → บางกรณีได้ ชนะครึ่ง (+b/2) หรือ แพ้ครึ่ง (-0.5)

    ข้อจำกัดของ 5-bucket model สำหรับเส้น > 1.5:
      w2 รวม margin=2 และ margin≥3 ไว้ด้วยกัน ทำให้เส้น 2.0+ มีความคลาดเคลื่อน
      เล็กน้อยเมื่อเทียบกับ full score matrix (แต่ยังดีกว่าคืน EV=0)
    """
    b = odds - 1
    h = abs(hdp)

    if h == 0:
        # AH 0 (Level Ball): ชนะถ้า margin>0, คืนทุนถ้าเสมอ, แพ้ถ้า margin<0
        res = (w2 + w1) * b - (l1 + l2)

    elif fav:
        # ======================== FAVOURITE (ทีมต่อ) ========================
        # ต่อ 0.25 (quarter ball: ครึ่งเล่น 0, ครึ่งเล่น 0.5)
        # margin>0 → ชนะทั้ง 2 ส่วน | margin=0 → ชนะ 0.5, คืนทุน 0.5 → net +b/2
        # margin<0 → แพ้ทั้ง 2 ส่วน
        if   h == 0.25: res = (w2 + w1) * b - d * 0.5 - (l1 + l2)

        # ต่อ 0.5: ไม่มีคืนทุน — margin>0 ชนะ, ≤0 แพ้
        elif h == 0.5:  res = (w2 + w1) * b - (d + l1 + l2)

        # ต่อ 0.75 (ครึ่งเล่น 0.5, ครึ่งเล่น 1.0)
        # margin≥2 → ชนะทั้งคู่ (+b) | margin=1 → ชนะ 0.5 (+b/2), คืนทุน 0.5 → net +b/2
        # margin≤0 → แพ้ทั้งคู่
        elif h == 0.75: res = w2 * b + w1 * (b / 2) - (d + l1 + l2)

        # ต่อ 1.0: margin≥2 ชนะ, margin=1 คืนทุน, ≤0 แพ้
        elif h == 1.0:  res = w2 * b - (d + l1 + l2)

        # ต่อ 1.25 (ครึ่งเล่น 1.0, ครึ่งเล่น 1.5)
        # margin≥2 → ชนะทั้งคู่ (+b) | margin=1 → คืนทุน 0.5, แพ้ 0.5 → net -0.5
        # margin≤0 → แพ้ทั้งคู่
        elif h == 1.25: res = w2 * b - w1 * 0.5 - (d + l1 + l2)

        # ต่อ 1.5: margin≥2 ชนะ, ≤1 แพ้ (ไม่มีคืนทุน)
        elif h == 1.5:  res = w2 * b - (w1 + d + l1 + l2)

        # [แก้ไข ข้อจำกัด #1] เส้น 1.75 – 2.5 สำหรับ Favourite
        # ต่อ 1.75 (ครึ่งเล่น 1.5, ครึ่งเล่น 2.0)
        # margin≥2 → ชนะทั้งคู่ (+b) | margin=1 → แพ้ 1.5, คืนทุน 2.0 → net -0.5
        # margin≤0 → แพ้ทั้งคู่
        elif h == 1.75: res = w2 * b - w1 * 0.5 - (d + l1 + l2)
        # หมายเหตุ: สูตรเหมือน 1.25 Fav เพราะ pattern ซ้ำทุก 0.5 step

        # ต่อ 2.0: margin≥2 คืนทุน (w2), margin=1 แพ้, ≤0 แพ้
        # แต่ w2 รวม margin=2 และ ≥3 → ประมาณ: margin≥2 ชนะ, margin=1 แพ้ครึ่ง, ≤0 แพ้
        # correction ที่ดีที่สุดจาก 5-bucket: w2 ≈ margin≥2 ชนะ, w1=margin1 แพ้ครึ่ง
        elif h == 2.0:  res = w2 * b - w1 * 0.5 - (d + l1 + l2)

        # ต่อ 2.25 (ครึ่งเล่น 2.0, ครึ่งเล่น 2.5)
        # margin≥3 ชนะทั้งคู่, margin=2 → คืนทุน 2.0 แพ้ 2.5 → net -0.5
        # margin≤1 → แพ้ทั้งคู่
        # 5-bucket: w2≈margin≥2 ซึ่งรวม margin=2 ด้วย
        # ประมาณ: w2*b - (w1+d+l1+l2) [margin≥2 ชนะ สมมติทั้งหมด]
        elif h == 2.25: res = w2 * b - (w1 + d + l1 + l2)

        # ต่อ 2.5: ต้องชนะ ≥3 ประตู เท่านั้น — ไม่มีคืนทุน
        # w2 ≈ margin≥2 (รวม margin=2 ซึ่งแพ้) → คลาดเคลื่อน แต่ดีกว่า EV=0
        elif h == 2.5:  res = w2 * b - (w1 + d + l1 + l2)

        else:
            res = 0.0

    else:
        # ======================== UNDERDOG (ทีมรอง) ========================
        # รอง 0.25: margin<0 แพ้ทั้งคู่, margin=0 แพ้ 0.5 คืนทุน 0.5 → net +b/2
        # margin>0 (l1,l2 ในมุมทีมรอง) → ชนะ
        if   h == 0.25: res = (w2 + w1) * b + d * (b / 2) - (l1 + l2)

        # รอง 0.5: margin<0 ทีมรองชนะ, ≥0 แพ้ (ไม่มีคืนทุน)
        elif h == 0.5:  res = (w2 + w1 + d) * b - (l1 + l2)

        # รอง 0.75: margin≤-2 ชนะทั้งคู่, margin=-1 ชนะ 0.5 (+b/2), ≥0 แพ้
        # ใน bucket: l2=แพ้≥2 = ทีมรองชนะ≥2; l1=แพ้1 = ทีมรองชนะ1
        # → (w2+w1+d)*b - l1*0.5 - l2  [w2=ทีมเยือนแพ้, wn เป็น prob ฝั่งเจ้าบ้าน]
        elif h == 0.75: res = (w2 + w1 + d) * b - l1 * 0.5 - l2

        # รอง 1.0: ทีมรองชนะถ้าแพ้ ≥2 ประตู (l2), คืนทุนถ้าแพ้ 1 (l1)
        elif h == 1.0:  res = (w2 + w1 + d) * b - l2

        # รอง 1.25: ชนะทั้งคู่ถ้าแพ้≥2, คืนทุน 1.0 ชนะ 1.5 ถ้าแพ้ 1 → net +b/2
        elif h == 1.25: res = (w2 + w1 + d) * b + l1 * (b / 2) - l2

        # รอง 1.5: ทีมรองชนะถ้าแพ้≥2 หรือ 1, ≥ 0 แพ้
        elif h == 1.5:  res = (w2 + w1 + d + l1) * b - l2

        # [แก้ไข ข้อจำกัด #1] เส้น 1.75 – 2.5 สำหรับ Underdog
        # รอง 1.75 (ครึ่งเล่น 1.5, ครึ่งเล่น 2.0)
        # ทีมรองชนะถ้าแพ้≥2 (l2) ด้วยทั้งคู่, แพ้=1 (l1) → ชนะ 1.5 คืนทุน 2.0 → net +b/2
        elif h == 1.75: res = (w2 + w1 + d + l1) * b + l2 * (b / 2)

        # รอง 2.0: ทีมรองชนะถ้าแพ้≥2 (l2) คืนทุน, แพ้=1 ชนะ, ≤0 ชนะ
        # correction: (w2+w1+d+l1)*b ≈ ชนะถ้าไม่แพ้≥2
        elif h == 2.0:  res = (w2 + w1 + d + l1) * b

        # รอง 2.25 (ครึ่งเล่น 2.0, ครึ่งเล่น 2.5)
        # แพ้≥2 → ชนะ 2.0 (คืนทุน), แพ้ 2.5 → net +b/2
        elif h == 2.25: res = (w2 + w1 + d + l1) * b + l2 * (b / 2)

        # รอง 2.5: ชนะถ้าแพ้น้อยกว่า 3 ประตู (แทบทุก bucket ยกเว้น margin≤-3)
        # 5-bucket: l2 ≈ margin≤-2 → ทีมรองชนะทุก bucket
        elif h == 2.5:  res = (w2 + w1 + d + l1 + l2) * b

        else:
            res = 0.0

    return _quant_penalty(res, hdp, odds)


# [แก้ไข #3] รวมทุก case เข้า res แล้ว return ครั้งเดียว
# ป้องกัน early return ที่หนีการ apply penalty
def ev_ou(line, pt, odds, over):
    b  = odds - 1
    fl = math.floor(line)
    rm = line - fl
    g  = lambda cond: sum(pt.get(k, 0) for k in pt if cond(k))

    if over:
        if   rm == 0.0:  res = g(lambda k: k > fl)  * b  - g(lambda k: k < fl)
        elif rm == 0.25: res = g(lambda k: k >= fl+1)* b  - pt.get(fl, 0)*0.5 - g(lambda k: k < fl)
        elif rm == 0.5:  res = g(lambda k: k >= fl+1)* b  - g(lambda k: k <= fl)
        elif rm == 0.75: res = g(lambda k: k >= fl+2)* b  + pt.get(fl+1, 0)*(b/2) - g(lambda k: k <= fl)
        else: res = 0.0
    else:
        if   rm == 0.0:  res = g(lambda k: k < fl)  * b  - g(lambda k: k > fl)
        elif rm == 0.25: res = g(lambda k: k < fl)  * b  + pt.get(fl, 0)*(b/2) - g(lambda k: k >= fl+1)
        elif rm == 0.5:  res = g(lambda k: k <= fl) * b  - g(lambda k: k >= fl+1)
        elif rm == 0.75: res = g(lambda k: k <= fl) * b  - pt.get(fl+1, 0)*0.5  - g(lambda k: k >= fl+2)
        else: res = 0.0

    return _quant_penalty(res, line, odds)


# ==========================================
# 🧠 AI ORACLE ENGINE  — v2 (Full Coverage Prompt)
# ==========================================
def ai_engine(match_name, target, base_ev, hdp, odds,
              live=False, current_min=0, score="0-0",
              thr=0.08, stats="", fav=None,
              line_movement="➖ Stable (นิ่ง/ปกติ)"):
    """
    Oracle Decision Engine — ทำหน้าที่เป็น Chief Risk Officer (CRO)
    รับ Base EV จาก Quant Engine แล้วกรองด้วย GEM RULES + บริบทตลาด
    คืนค่า impact_score เพื่อปรับ Net EV และ final_decision สำหรับ approval
    """
    raw = load_gem_rules()
    try:
        db = get_dynamic_rules(target, live, raw)
    except:
        db = raw

    # ── context blocks ──────────────────────────────────────────
    is_ah   = target in ["เจ้าบ้าน", "ทีมเยือน"]
    is_ou   = target in ["สูง", "ต่ำ"]
    market  = "Asian Handicap (AH)" if is_ah else "Total Goals (O/U)"
    fav_str = ("" if fav is None
               else (" [ทีมต่อ / Favourite]" if fav else " [ทีมรอง / Underdog]"))
    sit_str = (f"IN-PLAY — นาทีที่ {current_min} สกอร์ปัจจุบัน {score}"
               if live else "PRE-MATCH")
    mode_weight = ("Math 50% + GEM Rules 50%" if live
                   else "Math 70% + GEM Rules 30%")

    # ── line movement interpretation ────────────────────────────
    lm_lower = line_movement.lower()
    if "steam" in lm_lower or "ไหลลง" in lm_lower:
        lm_note = "🔥 STEAM — เงิน Smart Money ไหลเข้าฝั่งนี้ → สัญญาณบวกเพิ่มความมั่นใจ"
    elif "drift" in lm_lower or "ไหลขึ้น" in lm_lower:
        lm_note = "❄️ DRIFT — ราคาไหลออกจากฝั่งนี้ → ระวัง Trap ของบ่อน พิจารณาลด impact_score"
    else:
        lm_note = "➖ STABLE — ราคานิ่ง ไม่มีสัญญาณผิดปกติจาก Smart Money"

    prompt = f"""คุณคือ Chief Risk Officer (CRO) ของกองทุน Quant Sports Betting
ภารกิจ: ตรวจสอบ Base EV ที่ได้จาก Dixon-Coles + Shin Devigging แล้วปรับด้วย GEM RULES และบริบทตลาด
เพื่อคืนค่า Net EV ที่แม่นยำและ final_decision สำหรับการลงทุน

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 ข้อมูลการลงทุน
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• แมตช์     : {match_name}
• สถานการณ์ : {sit_str}
• ตลาด      : {market}
• เป้าหมาย  : {target}{fav_str}
• เรต (line): {abs(hdp)}
• Odds      : {odds}
• Base EV   : {base_ev*100:.2f}%
• EV threshold: {thr*100:.1f}% (ขั้นต่ำที่ระบบยอมรับ)

📈 กระแสราคา (Line Movement)
• {line_movement}
• {lm_note}

📊 ข้อมูลสถิติ / บริบทเพิ่มเติม
{stats if stats.strip() else "ไม่มีข้อมูลสถิติเพิ่มเติม"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚙️ โหมดการวิเคราะห์: {mode_weight}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{"🔴 IN-PLAY MODE: ตรวจสถานการณ์สนาม Red Card / Score / Momentum แบบ Real-time ร่วมกับ GEM RULES เต็มรูปแบบ หาก Fatal Rule ถูก trigger ให้ Reject ทันที" if live else "🟡 PRE-MATCH MODE: ใช้ Math เป็นหลัก GEM RULES เป็น Risk Filter อย่างเดียว ถ้า Base EV แข็งแกร่ง Warning Rule ไม่ควรทำให้ Reject"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📖 GEM RULES (จาก Cloud Database)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{db}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 คำสั่งบังคับ (ต้องปฏิบัติตามทุกข้อ)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. ROLE INTEGRITY
   • ตรวจ {fav_str if fav_str else "[ทีมต่อ/ทีมรอง]"} ให้แม่นยำก่อนวิเคราะห์ ห้ามสับสนเด็ดขาด
   • ทีมต่อ (Favourite) = ทีมที่มี true probability สูงกว่า = ต้องชนะด้วย margin
   • ทีมรอง (Underdog) = ทีมที่ได้ handicap เพิ่ม = ได้เปรียบจากเสมอและแพ้น้อย

2. MARKET ISOLATION
   • หากตลาดคือ AH → ห้ามนำกฎ O/U หรือสกอร์รวมมาพิจารณาการ approve/reject เด็ดขาด
   • หากตลาดคือ O/U → ห้ามนำกฎ AH หรือ supremacy มาพิจารณา เด็ดขาด
   • กฎที่ label [ALL] ใช้ได้ทั้งสองตลาด

3. RULE CITATION
   • ทุกครั้งที่อ้างกฎ ต้องระบุ [Rule ID] และ [หมวด] ให้ชัดเจน
   • ถ้าไม่มีกฎที่ตรง → ระบุ "ไม่มีกฎที่เกี่ยวข้อง" แทนการแต่งกฎขึ้นเอง

4. IMPACT SCORE RULES
   • ค่าต้องเป็น float อยู่ในช่วง -1.0 ถึง +1.0 เท่านั้น
   • +0.05 = เพิ่ม EV 5% (สัญญาณบวกชัดเจน เช่น Steam + กฎสนับสนุน)
   • -0.10 = ลด EV 10% (Risk factor จากกฎหรือ Drift)
   • 0.00  = ข้อมูลไม่เพียงพอหรือสัญญาณหักล้างกัน
   • ห้ามส่งค่าเป็น percentage (เช่น 5.0 หรือ -10.0) → ต้องเป็น 0.05 หรือ -0.10

5. DECISION LOGIC
   PRE-MATCH:
   • Base EV ≥ threshold + ไม่มี Fatal Rule → final_decision: true
   • มี Warning Rule → ลด impact_score แต่ยัง approve ถ้า Net EV ≥ threshold
   • มี Fatal Rule (ระบุชัดใน rule_triggered) → final_decision: false เสมอ
   IN-PLAY:
   • Base EV สูงมาก (≥ threshold × 1.5) + Warning Rule → อาจ approve พร้อม impact ลบ
   • Fatal Rule → Reject ทันทีโดยไม่คำนึง EV
   • Red card / Score ผิดปกติ → ตรวจสอบ momentum ก่อน approve

6. CONFIDENCE LEVEL
   • 5 = ข้อมูลครบ, EV สูง, กฎสนับสนุน, Steam
   • 4 = EV ดี, ไม่มีกฎขัดแย้ง
   • 3 = กลางๆ มีความไม่แน่นอนบ้าง
   • 2 = มี Risk factors หลายตัว
   • 1 = Fallback หรือข้อมูลน้อยมาก

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📤 ตอบกลับเป็น JSON (ภาษาไทย) เท่านั้น ห้ามมีข้อความนอก JSON:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{{
  "pros_analysis": "วิเคราะห์ข้อดีทางคณิตศาสตร์ + กฎที่สนับสนุน + สัญญาณตลาด",
  "cons_analysis": "ความเสี่ยงและกฎที่ขัดแย้ง พร้อมระบุ [Rule ID]",
  "rule_triggered": "เช่น [GEM_DEF_001 - Risk Management] หรือ ไม่มีกฎที่เกี่ยวข้อง",
  "impact_score": 0.0,
  "final_decision": true,
  "final_comment": "บทสรุปฟันธงจาก CRO ในภาษาที่กระชับและตรงประเด็น",
  "confidence_level": 3
}}"""

    for attempt in range(3):
        try:
            model = genai.GenerativeModel('models/gemma-4-31b-it')
            res   = model.generate_content(prompt)
            data  = safe_json_loads(res.text)
            if data:
                imp = float(data.get('impact_score', 0.0))
                # guard: ถ้า AI ส่งมาเป็น percentage เช่น 5.0 แทน 0.05
                if abs(imp) >= 1.0:
                    imp /= 100.0
                # clamp ไม่ให้เกิน ±0.50 ในทางปฏิบัติ
                imp = max(-0.50, min(0.50, imp))
                data['impact_score'] = imp
                # guard: confidence_level ต้องอยู่ใน 1-5
                cl = int(data.get('confidence_level', 3))
                data['confidence_level'] = max(1, min(5, cl))
                return data
        except Exception as e:
            if attempt == 2:
                return {
                    "pros_analysis": "ระบบ AI ขัดข้องชั่วคราว ใช้ Base EV แทน",
                    "cons_analysis": f"Error: {str(e)}",
                    "rule_triggered": "System Fallback — ไม่สามารถโหลด GEM RULES ได้",
                    "impact_score": 0.0,
                    "final_decision": base_ev >= thr,
                    "final_comment": (
                        "⚠️ Oracle ไม่ตอบสนอง — ยืนยันด้วย Base EV เท่านั้น "
                        "ควรตรวจสอบ API Key และ connection ก่อนใช้งาน"
                    ),
                    "confidence_level": 1
                }
            time.sleep(2)


# ==========================================
# 📊 CHART HELPERS
# ==========================================
def ev_gauge(val, title, thr=8.0):
    pct = val * 100
    c   = "#00ff88" if pct >= thr else ("#ffd600" if pct > 0 else "#ff3b5c")
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=pct,
        number={'suffix': "%", 'font': {'color': c, 'size': 30, 'family': 'Share Tech Mono'}},
        title={'text': title, 'font': {'size': 12, 'color': '#4a7a60', 'family': 'Rajdhani'}},
        gauge={
            'axis': {'range': [-20, 20], 'tickwidth': 1, 'tickcolor': "#0f2535",
                     'tickfont': {'color': '#1a3528', 'size': 8}},
            'bar': {'color': c, 'thickness': 0.22},
            'bgcolor': "rgba(0,0,0,0)", 'borderwidth': 0,
            'steps': [
                {'range': [-20, 0],  'color': "rgba(255,59,92,0.07)"},
                {'range': [0, thr],  'color': "rgba(255,214,0,0.05)"},
                {'range': [thr, 20], 'color': "rgba(0,255,136,0.07)"},
            ],
            'threshold': {'line': {'color': c, 'width': 2}, 'thickness': 0.8, 'value': pct}
        }
    ))
    fig.update_layout(height=185, margin=dict(l=12, r=12, t=26, b=6),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def neon_layout(fig, title=""):
    fig.update_layout(
        title=dict(text=title, font=dict(family="Rajdhani", size=12, color="#2a5040")),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(9,21,32,0.55)",
        font=dict(family="Share Tech Mono", color="#4a7a60"),
        xaxis=dict(gridcolor="#0f2535", linecolor="#0f2535", tickfont=dict(color="#2a5040")),
        yaxis=dict(gridcolor="#0f2535", linecolor="#0f2535", tickfont=dict(color="#2a5040")),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#4a7a60")),
        margin=dict(l=8, r=8, t=36, b=8)
    )
    return fig


def adj_hdp(v): st.session_state['live_hdp'] += v
def adj_ou(v):  st.session_state['live_ou']  += v
def fix(o):     return o + 1.0 if o < 1.1 else o


def save_db(rows):
    if not rows or not supabase: return
    try:
        supabase.table("investment_logs").insert(rows).execute()
    except Exception as e:
        st.error(f"DB Error: {e}")


def load_logs():
    if not supabase: return pd.DataFrame()
    try:
        r = supabase.table("investment_logs").select("*").order("Time", desc=True).execute()
        if r.data:
            df = pd.DataFrame(r.data)
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
            for c in ['EV_Pct', 'Investment', 'Odds', 'Closing_Odds']:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
            if 'Result' in df.columns: df['Result'] = df['Result'].fillna("")
            return df.dropna(subset=['Time'])
        return pd.DataFrame()
    except:
        return pd.DataFrame()


# [แก้ไข #2] ใช้ margin-based comparison แทน exact float equality
# เพื่อหลีกเลี่ยง floating-point precision bugs
def calc_pnl(row):
    try:
        if pd.isna(row['Result']) or str(row['Result']).strip() == "" \
                or float(row['Investment']) <= 0:
            return 0.0
        sc = re.findall(r'\d+', str(row['Result']).strip())
        if len(sc) < 2: return 0.0
        hs, as_ = int(sc[0]), int(sc[1])
        hdp  = float(row['HDP'])
        tgt  = str(row['Target']).strip()
        odds = float(row['Odds'])
        inv  = float(row['Investment'])

        if tgt == "เจ้าบ้าน":
            nm = (hs - as_) - hdp
        elif tgt == "ทีมเยือน":
            nm = (as_ - hs) + hdp
        elif tgt == "สูง":
            nm = (hs + as_) - hdp
        elif tgt == "ต่ำ":
            nm = hdp - (hs + as_)
        else:
            return 0.0

        # margin ±0.01 ป้องกัน floating-point drift เช่น 0.2499999
        if nm > 0.26:    return inv * (odds - 1)         # full win
        elif nm > 0.0:   return inv * (odds - 1) / 2     # half win  (0 < nm ≤ 0.25)
        elif nm > -0.01: return 0.0                       # push      (nm ≈ 0)
        elif nm > -0.26: return -(inv / 2)               # half loss
        else:            return -inv                      # full loss
    except:
        return 0.0


def calc_clv(row):
    try:
        if pd.isna(row['Closing_Odds']) or float(row['Closing_Odds']) <= 1.0: return 0.0
        return ((float(row['Odds']) / float(row['Closing_Odds'])) - 1.0) * 100.0
    except:
        return 0.0


# ==========================================
# 🖥️ HEADER
# ==========================================
st.markdown("""
<div style="display:flex;align-items:center;gap:14px;margin-bottom:4px;">
  <div style="flex:1;">
    <div style="font-family:'Share Tech Mono';font-size:0.62rem;color:#1a3528;letter-spacing:0.22em;margin-bottom:3px;">
      ◈ QUANTITATIVE SPORTS ANALYTICS PLATFORM ◈
    </div>
    <h1 style="margin:0;padding:0;line-height:1.1;">
      GEM SYSTEM <span style="color:#00cc6a;font-size:1.5rem;">10.0</span>
      &nbsp;<span style="font-size:0.9rem;color:#2a5040;font-family:'Share Tech Mono';font-weight:400;text-shadow:none;">THE ORACLE</span>
    </h1>
  </div>
  <div style="text-align:right;">
    <div style="font-family:'Share Tech Mono';font-size:0.6rem;color:#1a3528;letter-spacing:.15em;">BUILD v10.0.15</div>
    <span class="gem-badge">● SYSTEM ONLINE</span>
  </div>
</div>
<div class="gem-divider"></div>
""", unsafe_allow_html=True)

# ==========================================
# 🔧 SIDEBAR
# ==========================================
with st.sidebar:
    st.markdown('<div class="gem-label">◈ AI ORACLE</div>', unsafe_allow_html=True)
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        st.markdown('<p class="gem-ok">▶ AI ENGINE: CONNECTED</p>', unsafe_allow_html=True)
    else:
        api_key = st.text_input("Gemini API Key", type="password", placeholder="paste key here...")
        if api_key:
            genai.configure(api_key=api_key)
            st.markdown('<p class="gem-ok">▶ CONNECTED</p>', unsafe_allow_html=True)
        else:
            st.markdown('<p class="gem-warn">▶ AWAITING KEY</p>', unsafe_allow_html=True)

    st.markdown('<div class="gem-label" style="margin-top:10px;">◈ DATABASE</div>', unsafe_allow_html=True)
    if supabase:
        st.markdown('<p class="gem-ok">▶ SUPABASE: ONLINE</p>', unsafe_allow_html=True)
        st.markdown('<p class="gem-dim">▸ CLOUD SYNC ACTIVE</p>', unsafe_allow_html=True)
    else:
        st.markdown('<p class="gem-err">▶ SUPABASE: OFFLINE</p>', unsafe_allow_html=True)

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="gem-label">◈ PORTFOLIO</div>', unsafe_allow_html=True)
    total_bankroll = st.number_input("Bankroll (THB)", min_value=0.0, value=10000.0)
    # HDBA slider ยังคงไว้เพื่อใช้ใน future หรือ manual override
    # แต่ระบบใช้ Dynamic HDBA = pd × dog_odds × 0.25 เป็นค่าหลัก
    hdba_val = st.slider(
        "HDBA Adj Factor",
        0.10, 0.50, 0.25, step=0.05,
        help="Dynamic Dog Penalty = pd × odds × factor (0.25 = หัก 25% ของ draw advantage)"
    )

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="gem-label">◈ KELLY CRITERION (MONEY MGT)</div>', unsafe_allow_html=True)
    kelly_fraction = st.slider("Kelly Fraction", 0.05, 0.50, 0.25, step=0.05,
                               help="สัดส่วน Kelly (แนะนำ 0.25)")
    max_bet_cap    = st.slider("Max Bet Cap %", 1.0, 10.0, 5.0, step=0.5,
                               help="ลิมิตเงินลงทุนสูงสุดต่อบิล")

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="gem-label">◈ EV THRESHOLDS — PRE-MATCH</div>', unsafe_allow_html=True)
    pre_ah_thr = st.slider("AH %",  1.0, 50.0, 10.0, step=0.5)
    pre_ou_thr = st.slider("O/U %", 1.0, 50.0, 10.0, step=0.5)
    st.markdown('<div class="gem-label">◈ EV THRESHOLDS — IN-PLAY</div>', unsafe_allow_html=True)
    live_ah_thr = st.slider("AH Live %",  5.0, 50.0, 24.0, step=1.0)
    live_ou_thr = st.slider("O/U Live %", 5.0, 50.0, 23.0, step=1.0)

pre_ah_lim  = pre_ah_thr  / 100
pre_ou_lim  = pre_ou_thr  / 100
live_ah_lim = live_ah_thr / 100
live_ou_lim = live_ou_thr / 100

# ==========================================
# 📑 TABS
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs([
    "  PRE-MATCH  ", "  DASHBOARD  ", "  IN-PLAY SNIPER  ", "  BACKTEST  "
])

# ╔══════════════╗
# ║  TAB 1       ║
# ╚══════════════╝
with tab1:
    st.markdown('<div class="gem-label">◈ QUICK IMPORT</div>', unsafe_allow_html=True)
    qi1, qi2 = st.columns(2)

    with qi1:
        with st.expander("📷 AI VISION — Extract from image"):
            if not api_key:
                st.markdown('<p class="gem-warn">▸ API Key required</p>', unsafe_allow_html=True)
            else:
                uf = st.file_uploader("Upload odds screenshot", type=['png', 'jpg'])
                if uf and st.button("⚡ EXTRACT IMAGE", use_container_width=True):
                    with st.spinner("Scanning Matrix..."):
                        try:
                            img   = Image.open(uf)
                            model = genai.GenerativeModel('models/gemma-4-31b-it')
                            prompt_img = """สกัดข้อมูลตารางราคาฟุตบอลจากภาพ ตอบกลับ JSON เท่านั้น:
1. match_name: ทีมแถวบน + " VS " + ทีมแถวล่าง
2. แฮนดิแคป: hdp_line_val (แปลงเป็นทศนิยม เช่น 0.5/1→0.75), hdp_h_w_val, hdp_a_w_val
3. สูง/ต่ำ: ou_line_val (แปลงเป็นทศนิยม เช่น 3/3.5→3.25), ou_over_w_val, ou_under_w_val
4. 1X2: h1x2_val, d1x2_val, a1x2_val
{"match_name":"","h1x2_val":0.0,"d1x2_val":0.0,"a1x2_val":0.0,"hdp_line_val":0.0,"hdp_h_w_val":0.0,"hdp_a_w_val":0.0,"ou_line_val":0.0,"ou_over_w_val":0.0,"ou_under_w_val":0.0}"""
                            d = safe_json_loads(model.generate_content([prompt_img, img]).text)
                            for k, v in d.items():
                                if k == 'match_name': st.session_state[k] = str(v)
                                else:
                                    try: st.session_state[k] = float(v)
                                    except: st.session_state[k] = 0.0
                            st.toast("✅ สกัดข้อมูลสำเร็จ!", icon="🎯")
                            time.sleep(1); st.rerun()
                        except Exception as e:
                            st.error(str(e))

    with qi2:
        with st.expander("⌨️ TEXT PARSER — Paste raw text"):
            st.text_area("Paste odds...", height=75, key="raw_text")
            tp1, tp2 = st.columns(2)
            with tp1:
                if st.button("⚡ PARSE", use_container_width=True):
                    try:
                        raw = st.session_state.raw_text
                        mv  = re.search(r'(.*VS.*)', raw)
                        if mv: st.session_state.match_name = mv.group(1).strip()
                        hm = re.findall(r'^\s*เหย้า\s+([0-9.]+)', raw, re.MULTILINE)
                        if len(hm) >= 1: st.session_state.h1x2_val    = float(hm[0])
                        if len(hm) >= 2: st.session_state.hdp_h_w_val = float(hm[1])
                        dm = re.findall(r'^\s*เสมอ\s+([0-9.]+)', raw, re.MULTILINE)
                        if dm: st.session_state.d1x2_val = float(dm[0])
                        am = re.findall(r'^\s*เยือน\s+([0-9.]+)', raw, re.MULTILINE)
                        if len(am) >= 1: st.session_state.a1x2_val    = float(am[0])
                        if len(am) >= 2: st.session_state.hdp_a_w_val = float(am[1])
                        ahm = re.search(r'^\s*AH\s+([-+0-9.,/]+)', raw, re.MULTILINE)
                        if ahm: st.session_state.hdp_line_val = parse_line(ahm.group(1))
                        oum = re.search(r'^\s*สูง/ต่ำ\s+([-+0-9.,/]+)', raw, re.MULTILINE)
                        if oum: st.session_state.ou_line_val = parse_line(oum.group(1))
                        om = re.search(r'^\s*สูง\s+([0-9.]+)', raw, re.MULTILINE)
                        if om: st.session_state.ou_over_w_val = float(om.group(1))
                        um = re.search(r'^\s*ต่ำ\s+([0-9.]+)', raw, re.MULTILINE)
                        if um: st.session_state.ou_under_w_val = float(um.group(1))
                        st.toast("✅ Parsed!", icon="🎯")
                        time.sleep(1); st.rerun()
                    except Exception as e:
                        st.error(str(e))
            with tp2:
                st.button("🗑 CLEAR", use_container_width=True, on_click=clear_form_data)

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    match_name = st.text_input("MATCH", key="match_name", placeholder="Home Team VS Away Team")

    st.markdown('<div class="gem-label" style="margin-top:10px;">◈ MARKET DATA</div>', unsafe_allow_html=True)
    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        st.markdown('<div class="gem-panel"><div class="gem-label">1X2 POOL</div>', unsafe_allow_html=True)
        h1x2  = st.number_input("HOME",  format="%.2f", key="h1x2_val")
        d1x2  = st.number_input("DRAW",  format="%.2f", key="d1x2_val")
        a1x2  = st.number_input("AWAY",  format="%.2f", key="a1x2_val")
        st.markdown('</div>', unsafe_allow_html=True)
    with mc2:
        st.markdown('<div class="gem-panel"><div class="gem-label">HANDICAP (AH)</div>', unsafe_allow_html=True)
        hdp_line = st.number_input("LINE",      format="%.2f", step=0.25, key="hdp_line_val")
        hdp_h_w  = st.number_input("HOME ODDS", format="%.2f", key="hdp_h_w_val")
        hdp_a_w  = st.number_input("AWAY ODDS", format="%.2f", key="hdp_a_w_val")
        st.markdown('</div>', unsafe_allow_html=True)
    with mc3:
        st.markdown('<div class="gem-panel"><div class="gem-label">TOTAL GOALS (O/U)</div>', unsafe_allow_html=True)
        ou_line    = st.number_input("LINE",  format="%.2f", step=0.25, key="ou_line_val")
        ou_over_w  = st.number_input("OVER",  format="%.2f", key="ou_over_w_val")
        ou_under_w = st.number_input("UNDER", format="%.2f", key="ou_under_w_val")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="gem-label">◈ EXPECTED GOALS (xG) INTEGRATION</div>', unsafe_allow_html=True)
    c_xg1, c_xg2, c_xg3 = st.columns(3)
    xg_h      = c_xg1.number_input("xG Home", min_value=0.0, format="%.2f", step=0.1, key="xg_h_val")
    xg_a      = c_xg2.number_input("xG Away", min_value=0.0, format="%.2f", step=0.1, key="xg_a_val")
    xg_weight = c_xg3.slider("xG Weight %", 0.0, 1.0, 0.50, step=0.1,
                              help="0.5 = ผสม xG กับราคาบ่อนคนละครึ่ง")

    st.markdown('<div class="gem-label">◈ CONTEXT & MARKET FLOW</div>', unsafe_allow_html=True)
    col_st1, col_st2 = st.columns([2, 1])
    with col_st1:
        match_stats = st.text_area("H2H / Stats (Optional)", height=70,
                                   label_visibility="collapsed",
                                   placeholder="วางสถิติ H2H, ฟอร์มย้อนหลัง...")
    with col_st2:
        line_movement = st.selectbox("กระแสราคา (Line Movement)",
                                     ["➖ Stable (นิ่ง/ปกติ)",
                                      "🔥 Steam (ราคาไหลลง/เงินเข้า)",
                                      "❄️ Drift (ราคาไหลขึ้น/เงินออก)"])

    st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)

    if st.button("⚡  RUN ORACLE ANALYSIS", use_container_width=True, type="primary"):
        # [แก้ไข ข้อจำกัด #3] ตรวจสอบ input ก่อนคำนวณ
        # fix(0.0) = 1.0 → odds-1 = 0 → EV = 0 ทุกกรณีโดยไม่แจ้งเตือน
        input_errors = []
        if h1x2 <= 0 or d1x2 <= 0 or a1x2 <= 0:
            input_errors.append("กรุณากรอก **ราคา 1X2** (เหย้า / เสมอ / เยือน) ให้ครบ")
        if hdp_h_w <= 0 or hdp_a_w <= 0:
            input_errors.append("กรุณากรอก **น้ำ AH** (Home Odds / Away Odds) ให้ครบ")
        if ou_over_w <= 0 or ou_under_w <= 0:
            input_errors.append("กรุณากรอก **น้ำ O/U** (Over / Under) ให้ครบ")
        if abs(hdp_line) not in [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5,
                                   1.75, 2.0, 2.25, 2.5]:
            input_errors.append(
                f"⚠️ เส้น AH **{hdp_line}** ไม่รองรับ — "
                "ระบบคำนวณได้เฉพาะ 0 / 0.25 / 0.5 / 0.75 / 1.0 / 1.25 / 1.5 / 1.75 / 2.0 / 2.25 / 2.5"
            )
        if input_errors:
            for err in input_errors:
                st.error(f"❌ {err}")
            st.stop()
        ho, do_, ao   = fix(h1x2), fix(d1x2), fix(a1x2)
        hwo, awo, owo, uwo = fix(hdp_h_w), fix(hdp_a_w), fix(ou_over_w), fix(ou_under_w)
        ph, pd_, pa   = shin_devig(ho, do_, ao)
        hw2, hw1, dex, aw1, aw2, pt = calc_dixon_coles_matrix(
            ph, pd_, pa, ou_line, owo, uwo,
            xg_h=xg_h, xg_a=xg_a, xg_weight=xg_weight
        )

        fav_h = ph >= pa
        evh   = ev_ah(hdp_line, hw2, hw1, dex, aw1, aw2, hwo, fav_h)
        # [Calibration v2] Dynamic HDBA = pd_ × dog_odds × hdba_val
        # hdba_val (slider 0.10–0.50) คือสัดส่วน draw advantage ที่หักออก
        # ค่า default 0.25 = หัก 25% ของ draw advantage ที่ Dog ได้ฟรี
        hdba_dynamic = pd_ * awo * hdba_val
        eva   = ev_ah(hdp_line, aw2, aw1, dex, hw1, hw2, awo, not fav_h) - hdba_dynamic
        evo   = ev_ou(ou_line, pt, owo, True)
        evu   = ev_ou(ou_line, pt, uwo, False)

        bah = max([{"n": "เจ้าบ้าน", "ev": evh, "odds": hwo, "hdp": hdp_line},
                   {"n": "ทีมเยือน", "ev": eva, "odds": awo, "hdp": hdp_line}], key=lambda x: x['ev'])
        bou = max([{"n": "สูง",      "ev": evo, "odds": owo, "hdp": ou_line},
                   {"n": "ต่ำ",      "ev": evu, "odds": uwo, "hdp": ou_line}], key=lambda x: x['ev'])

        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="gem-label">◈ PROBABILITY ENGINE</div>', unsafe_allow_html=True)
        p1, p2, p3 = st.columns(3)
        p1.metric("HOME WIN", f"{ph*100:.1f}%")
        p2.metric("DRAW",     f"{pd_*100:.1f}%")
        p3.metric("AWAY WIN", f"{pa*100:.1f}%")

        g1, g2 = st.columns(2)
        with g1: st.plotly_chart(ev_gauge(bah['ev'], f"TARGET: {bah['n']}", pre_ah_thr), use_container_width=True)
        with g2: st.plotly_chart(ev_gauge(bou['ev'], f"TARGET: {bou['n']}", pre_ou_thr), use_container_width=True)

        # Cross-Market Dutching — วิเคราะห์ทุกตลาดที่ผ่าน threshold
        valid_bets = []
        if bah['ev'] >= pre_ah_lim: valid_bets.append(bah)
        if bou['ev'] >= pre_ou_lim: valid_bets.append(bou)

        if valid_bets:
            with st.spinner("◈ THE ORACLE PROCESSING..."):
                for tc in valid_bets:
                    tf = None
                    if tc['n'] == "เจ้าบ้าน": tf = fav_h
                    elif tc['n'] == "ทีมเยือน": tf = not fav_h
                    v   = ai_engine(match_name, tc['n'], tc['ev'], tc['hdp'], tc['odds'],
                                    live=False, thr=pre_ah_lim, stats=match_stats,
                                    fav=tf, line_movement=line_movement)
                    nev = tc['ev'] + v.get('impact_score', 0)

                    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="gem-label">◈ ORACLE VERDICT : {tc["n"]}</div>', unsafe_allow_html=True)
                    vc1, vc2, vc3 = st.columns(3)
                    vc1.metric("BASE EV",    f"{tc['ev']*100:.2f}%")
                    vc2.metric("ORACLE ADJ", f"{v.get('impact_score',0)*100:.2f}%")
                    vc3.metric("NET EV",     f"{nev*100:.2f}%")

                    with st.expander(f"◈ FULL ANALYSIS : {tc['n']}", expanded=True):
                        stars = v.get('confidence_level', 3)
                        st.markdown(f'<div class="gem-label">CONFIDENCE: {"★"*stars}{"☆"*(5-stars)} ({stars}/5)</div>', unsafe_allow_html=True)
                        st.success(f"**PROS:** {v.get('pros_analysis','—')}")
                        st.error(f"**RISK:** {v.get('cons_analysis','—')}")
                        st.info(f"**RULES:** {v.get('rule_triggered','None')}")

                    col_v = "#00ff88" if v.get('final_decision', False) and nev > 0 else "#ff3b5c"
                    label = "◈ ORACLE APPROVED — EXECUTE" if v.get('final_decision', False) and nev > 0 else "◈ ORACLE REJECTED — STAND DOWN"
                    st.markdown(
                        f'<div class="gem-panel" style="border-top:2px solid {col_v};">'
                        f'<div class="gem-label" style="border-color:{col_v};color:{col_v};">{label}</div>'
                        f'<p style="color:{col_v};font-family:\'Share Tech Mono\';font-size:0.82rem;">'
                        f'{v.get("final_comment","")}</p></div>',
                        unsafe_allow_html=True
                    )

                    if v.get('final_decision', False) and nev > 0:
                        st.balloons()
                        # [แก้ไข #8] dutch_factor พร้อม correlation warning
                        # AH และ O/U อาจ correlated สูง → ลด exposure เหลือ 60% ต่อตลาด
                        # แทนที่จะเป็น 50% flat ซึ่งไม่สะท้อน correlation จริง
                        dutch_factor = 0.60 if len(valid_bets) == 2 else 1.00
                        kelly_opt = nev / (tc['odds'] - 1)
                        inv = min(kelly_opt * kelly_fraction * dutch_factor,
                                  max_bet_cap / 100.0) * total_bankroll
                        inv = max(inv, 0.0)
                        if len(valid_bets) == 2:
                            st.warning(
                                "⚠️ Dutching 2 markets: AH & O/U อาจ positively correlated "
                                "— ระบบลด exposure เหลือ 60% ต่อตลาด"
                            )
                        tz_th = timezone(timedelta(hours=7))
                        save_db([{
                            "Time": datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S"),
                            "Match": match_name, "HDP": tc['hdp'], "Target": tc['n'],
                            "EV_Pct": round(nev * 100, 2), "Investment": round(inv, 2),
                            "Odds": tc['odds'], "Closing_Odds": 0.0, "Result": ""
                        }])
                        st.success(f"บันทึกบิล {tc['n']} สำเร็จ!")
        else:
            st.markdown(
                f'<div class="gem-panel" style="border-top:2px solid #ffd600;">'
                f'<div class="gem-label" style="border-color:#ffd600;color:#ffd600;">◈ BELOW THRESHOLD — NO SIGNAL</div>'
                f'<p class="gem-warn">AH {bah["ev"]*100:.2f}% (min {pre_ah_thr}%) | O/U {bou["ev"]*100:.2f}% (min {pre_ou_thr}%)</p></div>',
                unsafe_allow_html=True
            )

# ╔══════════════╗
# ║  TAB 2       ║
# ╚══════════════╝
with tab2:
    tab2_logs = load_logs()
    tz_th     = timezone(timedelta(hours=7))
    today_str = datetime.now(tz_th).strftime("%Y-%m-%d")

    if not tab2_logs.empty:
        # ── CSS เพิ่มเติมสำหรับ Match Cards ──────────────────────────────
        st.markdown("""
<style>
.match-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 10px;
    position: relative;
    transition: border-color 0.18s;
    cursor: pointer;
}
.match-card::before {
    content: "";
    position: absolute;
    top: 0; left: 0; bottom: 0;
    width: 3px;
    border-radius: 6px 0 0 6px;
}
.match-card.win::before   { background: #00ff88; }
.match-card.loss::before  { background: #ff3b5c; }
.match-card.push::before  { background: #4a7a60; }
.match-card.open::before  { background: #ffd600; }
.match-card.live::before  { background: #ff8c00; }

.mc-header {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
}
.mc-match {
    font-family: 'Exo 2', sans-serif;
    font-weight: 600;
    font-size: 0.92rem;
    color: #c8e6d4;
    flex: 1;
    min-width: 0;
}
.mc-live-tag {
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.62rem;
    color: #ff8c00;
    background: rgba(255,140,0,0.12);
    border: 1px solid rgba(255,140,0,0.3);
    padding: 1px 7px;
    border-radius: 2px;
    letter-spacing: 0.1em;
    white-space: nowrap;
}
.mc-badge {
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.66rem;
    padding: 2px 8px;
    border-radius: 2px;
    letter-spacing: 0.07em;
    white-space: nowrap;
}
.mc-badge.win   { background: rgba(0,255,136,0.12); color:#00ff88; border:1px solid rgba(0,255,136,0.3); }
.mc-badge.loss  { background: rgba(255,59,92,0.12);  color:#ff3b5c; border:1px solid rgba(255,59,92,0.3); }
.mc-badge.push  { background: rgba(74,122,96,0.15);  color:#4a7a60; border:1px solid rgba(74,122,96,0.3); }
.mc-badge.open  { background: rgba(255,214,0,0.10);  color:#ffd600; border:1px solid rgba(255,214,0,0.3); }

.mc-meta {
    display: flex;
    gap: 16px;
    margin-top: 8px;
    flex-wrap: wrap;
}
.mc-kv {
    display: flex;
    flex-direction: column;
    gap: 1px;
}
.mc-kv-label {
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.58rem;
    color: #2a5040;
    letter-spacing: 0.12em;
    text-transform: uppercase;
}
.mc-kv-value {
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.82rem;
    color: #c8e6d4;
}
.mc-pnl.pos { color: #00ff88 !important; }
.mc-pnl.neg { color: #ff3b5c !important; }
.mc-pnl.zero{ color: #4a7a60 !important; }
.mc-time {
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.62rem;
    color: #2a5040;
    margin-left: auto;
    white-space: nowrap;
}
</style>
""", unsafe_allow_html=True)

        tab2_logs['Net_Profit'] = tab2_logs.apply(calc_pnl, axis=1)
        tab2_logs['CLV_Pct']   = tab2_logs.apply(calc_clv, axis=1)

        st.markdown('<div class="gem-label">◈ POSITION LOG</div>', unsafe_allow_html=True)

        # ── Filter bar ────────────────────────────────────────────────────
        fc1, fc2 = st.columns([1, 3])
        with fc1:
            flt = st.selectbox("FILTER", ["Today", "Pending Results", "All Records"])
        with fc2:
            search_q = st.text_input("🔍 ค้นหาแมตช์", placeholder="พิมพ์ชื่อทีม...", label_visibility="collapsed")

        df2 = tab2_logs.copy()
        if flt == "Today":
            df2 = df2[df2['Time'].astype(str).str.contains(today_str, na=False)]
        elif flt == "Pending Results":
            df2 = df2[df2['Result'].astype(str).str.strip() == ""]
        if search_q.strip():
            df2 = df2[df2['Match'].astype(str).str.contains(search_q, case=False, na=False)]
        df2 = df2.sort_values('Time', ascending=False).reset_index(drop=True)

        if df2.empty:
            st.info("◈ ไม่พบรายการที่ตรงเงื่อนไข")
        else:
            st.markdown(f'<div class="gem-dim" style="margin-bottom:10px;">แสดง {len(df2)} รายการ</div>',
                        unsafe_allow_html=True)

            # ── Dialog function (popup modal) ─────────────────────────────
            # st.dialog ต้องนิยามนอก loop และรับ row data เข้าไป
            @st.dialog("◈ MATCH DETAIL", width="large")
            def show_match_dialog(row_data):
                mn        = row_data['match_name']
                target_d  = row_data['target']
                hdp_d     = row_data['hdp']
                odds_d    = row_data['odds']
                ev_d      = row_data['ev_pct']
                invest_d  = row_data['invest']
                result_d  = row_data['result']
                closing_d = row_data['closing']
                pnl_d     = row_data['net_pnl']
                rid       = row_data['row_id']
                time_d    = row_data['time_str']
                border_d  = row_data['border_col']
                status_d  = row_data['status_label']

                pnl_col = ("#00ff88" if pnl_d > 0
                           else ("#ff3b5c" if pnl_d < 0 else "#4a7a60"))

                # header inside dialog
                st.markdown(
                    f'<div style="border-left:3px solid {border_d};padding:10px 14px;'
                    f'background:#091520;border-radius:0 4px 4px 0;margin-bottom:14px;">'
                    f'<div style="font-family:\'Exo 2\',sans-serif;font-weight:700;'
                    f'font-size:1rem;color:#c8e6d4;">{mn}</div>'
                    f'<div style="font-family:\'Share Tech Mono\',monospace;font-size:0.68rem;'
                    f'color:{border_d};margin-top:3px;">{status_d} &nbsp;·&nbsp; {time_d}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

                det1, det2 = st.columns(2)

                # ── left: oracle metrics ──────────────────────────────────
                with det1:
                    st.markdown('<div class="gem-label">◈ ORACLE METRICS</div>',
                                unsafe_allow_html=True)
                    d1, d2, d3 = st.columns(3)
                    d1.metric("EV ตอนลง",  f"{ev_d:.2f}%")
                    d2.metric("Odds",       f"{odds_d:.2f}")
                    d3.metric("เงินลงทุน", f"฿{invest_d:,.0f}")

                    try:
                        clv_val = float(closing_d) if closing_d and float(closing_d) > 1.0 else None
                    except:
                        clv_val = None
                    if clv_val:
                        clv_pct = ((odds_d / clv_val) - 1.0) * 100
                        d4, d5 = st.columns(2)
                        d4.metric("Closing Odds", f"{clv_val:.2f}")
                        d5.metric("CLV", f"{clv_pct:+.2f}%",
                                  delta_color="normal" if clv_pct >= 0 else "inverse")

                    if result_d:
                        st.markdown('<div class="gem-label" style="margin-top:12px;">◈ FINAL RESULT</div>',
                                    unsafe_allow_html=True)
                        st.metric("สกอร์จริง", result_d)
                        st.markdown(
                            f'<div style="font-family:\'Share Tech Mono\';font-size:1.05rem;'
                            f'color:{pnl_col};margin-top:4px;">P&L: ฿{pnl_d:+,.2f}</div>',
                            unsafe_allow_html=True
                        )

                    st.markdown('<div class="gem-label" style="margin-top:12px;">◈ ORACLE CONTEXT</div>',
                                unsafe_allow_html=True)
                    mkt  = ("Asian Handicap (AH)"
                            if target_d in ["เจ้าบ้าน","ทีมเยือน"] else "Total Goals (O/U)")
                    role = ("[ทีมต่อ / Fav]" if target_d == "เจ้าบ้าน"
                            else "[ทีมรอง / Dog]" if target_d == "ทีมเยือน"
                            else target_d)
                    ev_flag = ("🟢 EV ดีมาก" if ev_d >= 25
                               else "🟡 EV ปานกลาง" if ev_d >= 10
                               else "🔴 EV ต่ำ")
                    st.markdown(
                        f'<div style="font-family:\'Share Tech Mono\';font-size:0.75rem;'
                        f'color:#4a7a60;line-height:2.0;">'
                        f'ตลาด: <span style="color:#c8e6d4;">{mkt}</span><br>'
                        f'บทบาท: <span style="color:#c8e6d4;">{role}</span><br>'
                        f'EV: <span style="color:#c8e6d4;">{ev_flag} ({ev_d:.1f}%)</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                    if result_d and pnl_d != 0:
                        ob  = "rgba(0,255,136,0.07)" if pnl_d > 0 else "rgba(255,59,92,0.07)"
                        oc  = "#00ff88" if pnl_d > 0 else "#ff3b5c"
                        otx = (f"✓ ระบบคาดถูก — EV {ev_d:.1f}% → กำไร ฿{pnl_d:,.0f}"
                               if pnl_d > 0
                               else f"✗ Variance — EV {ev_d:.1f}% แต่ขาดทุน ฿{abs(pnl_d):,.0f}")
                        st.markdown(
                            f'<div style="margin-top:10px;padding:10px 14px;background:{ob};'
                            f'border-left:3px solid {oc};border-radius:3px;'
                            f'font-family:\'Share Tech Mono\';font-size:0.75rem;color:{oc};">{otx}</div>',
                            unsafe_allow_html=True
                        )

                # ── right: update form ────────────────────────────────────
                with det2:
                    st.markdown('<div class="gem-label">◈ UPDATE RESULT</div>',
                                unsafe_allow_html=True)
                    try:
                        closing_default = float(closing_d) if closing_d and float(closing_d) > 0 else 0.0
                    except:
                        closing_default = 0.0

                    new_closing = st.number_input(
                        "Closing Odds",
                        min_value=0.0,
                        value=closing_default,
                        format="%.2f",
                        key=f"dlg_closing_{rid}"
                    )
                    new_result = st.text_input(
                        "Result (สกอร์ เช่น 2-1)",
                        value=result_d,
                        placeholder="H-A เช่น 2-1",
                        key=f"dlg_result_{rid}"
                    )
                    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

                    if st.button("💾  บันทึก", key=f"dlg_save_{rid}",
                                 use_container_width=True, type="primary"):
                        try:
                            supabase.table("investment_logs").update({
                                "Closing_Odds": float(new_closing),
                                "Result":       str(new_result).strip()
                            }).eq("id", rid).execute()
                            st.toast("✓ บันทึกเรียบร้อยแล้ว", icon="💾")
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")

            # ── Match Cards loop ──────────────────────────────────────────
            for idx, row in df2.iterrows():
                match_raw  = str(row.get('Match', ''))
                is_live    = '[LIVE' in match_raw.upper()
                match_name = (match_raw
                              .replace('[LIVE]', '').replace('[LIVE', '')
                              .strip().strip("'").rstrip("]").strip())

                target   = str(row.get('Target', '—'))
                hdp      = row.get('HDP', 0)
                odds     = float(row.get('Odds', 0))
                ev_pct   = float(row.get('EV_Pct', 0))
                invest   = float(row.get('Investment', 0))
                result   = str(row.get('Result', '')).strip()
                closing  = row.get('Closing_Odds', 0.0)
                net_pnl  = float(row.get('Net_Profit', 0.0))
                row_id   = row.get('id', idx)
                time_str = str(row.get('Time', ''))[:16]

                if is_live:
                    border_col = "#ff8c00"; status_label = "🟠 LIVE"
                elif not result:
                    border_col = "#ffd600"; status_label = "⏳ PENDING"
                elif net_pnl > 0:
                    border_col = "#00ff88"; status_label = "✅ WIN"
                elif net_pnl < 0:
                    border_col = "#ff3b5c"; status_label = "❌ LOSS"
                else:
                    border_col = "#4a7a60"; status_label = "➖ PUSH"

                pnl_display = f"฿{net_pnl:+,.0f}" if result else "—"
                pnl_color   = ("#00ff88" if net_pnl > 0
                               else ("#ff3b5c" if net_pnl < 0 else "#4a7a60"))

                # ── card HTML ─────────────────────────────────────────────
                st.markdown(
                    f'<div style="border-left:3px solid {border_col};'
                    f'background:#0d1e2e;border-radius:0 6px 6px 0;'
                    f'padding:14px 18px;margin-bottom:4px;">'
                    f'<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">'
                    f'<span style="font-family:\'Exo 2\',sans-serif;font-weight:600;'
                    f'font-size:0.95rem;color:#c8e6d4;flex:1;">'
                    f'{"🔴 " if is_live else ""}{match_name}</span>'
                    f'<span style="font-family:\'Share Tech Mono\',monospace;font-size:0.7rem;'
                    f'color:{border_col};">{status_label}</span>'
                    f'<span style="font-family:\'Share Tech Mono\',monospace;font-size:0.65rem;'
                    f'color:#2a5040;">{time_str}</span>'
                    f'</div>'
                    f'<div style="display:flex;gap:20px;margin-top:8px;flex-wrap:wrap;">'
                    f'<span style="font-family:\'Share Tech Mono\',monospace;font-size:0.78rem;color:#4a7a60;">'
                    f'<span style="font-size:0.6rem;letter-spacing:.1em;">TARGET</span><br>'
                    f'<span style="color:#c8e6d4;">{target}</span></span>'
                    f'<span style="font-family:\'Share Tech Mono\',monospace;font-size:0.78rem;color:#4a7a60;">'
                    f'<span style="font-size:0.6rem;letter-spacing:.1em;">LINE</span><br>'
                    f'<span style="color:#c8e6d4;">{hdp}</span></span>'
                    f'<span style="font-family:\'Share Tech Mono\',monospace;font-size:0.78rem;color:#4a7a60;">'
                    f'<span style="font-size:0.6rem;letter-spacing:.1em;">ODDS</span><br>'
                    f'<span style="color:#c8e6d4;">{odds:.2f}</span></span>'
                    f'<span style="font-family:\'Share Tech Mono\',monospace;font-size:0.78rem;color:#4a7a60;">'
                    f'<span style="font-size:0.6rem;letter-spacing:.1em;">EV</span><br>'
                    f'<span style="color:#c8e6d4;">{ev_pct:.1f}%</span></span>'
                    f'<span style="font-family:\'Share Tech Mono\',monospace;font-size:0.78rem;color:#4a7a60;">'
                    f'<span style="font-size:0.6rem;letter-spacing:.1em;">INVEST</span><br>'
                    f'<span style="color:#c8e6d4;">฿{invest:,.0f}</span></span>'
                    f'<span style="font-family:\'Share Tech Mono\',monospace;font-size:0.78rem;color:#4a7a60;">'
                    f'<span style="font-size:0.6rem;letter-spacing:.1em;">RESULT</span><br>'
                    f'<span style="color:#c8e6d4;">{result if result else "—"}</span></span>'
                    f'<span style="font-family:\'Share Tech Mono\',monospace;font-size:0.78rem;color:#4a7a60;">'
                    f'<span style="font-size:0.6rem;letter-spacing:.1em;">P&amp;L</span><br>'
                    f'<span style="color:{pnl_color};font-weight:600;">{pnl_display}</span></span>'
                    f'</div></div>',
                    unsafe_allow_html=True
                )

                # ── popup trigger button (flush ใต้การ์ด) ────────────────
                if st.button(
                    "📋  ดูรายละเอียด & กรอกผล",
                    key=f"open_dlg_{row_id}",
                    use_container_width=True
                ):
                    show_match_dialog({
                        'match_name':  match_name,
                        'target':      target,
                        'hdp':         hdp,
                        'odds':        odds,
                        'ev_pct':      ev_pct,
                        'invest':      invest,
                        'result':      result,
                        'closing':     closing,
                        'net_pnl':     net_pnl,
                        'row_id':      row_id,
                        'time_str':    time_str,
                        'border_col':  border_col,
                        'status_label':status_label,
                    })

                st.markdown('<div style="height:4px"></div>', unsafe_allow_html=True)

        # ── Quick refresh ─────────────────────────────────────────────────
        if st.button("↺  REFRESH ALL", use_container_width=True):
            st.rerun()



        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="gem-label">◈ PERFORMANCE DASHBOARD</div>', unsafe_allow_html=True)
        vf1, vf2 = st.columns(2)
        with vf1: tf2 = st.radio("PERIOD", ["All Time", "Today"], horizontal=True)
        with vf2: vm  = st.radio("VIEW",   ["All", "Pre-Match", "In-Play"], horizontal=True)

        tfl = (tab2_logs[tab2_logs['Time'].astype(str).str.contains(today_str, na=False)].copy()
               if tf2 == "Today" else tab2_logs.copy())
        if vm == "In-Play":    fl = tfl[tfl['Match'].str.contains(r'\[LIVE\]', na=False, case=False)]
        elif vm == "Pre-Match": fl = tfl[~tfl['Match'].str.contains(r'\[LIVE\]', na=False, case=False)]
        else: fl = tfl
        il = fl[fl['Investment'] > 0]

        max_drawdown = mdd_pct = 0.0
        if not fl.empty:
            dd_df = fl.sort_values('Time').copy()
            dd_df['Cum'] = dd_df['Net_Profit'].cumsum()
            drawdown = dd_df['Cum'] - dd_df['Cum'].cummax()
            max_drawdown = drawdown.min()
            if total_bankroll > 0: mdd_pct = (max_drawdown / total_bankroll) * 100

        v_clv = il[il['Closing_Odds'] > 1.0]
        beating_clv_pct = (
            len(v_clv[v_clv['CLV_Pct'] > 0]) / len(v_clv) * 100
            if not v_clv.empty else 0.0
        )

        st.markdown('<div class="gem-label" style="margin-top:14px;">◈ PORTFOLIO OVERVIEW</div>', unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("NET PROFIT", f"฿{fl['Net_Profit'].sum():,.0f}")
        m2.metric("DEPLOYED",   f"฿{il['Investment'].sum():,.0f}")
        m3.metric("WIN RATE",   f"{(len(il[il['Net_Profit']>0])/len(il)*100 if not il.empty else 0):.1f}%")
        m4.metric("ROI",        f"{(fl['Net_Profit'].sum()/il['Investment'].sum()*100 if not il.empty and il['Investment'].sum()>0 else 0):.2f}%")

        st.markdown('<div class="gem-label" style="margin-top:14px;">◈ INSTITUTIONAL METRICS</div>', unsafe_allow_html=True)
        n1, n2, n3 = st.columns(3)
        n1.metric("MAX DRAWDOWN",  f"฿{max_drawdown:,.0f}", f"{mdd_pct:.2f}% of Bankroll", delta_color="inverse")
        n2.metric("AVG CLV",       f"{v_clv['CLV_Pct'].mean():.2f}%" if not v_clv.empty else "—")
        n3.metric("% BEATING CLV", f"{beating_clv_pct:.1f}%"         if not v_clv.empty else "—")

        if not fl.empty:
            ls = fl.sort_values('Time').copy()
            ls['Cum'] = ls['Net_Profit'].cumsum()
            lc = '#ff8c00' if vm == "In-Play" else ('#00b4ff' if vm == "Pre-Match" else '#00ff88')
            fc = ("rgba(255,140,0,0.12)" if vm == "In-Play"
                  else ("rgba(0,180,255,0.12)" if vm == "Pre-Match" else "rgba(0,255,136,0.12)"))
            fig_e = go.Figure(go.Scatter(x=ls['Time'], y=ls['Cum'], mode='lines', fill='tozeroy',
                                          line=dict(color=lc, width=2), fillcolor=fc))
            neon_layout(fig_e, f"EQUITY CURVE — {vm.upper()}")
            st.plotly_chart(fig_e, use_container_width=True)

            bc1, bc2 = st.columns(2)
            with bc1:
                st.markdown('<div class="gem-dim" style="margin-bottom:4px;">P&L BY TARGET</div>', unsafe_allow_html=True)
                tgt   = ls.groupby('Target')['Net_Profit'].sum()
                fig_t = go.Figure(go.Bar(x=tgt.index, y=tgt.values,
                                          marker_color=lc, marker_line_color='rgba(0,0,0,0)'))
                neon_layout(fig_t); fig_t.update_layout(height=210, margin=dict(l=8,r=8,t=10,b=8))
                st.plotly_chart(fig_t, use_container_width=True)
            with bc2:
                st.markdown('<div class="gem-dim" style="margin-bottom:4px;">WIN RATE BY ODDS BRACKET</div>', unsafe_allow_html=True)
                ls['OB'] = pd.cut(ls['Odds'], bins=[0,1.8,2.0,2.2,5.0],
                                   labels=['<1.80','1.80-2.00','2.00-2.20','>2.20'])
                wr = (ls[ls['Net_Profit']>0].groupby('OB', observed=False).size()
                      / ls.groupby('OB', observed=False).size() * 100).fillna(0)
                fig_w = go.Figure(go.Bar(x=wr.index.astype(str), y=wr.values,
                                          marker_color=lc, marker_line_color='rgba(0,0,0,0)'))
                neon_layout(fig_w); fig_w.update_layout(height=210, margin=dict(l=8,r=8,t=10,b=8))
                st.plotly_chart(fig_w, use_container_width=True)

        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="gem-label">◈ ORACLE LEARNING ENGINE</div>', unsafe_allow_html=True)
        # [Fix 1] กรอง push/void (Net_Profit==0 และ Result มีข้อมูล) ออก
        # push ไม่ได้บอกว่าระบบถูกหรือผิด ไม่ควรนำมาเรียนรู้
        if 'Net_Profit' in tab2_logs.columns:
            settled = tab2_logs[tab2_logs['Result'].astype(str).str.strip() != ""].copy()
            comp    = settled[settled['Net_Profit'] != 0].copy()
        else:
            comp = pd.DataFrame()

        if len(comp) > 0:
            lm = st.radio("LEARNING MODE",
                          ["🔴 Defensive (losses)", "🟢 Offensive (wins)", "⚪ Mixed"],
                          horizontal=True)
            if "🔴" in lm:
                tl        = comp[comp['Net_Profit'] < 0].copy()
                task_mode = "Defensive"
                pfx       = "GEM_DEF_"
            elif "🟢" in lm:
                tl        = comp[comp['Net_Profit'] > 0].copy()
                task_mode = "Offensive"
                pfx       = "GEM_OFF_"
            else:
                tl        = comp.copy()
                task_mode = "Mixed"
                pfx       = "GEM_MIX_"

            if len(tl) > 0:
                # [Fix 2] แสดง warning ถ้าข้อมูลน้อยกว่า 3 ไม้
                if len(tl) < 3:
                    st.warning(f"⚠️ มีเพียง {len(tl)} records — AI อาจสร้างกฎจากข้อมูลน้อยเกินไป แนะนำให้มีอย่างน้อย 3 ไม้")
                total_pnl   = tl['Net_Profit'].sum()
                avg_ev      = tl['EV_Pct'].mean() if 'EV_Pct' in tl.columns else 0
                ah_count    = len(tl[tl['Target'].isin(['เจ้าบ้าน','ทีมเยือน'])])
                ou_count    = len(tl[tl['Target'].isin(['สูง','ต่ำ'])])
                ms1, ms2, ms3, ms4 = st.columns(4)
                ms1.metric("Records", f"{len(tl)}")
                ms2.metric("Total P&L", f"฿{total_pnl:,.0f}")
                ms3.metric("AH / O/U", f"{ah_count} / {ou_count}")
                ms4.metric("Avg EV", f"{avg_ev:.1f}%")

                st.info(f"◈ {len(tl)} records — ติ๊กเลือกแมตช์ที่ต้องการให้ Oracle เรียนรู้")
                tl_display = tl.copy()
                tl_display.insert(0, "Analyze", False)
                sel = st.data_editor(
                    tl_display[['Analyze','Time','Match','HDP','Target','Odds','Result','Net_Profit','EV_Pct']],
                    column_config={
                        "Analyze":    st.column_config.CheckboxColumn("✓", default=False),
                        "Net_Profit": st.column_config.NumberColumn("P&L", format="%.2f"),
                        "EV_Pct":     st.column_config.NumberColumn("EV%", format="%.1f"),
                    },
                    hide_index=True, use_container_width=True, key="debrief_editor"
                )
                picked = sel[sel['Analyze'] == True]

                if st.button("⚡  EXECUTE ORACLE LEARNING", use_container_width=True, type="primary"):
                    if picked.empty:
                        st.warning("⚠️ ติ๊กเลือกอย่างน้อย 1 รายการก่อนครับ")
                    elif not api_key:
                        st.error("⚠️ API Key missing")
                    else:
                        with st.spinner(f"Oracle กำลังเรียนรู้จาก {len(picked)} แมตช์..."):

                            # ── เตรียมข้อมูล ──────────────────────────────────────
                            csv_s = picked[[
                                'Time','Match','HDP','Target','Odds',
                                'Result','Net_Profit','EV_Pct'
                            ]].to_csv(index=False)

                            # ── สถิติเพิ่มเติม ────────────────────────────────────
                            p_pnl     = picked['Net_Profit'].sum()
                            p_wr      = len(picked[picked['Net_Profit'] > 0]) / len(picked) * 100
                            p_ah      = picked[picked['Target'].isin(['เจ้าบ้าน','ทีมเยือน'])]
                            p_ou      = picked[picked['Target'].isin(['สูง','ต่ำ'])]
                            p_fav     = picked[picked['Target'] == 'เจ้าบ้าน']
                            p_dog     = picked[picked['Target'] == 'ทีมเยือน']
                            p_over    = picked[picked['Target'] == 'สูง']
                            p_under   = picked[picked['Target'] == 'ต่ำ']
                            stats_ctx = (
                                f"สรุปชุดข้อมูล: {len(picked)} บิล | "
                                f"P&L รวม ฿{p_pnl:,.0f} | "
                                f"Win Rate {p_wr:.0f}% | "
                                f"AH {len(p_ah)} บิล (Fav={len(p_fav)} Dog={len(p_dog)}) | "
                                f"O/U {len(p_ou)} บิล (Over={len(p_over)} Under={len(p_under)})"
                            )

                            # ── โหลด GEM RULES ปัจจุบัน ──────────────────────────
                            try:
                                rr = supabase.table("gem_knowledge").select(
                                    "rule_id,category,rule_text"
                                ).eq("is_active", True).execute()
                                rs = "\n".join([
                                    f"[{item['rule_id']} - {item['category']}] {item['rule_text']}"
                                    for item in (rr.data or [])
                                ])
                            except:
                                rs = "ไม่สามารถโหลด GEM RULES ได้"

                            # ── task instruction ตาม mode ─────────────────────────
                            if task_mode == "Defensive":
                                task_detail = """ภารกิจ: POST-MORTEM ANALYSIS
1. วิเคราะห์สาเหตุที่แท้จริงของการขาดทุน — โครงสร้างราคา, เส้น, ประเภทเป้าหมาย, EV range
2. ค้นหา pattern ที่ซ้ำกัน (เช่น ขาดทุนบ่อยในเส้นเดิม หรือเป้าหมายเดิม)
3. เปรียบเทียบกับ GEM RULES ปัจจุบัน — กฎใดควรมีอยู่แล้วแต่ไม่ได้ป้องกัน?
4. สร้างกฎป้องกัน (Defensive Rules) เชิงเทคนิค ห้ามระบุชื่อทีมหรือลีก
5. ถ้า case น้อยกว่า 3 ไม้ → อาจเป็น variance ปกติ แนะนำเฝ้าดูต่อ
6. ระบุ [FATAL] ถ้าควรห้ามเด็ดขาด หรือ [WARNING] ถ้าแค่ให้ระวัง"""
                                severity = "FATAL หรือ WARNING"
                                rule_type = "Defensive 🔴"

                            elif task_mode == "Offensive":
                                task_detail = """ภารกิจ: SUCCESS PATTERN ANALYSIS
1. หา pattern ที่ทำให้ชนะตลาด — EV range ที่ดีที่สุด, เส้น, ประเภทเป้าหมาย
2. ระบุ EV threshold ที่ให้ผลดีที่สุดจากข้อมูลจริง
3. สร้างกฎเชิงบวก (Offensive Rules) ที่บอกว่า "เพิ่มความมั่นใจเมื่อ..."
4. อาจสร้างกฎที่ผ่อนปรนกฎ Defensive เดิมได้ถ้ามีหลักฐานชัดเจน
5. หา Fav/Dog และ Over/Under pattern ว่าฝั่งไหนชนะสม่ำเสมอกว่า
6. ระบุ [BOOST] สำหรับกฎที่เพิ่ม confidence หรือ [EXCEPTION] ที่ยกเว้นกฎเดิม"""
                                severity = "BOOST หรือ EXCEPTION"
                                rule_type = "Offensive 🟢"

                            else:
                                task_detail = """ภารกิจ: MIXED ANALYSIS (เปรียบเทียบชนะ vs แพ้)
1. แยกบิลชนะ vs บิลแพ้ แล้วหาความแตกต่างของ pattern อย่างละเอียด
2. ตรวจ AH vs O/U แยกกัน — ตลาดไหนทำผลดีกว่า?
3. ตรวจ Fav vs Dog — ฝั่งไหนให้ผลที่ดีกว่าในข้อมูลชุดนี้?
4. ตรวจ EV range — บิล EV สูง vs ต่ำ ให้ผลต่างกันแค่ไหน?
5. สร้างทั้งกฎป้องกัน (Defensive) สำหรับรูปแบบที่แพ้
   และกฎเสริมพลัง (Offensive) สำหรับรูปแบบที่ชนะ
6. ประเมินว่ากฎเดิมใดในระบบควรปรับ, เพิ่ม, หรือลบ"""
                                severity = "FATAL / WARNING / BOOST / EXCEPTION"
                                rule_type = "Mixed ⚪"

                            # ── build learning prompt ─────────────────────────────
                            pd_prompt = f"""คุณคือ Chief Risk Officer (CRO) และ Quant Analyst ของกองทุน Sports Betting
ภารกิจ: วิเคราะห์ประวัติการลงทุนและพัฒนา GEM RULES ให้แม่นยำขึ้น

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 CASE STUDY DATA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{csv_s}

📊 สถิติชุดข้อมูล: {stats_ctx}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{task_detail}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📖 GEM RULES ปัจจุบัน (ห้ามซ้ำกฎเดิม)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{rs if rs else "ยังไม่มีกฎในระบบ — สร้างได้เลย"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 คำสั่งบังคับสำหรับการสร้างกฎ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. MARKET LABEL (บังคับ)
   ทุกกฎต้องระบุตลาดใน category:
   [AH]  = Asian Handicap เท่านั้น
   [OU]  = Over/Under เท่านั้น
   [ALL] = ทุกตลาด
   ตัวอย่าง: "Risk Management [AH]", "Momentum [ALL]"

2. RULE FORMAT (บังคับ)
   เริ่มด้วย [{severity}] แล้วตามด้วยเงื่อนไข IF...THEN ที่ชัดเจน
   ตัวอย่าง:
   "[WARNING] ถ้า EV < 15% และเส้น > 1.0 ใน Pre-Match → ลด confidence"
   "[FATAL] ถ้า odds < 1.50 และ Dog → ห้ามลงเด็ดขาด"
   "[BOOST] ถ้า Steam + EV > 20% → เพิ่ม confidence level 1 ขั้น"

3. MARKET ISOLATION (บังคับ)
   กฎ AH ห้ามพาด O/U logic และในทางกลับกัน

4. QUALITY CONTROL
   ห้ามระบุชื่อทีม ลีก นักเตะ
   กฎต้องใช้ได้กว้างในหลายแมตช์
   ห้ามซ้ำกฎที่มีอยู่แล้ว
   สร้างได้สูงสุด 3 กฎต่อ session

5. SEVERITY DEFINITIONS
   FATAL   = ห้ามลงเด็ดขาด ไม่ว่า EV จะสูงแค่ไหน
   WARNING = ระวัง ลด impact_score แต่ยังลงได้ถ้า EV แข็งแกร่ง
   BOOST   = เพิ่มความมั่นใจ เพิ่ม confidence_level
   EXCEPTION = ยกเว้นกฎ Defensive เดิมได้ถ้าตรงเงื่อนไขนี้

6. ถ้าข้อมูลน้อยกว่า 3 บิล หรือเป็น variance → ส่ง new_rules_to_add: []

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📤 ตอบกลับ JSON (ภาษาไทย) เท่านั้น:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{{
  "analysis_summary": "สรุป: pattern ที่พบ | สาเหตุหลัก | ข้อสังเกต AH vs OU | Fav vs Dog",
  "new_rules_to_add": [
    {{
      "rule_text": "[FATAL/WARNING/BOOST/EXCEPTION] IF เงื่อนไข THEN action",
      "category": "Risk Management [AH]"
    }}
  ]
}}"""

                            try:
                                m = genai.GenerativeModel('models/gemma-4-31b-it')
                                d = safe_json_loads(m.generate_content(pd_prompt).text)
                                if d:
                                    st.success("✅ Oracle Learning เสร็จสิ้น")
                                    st.info(f"**📊 Analysis:** {d.get('analysis_summary','—')}")
                                    nr = d.get("new_rules_to_add", [])
                                    if nr:
                                        pl  = []
                                        bid = datetime.now(timezone(timedelta(hours=7))).strftime("%Y%m%d_%H%M")
                                        st.markdown(f'<div class="gem-label">◈ NEW RULES — {rule_type}</div>', unsafe_allow_html=True)
                                        for i, rule in enumerate(nr):
                                            rid = f"{pfx}{bid}_{i+1}"
                                            pl.append({
                                                "rule_id":   rid,
                                                "rule_text": rule.get("rule_text", ""),
                                                "category":  rule.get("category", "AI Learning"),
                                                "is_active": True   # [Fix 3] บังคับให้ active ทันทีหลัง insert
                                            })
                                            c2 = ("#ff3b5c" if "DEF" in pfx
                                                  else ("#00ff88" if "OFF" in pfx else "#ffd600"))
                                            st.markdown(
                                                f'<div class="gem-panel" style="border-top:2px solid {c2};">'
                                                f'<span style="font-family:\'Share Tech Mono\';font-size:0.68rem;color:{c2};">'
                                                f'[{rid}] {rule.get("category","")}</span><br>'
                                                f'<span style="color:#c8e6d4;">{rule.get("rule_text","")}</span></div>',
                                                unsafe_allow_html=True
                                            )
                                        supabase.table("gem_knowledge").insert(pl).execute()
                                        load_gem_rules.clear()
                                        st.balloons()
                                        st.success(f"✅ {len(pl)} กฎใหม่ sync ขึ้น Cloud แล้ว (is_active=True — พร้อมใช้งานทันที)")
                                    else:
                                        st.info("◈ Oracle ประเมินว่าเป็น variance ปกติ — ไม่จำเป็นต้องสร้างกฎใหม่")
                                else:
                                    st.error("⚠️ AI ตอบกลับผิดรูปแบบ JSON — ลองใหม่อีกครั้ง")
                            except Exception as e:
                                st.error(f"❌ Error: {e}")
            else:
                st.info("ไม่มีข้อมูลในหมวดหมู่นี้")
        else:
            st.info("◈ ยังไม่มีผลลัพธ์ที่ทราบแล้ว (push/void ถูกตัดออกแล้ว) — กรอก Result ในตาราง Position Log ก่อนครับ")

# ╔══════════════╗
# ║  TAB 3       ║
# ╚══════════════╝
with tab3:
    st.markdown('<div class="gem-label">◈ LIVE SNIPER COMMAND CENTER</div>', unsafe_allow_html=True)

    with st.expander("📷 AI LIVE VISION — Multi-image scan"):
        if not api_key:
            st.markdown('<p class="gem-warn">▸ API Key required</p>', unsafe_allow_html=True)
        else:
            limgs = st.file_uploader("Upload live screenshots", type=['png','jpg'], accept_multiple_files=True)
            if limgs and st.button("⚡ EXTRACT LIVE DATA", use_container_width=True):
                with st.spinner("Scanning..."):
                    try:
                        imgs  = [Image.open(f) for f in limgs]
                        model = genai.GenerativeModel('models/gemma-4-31b-it')
                        pl = ('สกัดข้อมูลฟุตบอล LIVE จากภาพ ตอบ JSON เท่านั้น:\n'
                              '- match_name, current_min (int), current_score_h (int), current_score_a (int)\n'
                              '- rc_h (bool), rc_a (bool)\n'
                              '- live_hdp (float แปลง x/y→ทศนิยม), live_hdp_h, live_hdp_a\n'
                              '- live_ou (float), live_ou_over, live_ou_under\n'
                              '{"match_name":"","current_min":0,"current_score_h":0,"current_score_a":0,'
                              '"rc_h":false,"rc_a":false,"live_hdp":0.0,"live_hdp_h":0.0,"live_hdp_a":0.0,'
                              '"live_ou":0.0,"live_ou_over":0.0,"live_ou_under":0.0}')
                        d = safe_json_loads(model.generate_content([pl] + imgs).text)
                        for k, v in d.items():
                            if k == 'match_name':       st.session_state['match_name_live'] = str(v)
                            elif k == 'current_score_h':
                                try: st.session_state['lh_s_input'] = int(v)
                                except: pass
                            elif k == 'current_score_a':
                                try: st.session_state['la_s_input'] = int(v)
                                except: pass
                            elif k == 'rc_h': st.session_state['rc_h_chk'] = bool(v)
                            elif k == 'rc_a': st.session_state['rc_a_chk'] = bool(v)
                            elif k == 'current_min':
                                try: st.session_state['current_min'] = int(v)
                                except: pass
                            else:
                                try: st.session_state[k] = float(v)
                                except: st.session_state[k] = 0.0
                        st.toast("✅ สกัดข้อมูล Live สำเร็จ!", icon="🎯")
                        time.sleep(1); st.rerun()
                    except Exception as e:
                        st.error(f"⚠️ พลาด: {e}")

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    default_live_mn = st.session_state.get('match_name_live', st.session_state.get('match_name', ''))
    live_mn = st.text_input("MATCH (Live)", value=default_live_mn, key="match_name_live_input")

    gl1, gl2 = st.columns(2)
    with gl1:
        st.markdown('<div class="gem-label">◈ LIVE MATCH STATE</div>', unsafe_allow_html=True)
        s1, s2 = st.columns(2)
        csh = s1.number_input("HOME SCORE", min_value=0,
                               value=st.session_state.get('lh_s_input', 0), key="lh_s_input")
        rch = s2.checkbox("🟥 HOME RED",
                           value=st.session_state.get('rc_h_chk', False), key="rc_h_chk")
        s3, s4 = st.columns(2)
        csa = s3.number_input("AWAY SCORE", min_value=0,
                               value=st.session_state.get('la_s_input', 0), key="la_s_input")
        rca = s4.checkbox("🟥 AWAY RED",
                           value=st.session_state.get('rc_a_chk', False), key="rc_a_chk")
        cmin = st.slider("MINUTE", 0, 120, st.session_state.get('current_min', 45))
    with gl2:
        st.markdown('<div class="gem-label">◈ PRE-MATCH REFERENCE</div>', unsafe_allow_html=True)
        preh  = st.number_input("HOME (open)", value=st.session_state.get('pre_h', 2.0),  format="%.2f", key="pre_h")
        pred  = st.number_input("DRAW (open)", value=st.session_state.get('pre_d', 3.0),  format="%.2f", key="pre_d")
        prea  = st.number_input("AWAY (open)", value=st.session_state.get('pre_a', 3.0),  format="%.2f", key="pre_a")
        preou = st.number_input("O/U (open)",  value=st.session_state.get('pre_ou', 2.5), format="%.2f", step=0.25, key="pre_ou")

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="gem-label">◈ LIVE MARKET FEED</div>', unsafe_allow_html=True)
    lm1, lm2 = st.columns(2)
    with lm1:
        st.markdown('<div class="gem-dim" style="margin-bottom:4px;">── HANDICAP ──</div>', unsafe_allow_html=True)
        bh1, bh2, bh3 = st.columns([1, 2, 1])
        bh1.button("◀ -0.25", key="h_sub", on_click=adj_hdp, args=(-0.25,))
        lhdp = bh2.number_input("HDP", value=st.session_state['live_hdp'], step=0.25,
                                  key="live_hdp", label_visibility="collapsed", format="%.2f")
        bh3.button("▶ +0.25", key="h_add", on_click=adj_hdp, args=(0.25,))
        hw1, hw2_ = st.columns(2)
        lhdph = hw1.number_input("HOME",  value=st.session_state.get('live_hdp_h', 0.9), format="%.2f", key="live_hdp_h")
        lhdpa = hw2_.number_input("AWAY", value=st.session_state.get('live_hdp_a', 0.9), format="%.2f", key="live_hdp_a")
    with lm2:
        st.markdown('<div class="gem-dim" style="margin-bottom:4px;">── TOTAL GOALS ──</div>', unsafe_allow_html=True)
        bo1, bo2, bo3 = st.columns([1, 2, 1])
        bo1.button("◀ -0.25", key="o_sub", on_click=adj_ou, args=(-0.25,))
        lou = bo2.number_input("O/U", value=st.session_state['live_ou'], step=0.25,
                                key="live_ou", label_visibility="collapsed", format="%.2f")
        bo3.button("▶ +0.25", key="o_add", on_click=adj_ou, args=(0.25,))
        ow1, ow2 = st.columns(2)
        louov = ow1.number_input("OVER",  value=st.session_state.get('live_ou_over',  0.9), format="%.2f", key="live_ou_over")
        louun = ow2.number_input("UNDER", value=st.session_state.get('live_ou_under', 0.9), format="%.2f", key="live_ou_under")

    line_movement_live = st.selectbox(
        "กระแสราคา (Live Line Movement)",
        ["➖ Stable (นิ่ง/ปกติ)", "🔥 Steam (ราคาไหลลง/เงินเข้า)", "❄️ Drift (ราคาไหลขึ้น/เงินออก)"],
        key="lm_live"
    )

    ac1, ac2 = st.columns([4, 1])
    snap = ac1.button("⚡  ENGAGE SNIPER", use_container_width=True, type="primary")
    ac2.button("↺ RESET", use_container_width=True, on_click=clear_inplay_data)

    if snap:
        # [แก้ไข ข้อจำกัด #3] ตรวจสอบ input Live ก่อนคำนวณ
        live_errors = []
        if preh <= 0 or pred <= 0 or prea <= 0:
            live_errors.append("กรุณากรอก **ราคาเปิด 1X2** (Home / Draw / Away) ให้ครบ")
        if fix(louov) <= 1.0 or fix(louun) <= 1.0:
            live_errors.append("กรุณากรอก **น้ำ O/U Live** (Over / Under) ให้ครบ")
        if fix(lhdph) <= 1.0 or fix(lhdpa) <= 1.0:
            live_errors.append("กรุณากรอก **น้ำ AH Live** (Home / Away) ให้ครบ")
        if abs(lhdp) not in [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5,
                               1.75, 2.0, 2.25, 2.5]:
            live_errors.append(
                f"⚠️ เส้น AH Live **{lhdp}** ไม่รองรับ — "
                "ใช้ได้เฉพาะ 0 / 0.25 / 0.5 / 0.75 / 1.0 / 1.25 / 1.5 / 1.75 / 2.0 / 2.25 / 2.5"
            )
        if live_errors:
            for err in live_errors:
                st.error(f"❌ {err}")
            st.stop()
        ml = max(90 - cmin, 1)

        hw2l, hw1l, dexl, aw1l, aw2l, ptl = calc_dixon_coles_matrix(
            lph, lpd, lpa, lou, fix(louov), fix(louun),
            ch=csh, ca=csa, ml=ml, rch=rch, rca=rca,
            xg_h=st.session_state.get('xg_h_val', 0.0),
            xg_a=st.session_state.get('xg_a_val', 0.0),
            xg_weight=0.5
        )

        fvl   = lph >= lpa
        evhl  = ev_ah(lhdp, hw2l, hw1l, dexl, aw1l, aw2l, fix(lhdph), fvl)
        # [Calibration v2] Dynamic HDBA สำหรับ Live ใช้ hdba_val เดียวกัน
        hdba_dynamic_live = lpd * fix(lhdpa) * hdba_val
        eval_ = ev_ah(lhdp, aw2l, aw1l, dexl, hw1l, hw2l, fix(lhdpa), not fvl) - hdba_dynamic_live
        evol  = ev_ou(lou, ptl, fix(louov), True)
        evul  = ev_ou(lou, ptl, fix(louun), False)

        bav = max(evhl, eval_); tah = "เจ้าบ้าน" if evhl > eval_ else "ทีมเยือน"
        bov = max(evol, evul);  tou = "สูง" if evol > evul else "ต่ำ"

        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
        gg1, gg2 = st.columns(2)
        with gg1: st.plotly_chart(ev_gauge(bav, f"AH: {tah}", live_ah_thr), use_container_width=True)
        with gg2: st.plotly_chart(ev_gauge(bov, f"O/U: {tou}", live_ou_thr), use_container_width=True)

        valid_bets_live = []
        if bav >= live_ah_lim:
            valid_bets_live.append({"n": tah, "ev": bav, "hdp": lhdp,
                                    "odds": fix(lhdph) if tah == "เจ้าบ้าน" else fix(lhdpa)})
        if bov >= live_ou_lim:
            valid_bets_live.append({"n": tou, "ev": bov, "hdp": lou,
                                    "odds": fix(louov) if tou == "สูง" else fix(louun)})

        if valid_bets_live:
            with st.spinner("◈ SNIPER ORACLE PROCESSING..."):
                for tl2 in valid_bets_live:
                    tf2 = None
                    if tl2['n'] == "เจ้าบ้าน":  tf2 = fvl
                    elif tl2['n'] == "ทีมเยือน": tf2 = not fvl
                    live_mn_val = st.session_state.get('match_name_live_input', live_mn)
                    al  = ai_engine(
                        live_mn_val, tl2['n'], tl2['ev'], tl2['hdp'], tl2['odds'],
                        live=True, current_min=cmin, score=f"{csh}-{csa}",
                        thr=live_ah_lim, fav=tf2, line_movement=line_movement_live
                    )
                    nlev = tl2['ev'] + al.get('impact_score', 0)

                    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="gem-label">◈ ORACLE VERDICT : {tl2["n"]}</div>', unsafe_allow_html=True)
                    lc1, lc2, lc3 = st.columns(3)
                    lc1.metric("LIVE EV",    f"{tl2['ev']*100:.2f}%")
                    lc2.metric("ORACLE ADJ", f"{al.get('impact_score',0)*100:.2f}%")
                    lc3.metric("NET EV",     f"{nlev*100:.2f}%")

                    with st.expander(f"◈ LIVE ANALYSIS : {tl2['n']}", expanded=True):
                        st.success(f"**PROS:** {al.get('pros_analysis','—')}")
                        st.error(f"**RISK:** {al.get('cons_analysis','—')}")
                        st.info(f"**RULES:** {al.get('rule_triggered','None')}")

                    lim = live_ah_lim if tl2['n'] in ["เจ้าบ้าน","ทีมเยือน"] else live_ou_lim
                    if al.get('final_decision', False) and nlev >= lim:
                        st.balloons()
                        st.markdown(
                            f'<div class="gem-panel" style="border-top:2px solid #ff3b5c;border-left:2px solid #ff3b5c;">'
                            f'<div class="gem-label" style="border-color:#ff3b5c;color:#ff3b5c;">◈ SNIPER APPROVED — TARGET LOCKED</div>'
                            f'<p style="color:#ff3b5c;font-family:\'Share Tech Mono\';">TARGET: {tl2["n"]} | NET EV: {nlev*100:.2f}%</p>'
                            f'<p style="color:#c8e6d4;">{al.get("final_comment","")}</p></div>',
                            unsafe_allow_html=True
                        )
                        dutch_factor = 0.60 if len(valid_bets_live) == 2 else 1.00
                        kelly_opt_live = nlev / (tl2['odds'] - 1)
                        inv = min(kelly_opt_live * kelly_fraction * dutch_factor,
                                  max_bet_cap / 100.0) * total_bankroll
                        inv = max(inv, 0.0)
                        if len(valid_bets_live) == 2:
                            st.warning("⚠️ Dutching 2 markets: exposure ลดเหลือ 60% ต่อตลาด")
                        tz2 = timezone(timedelta(hours=7))
                        save_db([{
                            "Time": datetime.now(tz2).strftime("%Y-%m-%d %H:%M:%S"),
                            "Match": f"[LIVE {cmin}'] {live_mn_val if live_mn_val else 'Live Match'}",
                            "HDP": tl2['hdp'], "Target": tl2['n'],
                            "EV_Pct": round(nlev * 100, 2), "Investment": round(inv, 2),
                            "Odds": tl2['odds'], "Closing_Odds": 0.0, "Result": ""
                        }])
                        st.toast("✅ SNIPER DEPLOYED: บันทึกข้อมูลแล้ว", icon="🚀")
                    else:
                        st.markdown(
                            f'<div class="gem-panel" style="border-top:2px solid #ffd600;">'
                            f'<div class="gem-label" style="border-color:#ffd600;color:#ffd600;">◈ ORACLE STAND DOWN</div>'
                            f'<p class="gem-warn">{al.get("final_comment","")}</p></div>',
                            unsafe_allow_html=True
                        )
        else:
            st.markdown(
                f'<div class="gem-panel" style="border-top:2px solid #0f2535;">'
                f'<div class="gem-label">◈ WITHIN NORMAL RANGE</div>'
                f'<p class="gem-dim">AH {bav*100:.2f}% (min {live_ah_thr}%) | O/U {bov*100:.2f}% (min {live_ou_thr}%)</p></div>',
                unsafe_allow_html=True
            )

# ╔══════════════╗
# ║  TAB 4       ║
# ╚══════════════╝
with tab4:
    st.markdown('<div class="gem-label">◈ BRIER SCORE ACCURACY ENGINE</div>', unsafe_allow_html=True)
    st.markdown(
        '<p style="font-family:\'Rajdhani\';font-size:0.85rem;color:#4a7a60;">'
        'Compares GEM estimates vs bookmaker implied probabilities. Lower = More Accurate.</p>',
        unsafe_allow_html=True
    )

    t4l = load_logs()
    if t4l is not None and not t4l.empty:
        t4l['Net_Profit'] = t4l.apply(calc_pnl, axis=1)
        fin = t4l[t4l['Result'].astype(str).str.strip() != ""].copy()

        if not fin.empty:
            def score_row(row):
                try:
                    inv, net, odds = float(row['Investment']), float(row['Net_Profit']), float(row['Odds'])
                    if inv <= 0: return np.nan
                    mw = inv * (odds - 1)
                    if net >= mw * 0.95:   return 1.0
                    elif net > 0:           return 0.75
                    elif net == 0:          return 0.50
                    elif net <= -inv * 0.95: return 0.0
                    elif net < 0:           return 0.25
                    return np.nan
                except:
                    return np.nan

            fin['Actual'] = fin.apply(score_row, axis=1)
            fin = fin.dropna(subset=['Actual'])

            if not fin.empty:
                fin['BP'] = (1 / fin['Odds']).clip(0, 1)
                rp        = (((fin['EV_Pct'] / 100) + 1) / fin['Odds']).clip(0, 1)
                fin['OP'] = ((rp * 0.85) + (fin['BP'] * 0.15)).clip(0, 1)
                fin['OE'] = (fin['OP'] - fin['Actual']) ** 2
                fin['BE'] = (fin['BP'] - fin['Actual']) ** 2

                ao   = fin['OE'].mean()
                ab   = fin['BE'].mean()
                diff = ab - ao

                st.markdown(f'<div class="gem-label">◈ ACCURACY — {len(fin)} SETTLED BETS</div>', unsafe_allow_html=True)
                rc1, rc2, rc3 = st.columns(3)
                rc1.metric("GEM SCORE",    f"{ao:.4f}", f"{-diff:.4f} vs bookie", delta_color="inverse")
                rc2.metric("BOOKIE SCORE",  f"{ab:.4f}")
                col3 = "#00ff88" if ao < ab else "#ff3b5c"
                lab3 = "▲ GEM BEATS MARKET" if ao < ab else "▼ CALIBRATION NEEDED"
                rc3.markdown(
                    f'<div class="gem-panel" style="border-top:2px solid {col3};text-align:center;padding:10px;">'
                    f'<span style="font-family:\'Share Tech Mono\';color:{col3};font-size:0.78rem;">{lab3}</span></div>',
                    unsafe_allow_html=True
                )

                st.markdown('<div class="gem-label" style="margin-top:14px;">◈ CUMULATIVE ERROR</div>', unsafe_allow_html=True)
                fin = fin.sort_values('Time').reset_index(drop=True)
                fin['CumO'] = fin['OE'].cumsum()
                fin['CumB'] = fin['BE'].cumsum()
                fig_bt = go.Figure()
                fig_bt.add_trace(go.Scatter(x=fin.index, y=fin['CumO'], mode='lines',
                                             name='GEM', line=dict(color='#00ff88', width=2)))
                fig_bt.add_trace(go.Scatter(x=fin.index, y=fin['CumB'], mode='lines',
                                             name='Bookmaker', line=dict(color='#ff3b5c', width=2, dash='dot')))
                neon_layout(fig_bt, "CUMULATIVE BRIER ERROR")
                fig_bt.update_layout(xaxis_title="Settled Bets", yaxis_title="Cumulative Error")
                st.plotly_chart(fig_bt, use_container_width=True)

                with st.expander("◈ RAW DATA"):
                    st.dataframe(
                        fin[['Time','Match','Target','Odds','Result','Net_Profit','Actual','BP','OP']],
                        use_container_width=True
                    )

                st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
                st.markdown('<div class="gem-label">◈ ML AUTO-TUNING (THRESHOLD OPTIMIZER)</div>', unsafe_allow_html=True)
                if st.button("🧪 RUN BACKTEST OPTIMIZATION", type="primary", use_container_width=True):
                    with st.spinner("วนลูปย้อนหลังเพื่อหา Threshold ที่ดีที่สุด..."):
                        best_ah_thr_opt, best_ah_pnl = 0.0, -99999.0
                        best_ou_thr_opt, best_ou_pnl = 0.0, -99999.0
                        ah_logs = fin[fin['Target'].isin(['เจ้าบ้าน', 'ทีมเยือน'])]
                        ou_logs = fin[fin['Target'].isin(['สูง', 'ต่ำ'])]

                        for t in np.arange(1.0, 30.0, 0.5):
                            pnl_ah = ah_logs[ah_logs['EV_Pct'] >= t]['Net_Profit'].sum()
                            if pnl_ah > best_ah_pnl:
                                best_ah_pnl, best_ah_thr_opt = pnl_ah, t
                            pnl_ou = ou_logs[ou_logs['EV_Pct'] >= t]['Net_Profit'].sum()
                            if pnl_ou > best_ou_pnl:
                                best_ou_pnl, best_ou_thr_opt = pnl_ou, t

                        st.success(
                            f"**🎯 Optimized Thresholds:**\n\n"
                            f"👉 **AH:** ตั้ง EV ขั้นต่ำที่ **{best_ah_thr_opt}%** "
                            f"(กำไรสูงสุด: ฿{best_ah_pnl:,.0f})\n\n"
                            f"👉 **O/U:** ตั้ง EV ขั้นต่ำที่ **{best_ou_thr_opt}%** "
                            f"(กำไรสูงสุด: ฿{best_ou_pnl:,.0f})"
                        )
                        st.info("นำตัวเลขนี้ไปปรับที่ Sidebar → EV THRESHOLDS ได้เลยครับ!")

            else:
                st.info("◈ No records with calculable outcomes")
        else:
            st.info("◈ No settled results — update Result column in Dashboard first")
    else:
        st.warning("◈ No investment log found")
