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
    # [แก้ไข #5] ลบ `import json` ซ้ำซ้อนออก — ใช้ที่ import ระดับ module แทน
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

# [แก้ไข #2] ย้าย set_page_config ขึ้นมาก่อนทุกอย่าง — ต้องเป็น Streamlit call แรกเสมอ
st.set_page_config(page_title="GEM System 10.0 (The Oracle)", layout="wide", initial_sidebar_state="expanded")

@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_connection()

# ==========================================
# 0. SESSION STATE & CLOUD DATABASE
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
# 🧮 1. ระบบคณิตศาสตร์ขั้นสูง (Syndicate Quant Engine)
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
    
    # 1. ฐานความคาดหวังจากเจ้ามือ (Baseline)
    base_expected_total = ou_line + 0.20 + ((true_o_prob - 0.5) * 2.5) 
    
    # 🌟 FIX: Cross-Market Calibration (ปลดล็อก EV สูง/ต่ำ)
    draw_divergence = 0.25 - p_d 
    total_adjustment = draw_divergence * 8.0 
    
    # 2. จำนวนประตูที่คาดหวังใหม่ (หักล้างกับตลาด 1X2 แล้ว)
    expected_total = max(0.5, base_expected_total + total_adjustment)
    
    # 3. คำนวณพลังโจมตีและอัตราเวลา
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
    p_h2 = 0.0; p_h1 = 0.0; p_draw = 0.0; p_a1 = 0.0; p_a2 = 0.0; p_ou = {} 

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

# [แก้ไข #3] เพิ่ม case Under rm=0.75 ที่หายไป
def calc_advanced_ou_ev(ou_line, p_total, odds, is_over):
    b = odds - 1; fl = math.floor(ou_line); rm = ou_line - fl
    if is_over:
        if rm == 0.0:
            return (sum(p_total.get(k, 0) for k in p_total if k > fl) * b) \
                 - (sum(p_total.get(k, 0) for k in p_total if k < fl) * 1)
        elif rm == 0.25:
            return (sum(p_total.get(k, 0) for k in p_total if k >= fl + 1) * b) \
                 - (p_total.get(fl, 0) * 0.5) \
                 - (sum(p_total.get(k, 0) for k in p_total if k < fl) * 1)
        elif rm == 0.5:
            return (sum(p_total.get(k, 0) for k in p_total if k >= fl + 1) * b) \
                 - (sum(p_total.get(k, 0) for k in p_total if k <= fl) * 1)
        elif rm == 0.75:
            return (sum(p_total.get(k, 0) for k in p_total if k >= fl + 2) * b) \
                 + (p_total.get(fl + 1, 0) * (b / 2)) \
                 - (sum(p_total.get(k, 0) for k in p_total if k <= fl) * 1)
    else:
        if rm == 0.0:
            return (sum(p_total.get(k, 0) for k in p_total if k < fl) * b) \
                 - (sum(p_total.get(k, 0) for k in p_total if k > fl) * 1)
        elif rm == 0.25:
            return (sum(p_total.get(k, 0) for k in p_total if k < fl) * b) \
                 + (p_total.get(fl, 0) * (b / 2)) \
                 - (sum(p_total.get(k, 0) for k in p_total if k >= fl + 1) * 1)
        elif rm == 0.5:
            return (sum(p_total.get(k, 0) for k in p_total if k <= fl) * b) \
                 - (sum(p_total.get(k, 0) for k in p_total if k >= fl + 1) * 1)
        elif rm == 0.75:
            # [แก้ไข #3] เพิ่ม case นี้ที่หายไปในโค้ดเดิม
            # Under 2.75 = เสียครึ่งถ้ารวม 3 ลูก, แพ้เต็มถ้ารวม 4+
            return (sum(p_total.get(k, 0) for k in p_total if k <= fl) * b) \
                 - (p_total.get(fl + 1, 0) * 0.5) \
                 - (sum(p_total.get(k, 0) for k in p_total if k >= fl + 2) * 1)
    return 0.0

# ==========================================
# 🧠 2. ระบบ AI Decision Engine (Chief Risk Officer)
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
    if is_target_fav is True:
        role_info = " [สถานะ: ทีมต่อ (Favorite)]"
    elif is_target_fav is False:
        role_info = " [สถานะ: ทีมรอง (Underdog)]"

    prompt = (
        f"คุณคือ Chief Risk Officer (CRO) ประจำกองทุน Quant Sports Betting\n"
        f"วิสัยทัศน์: ลงทุนเพื่อเอาชนะ Margin ของเจ้ามือด้วยหลักการ Expected Value (EV)\n\n"
        f"[ข้อมูลหน้างาน]\n"
        f"- คู่: {match_name}\n"
        f"- สถานการณ์: {'Live ' + str(current_min) + ' min (' + score + ')' if is_live else 'Pre-Match'}\n"
        f"- เป้าหมาย: {target}{role_info} (เรต {abs(hdp_line)}, Odds {odds})\n"
        f"- Base EV: {base_ev * 100:.2f}%\n\n"
        f"📊 [ข้อมูลสถิติเชิงลึก (ถ้ามี)]\n"
        f"{stats_data}\n\n"
        f"{mode_instruction}\n\n"
        f"📖 [คัมภีร์ GEM RULES จาก CLOUD]\n"
        f"{oracle_database}\n\n"
        "คำสั่งพิเศษ:\n"
        "1. เช็คสถานะ 'ทีมต่อ/ทีมรอง' ในข้อมูลหน้างานให้ดี ห้ามสับสน! กฎบางข้อห้ามใช้กับทีมรองเด็ดขาด\n"
        "2. ⚠️ แยกแยะตลาด (Market Isolation): หากเป้าหมายคือตลาด แฮนดิแคป (ทีมต่อ/ทีมรอง) ห้ามนำกฎของตลาด สูง/ต่ำ (O/U) มาใช้พิจารณาเด็ดขาด และในทางกลับกัน\n"
        "3. หากมีการละเมิดกฎ หรือนำกฎข้อใดมาพิจารณา 'ต้อง' ระบุ [Rule ID] และ [Category] ให้ชัดเจน\n"
        "4. ค่า impact_score ต้องเป็นทศนิยมเท่านั้น (เช่น 0.05 คือปรับเพิ่ม 5%, -0.10 คือปรับลด 10%) ห้ามส่งค่าตัวเลขเกิน 1.0 หรือต่ำกว่า -1.0 เด็ดขาด\n\n"
        "ตอบกลับเป็น JSON Format (ภาษาไทย) เท่านั้น:\n"
        "{\n"
        '    "pros_analysis": "วิเคราะห์ข้อดีทางคณิตศาสตร์ (และสถิติถ้ามี)",\n'
        '    "cons_analysis": "ระบุความเสี่ยงและกฎที่ตรวจพบ (ระบุ ID ด้วย)",\n'
        '    "rule_triggered": "ระบุเฉพาะ Rule ID และหมวดหมู่",\n'
        '    "impact_score": 0.0,\n'
        '    "final_decision": true,\n'
        '    "final_comment": "บทสรุปฟันธงจาก CRO",\n'
        '    "confidence_level": 3\n'
        "}"
    )
    
    for attempt in range(3):
        try:
            model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
            response = model.generate_content(prompt)
            data = safe_json_loads(response.text)
            if data:
                impact = float(data.get('impact_score', 0.0))
                if abs(impact) >= 1.0: 
                    impact = impact / 100.0 
                data['impact_score'] = impact
                return data
        except Exception as e:
            if attempt == 2:
                return {
                    "pros_analysis": "ระบบ AI ขัดข้องชั่วคราว", "cons_analysis": f"Error: {str(e)}",
                    "rule_triggered": "System Fallback Activated", "impact_score": 0.0,
                    "final_decision": True if base_ev >= threshold else False,
                    "final_comment": "⚠️ ยืนยันไม้ด้วยคณิตศาสตร์ (Base EV) เนื่องจาก AI ไม่ตอบสนอง", "confidence_level": 1
                }
            time.sleep(2)

