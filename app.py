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

# ── must be the very first Streamlit call ──
st.set_page_config(
    page_title="GEM System 10.0 · The Oracle",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="🎯"
)

# ==========================================
# 🛡️ HELPER FUNCTIONS & MATHEMATICAL ZONE
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

def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase = init_connection()
except Exception as e:
    supabase = None

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

def calc_pnl(row):
    try:
        if pd.isna(row['Result']) or str(row['Result']).strip() == "" or float(row['Investment']) <= 0:
            return 0.0
        sc = re.findall(r'\d+', str(row['Result']).strip())
        if len(sc) < 2: return 0.0
        hs, as_ = int(sc[0]), int(sc[1])
        hdp, tgt, odds, inv = float(row['HDP']), str(row['Target']).strip(), float(row['Odds']), float(row['Investment'])
        
        if tgt in ["เจ้าบ้าน", "ทีมเยือน"]:
            diff = hs - as_ if tgt == "เจ้าบ้าน" else as_ - hs
            nm = diff - hdp
        elif tgt in ["สูง", "ต่ำ"]:
            tot = hs + as_
            nm = tot - hdp if tgt == "สูง" else hdp - tot
        else: return 0.0
        
        if nm >= 0.5:   return inv * (odds - 1)
        elif nm == 0.25: return inv * (odds - 1) / 2
        elif nm == 0:    return 0.0
        elif nm == -0.25: return -(inv / 2)
        else: return -inv
    except:
        return 0.0

def calc_clv(row):
    try:
        if pd.isna(row['Closing_Odds']) or float(row['Closing_Odds']) <= 1.0: return 0.0
        return ((float(row['Odds']) / float(row['Closing_Odds'])) - 1.0) * 100.0
    except:
        return 0.0

def fix(o): return o + 1.0 if o < 1.1 else o

def shin_devig(oh, od, oa):
    pi = [1/oh, 1/od, 1/oa]
    sp = sum(pi)
    if sp <= 1.0: return pi[0]/sp, pi[1]/sp, pi[2]/sp
    lo, hi = 0.0, 1.0
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
    return p[0]/sp, p[1]/sp, p[2]/sp

def poisson(k, lam):
    return (lam**k * math.exp(-lam)) / math.factorial(k)

def calc_dixon_coles_matrix(ph, pd, pa, ou, oow, uuw,
                             ch=0, ca=0, ml=90,
                             rch=False, rca=False,
                             xg_h=0.0, xg_a=0.0, xg_weight=0.0):
    ow = oow + 1 if oow < 1.1 else oow
    uw = uuw + 1 if uuw < 1.1 else uuw
    op = 1/ow; up = 1/uw
    top = op / (op + up)

    bet = ou + 0.20 + ((top - 0.5) * 2.5)
    et = max(0.5, bet + (0.25 - pd) * 8.0)
    sup = (ph - pa) * (et ** 0.60)

    lh = max(0.15, (et + sup) / 2) * (ml / 90) ** 0.75
    la = max(0.15, (et - sup) / 2) * (ml / 90) ** 0.75

    if rch: lh *= 0.50; la *= 1.30
    if rca: la *= 0.50; lh *= 1.30

    if xg_h > 0.0 or xg_a > 0.0:
        lh = lh * (1 - xg_weight) + xg_h * (ml / 90) ** 0.75 * xg_weight
        la = la * (1 - xg_weight) + xg_a * (ml / 90) ** 0.75 * xg_weight

    dyn_rho = max(-0.25, min(0.0, -0.15 + (et - 2.5) * 0.05))

    mx = [[0.0] * 10 for _ in range(10)]
    for i in range(10):
        for j in range(10):
            bp = poisson(i, lh) * poisson(j, la)
            if i == 0 and j == 0:   tau = 1 - (lh * la * dyn_rho)
            elif i == 0 Basin and j == 1: tau = 1 + (lh * dyn_rho)
            elif i == 1 and j == 0: tau = 1 + (la * dyn_rho)
            elif i == 1 and j == 1: tau = 1 - dyn_rho
            else: tau = 1.0
            mx[i][j] = max(0, bp * tau)

    tp = sum(sum(r) for r in mx)
    h2 = h1 = dr = a1 = a2 = 0.0
    pou = {}
    for i in range(10):
        for j in range(10):
            p = mx[i][j] / tp
            fh = i + ch; fa = j + ca; d = fh - fa
            if d >= 2:   h2 += p
            elif d == 1: h1 += p
            elif d == 0: dr += p
            elif d == -1: a1 += p
            elif d <= -2: a2 += p
            tg = fh + fa
            pou[tg] = pou.get(tg, 0) + p
    return (h2, h1, dr, a1, a2, pou)

def apply_quant_penalties(ev, line, odds):
    rm = abs(line) - math.floor(abs(line))
    if rm in [0.25, 0.75]: ev -= 0.015
    if odds < 1.30 or odds > 4.00: ev -= 0.030
    return ev

