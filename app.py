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
st.set_page_config(page_title="GEM System 8.4 (AI-Powered)", layout="wide")
LOG_FILE = "gem_history_log.csv"

# ==========================================
# 0. ระบบตั้งค่าตัวแปร (Session State Init)
# ==========================================
def init_session_state():
    defaults = {
        'match_name': "ชื่อคู่แข่งขัน",
        'h1x2_val': 1.0, 'd1x2_val': 1.0, 'a1x2_val': 1.0,
        'hdp_line_val': 0.0, 'hdp_h_w_val': 0.0, 'hdp_a_w_val': 0.0,
        'ou_line_val': 2.5, 'ou_over_w_val': 0.0, 'ou_under_w_val': 0.0,
        'fh_ou_line_val': 1.0, 'fh_ou_over_w_val': 0.0, 'fh_ou_under_w_val': 0.0,
        'raw_text': ""
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session_state()

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

def calc_dixon_coles_matrix(p_h, p_d, p_a, total_goals, rho, current_h=0, current_a=0, minutes_left=90, red_card_h=False, red_card_a=False, is_fh=False):
    lam_h_base = total_goals * (p_h + (p_d * 0.5))
    lam_a_base = total_goals * (p_a + (p_d * 0.5))

    # 🆕 ผสานสมการจาก Paper วิจัย
    if is_fh:
        time_factor = 0.44 
    else:
        time_factor = (minutes_left / 90.0) ** 0.85 # Non-Linear Time-Decay

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

def save_to_csv(data_list):
    if not data_list: return
    df_new = pd.DataFrame(data_list)
    if not os.path.isfile(LOG_FILE): df_new.to_csv(LOG_FILE, index=False, encoding='utf-8-sig')
    else: df_new.to_csv(LOG_FILE, mode='a', index=False, header=False, encoding='utf-8-sig')

def load_logs():
    if os.path.exists(LOG_FILE):
        try:
            # 🛠️ ป้องกัน Error NaN ใน Streamlit 
            df_logs = pd.read_csv(LOG_FILE, dtype={'Result': str}, on_bad_lines='skip', encoding='utf-8-sig')
            df_logs['Time'] = pd.to_datetime(df_logs['Time'], errors='coerce')
            if 'Result' in df_logs.columns:
                df_logs['Result'] = df_logs['Result'].fillna("")
            return df_logs.dropna(subset=['Time'])
        except: return None
    return None

def calculate_net_profit(row):
    try:
        if pd.isna(row['Result']) or row['Result'] == "" or row['Investment'] <= 0: return 0.0
        scores = re.findall(r'\d+', str(row['Result']))
        if len(scores) < 2: return 0.0
        h_score, a_score = int(scores[0]), int(scores[1])
        hdp, target, odds, invest = float(row['HDP']), row['Target'], float(row['Odds']), float(row['Investment'])
        diff = h_score - a_score
        
        # 🆕 รองรับการตรวจสอบกำไรของครึ่งแรก (FH)
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
    except: return 0.0

# ==========================================
# 3. UI - Main Layout
# ==========================================
st.title("🎯 GEM System 8.4: AI-Powered Edition")

# 🆕 ตั้งค่า AI ใน Sidebar
st.sidebar.header("🔑 AI Integration (Gemini)")
api_key = st.sidebar.text_input("Gemini API Key", type="password", help="รับ API Key ฟรีได้ที่ Google AI Studio")
if api_key:
    genai.configure(api_key=api_key)
    st.sidebar.success("✅ AI Connected")

tab1, tab2, tab3 = st.tabs(["🚀 Pre-Match Terminal", "📈 Performance Dashboard", "📺 In-Play Live"])

# --- TAB 1: Pre-Match ---
with tab1:
    st.sidebar.header("💰 Portfolio Management")
    total_bankroll = st.sidebar.number_input("เงินทุนทั้งหมด (THB)", min_value=0.0, value=10000.0)
    
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Syndicate Parameters")
    dc_rho = st.sidebar.slider("🔗 Dixon-Coles Rho", -0.30, 0.0, -0.10, step=0.01)
    hdba_val = st.sidebar.slider("⚖️ HDBA Penalty %", 0.0, 10.0, 1.5)
    
    st.sidebar.markdown("---")
    st.sidebar.header("🚨 Live Sniper Settings")
    sniper_threshold = st.sidebar.slider("เป้าหมาย Value ขั้นต่ำ (%)", 1.0, 20.0, 8.0, step=0.5)
    trigger_limit = sniper_threshold / 100.0

    def clear_form_data():
        st.session_state.raw_text = ""
        st.session_state.match_name = "ชื่อคู่แข่งขัน"
        st.session_state.h1x2_val = 1.0; st.session_state.d1x2_val = 1.0; st.session_state.a1x2_val = 1.0
        st.session_state.hdp_line_val = 0.0; st.session_state.hdp_h_w_val = 0.0; st.session_state.hdp_a_w_val = 0.0
        st.session_state.ou_line_val = 2.5; st.session_state.ou_over_w_val = 0.0; st.session_state.ou_under_w_val = 0.0
        st.session_state.fh_ou_line_val = 1.0; st.session_state.fh_ou_over_w_val = 0.0; st.session_state.fh_ou_under_w_val = 0.0

    st.markdown("---")
    
    # 🆕 โหมดที่ 1: ระบบ AI อัปโหลดรูปภาพ (Vision OCR)
    with st.expander("👁️ AI Vision: สกัดราคาจากรูปภาพสกรีนช็อต (ใหม่!)", expanded=False):
        if not api_key:
            st.warning("⚠️ กรุณาใส่ Gemini API Key ที่เมนูด้านซ้ายก่อนใช้งานโหมดนี้")
        else:
            uploaded_file = st.file_uploader("อัปโหลดรูปภาพตารางราคา (PNG, JPG)", type=['png', 'jpg', 'jpeg'])
            if uploaded_file is not None:
                st.image(uploaded_file, caption="ภาพที่อัปโหลด", use_container_width=True)
                if st.button("🪄 ให้ AI สกัดข้อมูล (Extract from Image)", use_container_width=True):
                    with st.spinner('กำลังให้ AI กวาดสายตาอ่านตัวเลข...'):
                        try:
                            img = Image.open(uploaded_file)
                            model = genai.GenerativeModel('gemini-1.5-flash')
                            prompt = """
                            คุณคือผู้เชี่ยวชาญการอ่านตารางราคาฟุตบอล สกัดข้อมูลจากภาพนี้แล้วแปลงเป็น JSON เท่านั้น
                            ไม่ต้องมีคำอธิบายใดๆ หากข้อมูลไหนไม่มีให้ใส่ 0.0
                            Format ที่ต้องการ:
                            {
                                "match_name": "ชื่อทีมเจ้าบ้าน VS ชื่อทีมเยือน",
                                "h1x2_val": ราคาชนะเหย้าเต็มเวลา, "d1x2_val": ราคาเสมอเต็มเวลา, "a1x2_val": ราคาชนะเยือนเต็มเวลา,
                                "hdp_line_val": เรตแฮนดิแคป (เช่น 0.5, 1.25), "hdp_h_w_val": ค่าน้ำต่อรองเจ้าบ้าน, "hdp_a_w_val": ค่าน้ำต่อรองเยือน,
                                "ou_line_val": เรตสูงต่ำเต็มเวลา, "ou_over_w_val": ค่าน้ำสูงเต็มเวลา, "ou_under_w_val": ค่าน้ำต่ำเต็มเวลา,
                                "fh_ou_line_val": เรตสูงต่ำครึ่งแรก, "fh_ou_over_w_val": ค่าน้ำสูงครึ่งแรก, "fh_ou_under_w_val": ค่าน้ำต่ำครึ่งแรก
                            }
                            """
                            response = model.generate_content([prompt, img])
                            json_str = response.text.replace('```json', '').replace('```', '').strip()
                            extracted_data = json.loads(json_str)
                            
                            for k, v in extracted_data.items():
                                st.session_state[k] = v
                                
                            st.success("✅ AI สกัดข้อมูลสำเร็จ! ตรวจสอบความถูกต้องด้านล่างได้เลย")
                            st.rerun()
                        except Exception as e:
                            st.error(f"⚠️ AI อ่านข้อมูลไม่สำเร็จ กรุณาลองอัปโหลดรูปที่ชัดเจนกว่านี้: {e}")

    # โหมดที่ 2: วางข้อความแบบเดิม
    with st.expander("⚡ Text Parser: วางข้อความดิบ (โหมดคลาสสิก)", expanded=False):
        st.text_area("📋 ก๊อปปี้ราคาทั้งก้อนจากหน้าเว็บมาวางตรงนี้...", height=100, key="raw_text")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🪄 สกัดข้อมูล (Extract from Text)", use_container_width=True):
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
                    st.success("✅ สกัดข้อความสำเร็จ! (ส่วนของครึ่งแรกแนะนำให้กรอกมือเพื่อความแม่นยำครับ)")
                except Exception as e:
                    st.error(f"⚠️ ข้อความมีปัญหา: {e}")
        with col_btn2:
            st.button("🗑️ ล้างข้อมูลทั้งหมด", use_container_width=True, on_click=clear_form_data)

    match_name = st.text_input("📝 คู่แข่งขัน", key="match_name")
    
    col1, col2, col3 = st.columns(3)
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
    with col3:
        st.subheader("3. ตลาด O/U (ครึ่งแรก)")
        fh_ou_line = st.number_input("เรตสกอร์รวม (FH)", format="%.2f", step=0.25, key="fh_ou_line_val")
        fh_ou_over_w = st.number_input("น้ำสูง (FH)", format="%.2f", key="fh_ou_over_w_val")
        fh_ou_under_w = st.number_input("น้ำต่ำ (FH)", format="%.2f", key="fh_ou_under_w_val")

    if st.button("🚀 ANALYZE PRE-MATCH", use_container_width=True):
        def fix(o): return o + 1.0 if o < 1.1 else o
        h_o, d_o, a_o = fix(h1x2), fix(d1x2), fix(a1x2)
        hw_o, aw_o, ow_o, uw_o = fix(hdp_h_w), fix(hdp_a_w), fix(ou_over_w), fix(ou_under_w)
        fhow_o, fhuw_o = fix(fh_ou_over_w), fix(fh_ou_under_w)

        prob_h, prob_d, prob_a = shin_devig(h_o, d_o, a_o)
        
        hw2, hw1, d_exact, aw1, aw2, p_total = calc_dixon_coles_matrix(prob_h, prob_d, prob_a, ou_line, dc_rho)
        is_h_fav = prob_h >= prob_a
        ev_h = calc_advanced_ah_ev(hdp_line, hw2, hw1, d_exact, aw1, aw2, hw_o, is_fav_team=is_h_fav)
        ev_a = calc_advanced_ah_ev(hdp_line, aw2, aw1, d_exact, hw1, hw2, aw_o, is_fav_team=not is_h_fav) - (hdba_val/100)
        ev_over = calc_advanced_ou_ev(ou_line, p_total, ow_o, is_over=True)
        ev_under = calc_advanced_ou_ev(ou_line, p_total, uw_o, is_over=False)

        _, _, _, _, _, p_total_fh = calc_dixon_coles_matrix(prob_h, prob_d, prob_a, ou_line, dc_rho, is_fh=True)
        ev_fh_over = calc_advanced_ou_ev(fh_ou_line, p_total_fh, fhow_o, is_over=True)
        ev_fh_under = calc_advanced_ou_ev(fh_ou_line, p_total_fh, fhuw_o, is_over=False)

        def get_defensive_k(ev, odds, bank):
            if ev < trigger_limit: return 0.0
            b_k, p_k = odds - 1, (ev + 1) / odds
            k_pct = ((b_k * p_k) - (1 - p_k)) / b_k
            return min(k_pct * 0.25, 0.05) * bank

        ah_list = [{"n": "เจ้าบ้าน", "ev": ev_h, "odds": hw_o, "hdp": hdp_line}, {"n": "ทีมเยือน", "ev": ev_a, "odds": aw_o, "hdp": hdp_line}]
        ou_list = [{"n": "สูง", "ev": ev_over, "odds": ow_o, "hdp": ou_line}, {"n": "ต่ำ", "ev": ev_under, "odds": uw_o, "hdp": ou_line}]
        fh_list = [{"n": "สูง (FH)", "ev": ev_fh_over, "odds": fhow_o, "hdp": fh_ou_line}, {"n": "ต่ำ (FH)", "ev": ev_fh_under, "odds": fhuw_o, "hdp": fh_ou_line}]
        
        best_ah = max(ah_list, key=lambda x: x['ev'])
        best_ou = max(ou_list, key=lambda x: x['ev'])
        best_fh = max(fh_list, key=lambda x: x['ev'])

        k_money_ah = get_defensive_k(best_ah['ev'], best_ah['odds'], total_bankroll)
        k_money_ou = get_defensive_k(best_ou['ev'], best_ou['odds'], total_bankroll)
        k_money_fh = get_defensive_k(best_fh['ev'], best_fh['odds'], total_bankroll)

        ah_status = "🔥 INVEST" if best_ah['ev'] >= trigger_limit else "🛡️ NO BET"
        ou_status = "🔥 INVEST" if best_ou['ev'] >= trigger_limit else "🛡️ NO BET"
        fh_status = "🔥 INVEST" if best_fh['ev'] >= trigger_limit else "🛡️ NO BET"

        st.session_state['ai_analysis_data'] = {
            "match": match_name, "prob_h": prob_h, "prob_d": prob_d, "prob_a": prob_a,
            "best_ah": best_ah, "best_ou": best_ou, "best_fh": best_fh
        }

        st.session_state['report'] = f"""📊 GEM System 8.4: AI-Powered Quant Report
=======================================
⚽ คู่แข่งขัน: {match_name}

1️⃣ ข้อมูลความน่าจะเป็นที่แท้จริง (True Probabilities)
• โอกาสชนะเจ้าบ้าน : {prob_h*100:.2f}% | เสมอ: {prob_d*100:.2f}% | เยือน: {prob_a*100:.2f}%

2️⃣ ตลาดเอเชียนแฮนดิแคป (Asian Handicap)
• EV เจ้าบ้าน: {ev_h*100:.2f}% | EV ทีมเยือน: {ev_a*100:.2f}%
✅ สรุป AH: [{ah_status}] เป้าหมาย -> {best_ah['n']} (แนะนำลงทุน: {k_money_ah:,.2f} THB)

3️⃣ ตลาดสกอร์รวม (Over/Under เต็มเวลา)
• EV หน้าสูง: {ev_over*100:.2f}% | EV หน้าต่ำ: {ev_under*100:.2f}%
✅ สรุป O/U: [{ou_status}] เป้าหมาย -> {best_ou['n']} (แนะนำลงทุน: {k_money_ou:,.2f} THB)

4️⃣ ตลาดสกอร์รวม ครึ่งแรก (First-Half O/U)
• EV หน้าสูง: {ev_fh_over*100:.2f}% | EV หน้าต่ำ: {ev_fh_under*100:.2f}%
✅ สรุป FH: [{fh_status}] เป้าหมาย -> {best_fh['n']} (แนะนำลงทุน: {k_money_fh:,.2f} THB)
=======================================
"""
        tz_th = timezone(timedelta(hours=7))
        current_time = datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S")

        logs_to_save = []
        if best_ah['ev'] >= trigger_limit: logs_to_save.append({"Time": current_time, "Match": match_name, "HDP": best_ah['hdp'], "Target": best_ah['n'], "EV_Pct": round(best_ah['ev']*100, 2), "Investment": round(k_money_ah, 2), "Odds": best_ah['odds'], "Result": ""})
        if best_ou['ev'] >= trigger_limit: logs_to_save.append({"Time": current_time, "Match": match_name, "HDP": best_ou['hdp'], "Target": best_ou['n'], "EV_Pct": round(best_ou['ev']*100, 2), "Investment": round(k_money_ou, 2), "Odds": best_ou['odds'], "Result": ""})
        if best_fh['ev'] >= trigger_limit: logs_to_save.append({"Time": current_time, "Match": match_name, "HDP": best_fh['hdp'], "Target": best_fh['n'], "EV_Pct": round(best_fh['ev']*100, 2), "Investment": round(k_money_fh, 2), "Odds": best_fh['odds'], "Result": ""})

        # ระบบ Auto-Save 
        if logs_to_save:
            save_to_csv(logs_to_save)
            st.success(f"✅ สแกนพบไม้ระดับ A+ ระบบได้ทำการบันทึกลง Dashboard อัตโนมัติเรียบร้อยแล้ว!")
        else:
            st.warning(f"🛡️ ไม่มีไม้ที่เข้าเกณฑ์ ระบบแนะนำให้ปล่อยผ่านและข้ามการบันทึกประวัติ")

    if 'report' in st.session_state:
        st.text_area("Pre-Match Report:", value=st.session_state['report'], height=350)
        
        # 🆕 โหมดที่ 3: ให้ AI ช่วยวิเคราะห์และตัดสินใจด่านสุดท้าย (Chief Risk Officer)
        if api_key and 'ai_analysis_data' in st.session_state:
            if st.button("🤖 ให้ AI (Chief Risk Officer) ช่วยวิเคราะห์ความเสี่ยงด่านสุดท้าย", use_container_width=True):
                with st.spinner('AI กำลังวิเคราะห์ตัวเลขและประเมินความเสี่ยง...'):
                    d = st.session_state['ai_analysis_data']
                    model = genai.GenerativeModel('gemini-1.5-pro')
                    prompt = f"""
                    คุณคือ Chief Risk Officer ประจำกองทุนเดิมพันกีฬา คุณมีหน้าที่ให้คำแนะนำสั้นๆ กระชับๆ ดุดันแบบมืออาชีพ (ไม่เกิน 4-5 บรรทัด)
                    ข้อมูลการคำนวณคณิตศาสตร์ของคู่ {d['match']}:
                    - โอกาสชนะจริง: เหย้า {d['prob_h']*100:.1f}%, เสมอ {d['prob_d']*100:.1f}%, เยือน {d['prob_a']*100:.1f}%
                    - เป้าที่ดีที่สุด AH: {d['best_ah']['n']} (EV: {d['best_ah']['ev']*100:.2f}%)
                    - เป้าที่ดีที่สุด O/U: {d['best_ou']['n']} (EV: {d['best_ou']['ev']*100:.2f}%)
                    - เป้าที่ดีที่สุด FH: {d['best_fh']['n']} (EV: {d['best_fh']['ev']*100:.2f}%)
                    คำถาม: สรุปว่าคู่นี้มีความเสี่ยงแอบแฝงอะไรไหม? และควรลงทุนหนักหรือเบา? ตอบเป็นภาษาไทย
                    """
                    try:
                        ai_advice = model.generate_content(prompt)
                        st.info(f"**🧠 AI Risk Analysis:**\n\n{ai_advice.text}")
                    except Exception as e:
                        st.error("⚠️ AI ประมวลผลล้มเหลว ตรวจสอบ API Key อีกครั้ง")

# --- TAB 2: Performance Dashboard ---
with tab2:
    logs = load_logs()
    if logs is not None:
        st.subheader("📝 บันทึกผลสกอร์")
        display_df = logs.sort_values(by='Time', ascending=False).reset_index(drop=True)
        # 🛠️ ป้องกัน Error เวลาช่อง Result ว่างเปล่า
        display_df['Result'] = display_df['Result'].astype(str).replace('nan', '')
        edited_df = st.data_editor(display_df, column_config={"Result": st.column_config.TextColumn("Result (e.g. 2-1)")}, use_container_width=True, num_rows="dynamic")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("💾 Save Score & Calculate Profit"): edited_df.to_csv(LOG_FILE, index=False, encoding='utf-8-sig'); st.rerun()
        with col_btn2:
            if st.button("🗑️ ล้างประวัติทั้งหมด (Clear Logs)"):
                if os.path.exists(LOG_FILE): os.remove(LOG_FILE); st.rerun()
        logs['Net_Profit'] = logs.apply(calculate_net_profit, axis=1)
        inv_logs = logs[logs['Investment'] > 0]
        st.markdown("---")
        st.subheader("🏆 Performance Statistics")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("กำไรสุทธิ", f"{logs['Net_Profit'].sum():,.2f} THB")
        m2.metric("ยอดรวมลงทุน", f"{inv_logs['Investment'].sum():,.2f} THB")
        m3.metric("Win Rate", f"{(len(inv_logs[inv_logs['Net_Profit']>0])/len(inv_logs)*100 if not inv_logs.empty else 0):.1f}%")
        m4.metric("ROI", f"{(logs['Net_Profit'].sum()/inv_logs['Investment'].sum()*100 if not inv_logs.empty and inv_logs['Investment'].sum()>0 else 0):.2f}%")
        
        if not logs.empty:
            st.markdown("---")
            st.subheader("📉 กราฟกำไรสะสม (Equity Curve)")
            logs_sorted = logs.sort_values(by='Time')
            logs_sorted['Cumulative_Profit'] = logs_sorted['Net_Profit'].cumsum()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=logs_sorted['Time'], y=logs_sorted['Cumulative_Profit'], mode='lines', line=dict(color='#00FF7F', width=3, shape='spline'), fill='tozeroy', fillcolor='rgba(0, 255, 127, 0.15)', name='กำไรสะสม', hovertemplate='<b>วันที่/เวลา:</b> %{x}<br><b>กำไรสะสม:</b> %{y:,.2f} THB<extra></extra>'))
            fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis=dict(showgrid=False, title="", showticklabels=True), yaxis=dict(showgrid=True, gridcolor='rgba(128, 128, 128, 0.2)', title="ยอดเงิน (THB)", zeroline=True, zerolinecolor='rgba(255, 0, 0, 0.3)'), hovermode="x unified", margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)
            st.download_button("📥 Download Full CSV Report", logs.to_csv(index=False).encode('utf-8-sig'), "gem_backtest_report.csv", "text/csv")
    else:
        st.info("ยังไม่มีข้อมูลบันทึกในระบบ")

