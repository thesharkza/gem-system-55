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

# --- CONFIG ---
st.set_page_config(page_title="GEM System 10.0 (The Oracle)", layout="wide", initial_sidebar_state="expanded")
LOG_FILE = "gem_history_log.csv"
RULES_FILE = "gem_rules.txt" 

# ==========================================
# 0. ระบบตั้งค่าตัวแปร (Session State Init)
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
        if k not in st.session_state:
            st.session_state[k] = v

init_session_state()

@st.cache_data(ttl=60)
def load_gem_rules():
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return "ไม่พบไฟล์คัมภีร์ โปรดสร้างไฟล์ gem_rules.txt และใส่กฎทั้งหมดลงไป"
    
def get_dynamic_rules(target, is_live, raw_rules):
    """
    ฟังก์ชัน RAG (Retrieval-Augmented Generation) แบบเบา 
    ทำหน้าที่กรองคัมภีร์ GEM ให้เหลือเฉพาะกฎที่เข้ากับหน้างานปัจจุบัน
    """
    rules = raw_rules.split('\n')
    dynamic_db = []
    
    is_ah = target in ["เจ้าบ้าน", "ทีมเยือน"]
    is_ou = target in ["สูง", "ต่ำ"]
    
    for rule in rules:
        if not rule.strip(): 
            continue
            
        rule_lower = rule.lower()
        
        # 1. ตะแกรงกรองตลาด (AH vs O/U)
        # ถ้าเราแทงสูง/ต่ำ (O/U) แต่กฎข้อนี้พูดถึงแต่ 'ต่อ/รอง/เจ้าบ้าน/ทีมเยือน' -> ให้ตัดทิ้ง
        if is_ou and any(w in rule_lower for w in ['เจ้าบ้าน', 'ทีมเยือน', 'ต่อ', 'รอง', 'ah']) and not any(w in rule_lower for w in ['สูง', 'ต่ำ', 'สกอร์', 'o/u']):
            continue
            
        # ถ้าเราแทงแฮนดิแคป (AH) แต่กฎข้อนี้พูดถึงแต่ 'สูง/ต่ำ/ประตูรวม' -> ให้ตัดทิ้ง
        if is_ah and any(w in rule_lower for w in ['สูง', 'ต่ำ', 'สกอร์รวม', 'o/u']) and not any(w in rule_lower for w in ['เจ้าบ้าน', 'ทีมเยือน', 'ต่อ', 'รอง', 'ah']):
            continue
            
        # 2. ตะแกรงกรองเวลา (Pre-Match vs Live)
        # ถ้าแทงก่อนเตะ (Pre-match) แต่กฎเป็นของบอลสด -> ให้ตัดทิ้ง
        if not is_live and any(w in rule_lower for w in ['live', 'สด', 'นาที', 'ใบแดง', 'สกอร์ปัจจุบัน']):
            continue 
            
        # ถ้าแทงบอลสด (Live) แต่กฎเป็นของก่อนเตะ -> ให้ตัดทิ้ง
        if is_live and any(w in rule_lower for w in ['ก่อนเตะ', 'pre-match', 'ราคาเปิด']) and not any(w in rule_lower for w in ['live', 'สด', 'ไหล']):
            continue
            
        # กฎข้อไหนที่ผ่านตะแกรงมาได้ (หรือเป็นกฎกว้างๆ ที่ไม่มีคีย์เวิร์ดเฉพาะ) ให้เก็บไว้
        dynamic_db.append(rule)
        
    return "\n".join(dynamic_db)

def clear_form_data():
    st.session_state.raw_text = ""
    st.session_state.match_name = "ชื่อคู่แข่งขัน"
    st.session_state.h1x2_val = 1.0; st.session_state.d1x2_val = 1.0; st.session_state.a1x2_val = 1.0
    st.session_state.hdp_line_val = 0.0; st.session_state.hdp_h_w_val = 0.0; st.session_state.hdp_a_w_val = 0.0
    st.session_state.ou_line_val = 2.5; st.session_state.ou_over_w_val = 0.0; st.session_state.ou_under_w_val = 0.0

def approve_and_save_rule():
    """ฟังก์ชัน Callback สำหรับบันทึกกฎลงคัมภีร์แบบชัวร์ 100%"""
    try:
        # 1. เขียนไฟล์แบบ Append ('a')
        with open(RULES_FILE, "a", encoding="utf-8") as f:
            tz_th = timezone(timedelta(hours=7))
            now_str = datetime.now(tz_th).strftime("%Y-%m-%d %H:%M")
            f.write(f"\n\n### กฎใหม่ที่เรียนรู้จาก AI Debrief (วันที่ {now_str}) ###\n")
            f.write(st.session_state['debrief_result'])
            
        # 2. ล้างข้อมูลหน้าจอ
        st.session_state['debrief_result'] = ""
        
        # 3. ล้างแคช (Cache) ทันที! เพื่อให้ The Oracle ดึงกฎใหม่ไปใช้ในคู่ต่อไปได้เลย
        load_gem_rules.clear() 
        
    except Exception as e:
        st.error(f"❌ ไม่สามารถบันทึกไฟล์ได้: {e}")

def parse_line(line_str):
    line_str = str(line_str).replace(' ', '').replace('+', '')
    is_negative = '-' in line_str
    line_str = line_str.replace('-', '')
    try:
        if '/' in line_str or ',' in line_str:
            sep = '/' if '/' in line_str else ','
            parts = line_str.split(sep)
            return (-1 if is_negative else 1) * ((float(parts[0]) + float(parts[1])) / 2.0)
        else:
            return float(line_str) * (-1 if is_negative else 1)
    except:
        return 0.0