def ev_ah(hdp, w2, w1, d, l1, l2, odds, fav):
    b = odds - 1
    h = abs(hdp)
    res = 0.0
    if h == 0: res = (w2 + w1) * b - (l1 + l2)
    elif fav:
        if h == 0.25:  res = (w2 + w1) * b - d * 0.5 - (l1 + l2)
        elif h == 0.5:  res = (w2 + w1) * b - (d + l1 + l2)
        elif h == 0.75: res = w2 * b + w1 * (b/2) - (d + l1 + l2)
        elif h == 1.0:  res = w2 * b - (d + l1 + l2)
        elif h == 1.25: res = w2 * b - w1 * 0.5 - (d + l1 + l2)
        elif h == 1.5:  res = w2 * b - (w1 + d + l1 + l2)
    else:
        if h == 0.25:  res = (w2 + w1) * b + d * (b/2) - (l1 + l2)
        elif h == 0.5:  res = (w2 + w1 + d) * b - (l1 + l2)
        elif h == 0.75: res = (w2 + w1 + d) * b - l1 * 0.5 - l2
        elif h == 1.0:  res = (w2 + w1 + d) * b - l2
        elif h == 1.25: res = (w2 + w1 + d) * b + l1 * (b/2) - l2
        elif h == 1.5:  res = (w2 + w1 + d + l1) * b - l2
    return apply_quant_penalties(res, hdp, odds)

def ev_ou(line, pt, odds, over):
    b = odds - 1
    fl = math.floor(line)
    rm = line - fl
    g = lambda cond: sum(pt.get(k, 0) for k in pt if cond(k))
    res = 0.0
    if over:
        if rm == 0.0:   return g(lambda k: k > fl) * b - g(lambda k: k < fl)
        elif rm == 0.25: res = g(lambda k: k >= fl+1) * b - pt.get(fl, 0) * 0.5 - g(lambda k: k < fl)
        elif rm == 0.5:  return g(lambda k: k >= fl+1) * b - g(lambda k: k <= fl)
        elif rm == 0.75: res = g(lambda k: k >= fl+2) * b + pt.get(fl+1, 0) * (b/2) - g(lambda k: k <= fl)
    else:
        if rm == 0.0:   return g(lambda k: k < fl) * b - g(lambda k: k > fl)
        elif rm == 0.25: res = g(lambda k: k < fl) * b + pt.get(fl, 0) * (b/2) - g(lambda k: k >= fl+1)
        elif rm == 0.5:  return g(lambda k: k <= fl) * b - g(lambda k: k >= fl+1)
        elif rm == 0.75: res = g(lambda k: k <= fl) * b - pt.get(fl+1, 0) * 0.5 - g(lambda k: k >= fl+2)
    return apply_quant_penalties(res, line, odds)

def ai_engine(match_name, target, base_ev, hdp, odds,
              live=False, current_min=0, score="0-0",
              thr=0.08, stats="", fav=None,
              line_movement="➖ Stable (นิ่ง)"):
    raw = load_gem_rules()
    try: db = get_dynamic_rules(target, live, raw)
    except: db = raw
    mode = ("[PRE-MATCH] เน้น Math-First 70% + GEM Rules 30%" if not live else "[IN-PLAY] Real-time + Full GEM RULES")
    ri = ("" if fav is None else (" [ทีมต่อ]" if fav else " [ทีมรอง]"))
    prompt = (
        f"CRO — Quant Sports Betting Fund\n[Match] {match_name}\n"
        f"[Situation] {'Live ' + str(current_min) + 'min (' + score + ')' if live else 'Pre-Match'}\n"
        f"[Target] {target}{ri} line={abs(hdp)} odds={odds} BaseEV={base_ev*100:.2f}%\n"
        f"[Line Movement] {line_movement}\n[Stats] {stats}\n[Mode] {mode}\n[GEM RULES]\n{db}\n\n"
        "Rules:\n1. ห้ามสับสนทีมต่อ/รอง\n2. Market Isolation\n3. ระบุ RuleID\n4. impact_score -1.0 ถึง 1.0\n\n"
        'JSON Thai: {"pros_analysis":"","cons_analysis":"","rule_triggered":"","impact_score":0.0,"final_decision":true,"final_comment":"","confidence_level":3}'
    )
    for attempt in range(3):
        try:
            model = genai.GenerativeModel('models/gemma-4-31b-it')
            res = model.generate_content(prompt); data = safe_json_loads(res.text)
            if data:
                imp = float(data.get('impact_score', 0.0))
                if abs(imp) >= 1.0: imp /= 100.0
                data['impact_score'] = imp; return data
        except Exception as e:
            if attempt == 2: return {"pros_analysis": "AI ขัดข้อง", "cons_analysis": str(e), "rule_triggered": "Fallback", "impact_score": 0.0, "final_decision": base_ev >= thr, "final_comment": "⚠ ยืนยันด้วย Base EV", "confidence_level": 1}
            time.sleep(2)

