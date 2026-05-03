import streamlit as st
import pandas as pd
import os
import re
import math
import json
from datetime import datetime, timezone, timedelta
import plotly.graph_objects as go
from PIL import Image
import google.generativeai as genai

# --- CONFIG ---
st.set_page_config(page_title="GEM System 9.0 (The Book of GEMs)", layout="wide")
LOG_FILE = "gem_history_log.csv"

# ==========================================
# 🧠 THE KNOWLEDGE BASE (คัมภีร์ GEM)
# ==========================================
GEM_KNOWLEDGE_BASE = """
[กฎเหล็กการลงทุน GEM RULES]
1. ทฤษฎีความโกลาหลของใบแดง: มีใบแดง ห้ามกด "ต่ำสด (Live Under)" ให้เล็ง "สูงสด" ยกเว้นสกอร์ขาด 3 ลูก
2. จุดระเบิดสคริปต์บอลถ้วย: บอลถ้วยน็อกเอาต์ ถ้ายิงใน 20 นาทีแรก ห้ามแทงต่ำ ให้รอสวนสูงสด
3. สวิตช์ทำลายล้างสคริปต์: บอลสด หากเกิด ใบแดง, จุดโทษ 15 นาทีแรก, บาดเจ็บตัวหลัก ถือว่าสคริปต์ Pre-Match โมฆะ
4. ภาพลวงตารถถังลีกภูธร: ทีมต่อ -1.5 ในลีกภูมิภาค/ลีกสมัครเล่น/ลีกหญิง มักจะชนะแค่ 1-0 ห้ามต่อเต็มเวลา
5. กฎข้อยกเว้นบอลความผันผวนสูง: บอลหญิง, เยาวชน U19/U20, ออสเตรเลีย, เนเธอร์แลนด์ เพดานสกอร์พังง่าย ห้ามแทง Under 
6. กฎภาพลวงตาลีกยิงยับ: บอลหญิง/ออสเตรเลีย ถ้าราคาสูงต่ำจ่ายน้ำเต็ม 1.00 ฝั่ง Under คือของจริง ห้ามกด Over
7. ทฤษฎีไซยาไนด์กลับขั้วเอเชีย: J-League / K-League ถ้าเจ้าบ้านเป็นต่อแล้วน้ำล้น (ไซยาไนด์) คือ True Value ให้กดต่อเจ้าบ้านได้
8. ทฤษฎีไซยาไนด์ทะลักจุดเดือด: O/U ล้นทะลุ 1.35-1.50+ คือสคริปต์จริง ให้สวนแทงหน้าไซยาไนด์นั้นไปเลย
9. เพดานลวงโลกของทีมต่อมิดด้าม: ทีมต่อ 1.30 แต่ O/U ตั้งไว้ต่ำๆ (เช่น 2.5) แล้วจ่ายน้ำต่ำ ห้ามแทงต่ำเด็ดขาด
10. ทฤษฎีมีดโกนอ็อกแคม: ทีมใหญ่ (พูล < 1.80) ถ้า HDP จ่ายน้ำสมเหตุสมผล 0.75-0.85 ให้ต่อเลย ห้ามคิดซับซ้อน
11. กฎเหล็กพรีเมียมเรท: ห้ามลงทุนในไม้ที่จ่ายน้ำต่ำกว่า 0.75 เด็ดขาด ให้ PASS
12. ดัชนีความบ้าคลั่งภูมิภาค: ตุรกี, กรีซ, ละตินอเมริกา, ยุโรปตะวันออก ไซยาไนด์คือภาพสะท้อนกลับ ห้ามวิเคราะห์ตรงๆ
13. โพรโทคอลระงับแทงต่ำบอลเด็ก: ห้ามแทงต่ำ (Under) ก่อนเตะในลีคเยาวชนยุโรป/ละตินเด็ดขาด
14. แบนทีมเยือนอาหรับ: ลีกตะวันออกกลาง ห้ามต่อทีมเยือนเด็ดขาด ให้เล่นสูงครึ่งหลังแทน
15. โรงเชือดทีมเต็งมหาชน: ทีมเต็งจักรวาล พูล < 1.40 ห้ามต่อก่อนเตะ ให้รอโดนนำก่อนค่อยเล่นสด
16. กฎกามิกาเซ่ท้ายเกม: 20 นาทีสุดท้าย ทีมตามหลัง 2 ลูก และ O/U จ่ายน้ำล้น 1.30+ ให้สวนกด "สูง (Over)" ทันที
17. กฎห้ามลั่นไก 15 นาทีแรก: บอลสด ห้ามเทรดใน 15 นาทีแรก ให้รอการ Calibration ของเจ้ามือ
18. ทฤษฎีแฝดนรก 1X2: Live สด หากค่าน้ำ 1 หรือ 2 เท่ากับเสมอเป๊ะ ห้ามแทงต่ำเด็ดขาด
"""