# ==========================================
# 1. ระบบคณิตศาสตร์ขั้นสูง (Syndicate Quant Engine)
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
        except: break
    p = [(math.sqrt(z**2 + 4*(1-z)*pi_i) - z) / (2*(1-z)) for pi_i in pi]
    sum_p = sum(p) 
    return p[0]/sum_p, p[1]/sum_p, p[2]/sum_p

def poisson(k, lam):
    return (lam**k * math.exp(-lam)) / math.factorial(k)

def calc_dixon_coles_matrix(p_h, p_d, p_a, ou_line, ou_over_w, ou_under_w, rho, current_h=0, current_a=0, minutes_left=90, red_card_h=False, red_card_a=False):
    o_w = ou_over_w + 1.0 if ou_over_w < 1.1 else ou_over_w
    u_w = ou_under_w + 1.0 if ou_under_w < 1.1 else ou_under_w
    
    o_prob = 1.0 / o_w
    u_prob = 1.0 / u_w
    margin_ou = o_prob + u_prob
    true_o_prob = o_prob / margin_ou
    
    expected_total = ou_line + ((true_o_prob - 0.5) * 1.30)
    expected_total = max(0.5, expected_total) 
    
    supremacy = (p_h - p_a) * (expected_total ** 0.65)
    
    lam_h_base = (expected_total + supremacy) / 2.0
    lam_a_base = (expected_total - supremacy) / 2.0
    
    lam_h_base = max(0.15, lam_h_base)
    lam_a_base = max(0.15, lam_a_base)

    time_factor = (minutes_left / 90.0) ** 0.85 
    lam_h = lam_h_base * time_factor
    lam_a = lam_a_base * time_factor

    if red_card_h: 
        lam_h *= 0.50 
        lam_a *= 1.30 
    if red_card_a: 
        lam_a *= 0.50
        lam_h *= 1.30

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
    p_h_win_by_2plus = 0.0; p_h_win_by_1 = 0.0; p_draw = 0.0
    p_a_win_by_1 = 0.0; p_a_win_by_2plus = 0.0
    p_total_ou = {} 

    for i in range(10):
        for j in range(10):
            prob = matrix[i][j] / total_prob
            final_h = i + current_h
            final_a = j + current_a
            diff = final_h - final_a
            
            if diff >= 2: p_h_win_by_2plus += prob
            elif diff == 1: p_h_win_by_1 += prob
            elif diff == 0: p_draw += prob
            elif diff == -1: p_a_win_by_1 += prob
            elif diff <= -2: p_a_win_by_2plus += prob
            
            total_match_goals = final_h + final_a
            p_total_ou[total_match_goals] = p_total_ou.get(total_match_goals, 0.0) + prob
            
    return (p_h_win_by_2plus, p_h_win_by_1, p_draw, p_a_win_by_1, p_a_win_by_2plus, p_total_ou)

def calc_advanced_ah_ev(hdp_line, w2, w1, d, l1, l2, odds, is_fav_team):
    b = odds - 1
    hdp_abs = abs(hdp_line)
    if hdp_abs == 0: return ((w2 + w1) * b) - ((l1 + l2) * 1)
    if is_fav_team: 
        if hdp_abs == 0.25: return ((w2 + w1) * b) - (d * 0.5) - ((l1 + l2) * 1)
        elif hdp_abs == 0.5: return ((w2 + w1) * b) - ((d + l1 + l2) * 1)
        elif hdp_abs == 0.75: return (w2 * b) + (w1 * (b/2)) - ((d + l1 + l2) * 1)
        elif hdp_abs == 1.0: return (w2 * b) + (w1 * 0) - ((d + l1 + l2) * 1)
        elif hdp_abs == 1.25: return (w2 * b) - (w1 * 0.5) - ((d + l1 + l2) * 1)
        elif hdp_abs == 1.5: return (w2 * b) - ((w1 + d + l1 + l2) * 1)
    else: 
        if hdp_abs == 0.25: return ((w2 + w1) * b) + (d * (b/2)) - ((l1 + l2) * 1)
        elif hdp_abs == 0.5: return ((w2 + w1 + d) * b) - ((l1 + l2) * 1)
        elif hdp_abs == 0.75: return ((w2 + w1 + d) * b) - (l1 * 0.5) - (l2 * 1)
        elif hdp_abs == 1.0: return ((w2 + w1 + d) * b) + (l1 * 0) - (l2 * 1)
        elif hdp_abs == 1.25: return ((w2 + w1 + d) * b) + (l1 * (b/2)) - (l2 * 1)
        elif hdp_abs == 1.5: return ((w2 + w1 + d + l1) * b) - (l2 * 1)
    return 0.0