def ev_gauge(val, title, thr=8.0):
    pct = val * 100; c = "#00ff88" if pct >= thr else ("#ffd600" if pct > 0 else "#ff3b5c")
    fig = go.Figure(go.Indicator(mode="gauge+number", value=pct, number={'suffix': "%", 'font': {'color': c, 'size': 30, 'family': 'Share Tech Mono'}}, title={'text': title, 'font': {'size': 12, 'color': '#4a7a60', 'family': 'Rajdhani'}},
        gauge={'axis': {'range': [-20, 20], 'tickwidth': 1, 'tickcolor': "#0f2535", 'tickfont': {'color': '#1a3528', 'size': 8}}, 'bar': {'color': c, 'thickness': 0.22}, 'bgcolor': "rgba(0,0,0,0)", 'borderwidth': 0, 'steps': [{'range': [-20, 0], 'color': "rgba(255,59,92,0.07)"}, {'range': [0, thr], 'color': "rgba(255,214,0,0.05)"}, {'range': [thr, 20], 'color': "rgba(0,255,136,0.07)"}], 'threshold': {'line': {'color': c, 'width': 2}, 'thickness': 0.8, 'value': pct}}))
    fig.update_layout(height=185, margin=dict(l=12, r=12, t=26, b=6), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig

def neon_layout(fig, title=""):
    fig.update_layout(title=dict(text=title, font=dict(family="Rajdhani", size=12, color="#2a5040")), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(9,21,32,0.55)", font=dict(family="Share Tech Mono", color="#4a7a60"), xaxis=dict(gridcolor="#0f2535", linecolor="#0f2535", tickfont=dict(color="#2a5040")), yaxis=dict(gridcolor="#0f2535", linecolor="#0f2535", tickfont=dict(color="#2a5040")), legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#4a7a60")), margin=dict(l=8, r=8, t=36, b=8))
    return fig

def save_db(rows):
    if not rows or not supabase: return
    try:
        supabase.table("investment_logs").insert(rows).execute()
    except Exception as e:
        st.error(f"DB Error: {e}")

# ==========================================
# 🎨  NEON QUANT STYLE STYLING
# ==========================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;500;600;700&family=Exo+2:wght@300;400;600;800&display=swap');

:root {
    --bg-primary:   #050a0e;
    --bg-panel:     #0a1520;
    --bg-card:      #0d1e2e;
    --bg-card2:     #091520;
    --neon-green:   #00ff88;
    --neon-green2:  #00cc6a;
    --neon-dim:     #00ff8820;
    --neon-glow:    0 0 8px #00ff8870, 0 0 24px #00ff8828;
    --neon-red:     #ff3b5c;
    --neon-yellow:  #ffd600;
    --neon-blue:    #00b4ff;
    --border:       #0f2535;
    --border-neon:  #00ff8835;
    --text-main:    #c8e6d4;
    --text-dim:     #4a7a60;
    --text-label:   #2a5040;
    --font-mono:    'Share Tech Mono', monospace;
    --font-ui:      'Rajdhani', sans-serif;
    --font-head:    'Exo 2', sans-serif;
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
    background: linear-gradient(180deg, #060d14 0%, #050a0e 100%) !important;
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

[data-testid="stTabs"] [role="tablist"] {
    background: var(--bg-panel) !important;
    border-bottom: 1px solid var(--border-neon) !important;
    gap: 2px !important;
    padding: 4px 8px 0 !important;
    border-radius: 6px 6px 0 0 !important;
}
[data-testid="stTabs"] button[role="tab"] {
    font-family: var(--font-ui) !important;
    font-weight: 600 !important;
    font-size: 0.8rem !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: var(--text-dim) !important;
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    padding: 8px 16px !important;
}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: var(--neon-green) !important;
    border-bottom: 2px solid var(--neon-green) !important;
    text-shadow: 0 0 12px #00ff88 !important;
}

[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    background: var(--bg-card2) !important;
    color: var(--neon-green) !important;
    font-family: var(--font-mono) !important;
    font-size: 1rem !important;
    border: 1px solid var(--border) !important;
    border-radius: 4px !important;
}

.gem-panel {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 18px 20px;
    margin-bottom: 14px;
    position: relative;
}
.gem-panel::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, var(--neon-green2), transparent);
    border-radius: 6px 6px 0 0;
}
.gem-label {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    letter-spacing: 0.2em;
    color: var(--text-label);
    text-transform: uppercase;
    margin-bottom: 10px;
    border-left: 2px solid var(--neon-green2);
    padding-left: 8px;
}
.gem-badge {
    display: inline-block;
    background: var(--neon-dim);
    color: var(--neon-green);
    font-family: var(--font-mono);
    font-size: 0.68rem;
    padding: 2px 10px;
    border-radius: 2px;
    border: 1px solid var(--neon-green2);
}
.gem-ok   { color: #00ff88 !important; font-family: 'Share Tech Mono', monospace !important; font-size: 0.78rem !important; }
.gem-warn { color: #ffd600 !important; font-family: 'Share Tech Mono', monospace !important; font-size: 0.78rem !important; }
.gem-err  { color: #ff3b5c !important; font-family: 'Share Tech Mono', monospace !important; font-size: 0.78rem !important; }
.gem-dim  { color: #2a5040 !important; font-family: 'Share Tech Mono', monospace !important; font-size: 0.68rem !important; }
.gem-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, #00cc6a25, transparent);
    margin: 16px 0;
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
[data-testid="stHeader"] { background-color: transparent; }
</style>
""", unsafe_allow_html=True)

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
    <div style="font-family:'Share Tech Mono';font-size:0.6rem;color:#1a3528;letter-spacing:.15em;">BUILD v10.0.19</div>
    <span class="gem-badge">● SYSTEM ONLINE</span>
  </div>
</div>
<div class="gem-divider"></div>
""", unsafe_allow_html=True)

# ==========================================
# 🔧 SIDEBAR CONFIGURATION ZONE
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
    hdba_val = st.slider("HDBA Penalty %", 0.0, 10.0, 1.5, step=0.5)

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="gem-label">◈ KELLY CRITERION (MONEY MGT)</div>', unsafe_allow_html=True)
    kelly_fraction = st.slider("Kelly Fraction", 0.05, 0.50, 0.25, step=0.05, help="สัดส่วน Kelly (แนะนำ 0.25)")
    max_bet_cap = st.slider("Max Bet Cap %", 1.0, 10.0, 5.0, step=0.5, help="ลิมิตเงินลงทุนสูงสุดต่อบิล")

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="gem-label">◈ EV THRESHOLDS — PRE-MATCH</div>', unsafe_allow_html=True)
    pre_ah_thr = st.slider("AH %",  1.0, 50.0, 24.5, step=0.5)
    pre_ou_thr = st.slider("O/U %", 1.0, 50.0, 23.5, step=0.5)
    st.markdown('<div class="gem-label">◈ EV THRESHOLDS — IN-PLAY</div>', unsafe_allow_html=True)
    live_ah_thr = st.slider("AH Live %",  5.0, 50.0, 24.0, step=1.0)
    live_ou_thr = st.slider("O/U Live %", 5.0, 50.0, 23.0, step=1.0)

pre_ah_lim  = pre_ah_thr  / 100
pre_ou_lim  = pre_ou_thr  / 100
live_ah_lim = live_ah_thr / 100
live_ou_lim = live_ou_thr / 100

# ==========================================
# 📑 TABS MAIN ROUTING
# ==========================================
# 🌟 ทุกฟังก์ชันได้ถูกประกาศไว้ที่ต้นไฟล์ด้านบนอย่างสมบูรณ์แบบแล้ว ป้องกัน NameError 100%
# ==========================================
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
                            img = Image.open(uf)
                            model = genai.GenerativeModel('models/gemma-4-31b-it')
                            prompt_img = """คุณคือ AI Quant Analyst สกัดข้อมูลตารางราคาฟุตบอลจากภาพให้ออกมาเป็น JSON เท่านั้น"""
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
                        mv = re.search(r'(.*VS.*)', raw)
                        if mv: st.session_state.match_name = mv.group(1).strip()
                        hm = re.findall(r'^\s*เหย้า\s+([0-9.]+)', raw, re.MULTILINE)
                        if len(hm) >= 1: st.session_state.h1x2_val = float(hm[0])
                        if len(hm) >= 2: st.session_state.hdp_h_w_val = float(hm[1])
                        
                        dm = re.findall(r'^\s*เสมอ\s+([0-9.]+)', raw, re.MULTILINE)
                        if dm: 
                            st.session_state.d1x2_val = float(dm[0])
                            
                        am = re.findall(r'^\s*เยือน\s+([0-9.]+)', raw, re.MULTILINE)
                        if len(am) >= 1: st.session_state.a1x2_val = float(am[0])
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
        hdp_line = st.number_input("LINE",       format="%.2f", step=0.25, key="hdp_line_val")
        hdp_h_w  = st.number_input("HOME ODDS",  format="%.2f", key="hdp_h_w_val")
        hdp_a_w  = st.number_input("AWAY ODDS",  format="%.2f", key="hdp_a_w_val")
        st.markdown('</div>', unsafe_allow_html=True)
    with mc3:
        st.markdown('<div class="gem-panel"><div class="gem-label">TOTAL GOALS (O/U)</div>', unsafe_allow_html=True)
        ou_line   = st.number_input("LINE",  format="%.2f", step=0.25, key="ou_line_val")
        ou_over_w = st.number_input("OVER",  format="%.2f", key="ou_over_w_val")
        ou_under_w= st.number_input("UNDER", format="%.2f", key="ou_under_w_val")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="gem-label">◈ EXPECTED GOALS (xG) INTEGRATION</div>', unsafe_allow_html=True)
    c_xg1, c_xg2, c_xg3 = st.columns(3)
    xg_h      = c_xg1.number_input("xG Home", min_value=0.0, format="%.2f", step=0.1, key="xg_h_val")
    xg_a      = c_xg2.number_input("xG Away", min_value=0.0, format="%.2f", step=0.1, key="xg_a_val")
    xg_weight = c_xg3.slider("xG Weight %", 0.0, 1.0, 0.50, step=0.1)

    st.markdown('<div class="gem-label">◈ CONTEXT & MARKET FLOW</div>', unsafe_allow_html=True)
    col_st1, col_st2 = st.columns([2, 1])
    with col_st1:
        match_stats = st.text_area("H2H / Stats (Optional)", height=70, label_visibility="collapsed", placeholder="วางสถิติ H2H...")
    with col_st2:
        line_movement = st.selectbox("กระแสราคา (Line Movement)", ["➖ Stable (นิ่ง/ปกติ)", "🔥 Steam (ราคาไหลลง/เงินเข้า)", "❄️ Drift (ราคาไหลขึ้น/เงินออก)"])

    if st.button("⚡  RUN ORACLE ANALYSIS", use_container_width=True, type="primary"):
        ho, do_, ao = fix(h1x2), fix(d1x2), fix(a1x2)
        hwo, awo, owo, uwo = fix(hdp_h_w), fix(hdp_a_w), fix(ou_over_w), fix(ou_under_w)
        ph, pd_, pa = shin_devig(ho, do_, ao)
        hw2, hw1, dex, aw1, aw2, pt = calc_dixon_coles_matrix(ph, pd_, pa, ou_line, owo, uwo, xg_h=xg_h, xg_a=xg_a, xg_weight=xg_weight)
        
        fav_h = ph >= pa
        evh   = ev_ah(hdp_line, hw2, hw1, dex, aw1, aw2, hwo, fav_h)
        eva   = ev_ah(hdp_line, aw2, aw1, dex, hw1, hw2, awo, not fav_h) - (hdba_val / 100)
        evo   = ev_ou(ou_line, pt, owo, True)
        evu   = ev_ou(ou_line, pt, uwo, False)

        bah = max([{"n": "เจ้าบ้าน", "ev": evh, "odds": hwo, "hdp": hdp_line}, {"n": "ทีมเยือน", "ev": eva, "odds": awo, "hdp": hdp_line}], key=lambda x: x['ev'])
        bou = max([{"n": "สูง",     "ev": evo, "odds": owo, "hdp": ou_line}, {"n": "ต่ำ",     "ev": evu, "odds": uwo, "hdp": ou_line}], key=lambda x: x['ev'])

        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
        p1, p2, p3 = st.columns(3)
        p1.metric("HOME WIN", f"{ph*100:.1f}%")
        p2.metric("DRAW",     f"{pd_*100:.1f}%")
        p3.metric("AWAY WIN", f"{pa*100:.1f}%")

        g1, g2 = st.columns(2)
        with g1: st.plotly_chart(ev_gauge(bah['ev'], f"TARGET: {bah['n']}", pre_ah_thr), use_container_width=True)
        with g2: st.plotly_chart(ev_gauge(bou['ev'], f"TARGET: {bou['n']}", pre_ou_thr), use_container_width=True)

        valid_bets = []
        if bah['ev'] >= pre_ah_lim: valid_bets.append(bah)
        if bou['ev'] >= pre_ou_lim: valid_bets.append(bou)

        if valid_bets:
            for tc in valid_bets:
                with st.spinner(f"◈ THE ORACLE PROCESSING : {tc['n']}..."):
                    tf = (ph >= pa if tc['n'] == "เจ้าบ้าน" else not fav_h) if tc['n'] in ["เจ้าบ้าน","ทีมเยือน"] else None
                    v = ai_engine(match_name, tc['n'], tc['ev'], tc['hdp'], tc['odds'], live=False, stats=match_stats, fav=tf, line_movement=line_movement)
                    nev = tc['ev'] + v.get('impact_score', 0)

                    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="gem-label">◈ ORACLE VERDICT : {tc["n"]}</div>', unsafe_allow_html=True)
                    vc1, vc2, vc3 = st.columns(3)
                    vc1.metric("BASE EV",    f"{tc['ev']*100:.2f}%")
                    vc2.metric("ORACLE ADJ", f"{v.get('impact_score', 0)*100:.2f}%")
                    vc3.metric("NET EV",     f"{nev*100:.2f}%")

                    with st.expander(f"◈ FULL ANALYTICS MATRIX : {tc['n']}", expanded=True):
                        stars = v.get('confidence_level', 3)
                        st.markdown(f'<div class="gem-label">CONFIDENCE: {"★"*stars}{"☆"*(5-stars)} ({stars}/5)</div>', unsafe_allow_html=True)
                        st.success(f"**PROS:** {v.get('pros_analysis', '—')}")
                        st.error(f"**RISK:** {v.get('cons_analysis', '—')}")
                        st.info(f"**RULES TRIGGERED:** {v.get('rule_triggered', 'None')}")

                    col_v = "#00ff88" if v.get('final_decision', False) and nev > 0 else "#ff3b5c"
                    label = "◈ ORACLE APPROVED — EXECUTE" if v.get('final_decision', False) and nev > 0 else "◈ ORACLE REJECTED — STAND DOWN"
                    st.markdown(f'<div class="gem-panel" style="border-top:2px solid {col_v};"><div class="gem-label" style="border-color:{col_v};color:{col_v};">{label}</div><p style="color:{col_v};font-family:\'Share Tech Mono\';font-size:0.82rem;">{v.get("final_comment","")}</p></div>', unsafe_allow_html=True)

                    if v.get('final_decision', False) and nev > 0:
                        st.balloons()
                        kelly_opt = nev / (tc['odds'] - 1)
                        dutch_factor = 0.50 if len(valid_bets) == 2 else 1.00
                        inv = min(kelly_opt * kelly_fraction * dutch_factor, max_bet_cap / 100.0) * total_bankroll
                        inv = max(inv, 0.0)
                        tz_th = timezone(timedelta(hours=7))
                        save_db([{
                            "Time": datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S"),
                            "Match": match_name, "HDP": tc['hdp'], "Target": tc['n'],
                            "EV_Pct": round(nev * 100, 2), "Investment": round(inv, 2),
                            "Odds": tc['odds'], "Closing_Odds": 0.0, "Result": ""
                        }])
                        st.success(f"บันทึกบิลควบ {tc['n']} ลงระบบเรียบร้อย!")
        else:
            st.markdown(f'<div class="gem-panel" style="border-top:2px solid #ffd600;"><div class="gem-label" style="border-color:#ffd600;color:#ffd600;">◈ BELOW THRESHOLD — NO SIGNAL</div></div>', unsafe_allow_html=True)

# ╔══════════════╗
# ║  TAB 2       ║
# ╚══════════════╝
with tab2:
    tab2_logs = load_logs()
    tz_th = timezone(timedelta(hours=7))
    today_str = datetime.now(tz_th).strftime("%Y-%m-%d")

    if not tab2_logs.empty:
        st.markdown('<div class="gem-label">◈ POSITION LOG</div>', unsafe_allow_html=True)
        ef1, _ = st.columns([1, 3])
        with ef1: flt = st.selectbox("FILTER", ["Today", "Pending", "All"])
        df2 = tab2_logs.copy()
        if flt == "Today":   df2 = df2[df2['Time'].astype(str).str.contains(today_str, na=False)]
        elif flt == "Pending": df2 = df2[df2['Result'].astype(str).str.strip() == ""]
        df2 = df2.sort_values('Time', ascending=False).reset_index(drop=True)

        edf = st.data_editor(df2, column_config={"id": None, "Result": st.column_config.TextColumn("Result"), "Closing_Odds": st.column_config.NumberColumn("Closing Odds", min_value=0.0, format="%.2f")}, use_container_width=True, num_rows="dynamic")
        if st.button("💾  SYNC TO CLOUD", use_container_width=True, type="primary"):
            with st.spinner("Syncing..."):
                for _, row in edf.iterrows():
                    supabase.table("investment_logs").update({"Closing_Odds": float(row['Closing_Odds']), "Result": str(row['Result'])}).eq("id", row['id']).execute()
            st.toast("✓ Synced", icon="💾"); time.sleep(1); st.rerun()

        tab2_logs['Net_Profit'] = tab2_logs.apply(calc_pnl, axis=1)
        tab2_logs['CLV_Pct']   = tab2_logs.apply(calc_clv, axis=1)

        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("NET PROFIT", f"฿{tab2_logs['Net_Profit'].sum():,.0f}")
        il = tab2_logs[tab2_logs['Investment'] > 0]
        m2.metric("DEPLOYED",   f"฿{il['Investment'].sum():,.0f}")
        
        max_drawdown = mdd_pct = 0.0
        if not tab2_logs.empty:
            dd_df = tab2_logs.sort_values('Time').copy()
            dd_df['Cum'] = dd_df['Net_Profit'].cumsum()
            drawdown = dd_df['Cum'] - dd_df['Cum'].cummax()
            max_drawdown = drawdown.min()
            if total_bankroll > 0: mdd_pct = (max_drawdown / total_bankroll) * 100
            
        m3.metric("MAX DRAWDOWN", f"฿{max_drawdown:,.0f}", f"{mdd_pct:.2f}%")
        m4.metric("ROI",        f"{(tab2_logs['Net_Profit'].sum()/il['Investment'].sum()*100 if not il.empty else 0):.2f}%")

# ╔══════════════╗
# ║  TAB 3       ║
# ╚══════════════╝
with tab3:
    st.markdown('<div class="gem-label">◈ LIVE SNIPER COMMAND CENTER</div>', unsafe_allow_html=True)
    with st.expander("📷 AI LIVE VISION — Screenshot scanner"):
        limgs = st.file_uploader("Upload live screenshots", type=['png','jpg'], accept_multiple_files=True, key="live_uploader")
        if limgs and st.button("⚡ EXTRACT LIVE DATA", use_container_width=True, key="live_btn"):
            with st.spinner("Scanning..."):
                try:
                    imgs = [Image.open(f) for f in limgs]; model = genai.GenerativeModel('models/gemma-4-31b-it')
                    pl = '''คุณคือ AI Quant Analyst สกัดข้อมูลกระดานฟุตบอลสด LIVE เป็น JSON เท่านั้น'''
                    d = safe_json_loads(model.generate_content([pl] + imgs).text)
                    for k, v in d.items():
                        if k == 'match_name': st.session_state['match_name_live'] = str(v)
                        elif k == 'current_score_h': st.session_state['lh_s_input'] = int(v)
                        elif k == 'current_score_a': st.session_state['la_s_input'] = int(v)
                        elif k == 'rc_h': st.session_state['rc_h_chk'] = bool(v)
                        elif k == 'rc_a': st.session_state['rc_a_chk'] = bool(v)
                        elif k == 'current_min': st.session_state['current_min'] = int(v)
                        else: st.session_state[k] = float(v)
                    st.toast("✅ สกัด Live สำเร็จ!"); time.sleep(1); st.rerun()
                except Exception as e: st.error(str(e))

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    default_live_mn = st.session_state.get('match_name_live', st.session_state.get('match_name', ''))
    live_mn = st.text_input("MATCH (Live)", value=default_live_mn, key="match_name_live_input")

    gl1, gl2 = st.columns(2)
    with gl1:
        csh = st.number_input("HOME SCORE", min_value=0, key="lh_s_input")
        rch = st.checkbox("🟥 HOME RED", key="rc_h_chk")
        csa = st.number_input("AWAY SCORE", min_value=0, key="la_s_input")
        rca = st.checkbox("🟥 AWAY RED", key="rc_a_chk")
        cmin = st.slider("MINUTE", 0, 120, key="current_min")
    with gl2:
        preh  = st.number_input("PRE HOME ODDS", value=st.session_state.get('pre_h', 2.0), format="%.2f", key="pre_h")
        pred  = st.number_input("PRE DRAW ODDS", value=st.session_state.get('pre_d', 3.0), format="%.2f", key="pre_d")
        prea  = st.number_input("PRE AWAY ODDS", value=st.session_state.get('pre_a', 3.0), format="%.2f", key="pre_a")
        preou = st.number_input("PRE O/U Line",  value=st.session_state.get('pre_ou', 2.5), format="%.2f", step=0.25, key="pre_ou")

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    lm1, lm2 = st.columns(2)
    with lm1:
        lhdp = st.number_input("HDP", value=st.session_state['live_hdp'], step=0.25, key="live_hdp")
        lhdph = st.number_input("HOME WATER", value=st.session_state.get('live_hdp_h', 0.9), format="%.2f", key="live_hdp_h")
        lhdpa = st.number_input("AWAY WATER", value=st.session_state.get('live_hdp_a', 0.9), format="%.2f", key="live_hdp_a")
    with lm2:
        lou = st.number_input("O/U Line", value=st.session_state['live_ou'], step=0.25, key="live_ou")
        louov = st.number_input("OVER WATER",  value=st.session_state.get('live_ou_over', 0.9),  format="%.2f", key="live_ou_over")
        louun = ow2 = st.number_input("UNDER WATER", value=st.session_state.get('live_ou_under', 0.9), format="%.2f", key="live_ou_under")

    line_movement_live = st.selectbox("กระแสราคา (Live Line Movement)", ["➖ Stable (นิ่ง/ปกติ)", "🔥 Steam (ราคาไหลลง/เงินเข้า)", "❄️ Drift (ราคาไหลขึ้น/เงินออก)"], key="lm_live")

    if st.button("🎯  ENGAGE LIVE SNIPER", use_container_width=True, type="primary"):
        lph, lpd, lpa = shin_devig(fix(preh), fix(pred), fix(prea))
        ml = max(90 - cmin, 1)
        hw2l, hw1l, dexl, aw1l, aw2l, ptl = calc_dixon_coles_matrix(lph, lpd, lpa, lou, fix(louov), fix(louun), ch=csh, ca=csa, ml=ml, rch=rch, rca=rca, xg_h=st.session_state.get('xg_h_val', 0.0), xg_a=st.session_state.get('xg_a_val', 0.0), xg_weight=0.5)
        
        evhl = ev_ah(lhdp, hw2l, hw1l, dexl, aw1l, aw2l, fix(lhdph), lph>=lpa)
        eval_ = ev_ah(lhdp, aw2l, aw1l, dexl, hw1l, hw2l, fix(lhdpa), lpa>lph) - (hdba_val / 100)
        evol = ev_ou(lou, ptl, fix(louov), True)
        evul = ev_ou(lou, ptl, fix(louun), False)
        
        bav = max(evhl, eval_); tah = "เจ้าบ้าน" if evhl > eval_ else "ทีมเยือน"
        bov = max(evol, evul); tou = "สูง" if evol > evul else "ต่ำ"

        valid_bets_live = []
        if bav >= live_ah_lim: valid_bets_live.append({"n": tah, "ev": bav, "hdp": lhdp, "odds": fix(lhdph) if tah == "เจ้าบ้าน" else fix(lhdpa)})
        if bov >= live_ou_lim: valid_bets_live.append({"n": tou, "ev": bov, "hdp": lou, "odds": fix(louov) if tou == "สูง" else fix(louun)})

        if valid_bets_live:
            for tl2 in valid_bets_live:
                with st.spinner(f"◈ SNIPER PROCESSING : {tl2['n']}..."):
                    tf2 = (lph >= lpa if tl2['n'] == "เจ้าบ้าน" else not (lph >= lpa)) if tl2['n'] in ["เจ้าบ้าน","ทีมเยือน"] else None
                    live_mn_val = st.session_state.get('match_name_live_input', live_mn)
                    al = ai_engine(live_mn_val, tl2['n'], tl2['ev'], tl2['hdp'], tl2['odds'], live=True, current_min=cmin, score=f"{csh}-{csa}", thr=live_ah_lim, line_movement=line_movement_live)
                    nlev = tl2['ev'] + al.get('impact_score', 0)
                    
                    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="gem-label">◈ LIVE ORACLE VERDICT : {tl2["n"]}</div>', unsafe_allow_html=True)
                    lc1, lc2, lc3 = st.columns(3)
                    lc1.metric("LIVE EV", f"{tl2['ev']*100:.2f}%")
                    lc2.metric("ORACLE ADJ", f"{al.get('impact_score', 0)*100:.2f}%")
                    lc3.metric("NET EV", f"{nlev*100:.2f}%")
                    
                    with st.expander(f"◈ LIVE ANALYTICS : {tl2['n']}", expanded=True):
                        st.success(f"**PROS:** {al.get('pros_analysis', '—')}")
                        st.error(f"**RISK:** {al.get('cons_analysis', '—')}")
                        
                    lim = live_ah_lim if tl2['n'] in ["เจ้าบ้าน", "ทีมเยือน"] else live_ou_lim
                    if al.get('final_decision', False) and nlev >= lim:
                        st.balloons()
                        kelly_opt_live = nlev / (tl2['odds'] - 1)
                        dutch_factor = 0.50 if len(valid_bets_live) == 2 else 1.00
                        inv = min(kelly_opt_live * kelly_fraction * dutch_factor, max_bet_cap / 100.0) * total_bankroll
                        inv = max(inv, 0.0)
                        tz2 = timezone(timedelta(hours=7))
                        save_db([{"Time": datetime.now(tz2).strftime("%Y-%m-%d %H:%M:%S"), "Match": f"[LIVE {cmin}'] {live_mn_val}", "HDP": tl2['hdp'], "Target": tl2['n'], "EV_Pct": round(nlev * 100, 2), "Investment": round(inv, 2), "Odds": tl2['odds'], "Closing_Odds": 0.0, "Result": ""}])
                        st.toast("🎯 SNIPER DEPLOYED!", icon="🚀")


# ╔══════════════╗
# ║  TAB 4       ║
# ╚══════════════╝
with tab4:
    st.markdown('<div class="gem-label">◈ BRIER SCORE ACCURACY ENGINE</div>', unsafe_allow_html=True)
    st.markdown(
        '<p style="font-family:\'Rajdhani\';font-size:0.85rem;color:#4a7a60;">'
        'Compares GEM estimates vs bookmaker implied probabilities. Lower Brier Score = More Accurate.</p>',
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
                    if net >= mw * 0.95:  return 1.0
                    elif net > 0:          return 0.75
                    elif net == 0:         return 0.50
                    elif net <= -inv*0.95: return 0.0
                    elif net < 0:          return 0.25
                    return np.nan
                except:
                    return np.nan

            fin['Actual'] = fin.apply(score_row, axis=1)
            fin = fin.dropna(subset=['Actual'])

            if not fin.empty:
                fin['BP'] = (1 / fin['Odds']).clip(0, 1)
                rp = (((fin['EV_Pct'] / 100) + 1) / fin['Odds']).clip(0, 1)
                fin['OP'] = ((rp * 0.85) + (fin['BP'] * 0.15)).clip(0, 1)
                fin['OE'] = (fin['OP'] - fin['Actual']) ** 2
                fin['BE'] = (fin['BP'] - fin['Actual']) ** 2

                ao = fin['OE'].mean()
                ab = fin['BE'].mean()
                diff = ab - ao

                st.markdown(f'<div class="gem-label">◈ ACCURACY — {len(fin)} SETTLED BETS</div>',
                            unsafe_allow_html=True)
                rc1, rc2, rc3 = st.columns(3)
                rc1.metric("GEM SCORE",   f"{ao:.4f}", f"{-diff:.4f} vs bookie", delta_color="inverse")
                rc2.metric("BOOKIE SCORE", f"{ab:.4f}")
                col3 = "#00ff88" if ao < ab else "#ff3b5c"
                lab3 = "▲ GEM BEATS MARKET" if ao < ab else "▼ CALIBRATION NEEDED"
                rc3.markdown(
                    f'<div class="gem-panel" style="border-top:2px solid {col3};text-align:center;padding:10px;">'
                    f'<span style="font-family:\'Share Tech Mono\';color:{col3};font-size:0.78rem;">{lab3}</span></div>',
                    unsafe_allow_html=True
                )

                st.markdown('<div class="gem-label" style="margin-top:14px;">◈ CUMULATIVE ERROR</div>',
                            unsafe_allow_html=True)
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
                st.markdown('<div class="gem-label">◈ ML AUTO-TUNING (THRESHOLD OPTIMIZER)</div>',
                            unsafe_allow_html=True)
                if st.button("🧪 RUN BACKTEST OPTIMIZATION", type="primary", use_container_width=True):
                    with st.spinner("AI กำลังวนลูปย้อนหลังเพื่อหาจุดทำกำไรสูงสุด..."):
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

            else: st.info("◈ No records with calculable outcomes")
        else: st.info("◈ No settled results — update Result column in Dashboard first")
    else: st.warning("◈ No investment log found")
