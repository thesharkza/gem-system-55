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
import urllib.request

# ==========================================
# 🛡️ HELPER FUNCTIONS (ระบบเกราะป้องกัน)
# ==========================================
def safe_float(v, default=0.0, min_v=-100.0, max_v=100.0):
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f): f = default
    except: f = default
    return max(min_v, min(f, max_v))

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
        try: return json.loads(clean)
        except: return {}

# ==========================================
# 📡 DATA FEED INTEGRATION (iSports API)
# ==========================================
def fetch_isports_data(api_key, target_match_name):
    if not api_key:
        return "⚠️ ไม่มี iSports API Key (AI จะวิเคราะห์จากคณิตศาสตร์ EV ล้วน)"
    
    urls = [
        f"http://api.isportsapi.com/sport/football/livescores?api_key={api_key}",
        f"http://api2.isportsapi.com/sport/football/livescores?api_key={api_key}"
    ]
    
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read()
                data = json.loads(content.decode('utf-8'))
                
                if "data" in data:
                    raw_data = str(data["data"])[:3000] # ตัดข้อมูลกัน Token ล้น
                    return f"สถิติสดจาก iSports API (โปรดค้นหาข้อมูลคู่ '{target_match_name}'):\n{raw_data}"
                else:
                    return f"API ตอบกลับ แต่ข้อมูลไม่สมบูรณ์: {str(data)[:200]}"
        except Exception:
            continue
            
    return "❌ ไม่สามารถเชื่อมต่อกับ iSports API ได้"

# ==========================================
# ⚙️ CONFIG & DATABASE CONNECTION
# ==========================================
st.set_page_config(page_title="GEM System 10.0 (The Oracle)", layout="wide", initial_sidebar_state="expanded")

@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except: return None

supabase: Client = init_connection()