def calc_advanced_ou_ev(ou_line, p_total, odds, is_over):
    b = odds - 1
    floor_line = math.floor(ou_line)
    remainder = ou_line - floor_line
    if is_over:
        if remainder == 0.0:
            p_win = sum(p_total.get(k, 0) for k in p_total if k > floor_line); p_loss = sum(p_total.get(k, 0) for k in p_total if k < floor_line)
            return (p_win * b) - (p_loss * 1)
        elif remainder == 0.25:
            p_win = sum(p_total.get(k, 0) for k in p_total if k >= floor_line + 1); p_half_loss = p_total.get(floor_line, 0.0); p_loss = sum(p_total.get(k, 0) for k in p_total if k < floor_line)
            return (p_win * b) - (p_half_loss * 0.5) - (p_loss * 1)
        elif remainder == 0.5:
            p_win = sum(p_total.get(k, 0) for k in p_total if k >= floor_line + 1); p_loss = sum(p_total.get(k, 0) for k in p_total if k <= floor_line)
            return (p_win * b) - (p_loss * 1)
        elif remainder == 0.75:
            p_win = sum(p_total.get(k, 0) for k in p_total if k >= floor_line + 2); p_half_win = p_total.get(floor_line + 1, 0.0); p_loss = sum(p_total.get(k, 0) for k in p_total if k <= floor_line)
            return (p_win * b) + (p_half_win * (b / 2)) - (p_loss * 1)
    else: 
        if remainder == 0.0:
            p_win = sum(p_total.get(k, 0) for k in p_total if k < floor_line); p_loss = sum(p_total.get(k, 0) for k in p_total if k > floor_line)
            return (p_win * b) - (p_loss * 1)
        elif remainder == 0.25:
            p_win = sum(p_total.get(k, 0) for k in p_total if k < floor_line); p_half_win = p_total.get(floor_line, 0.0); p_loss = sum(p_total.get(k, 0) for k in p_total if k >= floor_line + 1)
            return (p_win * b) + (p_half_win * (b / 2)) - (p_loss * 1)
        elif remainder == 0.5:
            p_win = sum(p_total.get(k, 0) for k in p_total if k <= floor_line); p_loss = sum(p_total.get(k, 0) for k in p_total if k >= floor_line + 1)
            return (p_win * b) - (p_loss * 1)
        elif remainder == 0.75:
            p_win = sum(p_total.get(k, 0) for k in p_total if k <= floor_line); p_half_loss = p_total.get(floor_line + 1, 0.0); p_loss = sum(p_total.get(k, 0) for k in p_total if k >= floor_line + 2)
            return (p_win * b) - (p_half_loss * 0.5) - (p_loss * 1)
    return 0.0

# ==========================================
# 2. ระบบ AI Decision Engine (Chief Risk Officer) + LEVEL 3 Chain of Thought
# ==========================================
def ai_quant_decision_engine(match_name, target, base_ev, hdp_line, odds, is_live=False, current_min=0, score="0-0"):
    raw_database = load_gem_rules()
    # 🧠 LEVEL 2: DYNAMIC KNOWLEDGE RETRIEVAL (ร่อนตะแกรงเอากฎที่ตรงบริบทเท่านั้น)
    oracle_database = get_dynamic_rules(target, is_live, raw_database)
    
    if not is_live:
        mode_instruction = (
            "[โหมดการวิเคราะห์: PRE-MATCH (บอลก่อนเตะ)]\n"
            "คำสั่ง: ในโหมดนี้ ให้ความสำคัญกับ 'ความคุ้มค่าทางคณิตศาสตร์ (Base EV)' เป็นหลัก!\n"
            "- กฎ GEM Rules ให้ใช้เป็นแค่ 'ข้อควรระวัง (Warning)' เท่านั้น ไม่ต้องเคร่งครัดมาก\n"
            "- หาก Base EV ผ่านเกณฑ์ (Threshold) ที่ตั้งไว้ ให้ถือว่าคุ้มค่า และทำการอนุมัติ (final_decision: true) เสมอ"
        )
    else:
        mode_instruction = (
            "[โหมดการวิเคราะห์: IN-PLAY LIVE (บอลสด)]\n"
            "คำสั่ง: ในโหมดนี้ ให้เปิดใช้งาน 'คัมภีร์ GEM RULES' อย่างเต็มรูปแบบ! แต่อย่าตึงเกินไป ให้ประเมินตามเงื่อนไขต่อไปนี้:\n"
            "1. หาก Base EV สูงระดับ 'Golden Opportunity' (เช่น +15% ขึ้นไป): \n"
            "   - อนุญาตให้ 'เพิกเฉย' ต่อกฎ GEM ที่เป็นเพียงคำเตือนระดับต่ำ-กลาง (1-2 ดาว) ได้ \n"
            "   - หัก impact_score แค่นิดหน่อย (ไม่เกิน -0.05) และยังคงอนุมัติ (final_decision: true)\n"
            "2. หากละเมิดกฎ GEM ระดับ 'Fatal (อันตรายถึงชีวิต/สั่งห้ามแทง)':\n"
            "   - ไม่ว่า Base EV จะสูงแค่ไหน ก็ต้องสั่งทับมือทันที! (final_decision: false) พร้อมหัก impact_score หนักๆ (เช่น -0.20)\n"
            "3. ชั่งน้ำหนักตามบริบท: อธิบายเหตุผลแบบเซียนบอลว่าทำไมถึงกล้าฝืนกฎ หรือทำไมถึงต้องยอมทิ้ง Base EV สวยๆ"
        )

    prompt = (
        "คุณคือ Chief Risk Officer ประจำกองทุน Quant Sports Betting\n"
        "หน้าที่ของคุณคือการนำ 'คัมภีร์ GEM RULES' มาวิเคราะห์ร่วมกับ 'ความคุ้มค่าทางคณิตศาสตร์ (Base EV)' แบบชั่งน้ำหนักองค์รวม\n\n"
        "[ข้อมูลหน้างานปัจจุบัน]\n"
        f"- คู่แข่งขัน: {match_name}\n"
        f"- สถานการณ์: {'Live นาทีที่ ' + str(current_min) + ' สกอร์ ' + str(score) if is_live else 'Pre-Match (ก่อนเตะ)'}\n"
        f"- เป้าหมายลงทุน: {target} (เรต {hdp_line} ค่าน้ำ {odds})\n"
        f"- Base EV ทางคณิตศาสตร์: {base_ev * 100:.2f}%\n\n"
        f"{mode_instruction}\n\n"
        "[คัมภีร์ THE ORACLE DATABASE]\n"
        f"{oracle_database}\n\n"
        "คำสั่งการตอบกลับ:\n"
        "ตอบกลับเป็น JSON Format (ภาษาไทย) เท่านั้น! ห้ามมีตัวอักษรอื่นรอบนอก:\n"
        "{\n"
        '    "pros_analysis": "ให้เขียนเหตุผลสนับสนุน (ข้อดี) ของการลงทุนคู่นี้",\n'
        '    "cons_analysis": "หาช่องโหว่ ข้อควรระวัง หรือกับดักของเจ้ามือในราคานี้",\n'
        '    "rule_triggered": "สรุปชื่อกฎ GEM ทั้งหมดที่นำมาชั่งน้ำหนัก",\n'
        '    "impact_score": 0.0,\n'
        '    "final_decision": true,\n'
        '    "final_comment": "สรุปการตัดสินใจขั้นเด็ดขาดจากการชั่งน้ำหนัก Pros และ Cons"\n'
        "}"
    )
    
    for attempt in range(3):
        try:
            model = genai.GenerativeModel('models/gemini-2.5-flash')
            response = model.generate_content(prompt)
            bt = chr(96) * 3
            res_text = response.text.replace(bt + 'json', '').replace(bt, '').strip()
            return json.loads(res_text)
        except Exception as e:
            error_str = str(e).replace('"', "'")
            if "429" in error_str and attempt < 2:
                time.sleep(2)
                continue
            if attempt == 2:
                return {
                    "pros_analysis": "ไม่สามารถวิเคราะห์ได้เนื่องจากระบบขัดข้อง",
                    "cons_analysis": "ไม่สามารถวิเคราะห์ได้",
                    "rule_triggered": "System Error", 
                    "impact_score": 0.0, 
                    "final_decision": True if base_ev >= 0.08 else False, 
                    "final_comment": f"AI ล้มเหลว (ใช้คณิตศาสตร์ล้วน): {error_str}"
                }