# ==========================================
# 0. ระบบตั้งค่าตัวแปร (Session State Init)
# ==========================================
def init_session_state():
    defaults = {
        'match_name': "ชื่อคู่แข่งขัน",
        'h1x2_val': 1.0, 'd1x2_val': 1.0, 'a1x2_val': 1.0,
        'hdp_line_val': 0.0, 'hdp_h_w_val': 0.0, 'hdp_a_w_val': 0.0,
        'ou_line_val': 2.5, 'ou_over_w_val': 0.0, 'ou_under_w_val': 0.0,
        'raw_text': ""
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session_state()

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
            parts = line_str.split(sep)
            val = (float(parts[0]) + float(parts[1])) / 2.0
        else:
            val = float(line_str)
        return -val if is_negative else val
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

def calc_dixon_coles_matrix(p_h, p_d, p_a, total_goals, rho, current_h=0, current_a=0, minutes_left=90, red_card_h=False, red_card_a=False):
    lam_h_base = total_goals * (p_h + (p_d * 0.5))
    lam_a_base = total_goals * (p_a + (p_d * 0.5))
    time_factor = (minutes_left / 90.0) ** 0.85 
    lam_h = lam_h_base * time_factor
    lam_a = lam_a_base * time_factor

    if current_h < current_a:
        diff = current_a - current_h
        if diff == 1: lam_h *= 1.10
        elif diff >= 2: lam_h *= 1.20
    elif current_a < current_h:
        diff = current_h - current_a
        if diff == 1: lam_a *= 1.10
        elif diff >= 2: lam_a *= 1.20

    if red_card_h: lam_h *= 0.70
    if red_card_a: lam_a *= 0.70

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
# 2. ระบบ AI Decision Engine (Chief Risk Officer)
# ==========================================
def ai_quant_decision_engine(match_name, target, base_ev, hdp_line, odds, is_live=False, current_min=0, score="0-0"):
    prompt = f"""
    คุณคือ Chief Risk Officer ประจำกองทุน Quant Sports Betting 
    พิจารณาการลงทุนนี้โดยใช้ "กฎเหล็ก (GEM RULES)" อย่างเคร่งครัด
    
    [ข้อมูลหน้างาน]
    - คู่แข่งขัน: {match_name}
    - สถานการณ์: {'Live นาทีที่ ' + str(current_min) + ' สกอร์ ' + str(score) if is_live else 'Pre-Match (ก่อนเตะ)'}
    - เป้าหมายลงทุน: {target} (เรต {hdp_line} ค่าน้ำ {odds})
    - Base EV: {base_ev * 100:.2f}%
    
    {GEM_KNOWLEDGE_BASE}
    
    คำสั่ง: สกัดข้อมูลจากชื่อทีมหรือสถานการณ์ ว่าเข้าข่ายละเมิดกฎข้อใดหรือไม่? 
    ประเมินแล้วตอบกลับเป็น JSON Format ดังนี้:
    {{
        "rule_triggered": "ชื่อกฎที่เข้าข่าย (ถ้าไม่มีให้ระบุ None)",
        "impact_score": ตัวเลขปรับลดหรือเพิ่ม EV (ระหว่าง -0.10 ถึง 0.05),
        "final_decision": true (อนุมัติ) หรือ false (สั่ง Pass),
        "final_comment": "คำอธิบายเหตุผลแบบดุดันและฟันธง"
    }}
    """
    try:
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        response = model.generate_content(prompt)
        
        # ใช้ ASCII ของ backtick ป้องกันปัญหาการ copy โค้ดไปวางแล้วพัง
        bt = chr(96) * 3
        res_text = response.text.replace(bt + 'json', '').replace(bt, '').strip()
        
        return json.loads(res_text)
    except Exception as e:
        return {"rule_triggered": "Error", "impact_score": 0.0, "final_decision": True if base_ev >= 0.08 else False, "final_comment": "เชื่อมต่อ AI ล้มเหลว ใช้ Base EV เพียวๆ"}

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
        if pd.isna(row['Result']) or str(row['Result']).strip() == "" or float(row['Investment']) <= 0: 
            return 0.0
            
        result_str = str(row['Result']).strip()
        
        # 🛡️ ระบบป้องกันความเสี่ยง (Date Format Trap) จาก Excel
        if "00:00:00" in result_str or len(re.findall(r'-', result_str)) > 1:
            date_parts = re.findall(r'\d+', result_str.split(' ')[0])
            if len(date_parts) >= 3:
                h_score = int(date_parts[1]) if int(date_parts[1]) < 2000 else int(date_parts[0])
                a_score = int(date_parts[2]) if int(date_parts[2]) < 2000 else int(date_parts[1])
            else:
                 return 0.0
        else:
            scores = re.findall(r'\d+', result_str)
            if len(scores) < 2: return 0.0
            h_score, a_score = int(scores[0]), int(scores[1])
            
        hdp, target, odds, invest = float(row['HDP']), str(row['Target']).strip(), float(row['Odds']), float(row['Investment'])
        diff = h_score - a_score
        
        if target == "เจ้าบ้าน": net_margin = diff - hdp
        elif target == "ทีมเยือน": net_margin = (a_score - h_score) + hdp
        elif target == "สูง" or target == "สูง (FH)": net_margin = (h_score + a_score) - hdp
        elif target == "ต่ำ" or target == "ต่ำ (FH)": net_margin = hdp - (h_score + a_score)
        else: return 0.0
        
        if net_margin > 0.25: return invest * (odds - 1)
        elif net_margin == 0.25: return (invest * (odds - 1)) / 2
        elif net_margin == 0: return 0.0
        elif net_margin == -0.25: return -(invest / 2)
        else: return -invest
    except Exception as e: 
        return 0.0

def calculate_clv(row):
    try:
        if pd.isna(row['Closing_Odds']) or float(row['Closing_Odds']) <= 1.0: 
            return 0.0
        odds_taken = float(row['Odds'])
        closing_odds = float(row['Closing_Odds'])
        return ((odds_taken / closing_odds) - 1.0) * 100.0
    except: 
        return 0.0
# ==========================================
# 🎨 UI / UX Components (ระบบวาดหน้าปัดและปุ่ม)
# ==========================================
def create_ev_gauge(ev_value, title, threshold=8.0):
    ev_pct = ev_value * 100
    
    # 🚥 เปลี่ยนสีตามความคุ้มค่า (จิตวิทยาสี)
    if ev_pct >= threshold: color = "#00FF7F" # เขียวสว่าง (ยิงได้!)
    elif ev_pct > 0: color = "#FFD700" # เหลือง (เฝ้าระวัง)
    else: color = "#FF4500" # แดง (ยาพิษ)
        
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = ev_pct,
        number = {'suffix': "%", 'font': {'color': color, 'size': 32}},
        title = {'text': title, 'font': {'size': 18, 'color': 'white'}},
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
            'threshold': {
                'line': {'color': "white", 'width': 3},
                'thickness': 0.75,
                'value': ev_pct
            }
        }
    ))
    fig.update_layout(height=220, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig

# Callback Functions สำหรับ UX ปุ่มกดด่วน
def adj_hdp(val): st.session_state['live_hdp'] += val
def adj_ou(val): st.session_state['live_ou'] += val

# ==========================================
# 4. UI - Main Layout
# ==========================================
st.title("🎯 GEM System 9.0: The Book of GEMs Engine")

# 🛠️ ระบบดึง Key อัตโนมัติจาก Streamlit Secrets
st.sidebar.header("🔑 AI Integration (Gemini)")

# เช็คว่ามี Secrets ใน Streamlit Cloud ไหม
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    st.sidebar.success("✅ AI Connected (Auto Secrets)")
else:
    api_key = st.sidebar.text_input("ใส่ Gemini API Key:", type="password")
    if api_key:
        genai.configure(api_key=api_key)
        st.sidebar.success("✅ AI Connected (Manual Input)")
    else:
        st.sidebar.warning("⚠️ ไม่พบ API Key กรุณาระบุเพื่อเปิดใช้งาน AI")

tab1, tab2, tab3 = st.tabs(["🚀 Pre-Match Terminal", "📈 Performance Dashboard", "📺 In-Play Live"])

# --- TAB 1: Pre-Match ---
with tab1:
    st.sidebar.header("💰 Portfolio & Parameters")
    total_bankroll = st.sidebar.number_input("เงินทุนทั้งหมด (THB)", min_value=0.0, value=10000.0)
    dc_rho = st.sidebar.slider("🔗 Dixon-Coles Rho", -0.30, 0.0, -0.10, step=0.01)
    hdba_val = st.sidebar.slider("⚖️ HDBA Penalty %", 0.0, 10.0, 1.5)
    sniper_threshold = st.sidebar.slider("เป้าหมาย Value ขั้นต่ำ (%)", 1.0, 20.0, 8.0, step=0.5)
    trigger_limit = sniper_threshold / 100.0

    st.markdown("---")
    
    with st.expander("👁️ AI Vision: สกัดราคาจากภาพ", expanded=False):
        if not api_key:
            st.warning("⚠️ กรุณาตรวจสอบ API Key ก่อนใช้งานโหมดนี้")
        else:
            uploaded_file = st.file_uploader("อัปโหลดรูปตารางราคา", type=['png', 'jpg'])
            if uploaded_file and st.button("🪄 สกัดข้อมูลจากรูปภาพ", use_container_width=True):
                with st.spinner('กำลังอ่านรูป...'):
                    try:
                        img = Image.open(uploaded_file)
                        model = genai.GenerativeModel('models/gemini-2.5-flash')
                        p = 'สกัดข้อมูลจากภาพแปลงเป็น JSON: {"match_name":"","h1x2_val":0,"d1x2_val":0,"a1x2_val":0,"hdp_line_val":0,"hdp_h_w_val":0,"hdp_a_w_val":0,"ou_line_val":0,"ou_over_w_val":0,"ou_under_w_val":0}'
                        res = model.generate_content([p, img])
                        
                        # ใช้ ASCII ป้องกันปัญหา Copy & Paste
                        bt = chr(96) * 3
                        res_text = res.text.replace(bt + 'json', '').replace(bt, '').strip()
                        data = json.loads(res_text)
                        
                        for k, v in data.items(): st.session_state[k] = v
                        st.success("✅ สกัดข้อมูลสำเร็จ")
                        st.rerun()
                    except Exception as e:
                        st.error(f"⚠️ สกัดข้อมูลล้มเหลว: {e}")

    # 🆕 นำช่อง Text Parser แบบเก่ากลับมา
    with st.expander("⚡ Text Parser: วางข้อความดิบ (โหมดคลาสสิก)", expanded=False):
        st.text_area("📋 ก๊อปปี้ราคาทั้งก้อนจากหน้าเว็บมาวางตรงนี้...", height=100, key="raw_text")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🪄 สกัดข้อมูลจากข้อความ", use_container_width=True):
                try:
                    raw = st.session_state.raw_text
                    m_vs = re.search(r'(.*VS.*)', raw)
                    if m_vs: st.session_state.match_name = m_vs.group(1).strip()
                    h_matches = re.findall(r'^\s*เหย้า\s+([0-9.]+)', raw, re.MULTILINE)
                    if len(h_matches) >= 1: st.session_state.h1x2_val = float(h_matches[0]) 
                    if len(h_matches) >= 2: st.session_state.hdp_h_w_val = float(h_matches[1]) 
                    d_matches = re.findall(r'^\s*เสมอ\s+([0-9.]+)', raw, re.MULTILINE)
                    if len(d_matches) >= 1: st.session_state.d1x2_val = float(d_matches[0])
                    a_matches = re.findall(r'^\s*เยือน\s+([0-9.]+)', raw, re.MULTILINE)
                    if len(a_matches) >= 1: st.session_state.a1x2_val = float(a_matches[0]) 
                    if len(a_matches) >= 2: st.session_state.hdp_a_w_val = float(a_matches[1]) 
                    ah_match = re.search(r'^\s*AH\s+([-+0-9.,/]+)', raw, re.MULTILINE)
                    if ah_match: st.session_state.hdp_line_val = parse_line(ah_match.group(1))
                    ou_match = re.search(r'^\s*สูง/ต่ำ\s+([-+0-9.,/]+)', raw, re.MULTILINE)
                    if ou_match: st.session_state.ou_line_val = parse_line(ou_match.group(1))
                    o_match = re.search(r'^\s*สูง\s+([0-9.]+)', raw, re.MULTILINE)
                    if o_match: st.session_state.ou_over_w_val = float(o_match.group(1))
                    u_match = re.search(r'^\s*ต่ำ\s+([0-9.]+)', raw, re.MULTILINE)
                    if u_match: st.session_state.ou_under_w_val = float(u_match.group(1))
                    st.success("✅ สกัดข้อความสำเร็จ!")
                except Exception as e:
                    st.error(f"⚠️ ข้อความมีปัญหา: {e}")
        with col_btn2:
            st.button("🗑️ ล้างข้อมูลทั้งหมด", use_container_width=True, on_click=clear_form_data)

    st.markdown("---")

    match_name = st.text_input("📝 คู่แข่งขัน", key="match_name")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1. พูล & AH (เต็มเวลา)")
        h1x2 = st.number_input("เหย้า (1X2)", format="%.2f", key="h1x2_val")
        d1x2 = st.number_input("เสมอ (1X2)", format="%.2f", key="d1x2_val")
        a1x2 = st.number_input("เยือน (1X2)", format="%.2f", key="a1x2_val")
        hdp_line = st.number_input("เรตต่อรอง (HDP)", format="%.2f", step=0.25, key="hdp_line_val")
        hdp_h_w = st.number_input("น้ำเจ้าบ้าน", format="%.2f", key="hdp_h_w_val")
        hdp_a_w = st.number_input("น้ำทีมเยือน", format="%.2f", key="hdp_a_w_val")
    with col2:
        st.subheader("2. ตลาด O/U (เต็มเวลา)")
        ou_line = st.number_input("เรตสกอร์รวม (O/U)", format="%.2f", step=0.25, key="ou_line_val")
        ou_over_w = st.number_input("น้ำหน้าสูง (Over)", format="%.2f", key="ou_over_w_val")
        ou_under_w = st.number_input("น้ำหน้าต่ำ (Under)", format="%.2f", key="ou_under_w_val")

    if st.button("🚀 ANALYZE PRE-MATCH", use_container_width=True):
        def fix(o): return o + 1.0 if o < 1.1 else o
        h_o, d_o, a_o = fix(h1x2), fix(d1x2), fix(a1x2)
        hw_o, aw_o, ow_o, uw_o = fix(hdp_h_w), fix(hdp_a_w), fix(ou_over_w), fix(ou_under_w)
        prob_h, prob_d, prob_a = shin_devig(h_o, d_o, a_o)
        hw2, hw1, d_exact, aw1, aw2, p_total = calc_dixon_coles_matrix(prob_h, prob_d, prob_a, ou_line, dc_rho)
        is_h_fav = prob_h >= prob_a
        ev_h = calc_advanced_ah_ev(hdp_line, hw2, hw1, d_exact, aw1, aw2, hw_o, is_fav_team=is_h_fav)
        ev_a = calc_advanced_ah_ev(hdp_line, aw2, aw1, d_exact, hw1, hw2, aw_o, is_fav_team=not is_h_fav) - (hdba_val/100)
        ev_over = calc_advanced_ou_ev(ou_line, p_total, ow_o, is_over=True)
        ev_under = calc_advanced_ou_ev(ou_line, p_total, uw_o, is_over=False)

        best_ah = max([{"n": "เจ้าบ้าน", "ev": ev_h, "odds": hw_o, "hdp": hdp_line}, {"n": "ทีมเยือน", "ev": ev_a, "odds": aw_o, "hdp": hdp_line}], key=lambda x: x['ev'])
        best_ou = max([{"n": "สูง", "ev": ev_over, "odds": ow_o, "hdp": ou_line}, {"n": "ต่ำ", "ev": ev_under, "odds": uw_o, "hdp": ou_line}], key=lambda x: x['ev'])

        st.markdown("---")
        st.subheader(f"📊 ผลวิเคราะห์ทางคณิตศาสตร์คู่ {match_name}")
        st.write(f"**เป้า AH:** {best_ah['n']} (EV: {best_ah['ev']*100:.2f}%) | **เป้า O/U:** {best_ou['n']} (EV: {best_ou['ev']*100:.2f}%)")

        target_to_check = best_ah if best_ah['ev'] > best_ou['ev'] else best_ou
        
        if target_to_check['ev'] >= trigger_limit:
            if not api_key:
                st.warning("⚠️ กรุณาใส่ API Key เพื่อให้ AI กรองความเสี่ยง")
            else:
                with st.spinner("🧠 AI กำลังเทียบสมการกับ 'คัมภีร์ GEM'..."):
                    ai_verdict = ai_quant_decision_engine(match_name, target_to_check['n'], target_to_check['ev'], target_to_check['hdp'], target_to_check['odds'])
                    net_ev = target_to_check['ev'] + ai_verdict['impact_score']
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Base EV (คณิตศาสตร์)", f"{target_to_check['ev']*100:.2f}%")
                    c2.metric("GEM Rule Adjust", f"{ai_verdict['impact_score']*100:.2f}%")
                    c3.metric("Net EV (ความคุ้มค่าจริง)", f"{net_ev*100:.2f}%")
                    
                    st.info(f"**📖 กฎ GEM ที่เกี่ยวข้อง:** {ai_verdict['rule_triggered']}")
                    
                    if ai_verdict['final_decision'] and net_ev >= trigger_limit:
                        st.success(f"✅ AI APPROVED: {ai_verdict['final_comment']}")
                        # Save to DB
                        def get_defensive_k(ev, odds, bank):
                            if ev < trigger_limit: return 0.0
                            b_k, p_k = odds - 1, (ev + 1) / odds
                            k_pct = ((b_k * p_k) - (1 - p_k)) / b_k
                            return min(k_pct * 0.25, 0.05) * bank
                        
                        inv = get_defensive_k(net_ev, target_to_check['odds'], total_bankroll)
                        tz_th = timezone(timedelta(hours=7))
                        save_to_csv([{"Time": datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S"), "Match": match_name, "HDP": target_to_check['hdp'], "Target": target_to_check['n'], "EV_Pct": round(net_ev*100, 2), "Investment": round(inv, 2), "Odds": target_to_check['odds'], "Closing_Odds": 0.0, "Result": ""}])
                    else:
                        st.error(f"🚫 AI REJECTED (ทับมือ): {ai_verdict['final_comment']}")
                        st.write("ไม้นี้ถูก AI สกัดไว้ ไม่มีการบันทึกลงพอร์ตลงทุนครับ")
        else:
            st.warning("🛡️ Base EV ต่ำเกินไป ไม่เข้าเกณฑ์ลงทุน")

# --- TAB 2: Performance & CLV Dashboard ---
with tab2:
    logs = load_logs()
    if logs is not None:
        st.subheader("📝 บันทึกผลสกอร์ และราคาปิด (Closing Odds)")
        display_df = logs.sort_values(by='Time', ascending=False).reset_index(drop=True)
        
        edited_df = st.data_editor(
            display_df, 
            column_config={
                "Result": st.column_config.TextColumn("Result (e.g. 2-1)"),
                "Closing_Odds": st.column_config.NumberColumn("ราคาปิด (Closing Odds)", min_value=0.0, format="%.2f")
            }, 
            use_container_width=True, 
            num_rows="dynamic"
        )
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("💾 Save Score & Calculate Profit"): 
                edited_df.to_csv(LOG_FILE, index=False, encoding='utf-8-sig')
                st.rerun()
        with col_btn2:
            if st.button("🗑️ ล้างประวัติทั้งหมด (Clear Logs)"):
                if os.path.exists(LOG_FILE): os.remove(LOG_FILE); st.rerun()
        
        logs['Net_Profit'] = logs.apply(calculate_net_profit, axis=1)
        logs['CLV_Pct'] = logs.apply(calculate_clv, axis=1)
        inv_logs = logs[logs['Investment'] > 0]
        
        st.markdown("---")
        st.subheader("🏆 Performance & CLV Statistics")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("กำไรสุทธิ", f"{logs['Net_Profit'].sum():,.2f} THB")
        m2.metric("ยอดรวมลงทุน", f"{inv_logs['Investment'].sum():,.2f} THB")
        m3.metric("Win Rate", f"{(len(inv_logs[inv_logs['Net_Profit']>0])/len(inv_logs)*100 if not inv_logs.empty else 0):.1f}%")
        m4.metric("ROI", f"{(logs['Net_Profit'].sum()/inv_logs['Investment'].sum()*100 if not inv_logs.empty and inv_logs['Investment'].sum()>0 else 0):.2f}%")
        
        valid_clv = inv_logs[inv_logs['Closing_Odds'] > 1.0]
        avg_clv = valid_clv['CLV_Pct'].mean()
        m5.metric("🎯 Average CLV", f"{avg_clv:.2f}%" if pd.notna(avg_clv) else "0.00%")
        
        if not logs.empty:
            st.markdown("---")
            st.subheader("📉 กราฟกำไรสะสม (Equity Curve)")
            logs_sorted = logs.sort_values(by='Time')
            logs_sorted['Cumulative_Profit'] = logs_sorted['Net_Profit'].cumsum()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=logs_sorted['Time'], y=logs_sorted['Cumulative_Profit'], mode='lines', line=dict(color='#00FF7F', width=3, shape='spline'), fill='tozeroy', fillcolor='rgba(0, 255, 127, 0.15)', name='กำไรสะสม'))
            fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis=dict(showgrid=False, title="", showticklabels=True), yaxis=dict(showgrid=True, gridcolor='rgba(128, 128, 128, 0.2)', title="ยอดเงิน (THB)", zeroline=True, zerolinecolor='rgba(255, 0, 0, 0.3)'), hovermode="x unified", margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("ยังไม่มีข้อมูลบันทึกในระบบ")

# --- TAB 3: IN-PLAY LIVE (Sniper Module) ---
with tab3:
    st.header("📺 Live Sniper Command Center")
    
    with st.expander("👁️ AI Live Vision: สแกนราคาจากรูปภาพ", expanded=False):
        if not api_key:
            st.warning("⚠️ กรุณาตรวจสอบ API Key ก่อนใช้งานโหมดนี้")
        else:
            live_images = st.file_uploader("อัปโหลดรูป AH, O/U, 1x2 (สูงสุด 3 รูป)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
            if live_images:
                cols = st.columns(len(live_images))
                imgs = []
                for idx, img_file in enumerate(live_images):
                    img = Image.open(img_file)
                    imgs.append(img)
                    cols[idx].image(img, use_container_width=True, caption=f"รูปที่ {idx+1}")
                
                if st.button("🪄 สกัดข้อมูล Live ลงระบบ", use_container_width=True):
                    with st.spinner("AI กำลังกวาดสายตาทั้ง 3 ตาราง..."):
                        try:
                            model = genai.GenerativeModel('models/gemini-2.5-flash')
                            prompt = """คุณคือผู้เชี่ยวชาญ สกัดข้อมูลจากภาพเป็น JSON: {"current_min":0, "current_score_h":0, "current_score_a":0, "pre_h":2.0, "pre_d":3.0, "pre_a":3.0, "pre_ou":2.5, "live_hdp":0.0, "live_hdp_h":0.9, "live_hdp_a":0.9, "live_ou":2.5, "live_ou_over":0.9, "live_ou_under":0.9}"""
                            response = model.generate_content([prompt] + imgs)
                            bt = chr(96) * 3
                            data = json.loads(response.text.replace(bt+'json', '').replace(bt, '').strip())
                            for k, v in data.items(): st.session_state[k] = float(v) if 'score' not in k and 'min' not in k else int(v)
                            st.success("✅ AI ดึงข้อมูล สำเร็จ!")
                            st.rerun()
                        except Exception as e: st.error(f"⚠️ สกัดล้มเหลว: {e}")

    st.markdown("---")
    
    # 🏁 แถวที่ 1: สถานะเกม
    col_l1, col_l2 = st.columns(2)
    with col_l1:
        st.subheader("🏁 สถานะเกมปัจจุบัน")
        c_h1, c_h2 = st.columns(2)
        current_score_h = c_h1.number_input("สกอร์เจ้าบ้าน", min_value=0, value=st.session_state.get('lh_s', 0), key="lh_s_input")
        red_card_h = c_h2.checkbox("🟥 เจ้าบ้านใบแดง", key="rc_h")
        c_a1, c_a2 = st.columns(2)
        current_score_a = c_a1.number_input("สกอร์ทีมเยือน", min_value=0, value=st.session_state.get('la_s', 0), key="la_s_input")
        red_card_a = c_a2.checkbox("🟥 ทีมเยือนใบแดง", key="rc_a")
        current_min = st.slider("นาทีที่แข่งขัน", 0, 120, st.session_state.get('current_min', 45))
    with col_l2:
        st.subheader("💡 อ้างอิงราคาเปิด (Pre-match)")
        pre_h = st.number_input("เหย้า (เปิด)", value=st.session_state.get('pre_h', 2.00), format="%.2f")
        pre_d = st.number_input("เสมอ (เปิด)", value=st.session_state.get('pre_d', 3.40), format="%.2f")
        pre_a = st.number_input("เยือน (เปิด)", value=st.session_state.get('pre_a', 3.00), format="%.2f")
        pre_ou = st.number_input("O/U (เปิด)", value=st.session_state.get('pre_ou', 2.50), format="%.2f", step=0.25)

    st.markdown("---")
    
    # ⚡ แถวที่ 2: UX Frictionless Input (ปุ่มสไนเปอร์)
    st.subheader("💰 ราคา Live ปัจจุบัน (Sniper Adjust)")
    col_live1, col_live2 = st.columns(2)
    
    with col_live1:
        st.markdown("**Live HDP (เรตแฮนดิแคป)**")
        if 'live_hdp' not in st.session_state: st.session_state['live_hdp'] = 0.0
        btn_h1, btn_h2, btn_h3 = st.columns([1, 2, 1])
        btn_h1.button("➖ 0.25", key="h_sub", on_click=adj_hdp, args=(-0.25,), use_container_width=True)
        live_hdp = btn_h2.number_input("Live HDP", value=st.session_state['live_hdp'], step=0.25, key="live_hdp", label_visibility="collapsed", format="%.2f")
        btn_h3.button("➕ 0.25", key="h_add", on_click=adj_hdp, args=(0.25,), use_container_width=True)
        
        c_w1, c_w2 = st.columns(2)
        live_hdp_h = c_w1.number_input("น้ำเจ้าบ้าน", value=st.session_state.get('live_hdp_h', 0.90), format="%.2f")
        live_hdp_a = c_w2.number_input("น้ำทีมเยือน", value=st.session_state.get('live_hdp_a', 0.90), format="%.2f")

    with col_live2:
        st.markdown("**Live O/U (เรตสกอร์รวม)**")
        if 'live_ou' not in st.session_state: st.session_state['live_ou'] = 2.50
        btn_o1, btn_o2, btn_o3 = st.columns([1, 2, 1])
        btn_o1.button("➖ 0.25", key="o_sub", on_click=adj_ou, args=(-0.25,), use_container_width=True)
        live_ou = btn_o2.number_input("Live O/U", value=st.session_state['live_ou'], step=0.25, key="live_ou", label_visibility="collapsed", format="%.2f")
        btn_o3.button("➕ 0.25", key="o_add", on_click=adj_ou, args=(0.25,), use_container_width=True)
        
        c_w3, c_w4 = st.columns(2)
        live_ou_over = c_w3.number_input("น้ำหน้าสูง", value=st.session_state.get('live_ou_over', 0.90), format="%.2f")
        live_ou_under = c_w4.number_input("น้ำหน้าต่ำ", value=st.session_state.get('live_ou_under', 0.90), format="%.2f")

    st.markdown("<br>", unsafe_allow_html=True)

    # 🚀 แถวที่ 3: UI Visual Execution
    if st.button("🎯 ENGAGE SNIPER (ประมวลผล)", use_container_width=True):
        def fix(o): return o + 1.0 if o < 1.1 else o
        p_h, p_d, p_a = shin_devig(fix(pre_h), fix(pre_d), fix(pre_a))
        mins_left = 90 - current_min if current_min <= 90 else 1
        
        hw2, hw1, d_ex, aw1, aw2, p_total_ou = calc_dixon_coles_matrix(
            p_h, p_d, p_a, pre_ou, dc_rho, current_h=current_score_h, current_a=current_score_a, minutes_left=max(mins_left, 1), red_card_h=red_card_h, red_card_a=red_card_a
        )
        is_h_fav = p_h >= p_a
        ev_ah_h = calc_advanced_ah_ev(live_hdp, hw2, hw1, d_ex, aw1, aw2, fix(live_hdp_h), is_h_fav)
        ev_ah_a = calc_advanced_ah_ev(live_hdp, aw2, aw1, d_ex, hw1, hw2, fix(live_hdp_a), not is_h_fav) - (hdba_val/100)
        ev_over = calc_advanced_ou_ev(live_ou, p_total_ou, fix(live_ou_over), True)
        ev_under = calc_advanced_ou_ev(live_ou, p_total_ou, fix(live_ou_under), False)

        best_ah_val = max(ev_ah_h, ev_ah_a); target_ah = "เจ้าบ้าน" if ev_ah_h > ev_ah_a else "ทีมเยือน"
        best_ou_val = max(ev_over, ev_under); target_ou = "สูง" if ev_over > ev_under else "ต่ำ"
        
        st.success(f"⚡ วิเคราะห์เสร็จสิ้น: นาทีที่ {current_min} | สกอร์ {current_score_h}-{current_score_a}")
        
        # 📊 แสดงผลด้วย Gauge Chart
        g1, g2 = st.columns(2)
        with g1:
            st.plotly_chart(create_ev_gauge(best_ah_val, f"HDP ({target_ah})", sniper_threshold), use_container_width=True)
        with g2:
            st.plotly_chart(create_ev_gauge(best_ou_val, f"O/U ({target_ou})", sniper_threshold), use_container_width=True)
        
        target_live_check = {"n": target_ah, "ev": best_ah_val, "hdp": live_hdp, "odds": fix(live_hdp_h) if target_ah=="เจ้าบ้าน" else fix(live_hdp_a)}
        if best_ou_val > best_ah_val: target_live_check = {"n": target_ou, "ev": best_ou_val, "hdp": live_ou, "odds": fix(live_ou_over) if target_ou=="สูง" else fix(live_ou_under)}

        if target_live_check['ev'] >= trigger_limit:
            if not api_key:
                st.warning("⚠️ กรุณาใส่ API Key เพื่อให้ AI กรองความเสี่ยง")
            else:
                with st.spinner("🧠 AI กำลังพิจารณาความเสี่ยง In-Play ตามคัมภีร์ GEM..."):
                    ai_live = ai_quant_decision_engine("Live Match", target_live_check['n'], target_live_check['ev'], target_live_check['hdp'], target_live_check['odds'], is_live=True, current_min=current_min, score=f"{current_score_h}-{current_score_a}")
                    net_live_ev = target_live_check['ev'] + ai_live['impact_score']
                    
                    st.markdown("---")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Live Base EV", f"{target_live_check['ev']*100:.2f}%")
                    c2.metric("GEM Rule Adjust", f"{ai_live['impact_score']*100:.2f}%")
                    c3.metric("Net Live EV", f"{net_live_ev*100:.2f}%")
                    st.info(f"**📖 กฎ GEM ที่จับได้:** {ai_live['rule_triggered']}")
                    
                    if ai_live['final_decision'] and net_live_ev >= trigger_limit:
                        st.balloons() # 🎈 จุดพลุฉลองเมื่อเจอ Value Bet สวยๆ!
                        st.error(f"🚨 SNIPER ALERT: เป้าหมาย '{target_live_check['n']}' อนุมัติการโจมตี!")
                        st.success(f"✅ AI CRO: {ai_live['final_comment']}")
                    else:
                        st.warning(f"🚫 AI REJECTED: {ai_live['final_comment']}")
        else:
            st.write("🛡️ ตลาดปกติ (ยังไม่พบช่องโหว่ความตื่นตระหนก)")