# ==========================================
# 📊 UI / UX Components & Cloud Analytics
# ==========================================
def create_ev_gauge(ev_value, title, threshold=8.0):
    ev_pct = ev_value * 100
    if ev_pct >= threshold: color = "#00FF7F" 
    elif ev_pct > 0: color = "#FFD700" 
    else: color = "#FF4500" 
        
    fig = go.Figure(go.Indicator(
        mode = "gauge+number", value = ev_pct,
        number = {'suffix': "%", 'font': {'color': color, 'size': 30}},
        title = {'text': title, 'font': {'size': 16, 'color': 'white'}},
        gauge = {
            'axis': {'range': [-20, 20], 'tickwidth': 1, 'tickcolor': "white"},
            'bar': {'color': color}, 'bgcolor': "rgba(0,0,0,0.1)", 'borderwidth': 1, 'bordercolor': "gray",
            'steps': [{'range': [-20, 0], 'color': "rgba(255, 69, 0, 0.15)"}, {'range': [0, threshold], 'color': "rgba(255, 215, 0, 0.15)"}, {'range': [threshold, 20], 'color': "rgba(0, 255, 127, 0.15)"}],
            'threshold': {'line': {'color': "white", 'width': 3}, 'thickness': 0.75, 'value': ev_pct}
        }
    ))
    fig.update_layout(height=200, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig

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
# 🎯 3. UI - Main Layout
# ==========================================
st.title("🎯 GEM System 10.0: The Oracle")

st.sidebar.header("🔑 AI Oracle Integration")
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    st.sidebar.success("✅ AI Connected (Auto Secrets)")
else:
    api_key = st.sidebar.text_input("ใส่ Gemini API Key:", type="password")
    if api_key:
        genai.configure(api_key=api_key)
        st.sidebar.success("✅ AI Connected")
    else: st.sidebar.warning("⚠️ โปรดใส่ API Key")

st.sidebar.header("🗄️ Database Status")
if supabase:
    st.sidebar.success("☁️ Supabase: Connected")
    st.sidebar.info("📚 ระบบอ่านคัมภีร์จาก Cloud อัตโนมัติ")
else: st.sidebar.error("❌ Supabase: Disconnected (เช็ค Secrets)")

tab1, tab2, tab3, tab4 = st.tabs(["🚀 Pre-Match Terminal", "📊 Dashboard & AI Debrief", "⚡ IN-PLAY LIVE", "🧪 Backtest Engine (RPS)"])

# --- 🚀 TAB 1: Pre-Match ---
with tab1:
    st.sidebar.header("💰 Portfolio & Parameters")
    total_bankroll = st.sidebar.number_input("เงินทุนทั้งหมด (THB)", min_value=0.0, value=10000.0)
    dc_rho = st.sidebar.slider("🔗 Dixon-Coles Rho", -0.30, 0.0, -0.10, step=0.01)
    hdba_val = st.sidebar.slider("⚖️ HDBA Penalty %", 0.0, 10.0, 1.5, step=0.5)
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("🎯 Pre-Match EV Threshold")
    pre_ah_threshold = st.sidebar.slider("เป้า AH (Pre) %", 1.0, 15.0, 5.0, step=0.5)
    pre_ou_threshold = st.sidebar.slider("เป้า O/U (Pre) %", 1.0, 15.0, 5.0, step=0.5)
    st.sidebar.subheader("⚡ In-Play EV Threshold")
    live_ah_threshold = st.sidebar.slider("เป้า AH (Live) %", 5.0, 50.0, 20.0, step=1.0)
    live_ou_threshold = st.sidebar.slider("เป้า O/U (Live) %", 5.0, 50.0, 20.0, step=1.0)

    pre_ah_limit = pre_ah_threshold / 100.0
    pre_ou_limit = pre_ou_threshold / 100.0
    live_ah_limit = live_ah_threshold / 100.0
    live_ou_limit = live_ou_threshold / 100.0

    st.markdown("---")
    
    with st.expander("👁️ AI Vision: สกัดราคาจากภาพ", expanded=False):
        if not api_key: st.warning("⚠️ ต้องการ API Key")
        else:
            uploaded_file = st.file_uploader("อัปโหลดรูปตารางราคา", type=['png', 'jpg'])
            if uploaded_file and st.button("🪄 สกัดข้อมูลจากรูปภาพ", use_container_width=True):
                with st.spinner('กำลังอ่านรูป...'):
                    try:
                        img = Image.open(uploaded_file)
                        model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
                        prompt_img = 'สกัดข้อมูลจากภาพแปลงเป็น JSON: {"match_name":"","h1x2_val":0,"d1x2_val":0,"a1x2_val":0,"hdp_line_val":0,"hdp_h_w_val":0,"hdp_a_w_val":0,"ou_line_val":0,"ou_over_w_val":0,"ou_under_w_val":0}'
                        res = model.generate_content([prompt_img, img])
                        data = safe_json_loads(res.text)
                        for k, v in data.items(): st.session_state[k] = v
                        st.success("✅ สำเร็จ!"); st.rerun()
                    except Exception as e: st.error(f"⚠️ พลาด: {e}")

    with st.expander("⚡ Text Parser: วางข้อความดิบ", expanded=False):
        st.text_area("📋 ก๊อปปี้ราคาทั้งก้อนจากหน้าเว็บมาวางตรงนี้...", height=100, key="raw_text")
        c_b1, c_b2 = st.columns(2)
        with c_b1:
            if st.button("🪄 สกัดข้อมูลจากข้อความ", use_container_width=True):
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
                    st.success("✅ สำเร็จ!")
                except Exception as e: st.error(f"⚠️ Error: {e}")
        with c_b2: st.button("🗑️ ล้างฟอร์ม", use_container_width=True, on_click=clear_form_data)

    st.markdown("---")
    match_name = st.text_input("📝 คู่แข่งขัน", key="match_name")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1. พูล & AH")
        h1x2 = st.number_input("เหย้า (1X2)", format="%.2f", key="h1x2_val")
        d1x2 = st.number_input("เสมอ (1X2)", format="%.2f", key="d1x2_val")
        a1x2 = st.number_input("เยือน (1X2)", format="%.2f", key="a1x2_val")
        hdp_line = st.number_input("เรต (HDP)", format="%.2f", step=0.25, key="hdp_line_val")
        hdp_h_w = st.number_input("น้ำเจ้าบ้าน", format="%.2f", key="hdp_h_w_val")
        hdp_a_w = st.number_input("น้ำทีมเยือน", format="%.2f", key="hdp_a_w_val")
    with col2:
        st.subheader("2. ตลาด O/U")
        ou_line = st.number_input("เรต (O/U)", format="%.2f", step=0.25, key="ou_line_val")
        ou_over_w = st.number_input("น้ำสูง (Over)", format="%.2f", key="ou_over_w_val")
        ou_under_w = st.number_input("น้ำต่ำ (Under)", format="%.2f", key="ou_under_w_val")

    st.subheader("📊 ข้อมูลสถิติเพิ่มเติม (Optional)")
    match_stats = st.text_area("ก๊อปปี้สถิติย้อนหลัง (H2H, ฟอร์ม) จากเว็บอื่นมาวาง เพื่อให้ AI วิเคราะห์ร่วมด้วย", height=100)

    if st.button("🚀 ANALYZE PRE-MATCH", use_container_width=True):
        def fix(o): return o + 1.0 if o < 1.1 else o
        h_o, d_o, a_o = fix(h1x2), fix(d1x2), fix(a1x2)
        hw_o, aw_o, ow_o, uw_o = fix(hdp_h_w), fix(hdp_a_w), fix(ou_over_w), fix(ou_under_w)
        prob_h, prob_d, prob_a = shin_devig(h_o, d_o, a_o)
        hw2, hw1, d_exact, aw1, aw2, p_total = calc_dixon_coles_matrix(prob_h, prob_d, prob_a, ou_line, ow_o, uw_o, dc_rho)
        
        is_h_fav = prob_h >= prob_a
        ev_h = calc_advanced_ah_ev(hdp_line, hw2, hw1, d_exact, aw1, aw2, hw_o, is_fav=is_h_fav)
        ev_a = calc_advanced_ah_ev(hdp_line, aw2, aw1, d_exact, hw1, hw2, aw_o, is_fav=not is_h_fav) - (hdba_val/100)
        ev_over = calc_advanced_ou_ev(ou_line, p_total, ow_o, True)
        ev_under = calc_advanced_ou_ev(ou_line, p_total, uw_o, False)

        best_ah = max([{"n": "เจ้าบ้าน", "ev": ev_h, "odds": hw_o, "hdp": hdp_line}, {"n": "ทีมเยือน", "ev": ev_a, "odds": aw_o, "hdp": hdp_line}], key=lambda x: x['ev'])
        best_ou = max([{"n": "สูง", "ev": ev_over, "odds": ow_o, "hdp": ou_line}, {"n": "ต่ำ", "ev": ev_under, "odds": uw_o, "hdp": ou_line}], key=lambda x: x['ev'])

        st.markdown("---")
        st.markdown("<h3 style='text-align: center;'>📊 ANALYZE PRE-MATCH (ผลวิเคราะห์คณิตศาสตร์)</h3>", unsafe_allow_html=True)
        st.markdown("<h5 style='text-align: center; color: #aaaaaa;'>📈 สถิติความน่าจะเป็น (Implied Probabilities)</h5>", unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        col1.metric(label="🏠 โอกาสเจ้าบ้านชนะ", value=f"{prob_h*100:.1f}%")
        col2.metric(label="🤝 โอกาสเสมอ", value=f"{prob_d*100:.1f}%")
        col3.metric(label="✈️ โอกาสเยือนชนะ", value=f"{prob_a*100:.1f}%")

        g1, g2 = st.columns(2)
        with g1: 
            st.markdown("<h4 style='text-align: center; color: #4db8ff;'>🔵 ตลาดแฮนดิแคป (AH)</h4>", unsafe_allow_html=True)
            st.plotly_chart(create_ev_gauge(best_ah['ev'], f"เป้าหมาย: {best_ah['n']}", pre_ah_threshold), use_container_width=True)
        with g2: 
            st.markdown("<h4 style='text-align: center; color: #ff9933;'>🟠 ตลาดสกอร์รวม (O/U)</h4>", unsafe_allow_html=True)
            st.plotly_chart(create_ev_gauge(best_ou['ev'], f"เป้าหมาย: {best_ou['n']}", pre_ou_threshold), use_container_width=True)

        ah_passed = best_ah['ev'] >= pre_ah_limit
        ou_passed = best_ou['ev'] >= pre_ou_limit

        if ah_passed or ou_passed:
            target_to_check = best_ah if best_ah['ev'] > best_ou['ev'] else best_ou

            if not api_key: st.warning("⚠️ กรุณาใส่ API Key ให้ AI กรองความเสี่ยง")
            else:
                with st.spinner("🧠 THE ORACLE กำลังตรวจสอบ EV และสถิติ..."):
                    t_fav = None
                    if target_to_check['n'] == "เจ้าบ้าน": t_fav = is_h_fav
                    elif target_to_check['n'] == "ทีมเยือน": t_fav = not is_h_fav
                    
                    ai_verdict = ai_quant_decision_engine(match_name, target_to_check['n'], target_to_check['ev'], target_to_check['hdp'], target_to_check['odds'], is_live=False, threshold=pre_ah_limit, stats_data=match_stats, is_target_fav=t_fav)
                    net_ev = target_to_check['ev'] + ai_verdict.get('impact_score', 0)
                
                st.markdown("---")
                c1, c2, c3 = st.columns(3)
                c1.metric("Base EV", f"{target_to_check['ev']*100:.2f}%")
                c2.metric("Oracle Rule Adjust", f"{ai_verdict.get('impact_score', 0)*100:.2f}%")
                c3.metric("Net EV", f"{net_ev*100:.2f}%")
                
                with st.expander("📖 รายละเอียดการวิเคราะห์จาก THE ORACLE", expanded=True):
                    stars_count = ai_verdict.get('confidence_level', 3)
                    st.markdown(f"#### 🎯 ระดับความมั่นใจ: {'⭐' * stars_count} ({stars_count}/5)")
                    st.markdown("---")
                    st.success(f"**✅ ข้อดี (Pros):** {ai_verdict.get('pros_analysis', 'ไม่มี')}")
                    st.error(f"**⚠️ ข้อควรระวัง (Cons):** {ai_verdict.get('cons_analysis', 'ไม่มี')}")
                    st.info(f"**📜 กฎที่ทำงาน:** {ai_verdict.get('rule_triggered', 'None')}")
                
                if ai_verdict.get('final_decision', False) and net_ev > 0:
                    st.balloons()
                    st.success(f"✅ ORACLE APPROVED: {ai_verdict.get('final_comment', 'Good')}")
                    inv = min( (((target_to_check['odds']-1) * ((net_ev+1)/target_to_check['odds']) - (1-((net_ev+1)/target_to_check['odds']))) / (target_to_check['odds']-1)) * 0.25, 0.05) * total_bankroll
                    tz_th = timezone(timedelta(hours=7))
                    save_to_supabase([{"Time": datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S"), "Match": match_name, "HDP": target_to_check['hdp'], "Target": target_to_check['n'], "EV_Pct": round(net_ev*100, 2), "Investment": round(inv, 2), "Odds": target_to_check['odds'], "Closing_Odds": 0.0, "Result": ""}])
                else:
                    st.error(f"🚫 ORACLE REJECTED: {ai_verdict.get('final_comment', 'Pass')}")
        else:
            st.warning(f"🛡️ เป้าหมายไม่ถึงเกณฑ์ที่ตั้งไว้ (AH: {pre_ah_threshold}%, O/U: {pre_ou_threshold}%)")

# --- 📊 TAB 2: Dashboard & AI Debrief ---
with tab2:
    # [แก้ไข #4] เรียก load_logs() ครั้งเดียวและเก็บในตัวแปร tab2_logs
    # เพื่อไม่ให้ชนกับตัวแปร logs ที่ Tab 4 จะเรียกแยกต่างหาก
    tab2_logs = load_logs()
    if not tab2_logs.empty:
        st.subheader("📝 บันทึกผล & ราคาปิด (Closing Odds) - Cloud Sync")
        col_edit1, col_edit2 = st.columns([1, 2])
        with col_edit1:
            edit_filter = st.selectbox("🔍 เลือกรายการที่จะแสดงในตาราง:", ["แสดงเฉพาะวันนี้", "แสดงเฉพาะรายการที่ยังไม่ลงผล", "แสดงทั้งหมด"], index=0)
        
        df_to_edit = tab2_logs.copy()
        tz_th = timezone(timedelta(hours=7))
        today_str = datetime.now(tz_th).strftime("%Y-%m-%d")

        if edit_filter == "แสดงเฉพาะวันนี้": df_to_edit = df_to_edit[df_to_edit['Time'].astype(str).str.contains(today_str, na=False)]
        elif edit_filter == "แสดงเฉพาะรายการที่ยังไม่ลงผล": df_to_edit = df_to_edit[df_to_edit['Result'].astype(str).str.strip() == ""]

        df_to_edit = df_to_edit.sort_values(by='Time', ascending=False).reset_index(drop=True)
        edited_df = st.data_editor(
            df_to_edit, 
            column_config={"id": None, "Result": st.column_config.TextColumn("Result (สกอร์)"), "Closing_Odds": st.column_config.NumberColumn("Closing Odds", min_value=0.0, format="%.2f")}, 
            use_container_width=True, num_rows="dynamic"
        )
        
        c_b1, c_b2 = st.columns(2)
        if c_b1.button("💾 Save Score to Cloud", use_container_width=True, type="primary"): 
            with st.spinner("กำลังอัปเดตข้อมูลบน Cloud..."):
                for _, row in edited_df.iterrows():
                    supabase.table("investment_logs").update({"Closing_Odds": float(row['Closing_Odds']), "Result": str(row['Result'])}).eq("id", row['id']).execute()
            st.success("อัปเดตเรียบร้อย!"); st.rerun()
            
        if c_b2.button("🗑️ Clear Local Cache"): st.rerun()
        
        tab2_logs['Net_Profit'] = tab2_logs.apply(calculate_net_profit, axis=1)
        tab2_logs['CLV_Pct'] = tab2_logs.apply(calculate_clv, axis=1)
        
        st.markdown("---")
        st.markdown("### 🎛️ โหมดการวิเคราะห์ (Dashboard View)")
        col_f1, col_f2 = st.columns(2)
        with col_f1: time_filter = st.radio("⏳ ช่วงเวลา:", ["🌍 ทั้งหมด (All Time)", "📅 เฉพาะวันนี้ (Today)"], horizontal=True)
        with col_f2: view_mode = st.radio("🎯 เลือกมิติข้อมูล:", ["🌍 ภาพรวม (All)", "🚀 ก่อนเตะ (Pre-Match)", "⚡ บอลสด (In-Play)"], horizontal=True)

        if time_filter == "📅 เฉพาะวันนี้ (Today)": time_filtered_logs = tab2_logs[tab2_logs['Time'].astype(str).str.contains(today_str, na=False)].copy()
        else: time_filtered_logs = tab2_logs.copy()

        if view_mode == "⚡ บอลสด (In-Play)": filtered_logs = time_filtered_logs[time_filtered_logs['Match'].str.contains(r'\[LIVE\]', na=False, case=False)]
        elif view_mode == "🚀 ก่อนเตะ (Pre-Match)": filtered_logs = time_filtered_logs[~time_filtered_logs['Match'].str.contains(r'\[LIVE\]', na=False, case=False)]
        else: filtered_logs = time_filtered_logs

        inv_logs = filtered_logs[filtered_logs['Investment'] > 0]
        
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("กำไรสุทธิ", f"{filtered_logs['Net_Profit'].sum():,.2f} THB")
        m2.metric("ลงทุนสะสม", f"{inv_logs['Investment'].sum():,.2f} THB")
        m3.metric("Win Rate", f"{(len(inv_logs[inv_logs['Net_Profit']>0])/len(inv_logs)*100 if not inv_logs.empty else 0):.1f}%")
        m4.metric("ROI", f"{(filtered_logs['Net_Profit'].sum()/inv_logs['Investment'].sum()*100 if not inv_logs.empty and inv_logs['Investment'].sum()>0 else 0):.2f}%")
        m5.metric("Average CLV", f"{inv_logs[inv_logs['Closing_Odds']>1.0]['CLV_Pct'].mean():.2f}%" if not inv_logs[inv_logs['Closing_Odds']>1.0].empty else "0.00%")
        
        if not filtered_logs.empty:
            logs_s = filtered_logs.sort_values(by='Time').copy()
            logs_s['Cumulative_Profit'] = logs_s['Net_Profit'].cumsum()
            line_color = '#FF8C00' if "In-Play" in view_mode else ('#1E90FF' if "Pre-Match" in view_mode else '#00FF7F')
            
            fig = go.Figure(go.Scatter(x=logs_s['Time'], y=logs_s['Cumulative_Profit'], mode='lines', fill='tozeroy', line=dict(color=line_color, width=3)))
            fig.update_layout(title=f"Equity Curve - {view_mode}", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("---")
            st.subheader("🎯 เจาะลึกประสิทธิภาพ (Performance Breakdown)")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("#### 📊 กำไรแยกตามเป้าหมาย (Target)")
                target_stats = logs_s.groupby('Target')['Net_Profit'].sum()
                st.bar_chart(target_stats, color=line_color)
            with col_b:
                st.markdown("#### 🎯 อัตราการชนะแยกตามช่วงค่าน้ำ (%)")
                logs_s['Odds_Bin'] = pd.cut(logs_s['Odds'], bins=[0, 1.8, 2.0, 2.2, 5.0], labels=['<1.8', '1.8-2.0', '2.0-2.2', '>2.2'])
                wins = logs_s[logs_s['Net_Profit'] > 0].groupby('Odds_Bin', observed=False).size()
                totals = logs_s.groupby('Odds_Bin', observed=False).size()
                odds_win_rate = (wins / totals * 100).fillna(0)
                st.bar_chart(odds_win_rate, color=line_color)

        # ==========================================
        # 🤖 AI Oracle Learning
        # ==========================================
        st.markdown("---")
        st.subheader("🤖 AI Oracle Learning (พัฒนากฎจากชัยชนะและความพ่ายแพ้)")
        
        if 'Net_Profit' in tab2_logs.columns:
            completed_logs = tab2_logs[tab2_logs['Result'].astype(str).str.strip() != ""].copy()
        else:
            completed_logs = pd.DataFrame()
            
        if len(completed_logs) > 0:
            debrief_type = st.radio("🔍 เลือกประเภทข้อมูลที่จะให้ AI เรียนรู้:", 
                                   ["🔴 วิเคราะห์ความพ่ายแพ้ (หาจุดอ่อน/สร้างเกราะป้องกัน)", 
                                    "🟢 วิเคราะห์ชัยชนะ (หาจุดแข็ง/หักล้างกฎเดิมที่ตึงเกินไป)", 
                                    "⚪ วิเคราะห์ผสม (เปรียบเทียบหารูปแบบ)"], 
                                   horizontal=True)
            
            if "🔴" in debrief_type:
                target_logs = completed_logs[completed_logs['Net_Profit'] < 0].copy()
                ai_task = "ทำ 'Post-Mortem Analysis' จากข้อมูลที่ขาดทุน ค้นหาจุดอ่อน และสร้างกฎเพื่อป้องกันความผิดพลาดเดิม (Defensive Rules)"
                prefix_id = "GEM_DEF_"
            elif "🟢" in debrief_type:
                target_logs = completed_logs[completed_logs['Net_Profit'] > 0].copy()
                ai_task = "ทำ 'Success Analysis' จากข้อมูลที่ได้กำไร ค้นหารูปแบบที่ชนะตลาด และสร้างกฎเชิงบวก (Offensive Rules) เช่น 'ให้เพิ่มความมั่นใจหาก...' หรือ 'สามารถใช้ยกเว้นกฎความเสี่ยงข้ออื่นได้หากเข้าเงื่อนไขนี้'"
                prefix_id = "GEM_OFF_"
            else:
                target_logs = completed_logs.copy()
                ai_task = "วิเคราะห์เปรียบเทียบทั้งไม้ที่ชนะและแพ้ ค้นหารูปแบบความสำเร็จและความล้มเหลว เพื่อสร้างหรือปรับปรุงกฎในคัมภีร์ให้มีความสมดุล"
                prefix_id = "GEM_MIX_"
            
            if len(target_logs) > 0:
                st.info(f"📋 พบข้อมูลตรงตามเงื่อนไขจำนวน {len(target_logs)} รายการ โปรดติ๊กเลือกแมตช์ที่ต้องการให้ AI เรียนรู้")
                
                target_logs.insert(0, "Analyze", False)
                
                debrief_selection = st.data_editor(
                    target_logs[['Analyze', 'Time', 'Match', 'HDP', 'Target', 'Odds', 'Result', 'Net_Profit']],
                    column_config={
                        "Analyze": st.column_config.CheckboxColumn("✅ เลือกวิเคราะห์", default=False),
                        "Net_Profit": st.column_config.NumberColumn("กำไร/ขาดทุน", format="%.2f")
                    },
                    hide_index=True,
                    use_container_width=True,
                    key="debrief_editor"
                )
                
                selected_for_debrief = debrief_selection[debrief_selection['Analyze'] == True]
                
                if st.button(f"🧠 สั่ง AI เรียนรู้จากข้อมูลที่เลือก", use_container_width=True, type="primary"):
                    if selected_for_debrief.empty:
                        st.warning("⚠️ โปรดติ๊กเลือกอย่างน้อย 1 รายการ ในตารางด้านบนก่อนครับ")
                    else:
                        with st.spinner(f"The Oracle กำลังเรียนรู้จาก {len(selected_for_debrief)} แมตช์ที่คุณเลือก..."):
                            loss_data_str = selected_for_debrief[['Time', 'Match', 'HDP', 'Target', 'Odds', 'Result']].to_csv(index=False)
                            try:
                                rules_res = supabase.table("gem_knowledge").select("rule_id, category, rule_text").eq("is_active", True).execute()
                                rules_str = "\n".join([f"[{r['rule_id']} - หมวด {r['category']}] {r['rule_text']}" for r in (rules_res.data or [])])
                            except: rules_str = ""

                            prompt_debrief = (
                                f"คุณคือ Chief Risk Officer และ Quant Analyst ของกองทุนกีฬา\n"
                                f"หน้าที่: {ai_task}\n\n"
                                f"📋 [ข้อมูล Case Study ที่ผู้บริหารคัดเลือกมา (CSV)]\n{loss_data_str}\n\n"
                                f"📖 [คัมภีร์ปัจจุบัน (เพื่อใช้เทียบเคียง)]\n{rules_str}\n\n"
                                "คำสั่ง:\n"
                                "1. วิเคราะห์เจาะลึกสาเหตุของผลลัพธ์จากข้อมูลที่ให้มา\n"
                                "2. สร้างข้อเสนอเป็น 'กฎข้อใหม่' เชิงเทคนิค (โครงสร้างราคา/เวลา/เรต) ห้ามเจาะจงชื่อทีม\n"
                                "3. ⚠️ ต้องระบุประเภทตลาดของกฎให้ชัดเจน โดยใส่ป้ายกำกับไว้ที่ Category: ใช้ [AH] สำหรับกฎแฮนดิแคป, [OU] สำหรับกฎสูง/ต่ำ, หรือ [ALL] หากใช้ได้กับทุกตลาด\n"
                                "4. หากเป็นชัยชนะ ให้เน้นสร้างกฎเพื่อเจาะทำกำไร หรือกฎที่ใช้ผ่อนปรนความเข้มงวดของกฎเดิม\n"
                                "ตอบกลับเป็น JSON Format (ภาษาไทย) เท่านั้น:\n"
                                '{"analysis_summary": "สรุปผลการวิเคราะห์เชิงลึก", "new_rules_to_add": [{"rule_text": "เนื้อหากฎ...", "category": "Risk Management [AH]"}]}'
                            )
                            
                            try:
                                if "GEMINI_API_KEY" not in st.secrets and not api_key: 
                                    st.error("⚠️ ไม่พบ API Key กรุณาใส่ API Key ใน Sidebar")
                                else:
                                    model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
                                    res_debrief = model.generate_content(prompt_debrief)
                                    data = safe_json_loads(res_debrief.text)
                                    
                                    if data:
                                        st.success("✅ กระบวนการเรียนรู้เสร็จสิ้น!")
                                        st.info(f"**บทวิเคราะห์จาก CRO:**\n{data.get('analysis_summary', 'ไม่มีคำอธิบาย')}")
                                        
                                        new_rules = data.get("new_rules_to_add", [])
                                        if new_rules:
                                            insert_payload = []
                                            base_id = datetime.now(timezone(timedelta(hours=7))).strftime("%Y%m%d_%H%M")
                                            
                                            st.write("### 📜 กฎใหม่ที่ระบบสร้างและบันทึกอัตโนมัติ:")
                                            for idx, rule in enumerate(new_rules):
                                                rule_id = f"{prefix_id}{base_id}_{idx+1}"
                                                insert_payload.append({"rule_id": rule_id, "rule_text": rule.get("rule_text", ""), "category": rule.get("category", "AI Learning")})
                                                
                                                if "DEF" in prefix_id: st.error(f"**[{rule_id} - {rule.get('category')}]** {rule.get('rule_text')}")
                                                elif "OFF" in prefix_id: st.success(f"**[{rule_id} - {rule.get('category')}]** {rule.get('rule_text')}")
                                                else: st.warning(f"**[{rule_id} - {rule.get('category')}]** {rule.get('rule_text')}")
                                            
                                            supabase.table("gem_knowledge").insert(insert_payload).execute()
                                            # [แก้ไข #8 ใน original] clear cache อย่างถูกวิธี
                                            load_gem_rules.clear()
                                            st.balloons()
                                            st.success("💾 ซิงค์การเรียนรู้ลงฐานข้อมูล (Supabase) อัตโนมัติเรียบร้อยแล้ว!")
                                        else: st.write("🎉 AI ประเมินว่าเคสนี้ไม่จำเป็นต้องสร้างกฎใหม่ (ความผิดพลาดอาจเกิดจาก Variance เล็กน้อย)")
                                    else: st.error("⚠️ AI ตอบกลับผิดรูปแบบ JSON ไม่สามารถดึงข้อมูลกฎได้")
                            except Exception as e: st.error(f"❌ ระบบขัดข้องระหว่างการบันทึก: {e}")
            else:
                st.write("ยังไม่มีประวัติการลงทุนในหมวดหมู่นี้ครับ")
        else: st.info("ℹ️ ยังไม่มีประวัติการลงทุนที่ทราบผลลัพธ์เพื่อนำมาวิเคราะห์")

# --- ⚡ TAB 3: IN-PLAY LIVE ---
with tab3:
    st.header("📺 Live Sniper Command Center")
    with st.expander("👁️ AI Live Vision", expanded=False):
        if not api_key: st.warning("⚠️ ต้องการ API Key")
        else:
            live_images = st.file_uploader("อัปโหลดรูป (สูงสุด 3 รูป)", type=['png', 'jpg'], accept_multiple_files=True)
            if live_images and st.button("🪄 สกัดข้อมูล", use_container_width=True):
                with st.spinner("กวาดสายตา..."):
                    try:
                        imgs = [Image.open(f) for f in live_images]
                        model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
                        prompt_live = 'สกัดเป็น JSON: {"current_min":0, "current_score_h":0, "current_score_a":0, "pre_h":2.0, "pre_d":3.0, "pre_a":3.0, "pre_ou":2.5, "live_hdp":0.0, "live_hdp_h":0.9, "live_hdp_a":0.9, "live_ou":2.5, "live_ou_over":0.9, "live_ou_under":0.9}'
                        res = model.generate_content([prompt_live] + imgs)
                        data = safe_json_loads(res.text)
                        for k, v in data.items(): st.session_state[k] = float(v) if 'score' not in k and 'min' not in k else int(v)
                        st.success("✅ สำเร็จ!"); st.rerun()
                    except Exception as e: st.error(f"⚠️ พลาด: {e}")

    col_l1, col_l2 = st.columns(2)
    with col_l1:
        st.subheader("🏁 สถานะเกมปัจจุบัน")
        c_h1, c_h2 = st.columns(2)
        current_score_h = c_h1.number_input("สกอร์เหย้า", min_value=0, value=st.session_state.get('lh_s_input', 0), key="lh_s_input")
        red_card_h = c_h2.checkbox("🟥 เหย้าใบแดง", key="rc_h")
        c_a1, c_a2 = st.columns(2)
        current_score_a = c_a1.number_input("สกอร์เยือน", min_value=0, value=st.session_state.get('la_s_input', 0), key="la_s_input")
        red_card_a = c_a2.checkbox("🟥 เยือนใบแดง", key="rc_a")
        current_min = st.slider("นาทีแข่งขัน", 0, 120, st.session_state.get('current_min', 45))
    with col_l2:
        st.subheader("💡 ราคาเปิด (Pre-match)")
        pre_h = st.number_input("เหย้า(เปิด)", value=st.session_state.get('pre_h', 2.0), format="%.2f", key="pre_h")
        pre_d = st.number_input("เสมอ(เปิด)", value=st.session_state.get('pre_d', 3.0), format="%.2f", key="pre_d")
        pre_a = st.number_input("เยือน(เปิด)", value=st.session_state.get('pre_a', 3.0), format="%.2f", key="pre_a")
        pre_ou = st.number_input("O/U(เปิด)", value=st.session_state.get('pre_ou', 2.5), format="%.2f", step=0.25, key="pre_ou")

    st.markdown("---")
    st.subheader("💰 ราคา Live ปัจจุบัน (Sniper Adjust)")
    col_live1, col_live2 = st.columns(2)
    
    with col_live1:
        st.markdown("**Live HDP (เรตแฮนดิแคป)**")
        btn_h1, btn_h2, btn_h3 = st.columns([1, 2, 1])
        btn_h1.button("➖ 0.25", key="h_sub", on_click=adj_hdp, args=(-0.25,))
        live_hdp = btn_h2.number_input("Live HDP", value=st.session_state['live_hdp'], step=0.25, key="live_hdp", label_visibility="collapsed", format="%.2f")
        btn_h3.button("➕ 0.25", key="h_add", on_click=adj_hdp, args=(0.25,))
        c_w1, c_w2 = st.columns(2)
        live_hdp_h = c_w1.number_input("น้ำเหย้า", value=st.session_state.get('live_hdp_h', 0.9), format="%.2f", key="live_hdp_h")
        live_hdp_a = c_w2.number_input("น้ำเยือน", value=st.session_state.get('live_hdp_a', 0.9), format="%.2f", key="live_hdp_a")

    with col_live2:
        st.markdown("**Live O/U (เรตสกอร์รวม)**")
        btn_o1, btn_o2, btn_o3 = st.columns([1, 2, 1])
        btn_o1.button("➖ 0.25", key="o_sub", on_click=adj_ou, args=(-0.25,))
        live_ou = btn_o2.number_input("Live O/U", value=st.session_state['live_ou'], step=0.25, key="live_ou", label_visibility="collapsed", format="%.2f")
        btn_o3.button("➕ 0.25", key="o_add", on_click=adj_ou, args=(0.25,))
        c_w3, c_w4 = st.columns(2)
        live_ou_over = c_w3.number_input("น้ำสูง", value=st.session_state.get('live_ou_over', 0.9), format="%.2f", key="live_ou_over")
        live_ou_under = c_w4.number_input("น้ำต่ำ", value=st.session_state.get('live_ou_under', 0.9), format="%.2f", key="live_ou_under")

    c_btn1, c_btn2 = st.columns([4, 1])
    submit_live = c_btn1.button("🎯 ENGAGE SNIPER", use_container_width=True, type="primary")
    c_btn2.button("🗑️ ล้างค่า", use_container_width=True, on_click=clear_inplay_data)

    if submit_live:
        def fix(o): return o + 1.0 if o < 1.1 else o
        p_h, p_d, p_a = shin_devig(fix(pre_h), fix(pre_d), fix(pre_a))
        m_left = max(90 - current_min, 1)
        hw2, hw1, d_ex, aw1, aw2, p_tot = calc_dixon_coles_matrix(p_h, p_d, p_a, live_ou, fix(live_ou_over), fix(live_ou_under), dc_rho, current_score_h, current_score_a, m_left, red_card_h, red_card_a)
        
        is_fav = p_h >= p_a
        ev_h = calc_advanced_ah_ev(live_hdp, hw2, hw1, d_ex, aw1, aw2, fix(live_hdp_h), is_fav)
        ev_a = calc_advanced_ah_ev(live_hdp, aw2, aw1, d_ex, hw1, hw2, fix(live_hdp_a), not is_fav) - (hdba_val/100)
        ev_o = calc_advanced_ou_ev(live_ou, p_tot, fix(live_ou_over), True)
        ev_u = calc_advanced_ou_ev(live_ou, p_tot, fix(live_ou_under), False)

        b_ah_v = max(ev_h, ev_a); t_ah = "เจ้าบ้าน" if ev_h > ev_a else "ทีมเยือน"
        b_ou_v = max(ev_o, ev_u); t_ou = "สูง" if ev_o > ev_u else "ต่ำ"
        
        g1, g2 = st.columns(2)
        with g1: st.plotly_chart(create_ev_gauge(b_ah_v, f"AH: {t_ah}", live_ah_threshold), use_container_width=True)
        with g2: st.plotly_chart(create_ev_gauge(b_ou_v, f"O/U: {t_ou}", live_ou_threshold), use_container_width=True)
        
        ah_live_passed = b_ah_v >= live_ah_limit
        ou_live_passed = b_ou_v >= live_ou_limit

        if ah_live_passed or ou_live_passed:
            t_live = {"n": t_ah, "ev": b_ah_v, "hdp": live_hdp, "odds": fix(live_hdp_h) if t_ah=="เจ้าบ้าน" else fix(live_hdp_a)} if b_ah_v > b_ou_v else {"n": t_ou, "ev": b_ou_v, "hdp": live_ou, "odds": fix(live_ou_over) if t_ou=="สูง" else fix(live_ou_under)}

            if not api_key: st.warning("⚠️ โปรดใส่ API Key ให้ AI ทำงาน")
            else:
                with st.spinner("🧠 กำลังวิเคราะห์ข้อมูลด้วย The Oracle..."):
                    t_fav = None
                    if t_live['n'] == "เจ้าบ้าน": t_fav = is_fav
                    elif t_live['n'] == "ทีมเยือน": t_fav = not is_fav
                    
                    ai_live = ai_quant_decision_engine("Live", t_live['n'], t_live['ev'], t_live['hdp'], t_live['odds'], True, current_min, f"{current_score_h}-{current_score_a}", threshold=live_ah_limit, stats_data="", is_target_fav=t_fav)
                    net_l_ev = t_live['ev'] + ai_live.get('impact_score', 0)
                    
                    st.markdown("---")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Live EV", f"{t_live['ev']*100:.2f}%")
                    c2.metric("Oracle Adjust", f"{ai_live.get('impact_score', 0)*100:.2f}%")
                    c3.metric("Net Live EV", f"{net_l_ev*100:.2f}%")
                    
                    with st.expander("📖 รายละเอียดการวิเคราะห์ (Live Mode)", expanded=True):
                        st.success(f"**✅ ข้อดี (Pros):** {ai_live.get('pros_analysis', 'ไม่มี')}")
                        st.error(f"**⚠️ ข้อควรระวัง (Cons):** {ai_live.get('cons_analysis', 'ไม่มี')}")
                        st.info(f"**📜 กฎที่ทำงาน:** {ai_live.get('rule_triggered', 'None')}")
                    
                    limit_to_use = live_ah_limit if t_live['n'] in ["เจ้าบ้าน", "ทีมเยือน"] else live_ou_limit
                    if ai_live.get('final_decision', False) and net_l_ev >= limit_to_use:
                        st.balloons()
                        st.error(f"🚨 SNIPER ALERT: เป้า '{t_live['n']}' อนุมัติโจมตี!")
                        st.success(f"✅ ORACLE: {ai_live.get('final_comment', 'Good')}")
                        
                        inv = min( (((t_live['odds']-1) * ((net_l_ev+1)/t_live['odds']) - (1-((net_l_ev+1)/t_live['odds']))) / (t_live['odds']-1)) * 0.25, 0.05) * total_bankroll
                        tz_th = timezone(timedelta(hours=7))
                        save_to_supabase([{"Time": datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S"), "Match": f"[LIVE] {st.session_state.get('match_name', 'Live Match')}", "HDP": t_live['hdp'], "Target": t_live['n'], "EV_Pct": round(net_l_ev*100, 2), "Investment": round(inv, 2), "Odds": t_live['odds'], "Closing_Odds": 0.0, "Result": ""}])
                    else: 
                        st.warning(f"🚫 ORACLE REJECTED (ทับมือ): {ai_live.get('final_comment', 'Pass')}")
        else: st.write(f"🛡️ ตลาดปกติ (ยังไม่ผ่านเกณฑ์เป้าหมายที่ตั้งไว้ AH: {live_ah_threshold}%, O/U: {live_ou_threshold}%)")

# ==========================================
# --- TAB 4: BACKTEST ENGINE ---
# ==========================================
with tab4:
    st.header("🧪 ระบบทดสอบความแม่นยำจากข้อมูลจริง (Live Backtest)")
    st.markdown("ระบบจะดึงข้อมูลบิลการลงทุน **ที่รู้ผลแล้ว** จาก Dashboard มาคำนวณย้อนหลัง เพื่อดูว่า AI ของเราประเมิน 'โอกาสชนะ' ได้แม่นยำกว่า 'ราคาของเจ้ามือ' หรือไม่ (ใช้มาตรฐาน Brier Score: ยิ่งใกล้ 0 ยิ่งแปลว่าทายแม่น)")
    
    # [แก้ไข #4] ใช้ตัวแปรชื่อ tab4_logs แทน logs เพื่อไม่ให้ชนกับ tab2_logs
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
                
                finished_logs['Our_Error'] = (finished_logs['Our_Prob'] - finished_logs['Actual_Score'])**2
                finished_logs['Bookie_Error'] = (finished_logs['Bookie_Prob'] - finished_logs['Actual_Score'])**2
                
                avg_our_error = finished_logs['Our_Error'].mean()
                avg_bookie_error = finished_logs['Bookie_Error'].mean()
                error_diff = avg_bookie_error - avg_our_error 
                
                st.subheader(f"📊 ผลประชันความแม่นยำจาก {len(finished_logs)} บิลล่าสุด")
                c1, c2, c3 = st.columns(3)
                c1.metric("🤖 ค่าความคลาดเคลื่อนของเรา (Error)", f"{avg_our_error:.4f}", f"{-error_diff:.4f} vs เจ้ามือ", delta_color="inverse")
                c2.metric("🎩 ค่าความคลาดเคลื่อนของบ่อน", f"{avg_bookie_error:.4f}")
                if avg_our_error < avg_bookie_error: c3.success("🏆 กองทุนเราชนะตลาด!")
                else: c3.error("💀 บ่อนยังแม่นกว่า (ต้องจูนสมการต่อ)")
                    
                st.markdown("#### 📈 กราฟเปรียบเทียบความแม่นยำสะสม (Cumulative Error)")
                st.caption("เส้นกราฟยิ่งอยู่ต่ำยิ่งดี (สะสมความผิดพลาดน้อยกว่า)")
                
                finished_logs = finished_logs.sort_values(by='Time').reset_index(drop=True)
                finished_logs['Cum_Our_Error'] = finished_logs['Our_Error'].cumsum()
                finished_logs['Cum_Bookie_Error'] = finished_logs['Bookie_Error'].cumsum()
                
                fig_bt = go.Figure()
                fig_bt.add_trace(go.Scatter(x=finished_logs.index, y=finished_logs['Cum_Our_Error'], mode='lines', name='GEM System Error', line=dict(color='#00FF7F', width=3)))
                fig_bt.add_trace(go.Scatter(x=finished_logs.index, y=finished_logs['Cum_Bookie_Error'], mode='lines', name='Bookmaker Error', line=dict(color='#FF4500', width=2, dash='dash')))
                fig_bt.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis_title="จำนวนไม้ที่ลงทุน", yaxis_title="ค่าความผิดพลาดสะสม")
                st.plotly_chart(fig_bt, use_container_width=True)
                
                with st.expander("🔍 ดูข้อมูลเปรียบเทียบเชิงลึก (Raw Data)"):
                    st.dataframe(finished_logs[['Time', 'Match', 'Target', 'Odds', 'Result', 'Net_Profit', 'Actual_Score', 'Bookie_Prob', 'Our_Prob']], use_container_width=True)
            else: st.info("ℹ️ ยังไม่มีข้อมูลบิลที่คำนวณผลแพ้ชนะได้")
        else: st.info("ℹ️ ยังไม่มีข้อมูลบิลที่ทราบผลลัพธ์ (กรุณาไปอัปเดตผลลงในช่อง Result TAB 2 ก่อนครับ)")
    else: st.warning("⚠️ ไม่พบฐานข้อมูลการลงทุน")