# ==========================================
# UI / UX Components (ระบบวาดหน้าปัดและปุ่ม)
# ==========================================
def create_ev_gauge(ev_value, title, threshold=8.0):
    ev_pct = ev_value * 100
    if ev_pct >= threshold: color = "#00FF7F" 
    elif ev_pct > 0: color = "#FFD700" 
    else: color = "#FF4500" 
        
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = ev_pct,
        number = {'suffix': "%", 'font': {'color': color, 'size': 30}},
        title = {'text': title, 'font': {'size': 16, 'color': 'white'}},
        gauge = {
            'axis': {'range': [-20, 20], 'tickwidth': 1, 'tickcolor': "white"},
            'bar': {'color': color},
            'bgcolor': "rgba(0,0,0,0.1)",
            'borderwidth': 1,
            'bordercolor': "gray",
            'steps': [
                {'range': [-20, 0], 'color': "rgba(255, 69, 0, 0.15)"},
                {'range': [0, threshold], 'color': "rgba(255, 215, 0, 0.15)"},
                {'range': [threshold, 20], 'color': "rgba(0, 255, 127, 0.15)"}
            ],
            'threshold': {'line': {'color': "white", 'width': 3}, 'thickness': 0.75, 'value': ev_pct}
        }
    ))
    fig.update_layout(height=200, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig

def adj_hdp(val): st.session_state['live_hdp'] += val
def adj_ou(val): st.session_state['live_ou'] += val

# ==========================================
# 3. ระบบจัดการประวัติ, แก้บั๊ก Excel, และคำนวณ CLV
# ==========================================
def save_to_csv(data_list):
    if not data_list: return
    df_new = pd.DataFrame(data_list)
    if not os.path.isfile(LOG_FILE): df_new.to_csv(LOG_FILE, index=False, encoding='utf-8-sig')
    else: df_new.to_csv(LOG_FILE, mode='a', index=False, header=False, encoding='utf-8-sig')

def load_logs():
    if os.path.exists(LOG_FILE):
        try:
            df_logs = pd.read_csv(LOG_FILE, dtype={'Result': str}, on_bad_lines='skip', encoding='utf-8-sig')
            df_logs['Time'] = pd.to_datetime(df_logs['Time'], errors='coerce')
            if 'Result' in df_logs.columns: df_logs['Result'] = df_logs['Result'].fillna("")
            if 'Closing_Odds' not in df_logs.columns: df_logs['Closing_Odds'] = 0.0
            return df_logs.dropna(subset=['Time'])
        except: return None
    return None

def calculate_net_profit(row):
    try:
        if pd.isna(row['Result']) or str(row['Result']).strip() == "" or float(row['Investment']) <= 0: return 0.0
        result_str = str(row['Result']).strip()
        
        if "00:00:00" in result_str or len(re.findall(r'-', result_str)) > 1:
            date_parts = re.findall(r'\d+', result_str.split(' ')[0])
            if len(date_parts) >= 3:
                h_score = int(date_parts[1]) if int(date_parts[1]) < 2000 else int(date_parts[0])
                a_score = int(date_parts[2]) if int(date_parts[2]) < 2000 else int(date_parts[1])
            else: return 0.0
        else:
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
# 4. UI - Main Layout
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
    else:
        st.sidebar.warning("⚠️ โปรดใส่ API Key")

if os.path.exists(RULES_FILE):
    file_size = os.path.getsize(RULES_FILE) / 1024
    st.sidebar.info(f"📚 โหลดคัมภีร์แล้ว: {RULES_FILE} ({file_size:.1f} KB)")
else:
    st.sidebar.error(f"❌ ไม่พบไฟล์ '{RULES_FILE}' โปรดสร้างไฟล์และใส่กฎลงไป!")

tab1, tab2, tab3 = st.tabs(["🚀 Pre-Match Terminal", "📈 Performance Dashboard", "📺 In-Play Sniper"])

# --- TAB 1: Pre-Match ---
with tab1:
    st.sidebar.header("💰 Portfolio & Parameters")
    total_bankroll = st.sidebar.number_input("เงินทุนทั้งหมด (THB)", min_value=0.0, value=10000.0)
    dc_rho = st.sidebar.slider("🔗 Dixon-Coles Rho", -0.30, 0.0, -0.10, step=0.01)
    hdba_val = st.sidebar.slider("⚖️ HDBA Penalty %", 0.0, 10.0, 1.5,step=0.5)
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("🎯 EV Threshold (เป้าหมายกำไร)")
    ah_threshold = st.sidebar.slider("เป้าหมาย แฮนดิแคป (AH) %", 1.0, 20.0, 9.0, step=0.5)
    ou_threshold = st.sidebar.slider("เป้าหมาย สกอร์รวม (O/U) %", 1.0, 20.0, 9.0, step=0.5)
    ah_limit = ah_threshold / 100.0
    ou_limit = ou_threshold / 100.0

    st.markdown("---")
    
    with st.expander("👁️ AI Vision: สกัดราคาจากภาพ", expanded=False):
        if not api_key: st.warning("⚠️ ต้องการ API Key")
        else:
            uploaded_file = st.file_uploader("อัปโหลดรูปตารางราคา", type=['png', 'jpg'])
            if uploaded_file and st.button("🪄 สกัดข้อมูลจากรูปภาพ", use_container_width=True):
                with st.spinner('กำลังอ่านรูป...'):
                    try:
                        img = Image.open(uploaded_file)
                        model = genai.GenerativeModel('models/gemini-2.5-flash')
                        prompt_img = (
                            'สกัดข้อมูลจากภาพแปลงเป็น JSON: {"match_name":"","h1x2_val":0,'
                            '"d1x2_val":0,"a1x2_val":0,"hdp_line_val":0,"hdp_h_w_val":0,'
                            '"hdp_a_w_val":0,"ou_line_val":0,"ou_over_w_val":0,"ou_under_w_val":0}'
                        )
                        res = model.generate_content([prompt_img, img])
                        bt = chr(96) * 3
                        data = json.loads(res.text.replace(bt+'json', '').replace(bt, '').strip())
                        for k, v in data.items(): st.session_state[k] = v
                        st.success("✅ สำเร็จ!")
                        st.rerun()
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

    if st.button("🚀 ANALYZE PRE-MATCH", use_container_width=True):
        def fix(o): return o + 1.0 if o < 1.1 else o
        h_o, d_o, a_o = fix(h1x2), fix(d1x2), fix(a1x2)
        hw_o, aw_o, ow_o, uw_o = fix(hdp_h_w), fix(hdp_a_w), fix(ou_over_w), fix(ou_under_w)
        prob_h, prob_d, prob_a = shin_devig(h_o, d_o, a_o)
        hw2, hw1, d_exact, aw1, aw2, p_total = calc_dixon_coles_matrix(prob_h, prob_d, prob_a, ou_line, ow_o, uw_o, dc_rho)
        is_h_fav = prob_h >= prob_a
        ev_h = calc_advanced_ah_ev(hdp_line, hw2, hw1, d_exact, aw1, aw2, hw_o, is_fav_team=is_h_fav)
        ev_a = calc_advanced_ah_ev(hdp_line, aw2, aw1, d_exact, hw1, hw2, aw_o, is_fav_team=not is_h_fav) - (hdba_val/100)
        ev_over = calc_advanced_ou_ev(ou_line, p_total, ow_o, True)
        ev_under = calc_advanced_ou_ev(ou_line, p_total, uw_o, False)

        best_ah = max([{"n": "เจ้าบ้าน", "ev": ev_h, "odds": hw_o, "hdp": hdp_line}, {"n": "ทีมเยือน", "ev": ev_a, "odds": aw_o, "hdp": hdp_line}], key=lambda x: x['ev'])
        best_ou = max([{"n": "สูง", "ev": ev_over, "odds": ow_o, "hdp": ou_line}, {"n": "ต่ำ", "ev": ev_under, "odds": uw_o, "hdp": ou_line}], key=lambda x: x['ev'])

        st.markdown("---")
        st.markdown("<h3 style='text-align: center;'>📊 ANALYZE PRE-MATCH (ผลวิเคราะห์คณิตศาสตร์)</h3>", unsafe_allow_html=True)
        st.write("") 

        st.markdown("<h5 style='text-align: center; color: #aaaaaa;'>📈 สถิติความน่าจะเป็น (Implied Probabilities)</h5>", unsafe_allow_html=True)
        
        try:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(label="🏠 โอกาสเจ้าบ้านชนะ", value=f"{prob_h*100:.1f}%")
            with col2:
                st.metric(label="🤝 โอกาสเสมอ", value=f"{prob_d*100:.1f}%")
            with col3:
                st.metric(label="✈️ โอกาสเยือนชนะ", value=f"{prob_a*100:.1f}%")
        except:
            pass 
        g1, g2 = st.columns(2)
        with g1: 
            st.markdown("<h4 style='text-align: center; color: #4db8ff;'>🔵 ตลาดแฮนดิแคป (AH)</h4>", unsafe_allow_html=True)
            st.plotly_chart(create_ev_gauge(best_ah['ev'], f"เป้าหมาย: {best_ah['n']}", ah_threshold), use_container_width=True)
            
        with g2: 
            st.markdown("<h4 style='text-align: center; color: #ff9933;'>🟠 ตลาดสกอร์รวม (O/U)</h4>", unsafe_allow_html=True)
            st.plotly_chart(create_ev_gauge(best_ou['ev'], f"เป้าหมาย: {best_ou['n']}", ou_threshold), use_container_width=True)

        ah_passed = best_ah['ev'] >= ah_limit
        ou_passed = best_ou['ev'] >= ou_limit

        if ah_passed or ou_passed:
            if ah_passed and ou_passed:
                target_to_check = best_ah if best_ah['ev'] > best_ou['ev'] else best_ou
            elif ah_passed:
                target_to_check = best_ah
            else:
                target_to_check = best_ou

            if not api_key: st.warning("⚠️ กรุณาใส่ API Key ให้ AI กรองความเสี่ยง")
            else:
                with st.spinner("🧠 THE ORACLE กำลังตรวจสอบข้อควรระวัง (Pre-Match Mode)..."):
                    ai_verdict = ai_quant_decision_engine(match_name, target_to_check['n'], target_to_check['ev'], target_to_check['hdp'], target_to_check['odds'], is_live=False)
                    net_ev = target_to_check['ev'] + ai_verdict.get('impact_score', 0)
                    
                    st.markdown("---")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Base EV", f"{target_to_check['ev']*100:.2f}%")
                    c2.metric("Oracle Rule Adjust", f"{ai_verdict.get('impact_score', 0)*100:.2f}%")
                    c3.metric("Net EV", f"{net_ev*100:.2f}%")
                    
                    with st.expander("📖 รายละเอียดการวิเคราะห์จาก THE ORACLE", expanded=True):
                        st.success(f"**✅ ข้อดี (Pros):** {ai_verdict.get('pros_analysis', 'ไม่มี')}")
                        st.error(f"**⚠️ ข้อควรระวัง (Cons):** {ai_verdict.get('cons_analysis', 'ไม่มี')}")
                        st.info(f"**📜 กฎที่ทำงาน:** {ai_verdict.get('rule_triggered', 'None')}")
                    
                    if ai_verdict.get('final_decision', False) and net_ev > 0:
                        st.balloons()
                        st.success(f"✅ ORACLE APPROVED: {ai_verdict.get('final_comment', 'Good')}")
                        limit_for_calc = ah_limit if target_to_check['n'] in ["เจ้าบ้าน", "ทีมเยือน"] else ou_limit
                        inv = min( (((target_to_check['odds']-1) * ((net_ev+1)/target_to_check['odds']) - (1-((net_ev+1)/target_to_check['odds']))) / (target_to_check['odds']-1)) * 0.25, 0.05) * total_bankroll
                        tz_th = timezone(timedelta(hours=7))
                        save_to_csv([{"Time": datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S"), "Match": match_name, "HDP": target_to_check['hdp'], "Target": target_to_check['n'], "EV_Pct": round(net_ev*100, 2), "Investment": round(inv, 2), "Odds": target_to_check['odds'], "Closing_Odds": 0.0, "Result": ""}])
                    else:
                        st.error(f"🚫 ORACLE REJECTED: {ai_verdict.get('final_comment', 'Pass')}")
        else:
            st.warning(f"🛡️ เป้าหมายไม่ถึงเกณฑ์ที่ตั้งไว้ (AH: {ah_threshold}%, O/U: {ou_threshold}%)")

# --- TAB 2: Dashboard ---
with tab2:
    logs = load_logs()
    if logs is not None:
        st.subheader("📝 บันทึกผล & ราคาปิด (Closing Odds)")
        display_df = logs.sort_values(by='Time', ascending=False).reset_index(drop=True)
        edited_df = st.data_editor(display_df, column_config={"Result": st.column_config.TextColumn("Result"), "Closing_Odds": st.column_config.NumberColumn("Closing Odds", min_value=0.0, format="%.2f")}, use_container_width=True, num_rows="dynamic")
        
        c_b1, c_b2 = st.columns(2)
        if c_b1.button("💾 Save Score"): edited_df.to_csv(LOG_FILE, index=False, encoding='utf-8-sig'); st.rerun()
        if c_b2.button("🗑️ Clear Logs"): 
            if os.path.exists(LOG_FILE): os.remove(LOG_FILE); st.rerun()
        
        logs['Net_Profit'] = logs.apply(calculate_net_profit, axis=1)
        logs['CLV_Pct'] = logs.apply(calculate_clv, axis=1)
        inv_logs = logs[logs['Investment'] > 0]
        
        st.markdown("---")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("กำไรสุทธิ", f"{logs['Net_Profit'].sum():,.2f} THB")
        m2.metric("ลงทุนสะสม", f"{inv_logs['Investment'].sum():,.2f} THB")
        m3.metric("Win Rate", f"{(len(inv_logs[inv_logs['Net_Profit']>0])/len(inv_logs)*100 if not inv_logs.empty else 0):.1f}%")
        m4.metric("ROI", f"{(logs['Net_Profit'].sum()/inv_logs['Investment'].sum()*100 if not inv_logs.empty and inv_logs['Investment'].sum()>0 else 0):.2f}%")
        m5.metric("Average CLV", f"{inv_logs[inv_logs['Closing_Odds']>1.0]['CLV_Pct'].mean():.2f}%" if not inv_logs[inv_logs['Closing_Odds']>1.0].empty else "0.00%")
        
        if not logs.empty:
            logs_s = logs.sort_values(by='Time')
            logs_s['Cumulative_Profit'] = logs_s['Net_Profit'].cumsum()
            fig = go.Figure(go.Scatter(x=logs_s['Time'], y=logs_s['Cumulative_Profit'], mode='lines', fill='tozeroy', line=dict(color='#00FF7F', width=3)))
            fig.update_layout(title="Equity Curve", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)

        # ==========================================
        # 🤖 AI Daily Debrief (Level 4: Self-Reflection + 1-Click Save)
        # ==========================================
        st.markdown("---")
        st.subheader("🤖 AI Daily Debrief (วิเคราะห์หาจุดอ่อนของระบบ)")
        
        loss_logs = logs[logs['Net_Profit'] < 0]
        
        # สร้าง Session State เพื่อเก็บผลลัพธ์ของ AI ไม่ให้หายไปตอนกดปุ่ม
        if 'debrief_result' not in st.session_state:
            st.session_state['debrief_result'] = ""
            
        if len(loss_logs) > 0:
            st.info(f"🔍 พบประวัติการลงทุนที่ขาดทุนจำนวน {len(loss_logs)} รายการ")
            if st.button("🧠 สั่ง AI วิเคราะห์ความผิดพลาด (Post-Mortem)", use_container_width=True):
                with st.spinner("The Oracle กำลังสแกนหา 'กับดักราคา' จากประวัติความพ่ายแพ้..."):
                    loss_data_str = loss_logs[['Time', 'Match', 'HDP', 'Target', 'Odds', 'Result', 'Net_Profit']].to_string()
                    
                    prompt_debrief = (
                        "คุณคือ Chief Risk Officer ของกองทุน Quant Sports Betting\n"
                        "ด้านล่างนี้คือประวัติการลงทุนของกองทุนเราที่ 'ขาดทุน' ในช่วงที่ผ่านมา\n"
                        f"{loss_data_str}\n\n"
                        "คำสั่ง:\n"
                        "1. ให้วิเคราะห์หา 'รูปแบบ (Pattern) ความพ่ายแพ้' เช่น เรามักจะเสียเงินกับเรตแฮนดิแคปแบบไหน? หรือตลาดแบบใด?\n"
                        "2. ให้เขียน 'กฎเหล็กข้อใหม่ (New GEM Rule)' จำนวน 1-2 ข้อ สั้นๆ กระชับ เพื่อป้องกันความผิดพลาดเดิม\n"
                        "3. กฎใหม่ต้องขึ้นต้นด้วยคำว่า 'Gem : (ชื่อกฎ)' เพื่อให้เข้ากับระบบเดิม"
                    )
                    
                    try:
                        if "GEMINI_API_KEY" in st.secrets or ('api_key' in locals() and api_key):
                            model = genai.GenerativeModel('models/gemini-2.5-flash')
                            res_debrief = model.generate_content(prompt_debrief)
                            # เก็บผลลัพธ์ลงในหน่วยความจำ
                            st.session_state['debrief_result'] = res_debrief.text
                        else:
                            st.error("⚠️ ไม่พบ API Key กรุณาใส่ API Key ใน Sidebar")
                    except Exception as e:
                        st.error(f"เกิดข้อผิดพลาดในการวิเคราะห์: {e}")

            # ถ้าระบบมีข้อความ Debrief ค้างอยู่ ให้แสดงผล และโชว์ปุ่ม Save
            if st.session_state['debrief_result'] != "":
                st.success("✅ การวิเคราะห์เสร็จสิ้น!")
                st.markdown(st.session_state['debrief_result'])
                
                st.warning("⚠️ โปรดอ่านกฎใหม่ด้านบน หากคุณเห็นด้วยกับ The Oracle ให้กดปุ่มด้านล่างเพื่อบันทึกทันที")
                # ถ้าระบบมีข้อความ Debrief ค้างอยู่ ให้แสดงผล และโชว์ปุ่ม Save
            if st.session_state.get('debrief_result', "") != "":
                st.success("✅ การวิเคราะห์เสร็จสิ้น!")
                st.markdown(st.session_state['debrief_result'])
                
                st.warning("⚠️ โปรดอ่านกฎใหม่ด้านบน หากคุณเห็นด้วยกับ The Oracle ให้กดปุ่มด้านล่างเพื่อบันทึกทันที")
                
                # เปลี่ยนมาใช้ on_click ผูกกับฟังก์ชันแทน เพื่อให้ชัวร์ว่าทำงานเสร็จแน่นอนก่อนรีเฟรชจอ
                st.button("📥 อนุมัติและบันทึกกฎนี้ลงคัมภีร์ (gem_rules.txt)", type="primary", use_container_width=True, on_click=approve_and_save_rule)
                    # เปิดไฟล์แบบ Append ('a') เพื่อเขียนต่อท้าย
                    try:
                        with open(RULES_FILE, "a", encoding="utf-8") as f:
                            tz_th = timezone(timedelta(hours=7))
                            now_str = datetime.now(tz_th).strftime("%Y-%m-%d %H:%M")
                            f.write(f"\n\n### กฎใหม่ที่เรียนรู้จาก AI Debrief (วันที่ {now_str}) ###\n")
                            f.write(st.session_state['debrief_result'])
                        
                        st.success("🎉 บันทึกกฎใหม่ลงคัมภีร์สำเร็จแล้ว! กฎนี้จะถูกนำไปใช้สแกนหา Value Bet ในคู่ถัดไปทันที")
                        # ล้างค่าในหน้าจอหลังจากเซฟเสร็จ
                        st.session_state['debrief_result'] = ""
                        time.sleep(2) # หน่วงเวลาให้ผู้ใช้อ่านข้อความสำเร็จ
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ ไม่สามารถบันทึกไฟล์ได้: {e}")

        else:
            st.success("🌟 ยอดเยี่ยม! ระบบยังไม่พบประวัติการแทงเสีย AI จึงยังไม่ต้องวิเคราะห์จุดอ่อน")

    else: st.info("ยังไม่มีข้อมูลบันทึกในระบบ")

# --- TAB 3: IN-PLAY LIVE ---
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
                        model = genai.GenerativeModel('models/gemini-2.5-flash')
                        prompt_live = (
                            'สกัดเป็น JSON: {"current_min":0, "current_score_h":0, "current_score_a":0, '
                            '"pre_h":2.0, "pre_d":3.0, "pre_a":3.0, "pre_ou":2.5, "live_hdp":0.0, '
                            '"live_hdp_h":0.9, "live_hdp_a":0.9, "live_ou":2.5, "live_ou_over":0.9, "live_ou_under":0.9}'
                        )
                        res = model.generate_content([prompt_live] + imgs)
                        bt = chr(96)*3
                        data = json.loads(res.text.replace(bt+'json', '').replace(bt, '').strip())
                        for k, v in data.items(): st.session_state[k] = float(v) if 'score' not in k and 'min' not in k else int(v)
                        st.success("✅ สำเร็จ!")
                        st.rerun()
                    except Exception as e: st.error(f"⚠️ พลาด: {e}")

    col_l1, col_l2 = st.columns(2)
    with col_l1:
        st.subheader("🏁 สถานะเกมปัจจุบัน")
        c_h1, c_h2 = st.columns(2)
        current_score_h = c_h1.number_input("สกอร์เหย้า", min_value=0, value=st.session_state.get('lh_s', 0), key="lh_s_input")
        red_card_h = c_h2.checkbox("🟥 เหย้าใบแดง", key="rc_h")
        c_a1, c_a2 = st.columns(2)
        current_score_a = c_a1.number_input("สกอร์เยือน", min_value=0, value=st.session_state.get('la_s', 0), key="la_s_input")
        red_card_a = c_a2.checkbox("🟥 เยือนใบแดง", key="rc_a")
        current_min = st.slider("นาทีแข่งขัน", 0, 120, st.session_state.get('current_min', 45))
    with col_l2:
        st.subheader("💡 ราคาเปิด (Pre-match)")
        pre_h = st.number_input("เหย้า(เปิด)", value=st.session_state.get('pre_h', 2.0), format="%.2f")
        pre_d = st.number_input("เสมอ(เปิด)", value=st.session_state.get('pre_d', 3.0), format="%.2f")
        pre_a = st.number_input("เยือน(เปิด)", value=st.session_state.get('pre_a', 3.0), format="%.2f")
        pre_ou = st.number_input("O/U(เปิด)", value=st.session_state.get('pre_ou', 2.5), format="%.2f", step=0.25)

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
        live_hdp_h = c_w1.number_input("น้ำเหย้า", value=st.session_state.get('live_hdp_h', 0.9), format="%.2f")
        live_hdp_a = c_w2.number_input("น้ำเยือน", value=st.session_state.get('live_hdp_a', 0.9), format="%.2f")

    with col_live2:
        st.markdown("**Live O/U (เรตสกอร์รวม)**")
        btn_o1, btn_o2, btn_o3 = st.columns([1, 2, 1])
        btn_o1.button("➖ 0.25", key="o_sub", on_click=adj_ou, args=(-0.25,))
        live_ou = btn_o2.number_input("Live O/U", value=st.session_state['live_ou'], step=0.25, key="live_ou", label_visibility="collapsed", format="%.2f")
        btn_o3.button("➕ 0.25", key="o_add", on_click=adj_ou, args=(0.25,))
        c_w3, c_w4 = st.columns(2)
        live_ou_over = c_w3.number_input("น้ำสูง", value=st.session_state.get('live_ou_over', 0.9), format="%.2f")
        live_ou_under = c_w4.number_input("น้ำต่ำ", value=st.session_state.get('live_ou_under', 0.9), format="%.2f")

    if st.button("🎯 ENGAGE SNIPER", use_container_width=True):
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
        with g1: st.plotly_chart(create_ev_gauge(b_ah_v, f"AH: {t_ah}", ah_threshold), use_container_width=True)
        with g2: st.plotly_chart(create_ev_gauge(b_ou_v, f"O/U: {t_ou}", ou_threshold), use_container_width=True)
        
        ah_live_passed = b_ah_v >= ah_limit
        ou_live_passed = b_ou_v >= ou_limit

        if ah_live_passed or ou_live_passed:
            if ah_live_passed and ou_live_passed:
                t_live = {"n": t_ah, "ev": b_ah_v, "hdp": live_hdp, "odds": fix(live_hdp_h) if t_ah=="เจ้าบ้าน" else fix(live_hdp_a)} if b_ah_v > b_ou_v else {"n": t_ou, "ev": b_ou_v, "hdp": live_ou, "odds": fix(live_ou_over) if t_ou=="สูง" else fix(live_ou_under)}
            elif ah_live_passed:
                t_live = {"n": t_ah, "ev": b_ah_v, "hdp": live_hdp, "odds": fix(live_hdp_h) if t_ah=="เจ้าบ้าน" else fix(live_hdp_a)}
            else:
                t_live = {"n": t_ou, "ev": b_ou_v, "hdp": live_ou, "odds": fix(live_ou_over) if t_ou=="สูง" else fix(live_ou_under)}

            if not api_key: st.warning("⚠️ โปรดใส่ API Key")
            else:
                with st.spinner("🧠 THE ORACLE กำลังประมวลผล Live สด..."):
                    ai_live = ai_quant_decision_engine("Live", t_live['n'], t_live['ev'], t_live['hdp'], t_live['odds'], True, current_min, f"{current_score_h}-{current_score_a}")
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
                    
                    limit_to_use = ah_limit if t_live['n'] in ["เจ้าบ้าน", "ทีมเยือน"] else ou_limit
                    if ai_live.get('final_decision', False) and net_l_ev >= limit_to_use:
                        st.balloons()
                        st.error(f"🚨 SNIPER ALERT: เป้า '{t_live['n']}' อนุมัติโจมตี!")
                        st.success(f"✅ ORACLE: {ai_live.get('final_comment', 'Good')}")
                    else: st.warning(f"🚫 ORACLE REJECTED (ทับมือ): {ai_live.get('final_comment', 'Pass')}")
        else: st.write(f"🛡️ ตลาดปกติ (ยังไม่ผ่านเกณฑ์เป้าหมายที่ตั้งไว้ AH: {ah_threshold}%, O/U: {ou_threshold}%)")