# --- TAB 3: IN-PLAY LIVE (Sniper Module) ---
with tab3:
    st.header("📺 Live Sniper Engine (Market Overreaction)")
    
    col_l1, col_l2 = st.columns(2)
    with col_l1:
        st.subheader("🏁 สถานะเกมปัจจุบัน")
        c_h1, c_h2 = st.columns(2)
        current_score_h = c_h1.number_input("สกอร์เจ้าบ้าน", min_value=0, value=0, key="lh_s")
        red_card_h = c_h2.checkbox("🟥 เจ้าบ้านใบแดง", key="rc_h")
        c_a1, c_a2 = st.columns(2)
        current_score_a = c_a1.number_input("สกอร์ทีมเยือน", min_value=0, value=0, key="la_s")
        red_card_a = c_a2.checkbox("🟥 ทีมเยือนใบแดง", key="rc_a")
        current_min = st.slider("นาทีที่แข่งขัน", 0, 90, 45)
    with col_l2:
        st.subheader("💡 อ้างอิงราคาเปิด (Pre-match)")
        pre_h = st.number_input("เหย้า (เปิด)", value=2.00, key="live_pre_h")
        pre_d = st.number_input("เสมอ (เปิด)", value=3.40, key="live_pre_d")
        pre_a = st.number_input("เยือน (เปิด)", value=3.00, key="live_pre_a")
        pre_ou = st.number_input("O/U (เปิด)", value=2.50, key="live_pre_ou")

    st.markdown("---")
    st.subheader("💰 ราคา Live ปัจจุบัน")
    col_live1, col_live2 = st.columns(2)
    with col_live1:
        live_hdp = st.number_input("Live HDP", step=0.25, value=0.0)
        live_hdp_h = st.number_input("น้ำ Live เจ้าบ้าน", value=0.90)
        live_hdp_a = st.number_input("น้ำ Live ทีมเยือน", value=0.90)
    with col_live2:
        live_ou = st.number_input("Live O/U", step=0.25, value=2.50)
        live_ou_over = st.number_input("น้ำ Live สูง", value=0.90)
        live_ou_under = st.number_input("น้ำ Live ต่ำ", value=0.90)

    if st.button("🎯 SCAN FOR OVERREACTION", use_container_width=True):
        def fix(o): return o + 1.0 if o < 1.1 else o
        p_h, p_d, p_a = shin_devig(fix(pre_h), fix(pre_d), fix(pre_a))
        mins_left = 90 - current_min
        
        hw2, hw1, d_ex, aw1, aw2, p_total_ou = calc_dixon_coles_matrix(
            p_h, p_d, p_a, pre_ou, dc_rho, 
            current_h=current_score_h, current_a=current_score_a, minutes_left=mins_left,
            red_card_h=red_card_h, red_card_a=red_card_a
        )
        is_h_fav = p_h >= p_a
        ev_ah_h = calc_advanced_ah_ev(live_hdp, hw2, hw1, d_ex, aw1, aw2, fix(live_hdp_h), is_h_fav)
        ev_ah_a = calc_advanced_ah_ev(live_hdp, aw2, aw1, d_ex, hw1, hw2, fix(live_hdp_a), not is_h_fav) - (hdba_val/100)
        ev_over = calc_advanced_ou_ev(live_ou, p_total_ou, fix(live_ou_over), True)
        ev_under = calc_advanced_ou_ev(live_ou, p_total_ou, fix(live_ou_under), False)

        st.success(f"วิเคราะห์หน้างานนาทีที่ {current_min} | สกอร์ {current_score_h}-{current_score_a}")
        
        c1, c2 = st.columns(2)
        best_ah_val = max(ev_ah_h, ev_ah_a)
        target_ah = "เจ้าบ้าน" if ev_ah_h > ev_ah_a else "ทีมเยือน"
        best_ou_val = max(ev_over, ev_under)
        target_ou = "สูง" if ev_over > ev_under else "ต่ำ"

        alert_triggered = False

        with c1:
            st.metric(f"Live AH Value ({target_ah})", f"{best_ah_val*100:.2f}%")
            if best_ah_val >= trigger_limit: 
                st.error(f"🚨 SNIPER ALERT: {target_ah} คุ้มค่าแก่การลงทุน! (Value > {sniper_threshold}%)")
                alert_triggered = True
            elif best_ah_val > 0.0:
                st.info(f"🟢 Marginal Edge: รอดูสถานการณ์ หรือน้ำไหลขึ้นอีกนิด")
            else:
                st.write("🛡️ ตลาดปกติ (Negative Value) รอจังหวะต่อไป")

        with c2:
            st.metric(f"Live O/U Value ({target_ou})", f"{best_ou_val*100:.2f}%")
            if best_ou_val >= trigger_limit: 
                st.error(f"🚨 SNIPER ALERT: {target_ou} คุ้มค่าแก่การลงทุน! (Value > {sniper_threshold}%)")
                alert_triggered = True
            elif best_ou_val > 0.0:
                st.info(f"🟢 Marginal Edge: รอดูสถานการณ์ หรือน้ำไหลขึ้นอีกนิด")
            else:
                st.write("🛡️ ตลาดปกติ (Negative Value) รอจังหวะต่อไป")
                
        if alert_triggered:
            st.toast("🔥 พบช่องโหว่ความตื่นตระหนกของราคา! (Market Overreaction)", icon="🚨")