def init_session_state():
    defaults = {
        'match_name': "ชื่อคู่แข่งขัน",
        'h1x2_val': 2.0, 'd1x2_val': 3.0, 'a1x2_val': 3.0,
        'hdp_line_val': 0.0, 'hdp_h_w_val': 0.9, 'hdp_a_w_val': 0.9,
        'ou_line_val': 2.5, 'ou_over_w_val': 0.9, 'ou_under_w_val': 0.9,
        'raw_text': "", 'current_min': 45, 'lh_s_input': 0, 'la_s_input': 0,
        'pre_h': 2.0, 'pre_d': 3.0, 'pre_a': 3.0, 'pre_ou': 2.5,
        'live_hdp': 0.0, 'live_hdp_h': 0.9, 'live_hdp_a': 0.9,
        'live_ou': 2.5, 'live_ou_over': 0.9, 'live_ou_under': 0.9
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

init_session_state()

@st.cache_data(ttl=60)
def load_gem_rules():
    if not supabase: return "⚠️ ไม่สามารถเชื่อมต่อฐานข้อมูล Supabase ได้"
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
        dynamic_db.append(rule)
    return "\n".join(dynamic_db)

# ==========================================
# 1. QUANT ENGINE (คณิตศาสตร์ EV)
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
    except: p = pi 
    sum_p = sum(p) 
    return p[0]/sum_p, p[1]/sum_p, p[2]/sum_p

def poisson(k, lam): return (lam**k * math.exp(-lam)) / math.factorial(k)

def calc_dixon_coles_matrix(p_h, p_d, p_a, ou_line, ou_over_w, ou_under_w, rho, current_h=0, current_a=0, minutes_left=90, red_card_h=False, red_card_a=False):
    o_w = ou_over_w + 1.0 if ou_over_w < 1.1 else ou_over_w
    u_w = ou_under_w + 1.0 if ou_under_w < 1.1 else ou_under_w
    true_o_prob = (1.0 / o_w) / ((1.0 / o_w) + (1.0 / u_w))
    expected_total = max(0.5, ou_line + 0.20 + ((true_o_prob - 0.5) * 2.5))
    supremacy = (p_h - p_a) * (expected_total ** 0.85)
    time_factor = (minutes_left / 90.0) ** 0.85 
    lam_h = max(0.15, (expected_total + supremacy) / 2.0) * time_factor
    lam_a = max(0.15, (expected_total - supremacy) / 2.0) * time_factor

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
    p_h2 = 0.0; p_h1 = 0.0; p_dr = 0.0; p_a1 = 0.0; p_a2 = 0.0; p_ou = {} 
    for i in range(10):
        for j in range(10):
            prob = matrix[i][j] / total_prob
            diff = (i + current_h) - (j + current_a)
            if diff >= 2: p_h2 += prob
            elif diff == 1: p_h1 += prob
            elif diff == 0: p_dr += prob
            elif diff == -1: p_a1 += prob
            elif diff <= -2: p_a2 += prob
            tot = (i + current_h) + (j + current_a)
            p_ou[tot] = p_ou.get(tot, 0.0) + prob
    return (p_h2, p_h1, p_dr, p_a1, p_a2, p_ou)

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
        if rm == 0.0: return (sum(p_total.get(k, 0) for k in p_total if k > fl) * b) - (sum(p_total.get(k, 0) for k in p_total if k < fl) * 1)
        elif rm == 0.25: return (sum(p_total.get(k, 0) for k in p_total if k >= fl + 1) * b) - (p_total.get(fl, 0) * 0.5) - (sum(p_total.get(k, 0) for k in p_total if k < fl) * 1)
        elif rm == 0.5: return (sum(p_total.get(k, 0) for k in p_total if k >= fl + 1) * b) - (sum(p_total.get(k, 0) for k in p_total if k <= fl) * 1)
        elif rm == 0.75: return (sum(p_total.get(k, 0) for k in p_total if k >= fl + 2) * b) + (p_total.get(fl + 1, 0) * (b / 2)) - (sum(p_total.get(k, 0) for k in p_total if k <= fl) * 1)
    else: 
        if rm == 0.0: return (sum(p_total.get(k, 0) for k in p_total if k < fl) * b) - (sum(p_total.get(k, 0) for k in p_total if k > fl) * 1)
        elif rm == 0.25: return (sum(p_total.get(k, 0) for k in p_total if k < fl) * b) + (p_total.get(fl, 0) * (b / 2)) - (sum(p_total.get(k, 0) for k in p_total if k >= fl + 1) * 1)
        elif rm == 0.5: return (sum(p_total.get(k, 0) for k in p_total if k <= fl) * b) - (sum(p_total.get(k, 0) for k in p_total if k >= fl + 1) * 1)
        elif rm == 0.75: return (sum(p_total.get(k, 0) for k in p_total if k <= fl) * b) - (p_total.get(fl + 1, 0) * 0.5) - (sum(p_total.get(k, 0) for k in p_total if k >= fl + 2) * 1)
    return 0.0

# ==========================================
# 2. AI DECISION ENGINE (CRO) - Data-Driven
# ==========================================
def ai_quant_decision_engine(match_name, target, base_ev, hdp_line, odds, is_live=False, current_min=0, score="0-0", threshold=0.08, stats_data=""):
    raw_database = load_gem_rules() 
    try: oracle_database = get_dynamic_rules(target, is_live, raw_database)
    except: oracle_database = raw_database
    
    if not is_live:
        mode_instruction = "[โหมดการวิเคราะห์: PRE-MATCH]\nเน้นหา Value Bet โดยให้ Base EV เป็นหลัก และใช้สถิติ/กฎเป็นตัวช่วยกรองกับดักราคา"
    else:
        mode_instruction = "[โหมดการวิเคราะห์: IN-PLAY LIVE]\nตรวจสอบสถิติสดแบบ Real-time ร่วมกับ GEM RULES อย่างเต็มรูปแบบ"

    prompt = (
        f"คุณคือ Chief Risk Officer ประจำกองทุน Quant Sports Betting\n"
        f"[ข้อมูลหน้างาน]\n"
        f"- คู่: {match_name}\n"
        f"- สถานการณ์: {'Live ' + str(current_min) + ' min (' + score + ')' if is_live else 'Pre-Match'}\n"
        f"- เป้าหมาย: {target} (เรต {hdp_line}, Odds {odds})\n"
        f"- Base EV: {base_ev * 100:.2f}%\n\n"
        f"📊 [ข้อมูลสถิติเชิงลึก/API Data]\n"
        f"{stats_data}\n\n"
        f"{mode_instruction}\n\n"
        f"📖 [คัมภีร์ GEM RULES จาก CLOUD]\n{oracle_database}\n\n"
        "คำสั่งพิเศษ:\n"
        "1. หากมีการละเมิดกฎ ให้ระบุ [Rule ID] และ [Category] ให้ชัดเจน\n"
        "2. วิเคราะห์สถิติประกอบกับ EV ว่าทิศทางสอดคล้องกันหรือไม่\n"
        "ตอบกลับเป็น JSON Format (ภาษาไทย) เท่านั้น:\n"
        "{\n"
        '    "pros_analysis": "ข้อดีทางคณิตศาสตร์และสถิติ",\n'
        '    "cons_analysis": "ความเสี่ยงและกฎที่ละเมิด",\n'
        '    "rule_triggered": "ระบุ Rule ID และหมวดหมู่",\n'
        '    "impact_score": 0.0,\n'
        '    "final_decision": true,\n'
        '    "final_comment": "บทสรุปฟันธง",\n'
        '    "confidence_level": 3\n'
        "}"
    )
    
    for attempt in range(3):
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            res = model.generate_content(prompt)
            data = safe_json_loads(res.text)
            if data: return data
        except Exception:
            time.sleep(2)
            
    return {
        "pros_analysis": "ระบบ AI ขัดข้อง", "cons_analysis": "Error API Timeout", "rule_triggered": "Fallback",
        "impact_score": 0.0, "final_decision": base_ev >= threshold, "final_comment": "ยืนยันไม้ด้วย Base EV", "confidence_level": 1
    }

# ==========================================
# UI COMPONENTS & CLOUD
# ==========================================
def create_ev_gauge(ev_value, title, threshold=8.0):
    ev_pct = ev_value * 100
    color = "#00FF7F" if ev_pct >= threshold else ("#FFD700" if ev_pct > 0 else "#FF4500")
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=ev_pct, number={'suffix': "%", 'font': {'color': color, 'size': 30}},
        title={'text': title, 'font': {'size': 16, 'color': 'white'}},
        gauge={'axis': {'range': [-20, 20], 'tickwidth': 1, 'tickcolor': "white"}, 'bar': {'color': color}, 'bgcolor': "rgba(0,0,0,0.1)",
               'steps': [{'range': [-20, 0], 'color': "rgba(255,69,0,0.15)"}, {'range': [0, threshold], 'color': "rgba(255,215,0,0.15)"}, {'range': [threshold, 20], 'color': "rgba(0,255,127,0.15)"}],
               'threshold': {'line': {'color': "white", 'width': 3}, 'value': ev_pct}}
    ))
    fig.update_layout(height=200, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig

def save_to_supabase(data_list):
    if not supabase: return
    try: supabase.table("investment_logs").insert(data_list).execute()
    except Exception as e: st.error(f"Error saving: {e}")

def load_logs():
    if not supabase: return None
    try:
        response = supabase.table("investment_logs").select("*").order("Time", desc=True).execute()
        if response.data:
            df = pd.DataFrame(response.data)
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
            for col in ['EV_Pct', 'Investment', 'Odds', 'Closing_Odds']: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            df['Result'] = df['Result'].fillna("")
            return df.dropna(subset=['Time'])
        return pd.DataFrame()
    except: return None

# ==========================================
# 🎯 MAIN LAYOUT & SIDEBAR
# ==========================================
st.title("🎯 GEM System 10.0: The Oracle")

st.sidebar.header("🔑 API Integrations")
gemini_key = st.secrets.get("GEMINI_API_KEY", "")
isports_key = st.secrets.get("ISPORTS_API_KEY", "")

if gemini_key:
    genai.configure(api_key=gemini_key)
    st.sidebar.success("✅ Gemini AI Connected")
else: st.sidebar.warning("⚠️ โปรดใส่ Gemini API Key")

if not isports_key:
    isports_key = st.sidebar.text_input("ใส่ iSports API Key (สถิติสด):", type="password")
if isports_key: st.sidebar.success("📡 iSports Data Ready")

st.sidebar.header("🗄️ Database Status")
if supabase:
    st.sidebar.success("☁️ Supabase: Connected")
else: st.sidebar.error("❌ Supabase: Disconnected")

st.sidebar.header("💰 Portfolio & Parameters")
total_bankroll = st.sidebar.number_input("เงินทุน (THB)", min_value=0.0, value=10000.0)
dc_rho = st.sidebar.slider("🔗 Dixon-Coles Rho", -0.30, 0.0, -0.10, step=0.01)
hdba_val = st.sidebar.slider("⚖️ HDBA Penalty %", 0.0, 10.0, 1.5, step=0.5)

st.sidebar.subheader("🎯 EV Thresholds")
pre_ah_threshold = st.sidebar.slider("เป้า AH (Pre) %", 1.0, 15.0, 5.0, step=0.5)
pre_ou_threshold = st.sidebar.slider("เป้า O/U (Pre) %", 1.0, 15.0, 5.0, step=0.5)
live_ah_threshold = st.sidebar.slider("เป้า AH (Live) %", 5.0, 50.0, 20.0, step=1.0)
live_ou_threshold = st.sidebar.slider("เป้า O/U (Live) %", 5.0, 50.0, 20.0, step=1.0)

tab1, tab2, tab3, tab4 = st.tabs(["🚀 Pre-Match", "📊 Dashboard", "⚡ IN-PLAY LIVE", "🧪 Backtest"])

# --- 🚀 TAB 1: PRE-MATCH ---
with tab1:
    match_name = st.text_input("📝 คู่แข่งขัน", key="match_name")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1. พูล & AH")
        st.session_state['h1x2_val'] = safe_float(st.session_state.get('h1x2_val', 2.0), 2.0, 1.01, 100.0)
        st.session_state['d1x2_val'] = safe_float(st.session_state.get('d1x2_val', 3.0), 3.0, 1.01, 100.0)
        st.session_state['a1x2_val'] = safe_float(st.session_state.get('a1x2_val', 3.0), 3.0, 1.01, 100.0)
        st.session_state['hdp_line_val'] = safe_float(st.session_state.get('hdp_line_val', 0.0), 0.0, -10.0, 10.0)
        st.session_state['hdp_h_w_val'] = safe_float(st.session_state.get('hdp_h_w_val', 0.9), 0.9, -2.0, 10.0)
        st.session_state['hdp_a_w_val'] = safe_float(st.session_state.get('hdp_a_w_val', 0.9), 0.9, -2.0, 10.0)
        
        h1x2 = st.number_input("เหย้า (1X2)", min_value=1.01, format="%.2f", key="h1x2_val")
        d1x2 = st.number_input("เสมอ (1X2)", min_value=1.01, format="%.2f", key="d1x2_val")
        a1x2 = st.number_input("เยือน (1X2)", min_value=1.01, format="%.2f", key="a1x2_val")
        hdp_line = st.number_input("เรต (HDP)", format="%.2f", step=0.25, key="hdp_line_val")
        hdp_h_w = st.number_input("น้ำเจ้าบ้าน", format="%.2f", key="hdp_h_w_val")
        hdp_a_w = st.number_input("น้ำทีมเยือน", format="%.2f", key="hdp_a_w_val")
    with col2:
        st.subheader("2. ตลาด O/U")
        st.session_state['ou_line_val'] = safe_float(st.session_state.get('ou_line_val', 2.5), 2.5, 0.5, 20.0)
        st.session_state['ou_over_w_val'] = safe_float(st.session_state.get('ou_over_w_val', 0.9), 0.9, -2.0, 10.0)
        st.session_state['ou_under_w_val'] = safe_float(st.session_state.get('ou_under_w_val', 0.9), 0.9, -2.0, 10.0)

        ou_line = st.number_input("เรต (O/U)", format="%.2f", step=0.25, key="ou_line_val")
        ou_over_w = st.number_input("น้ำสูง (Over)", format="%.2f", key="ou_over_w_val")
        ou_under_w = st.number_input("น้ำต่ำ (Under)", format="%.2f", key="ou_under_w_val")

    st.subheader("📊 ข้อมูลสถิติเพิ่มเติม (Optional)")
    match_stats = st.text_area("วางสถิติย้อนหลัง (H2H, ฟอร์ม) เพื่อให้ AI วิเคราะห์ร่วมด้วย", height=100)

    if st.button("🚀 ANALYZE PRE-MATCH", use_container_width=True):
        def fix(o): return o + 1.0 if o < 1.1 else o
        prob_h, prob_d, prob_a = shin_devig(fix(h1x2), fix(d1x2), fix(a1x2))
        hw2, hw1, d_ex, aw1, aw2, p_tot = calc_dixon_coles_matrix(prob_h, prob_d, prob_a, ou_line, fix(ou_over_w), fix(ou_under_w), dc_rho)
        is_fav = prob_h >= prob_a
        ev_h = calc_advanced_ah_ev(hdp_line, hw2, hw1, d_ex, aw1, aw2, fix(hdp_h_w), is_fav)
        ev_a = calc_advanced_ah_ev(hdp_line, aw2, aw1, d_ex, hw1, hw2, fix(hdp_a_w), not is_fav) - (hdba_val/100)
        ev_o = calc_advanced_ou_ev(ou_line, p_tot, fix(ou_over_w), True)
        ev_u = calc_advanced_ou_ev(ou_line, p_tot, fix(ou_under_w), False)

        b_ah = {"n": "เจ้าบ้าน", "ev": ev_h, "odds": fix(hdp_h_w), "hdp": hdp_line} if ev_h > ev_a else {"n": "ทีมเยือน", "ev": ev_a, "odds": fix(hdp_a_w), "hdp": hdp_line}
        b_ou = {"n": "สูง", "ev": ev_o, "odds": fix(ou_over_w), "hdp": ou_line} if ev_o > ev_u else {"n": "ต่ำ", "ev": ev_u, "odds": fix(ou_under_w), "hdp": ou_line}

        g1, g2 = st.columns(2)
        with g1: st.plotly_chart(create_ev_gauge(b_ah['ev'], f"AH: {b_ah['n']}", pre_ah_threshold), use_container_width=True)
        with g2: st.plotly_chart(create_ev_gauge(b_ou['ev'], f"O/U: {b_ou['n']}", pre_ou_threshold), use_container_width=True)

        if b_ah['ev'] >= (pre_ah_threshold/100) or b_ou['ev'] >= (pre_ou_threshold/100):
            target = b_ah if b_ah['ev'] > b_ou['ev'] else b_ou
            with st.spinner("🧠 THE ORACLE กำลังตรวจสอบ EV และสถิติ..."):
                ai_res = ai_quant_decision_engine(match_name, target['n'], target['ev'], target['hdp'], target['odds'], False, threshold=(pre_ah_threshold/100), stats_data=match_stats)
                net_ev = target['ev'] + ai_res.get('impact_score', 0)
                
                st.markdown("---")
                c1, c2, c3 = st.columns(3)
                c1.metric("Base EV", f"{target['ev']*100:.2f}%")
                c2.metric("Oracle Adjust", f"{ai_res.get('impact_score', 0)*100:.2f}%")
                c3.metric("Net EV", f"{net_ev*100:.2f}%")
                
                with st.expander("📖 อ่านบทวิเคราะห์ AI"):
                    st.write(f"**Pros:** {ai_res.get('pros_analysis')}")
                    st.write(f"**Cons:** {ai_res.get('cons_analysis')}")
                    st.write(f"**Rules:** {ai_res.get('rule_triggered')}")
                
                if ai_res.get('final_decision') and net_ev > 0:
                    st.success(f"✅ APPROVED: {ai_res.get('final_comment')}")
                    inv = min(((((target['odds']-1) * ((net_ev+1)/target['odds']) - (1-((net_ev+1)/target['odds']))) / (target['odds']-1)) * 0.25), 0.05) * total_bankroll
                    tz_th = timezone(timedelta(hours=7))
                    save_to_supabase([{"Time": datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S"), "Match": match_name, "HDP": target['hdp'], "Target": target['n'], "EV_Pct": round(net_ev*100, 2), "Investment": round(inv, 2), "Odds": target['odds'], "Closing_Odds": 0.0, "Result": ""}])
                else: st.error(f"🚫 REJECTED: {ai_res.get('final_comment')}")

# --- 📊 TAB 2: DASHBOARD & DEBRIEF ---
with tab2:
    logs = load_logs()
    if logs is not None and not logs.empty:
        st.subheader("📝 บันทึกผล (อัปเดตราคาปิด & สกอร์)")
        df_edit = st.data_editor(logs, column_config={"id": None, "Result": "สกอร์จบ", "Closing_Odds": st.column_config.NumberColumn("Closing Odds", format="%.2f")}, use_container_width=True)
        if st.button("💾 Save to Cloud", type="primary"): 
            for _, r in df_edit.iterrows():
                supabase.table("investment_logs").update({"Closing_Odds": float(r['Closing_Odds']), "Result": str(r['Result'])}).eq("id", r['id']).execute()
            st.success("อัปเดตเรียบร้อย!"); st.rerun()

        # --- AUTO DEBRIEF (LEVEL 5) ---
        st.markdown("---")
        st.subheader("🤖 AI Daily Debrief (วิเคราะห์ & อัปเดตกฎอัตโนมัติ)")
        loss_logs = logs[logs['Result'].str.contains(r'-', na=False)]
        if len(loss_logs) > 0:
            st.info(f"🔍 พบประวัติการลงทุน {len(loss_logs)} รายการให้ชันสูตร")
            if st.button("🧠 สั่ง AI วิเคราะห์และปิดจุดอ่อนอัตโนมัติ", use_container_width=True, type="primary"):
                with st.spinner("The Oracle กำลังเขียนกฎใหม่ลงฐานข้อมูล..."):
                    loss_data_str = loss_logs[['Time', 'Match', 'HDP', 'Target', 'Odds', 'Result']].to_csv(index=False)
                    try:
                        rules_res = supabase.table("gem_knowledge").select("rule_id, category, rule_text").eq("is_active", True).execute()
                        rules_str = "\n".join([f"[{r['rule_id']} - หมวด {r['category']}] {r['rule_text']}" for r in (rules_res.data or [])])
                    except: rules_str = ""

                    prompt_debrief = (
                        "คุณคือ Chief Risk Officer ทำการ Post-Mortem จากข้อมูลแพ้ด้านล่าง\n\n"
                        f"📋 [ประวัติ]\n{loss_data_str}\n\n"
                        f"📖 [กฎเดิมที่มีอยู่แล้ว ห้ามสร้างซ้ำ]\n{rules_str}\n\n"
                        "สร้างกฎใหม่ (โครงสร้างราคา/เวลา/เรต) เพื่อป้องกันเหตุการณ์นี้ ตอบกลับเป็น JSON:\n"
                        '{"analysis_summary": "สรุปสั้นๆ", "new_rules_to_add": [{"rule_text": "ห้าม...หาก...", "category": "Risk Management"}]}'
                    )
                    
                    try:
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        res_debrief = model.generate_content(prompt_debrief)
                        data = safe_json_loads(res_debrief.text)
                        if data:
                            st.info(f"**วิเคราะห์:** {data.get('analysis_summary', '')}")
                            new_rules = data.get("new_rules_to_add", [])
                            if new_rules:
                                insert_payload = []
                                tz_th = timezone(timedelta(hours=7))
                                base_id = datetime.now(tz_th).strftime("%Y%m%d_%H%M")
                                for idx, rule in enumerate(new_rules):
                                    rule_id = f"GEM_AUTO_{base_id}_{idx+1}"
                                    insert_payload.append({"rule_id": rule_id, "rule_text": rule.get("rule_text", ""), "category": rule.get("category", "Auto")})
                                    st.warning(f"**[{rule_id}]** {rule.get('rule_text')}")
                                supabase.table("gem_knowledge").insert(insert_payload).execute()
                                if 'load_gem_rules' in globals(): load_gem_rules.clear()
                                st.success("💾 เพิ่มกฎลง Supabase อัตโนมัติแล้ว!")
                            else: st.write("🎉 เป็นแค่ Variance ไม่ต้องเพิ่มกฎใหม่")
                    except Exception as e: st.error(f"Error: {e}")

# --- ⚡ TAB 3: LIVE SNIPER ---
with tab3:
    st.header("📺 Live Sniper Command Center")
    col_l1, col_l2 = st.columns(2)
    with col_l1:
        st.subheader("🏁 สถานะเกมปัจจุบัน")
        st.session_state['lh_s_input'] = int(safe_float(st.session_state.get('lh_s_input', 0), 0, 0, 20))
        st.session_state['la_s_input'] = int(safe_float(st.session_state.get('la_s_input', 0), 0, 0, 20))
        st.session_state['current_min'] = int(safe_float(st.session_state.get('current_min', 45), 45, 0, 120))
        sc_h = st.number_input("สกอร์เหย้า", min_value=0, key="lh_s_input")
        sc_a = st.number_input("สกอร์เยือน", min_value=0, key="la_s_input")
        cur_min = st.slider("นาทีแข่งขัน", 0, 120, key="current_min")

    with col_l2:
        st.subheader("💡 ราคา Live")
        st.session_state['live_hdp'] = safe_float(st.session_state.get('live_hdp', 0.0), 0.0, -10.0, 10.0)
        st.session_state['live_hdp_h'] = safe_float(st.session_state.get('live_hdp_h', 0.9), 0.9, -2.0, 10.0)
        st.session_state['live_hdp_a'] = safe_float(st.session_state.get('live_hdp_a', 0.9), 0.9, -2.0, 10.0)
        st.session_state['live_ou'] = safe_float(st.session_state.get('live_ou', 2.5), 2.5, 0.5, 20.0)
        st.session_state['live_ou_over'] = safe_float(st.session_state.get('live_ou_over', 0.9), 0.9, -2.0, 10.0)
        st.session_state['live_ou_under'] = safe_float(st.session_state.get('live_ou_under', 0.9), 0.9, -2.0, 10.0)
        
        l_hdp = st.number_input("Live HDP", format="%.2f", step=0.25, key="live_hdp")
        c_hdp1, c_hdp2 = st.columns(2)
        l_hdp_h = c_hdp1.number_input("น้ำเหย้า", format="%.2f", key="live_hdp_h")
        l_hdp_a = c_hdp2.number_input("น้ำเยือน", format="%.2f", key="live_hdp_a")
        
        l_ou = st.number_input("Live O/U", format="%.2f", step=0.25, key="live_ou")
        c_ou1, c_ou2 = st.columns(2)
        l_ou_o = c_ou1.number_input("น้ำสูง", format="%.2f", key="live_ou_over")
        l_ou_u = c_ou2.number_input("น้ำต่ำ", format="%.2f", key="live_ou_under")

    if st.button("🎯 ENGAGE SNIPER (+ Auto API Fetch)", use_container_width=True, type="primary"):
        def fix(o): return o + 1.0 if o < 1.1 else o
        # สมมติราคาเปิดเท่ากับราคา Live ไปก่อนในเคสนี้ (หรือให้ User กรอกเพิ่มถ้าต้องการความแม่นยำ 100%)
        ph, pd, pa = shin_devig(fix(l_hdp_h), 3.0, fix(l_hdp_a)) 
        m_left = max(90 - cur_min, 1)
        hw2, hw1, dex, aw1, aw2, p_tot = calc_dixon_coles_matrix(ph, pd, pa, l_ou, fix(l_ou_o), fix(l_ou_u), dc_rho, sc_h, sc_a, m_left, False, False)
        
        is_fav = ph >= pa
        ev_h = calc_advanced_ah_ev(l_hdp, hw2, hw1, dex, aw1, aw2, fix(l_hdp_h), is_fav)
        ev_a = calc_advanced_ah_ev(l_hdp, aw2, aw1, dex, hw1, hw2, fix(l_hdp_a), not is_fav) - (hdba_val/100)
        ev_o = calc_advanced_ou_ev(l_ou, p_tot, fix(l_ou_o), True)
        ev_u = calc_advanced_ou_ev(l_ou, p_tot, fix(l_ou_u), False)

        b_ah_v = max(ev_h, ev_a); t_ah = "เจ้าบ้าน" if ev_h > ev_a else "ทีมเยือน"
        b_ou_v = max(ev_o, ev_u); t_ou = "สูง" if ev_o > ev_u else "ต่ำ"
        
        g1, g2 = st.columns(2)
        with g1: st.plotly_chart(create_ev_gauge(b_ah_v, f"AH: {t_ah}", live_ah_threshold), use_container_width=True)
        with g2: st.plotly_chart(create_ev_gauge(b_ou_v, f"O/U: {t_ou}", live_ou_threshold), use_container_width=True)

        if b_ah_v >= (live_ah_threshold/100) or b_ou_v >= (live_ou_threshold/100):
            target = {"n": t_ah, "ev": b_ah_v, "hdp": l_hdp, "odds": fix(l_hdp_h) if t_ah=="เจ้าบ้าน" else fix(l_hdp_a)} if b_ah_v > b_ou_v else {"n": t_ou, "ev": b_ou_v, "hdp": l_ou, "odds": fix(l_ou_o) if t_ou=="สูง" else fix(l_ou_u)}
            limit_to_use = (live_ah_threshold/100) if target['n'] in ["เจ้าบ้าน", "ทีมเยือน"] else (live_ou_threshold/100)
            
            with st.spinner("📡 กำลังดึงสถิติจาก iSports และส่งต่อให้ Oracle วิเคราะห์..."):
                # ดึงสถิติสดๆ ก่อนตัดสินใจ
                live_stats = fetch_isports_data(isports_key, st.session_state.get('match_name', ''))
                
                ai_live = ai_quant_decision_engine("Live", target['n'], target['ev'], target['hdp'], target['odds'], True, cur_min, f"{sc_h}-{sc_a}", threshold=limit_to_use, stats_data=live_stats)
                net_l_ev = target['ev'] + ai_live.get('impact_score', 0)
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Live EV", f"{target['ev']*100:.2f}%")
                c2.metric("Oracle Adjust", f"{ai_live.get('impact_score', 0)*100:.2f}%")
                c3.metric("Net Live EV", f"{net_l_ev*100:.2f}%")
                
                with st.expander("📖 อ่านบทวิเคราะห์ AI & ข้อมูล API", expanded=True):
                    st.write(f"**Pros:** {ai_live.get('pros_analysis')}")
                    st.write(f"**Cons:** {ai_live.get('cons_analysis')}")
                    st.write(f"**Rules:** {ai_live.get('rule_triggered')}")
                
                if ai_live.get('final_decision') and net_l_ev >= limit_to_use:
                    st.error(f"🚨 SNIPER ALERT: เป้า '{target['n']}' อนุมัติโจมตี!")
                    inv = min(((((target['odds']-1) * ((net_l_ev+1)/target['odds']) - (1-((net_l_ev+1)/target['odds']))) / (target['odds']-1)) * 0.25), 0.05) * total_bankroll
                    tz_th = timezone(timedelta(hours=7))
                    save_to_supabase([{"Time": datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S"), "Match": f"[LIVE] {st.session_state.get('match_name', 'Live Match')}", "HDP": target['hdp'], "Target": target['n'], "EV_Pct": round(net_l_ev*100, 2), "Investment": round(inv, 2), "Odds": target['odds'], "Closing_Odds": 0.0, "Result": ""}])
                else: st.warning(f"🚫 REJECTED: {ai_live.get('final_comment')}")

# --- 🧪 TAB 4: BACKTEST ---
with tab4: st.header("🧪 Backtest Data Management"); st.write("พร้อมเชื่อมต่อ API สถิติเต็มรูปแบบในอนาคต")
