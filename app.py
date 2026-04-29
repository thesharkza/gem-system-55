import streamlit as st
import pandas as pd
import os
import re
import math
from datetime import datetime, timezone, timedelta
import plotly.graph_objects as go

# --- CONFIG ---
st.set_page_config(page_title="GEM System 7.0 (Syndicate Edition)", layout="wide")
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
    """อัลกอริทึม Shin's Method สำหรับหา True Prob"""
    pi = [1/o_h, 1/o_d, 1/o_a]
    sum_pi = sum(pi)
    if sum_pi <= 1.0:
        return pi[0]/sum_pi, pi[1]/sum_pi, pi[2]/sum_pi
    
    low, high = 0.0, 1.0
    for _ in range(100): 
        z = (low + high) / 2
        try:
            p = [(math.sqrt(z**2 + 4*(1-z)*pi_i) - z) / (2*(1-z)) for pi_i in pi]
            if sum(p) > 1: low = z
            else: high = z
        except:
            break
            
    p = [(math.sqrt(z**2 + 4*(1-z)*pi_i) - z) / (2*(1-z)) for pi_i in pi]
    sum_p = sum(p) 
    return p[0]/sum_p, p[1]/sum_p, p[2]/sum_p

def poisson(k, lam):
    return (lam**k * math.exp(-lam)) / math.factorial(k)

def calc_dixon_coles_matrix(p_h, p_d, p_a, total_goals, rho):
    """อัปเกรด Poisson เป็น Dixon-Coles ปรับแก้น้ำหนักสกอร์ต่ำ (0-0, 1-1)"""
    lam_h = total_goals * (p_h + (p_d * 0.5))
    lam_a = total_goals * (p_a + (p_d * 0.5))
    matrix = [[0.0 for j in range(6)] for i in range(6)]
    
    for i in range(6):
        for j in range(6):
            base_prob = poisson(i, lam_h) * poisson(j, lam_a)
            # Dixon-Coles Adjustment
            if i == 0 and j == 0: tau = 1 - (lam_h * lam_a * rho)
            elif i == 0 and j == 1: tau = 1 + (lam_h * rho)
            elif i == 1 and j == 0: tau = 1 + (lam_a * rho)
            elif i == 1 and j == 1: tau = 1 - rho
            else: tau = 1.0
            
            matrix[i][j] = max(0, base_prob * tau) 
            
    # Normalize Matrix
    total_prob = sum(matrix[i][j] for i in range(6) for j in range(6))
    for i in range(6):
        for j in range(6):
            matrix[i][j] /= total_prob

    # คำนวณ AH
    p_h_win_by_2plus = sum(matrix[i][j] for i in range(6) for j in range(6) if i - j >= 2)
    p_h_win_by_1 = sum(matrix[i][j] for i in range(6) for j in range(6) if i - j == 1)
    p_draw = sum(matrix[i][i] for i in range(6))
    p_a_win_by_1 = sum(matrix[i][j] for i in range(6) for j in range(6) if j - i == 1)
    p_a_win_by_2plus = sum(matrix[i][j] for i in range(6) for j in range(6) if j - i >= 2)
    
    # คำนวณ O/U
    p_total = {k: 0.0 for k in range(12)}
    for i in range(6):
        for j in range(6):
            p_total[i+j] += matrix[i][j]
            
    return (p_h_win_by_2plus, p_h_win_by_1, p_draw, p_a_win_by_1, p_a_win_by_2plus, p_total)

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
            p_win = sum(p_total.get(k, 0) for k in p_total if k > floor_line)
            p_loss = sum(p_total.get(k, 0) for k in p_total if k < floor_line)
            return (p_win * b) - (p_loss * 1)
        elif remainder == 0.25:
            p_win = sum(p_total.get(k, 0) for k in p_total if k >= floor_line + 1)
            p_half_loss = p_total.get(floor_line, 0.0)
            p_loss = sum(p_total.get(k, 0) for k in p_total if k < floor_line)
            return (p_win * b) - (p_half_loss * 0.5) - (p_loss * 1)
        elif remainder == 0.5:
            p_win = sum(p_total.get(k, 0) for k in p_total if k >= floor_line + 1)
            p_loss = sum(p_total.get(k, 0) for k in p_total if k <= floor_line)
            return (p_win * b) - (p_loss * 1)
        elif remainder == 0.75:
            p_win = sum(p_total.get(k, 0) for k in p_total if k >= floor_line + 2)
            p_half_win = p_total.get(floor_line + 1, 0.0)
            p_loss = sum(p_total.get(k, 0) for k in p_total if k <= floor_line)
            return (p_win * b) + (p_half_win * (b / 2)) - (p_loss * 1)
    else: 
        if remainder == 0.0:
            p_win = sum(p_total.get(k, 0) for k in p_total if k < floor_line)
            p_loss = sum(p_total.get(k, 0) for k in p_total if k > floor_line)
            return (p_win * b) - (p_loss * 1)
        elif remainder == 0.25:
            p_win = sum(p_total.get(k, 0) for k in p_total if k < floor_line)
            p_half_win = p_total.get(floor_line, 0.0)
            p_loss = sum(p_total.get(k, 0) for k in p_total if k >= floor_line + 1)
            return (p_win * b) + (p_half_win * (b / 2)) - (p_loss * 1)
        elif remainder == 0.5:
            p_win = sum(p_total.get(k, 0) for k in p_total if k <= floor_line)
            p_loss = sum(p_total.get(k, 0) for k in p_total if k >= floor_line + 1)
            return (p_win * b) - (p_loss * 1)
        elif remainder == 0.75:
            p_win = sum(p_total.get(k, 0) for k in p_total if k <= floor_line)
            p_half_loss = p_total.get(floor_line + 1, 0.0)
            p_loss = sum(p_total.get(k, 0) for k in p_total if k >= floor_line + 2)
            return (p_win * b) - (p_half_loss * 0.5) - (p_loss * 1)
    return 0.0

# ==========================================
# 2. ระบบฐานข้อมูลและ Backtest
# ==========================================
def save_to_csv(data_list):
    if not data_list: return
    df_new = pd.DataFrame(data_list)
    if not os.path.isfile(LOG_FILE): df_new.to_csv(LOG_FILE, index=False, encoding='utf-8-sig')
    else: df_new.to_csv(LOG_FILE, mode='a', index=False, header=False, encoding='utf-8-sig')

def load_logs():
    if os.path.exists(LOG_FILE):
        try:
            df_logs = pd.read_csv(LOG_FILE, on_bad_lines='skip', encoding='utf-8-sig')
            df_logs['Match'] = df_logs['Match'].astype(str)
            df_logs['Target'] = df_logs['Target'].astype(str)
            df_logs['Result'] = df_logs['Result'].fillna("").astype(str)
            df_logs['HDP'] = pd.to_numeric(df_logs['HDP'], errors='coerce').fillna(0.0)
            df_logs['EV_Pct'] = pd.to_numeric(df_logs['EV_Pct'], errors='coerce').fillna(0.0)
            df_logs['Investment'] = pd.to_numeric(df_logs['Investment'], errors='coerce').fillna(0.0)
            df_logs['Odds'] = pd.to_numeric(df_logs.get('Odds', 1.90), errors='coerce').fillna(1.90)
            df_logs['Time'] = pd.to_datetime(df_logs['Time'], errors='coerce')
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

# ==========================================
# 3. UI - Main Layout
# ==========================================
st.title("📊 GEM System 7.0: Syndicate Edition")

tab1, tab2 = st.tabs(["🚀 Advanced Terminal", "📈 Performance Dashboard"])

with tab1:
    st.sidebar.header("💰 Portfolio Management")
    total_bankroll = st.sidebar.number_input("เงินทุนทั้งหมด (THB)", min_value=0.0, value=10000.0)
    
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Syndicate Parameters")
    dc_rho = st.sidebar.slider("🔗 Dixon-Coles Rho (ความสัมพันธ์สกอร์)", -0.30, 0.0, -0.10, step=0.01, help="ค่าติดลบยิ่งมาก ยิ่งเพิ่มน้ำหนักให้สกอร์เสมอ (0-0, 1-1) มากขึ้น")
    hdba_val = st.sidebar.slider("⚖️ HDBA Penalty %", 0.0, 10.0, 1.5)
    
    def clear_form_data():
        st.session_state.raw_text = ""
        st.session_state.match_name = "ชื่อคู่แข่งขัน"
        st.session_state.h1x2_val = 1.0; st.session_state.d1x2_val = 1.0; st.session_state.a1x2_val = 1.0
        st.session_state.hdp_line_val = 0.0; st.session_state.hdp_h_w_val = 0.0; st.session_state.hdp_a_w_val = 0.0
        st.session_state.ou_line_val = 2.5; st.session_state.ou_over_w_val = 0.0; st.session_state.ou_under_w_val = 0.0

    with st.expander("⚡ วางข้อความที่นี่เพื่อสกัดข้อมูลอัตโนมัติ (Smart Auto-Fill)", expanded=True):
        st.text_area("📋 ก๊อปปี้ราคาทั้งก้อนมาวางตรงนี้...", height=150, key="raw_text")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🪄 สกัดข้อมูล (Extract)", use_container_width=True):
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
                    st.success("✅ สกัดข้อมูลสำเร็จ!")
                except Exception as e:
                    st.error(f"⚠️ รูปแบบข้อความมีปัญหา: {e}")
        with col_btn2:
            st.button("🗑️ ล้างข้อมูล (Clear)", use_container_width=True, on_click=clear_form_data)

    match_name = st.text_input("📝 คู่แข่งขัน", key="match_name")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1. ตลาดราคาพูล & AH")
        h1x2 = st.number_input("เหย้า (1X2)", format="%.2f", key="h1x2_val")
        d1x2 = st.number_input("เสมอ (1X2)", format="%.2f", key="d1x2_val")
        a1x2 = st.number_input("เยือน (1X2)", format="%.2f", key="a1x2_val")
        hdp_line = st.number_input("เรตต่อรอง (HDP)", format="%.2f", step=0.25, key="hdp_line_val")
        hdp_h_w = st.number_input("น้ำเจ้าบ้าน", format="%.2f", key="hdp_h_w_val")
        hdp_a_w = st.number_input("น้ำทีมเยือน", format="%.2f", key="hdp_a_w_val")
    with col2:
        st.subheader("2. ตลาด O/U")
        ou_line = st.number_input("เรตสกอร์รวม (O/U)", format="%.2f", step=0.25, key="ou_line_val")
        ou_over_w = st.number_input("น้ำหน้าสูง (Over)", format="%.2f", key="ou_over_w_val")
        ou_under_w = st.number_input("น้ำหน้าต่ำ (Under)", format="%.2f", key="ou_under_w_val")

    if st.button("🚀 ANALYZE WITH SYNDICATE ENGINE"):
        def fix(o): return o + 1.0 if o < 1.1 else o
        h_o, d_o, a_o = fix(h1x2), fix(d1x2), fix(a1x2)
        hw_o, aw_o, ow_o, uw_o = fix(hdp_h_w), fix(hdp_a_w), fix(ou_over_w), fix(ou_under_w)
        
        # ถอดต๋งด้วย Shin's Method
        prob_h, prob_d, prob_a = shin_devig(h_o, d_o, a_o)
        
        # แปลงเป็นตารางสกอร์ด้วย Dixon-Coles
        hw2, hw1, d_exact, aw1, aw2, p_total = calc_dixon_coles_matrix(prob_h, prob_d, prob_a, ou_line, dc_rho)
        
        is_h_fav = prob_h >= prob_a
        ev_h = calc_advanced_ah_ev(hdp_line, hw2, hw1, d_exact, aw1, aw2, hw_o, is_fav_team=is_h_fav)
        ev_a = calc_advanced_ah_ev(hdp_line, aw2, aw1, d_exact, hw1, hw2, aw_o, is_fav_team=not is_h_fav) - (hdba_val/100)
        
        ev_over = calc_advanced_ou_ev(ou_line, p_total, ow_o, is_over=True)
        ev_under = calc_advanced_ou_ev(ou_line, p_total, uw_o, is_over=False)

        def get_defensive_k(ev, odds, bank):
            if ev < 0.05: return 0.0
            b_k, p_k = odds - 1, (ev + 1) / odds
            k_pct = ((b_k * p_k) - (1 - p_k)) / b_k
            return min(k_pct * 0.25, 0.05) * bank

        ah_list = [{"n": "เจ้าบ้าน", "ev": ev_h, "odds": hw_o, "hdp": hdp_line}, 
                   {"n": "ทีมเยือน", "ev": ev_a, "odds": aw_o, "hdp": hdp_line}]
        ou_list = [{"n": "สูง", "ev": ev_over, "odds": ow_o, "hdp": ou_line}, 
                   {"n": "ต่ำ", "ev": ev_under, "odds": uw_o, "hdp": ou_line}]
        
        best_ah = max(ah_list, key=lambda x: x['ev'])
        best_ou = max(ou_list, key=lambda x: x['ev'])
        
        k_money_ah = get_defensive_k(best_ah['ev'], best_ah['odds'], total_bankroll)
        k_money_ou = get_defensive_k(best_ou['ev'], best_ou['odds'], total_bankroll)

        ah_status = "🔥 INVEST" if best_ah['ev'] >= 0.05 else "🛡️ NO BET"
        ou_status = "🔥 INVEST" if best_ou['ev'] >= 0.05 else "🛡️ NO BET"

        st.session_state['report'] = f"""📊 GEM System 7.0: Syndicate Edition
คู่: {match_name}
✅ True Prob (Shin's Method): เหย้า {prob_h*100:.1f}% | เสมอ {prob_d*100:.1f}% | เยือน {prob_a*100:.1f}%
🔬 Model: Dixon-Coles (Rho={dc_rho})

🎯 สรุปผลการลงทุน (Dual Target Process):
[ตลาด AH] {ah_status}
- เป้าหมาย: {best_ah['n']} (EV: {best_ah['ev']*100:.2f}%)
- ยอดเงินลงทุน: {k_money_ah:,.2f} THB

[ตลาด O/U] {ou_status}
- เป้าหมาย: {best_ou['n']} (EV: {best_ou['ev']*100:.2f}%)
- ยอดเงินลงทุน: {k_money_ou:,.2f} THB
"""
        # ========================================================
        # อัปเดตเวลาให้เป็น Timezone ประเทศไทย (UTC+7)
        # ========================================================
        tz_th = timezone(timedelta(hours=7))
        current_time = datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S")

        logs_to_save = []
        if best_ah['ev'] >= 0.05:
            logs_to_save.append({"Time": current_time, "Match": match_name, "HDP": best_ah['hdp'], "Target": best_ah['n'], "EV_Pct": round(best_ah['ev']*100, 2), "Investment": round(k_money_ah, 2), "Odds": best_ah['odds'], "Result": ""})
        if best_ou['ev'] >= 0.05:
            logs_to_save.append({"Time": current_time, "Match": match_name, "HDP": best_ou['hdp'], "Target": best_ou['n'], "EV_Pct": round(best_ou['ev']*100, 2), "Investment": round(k_money_ou, 2), "Odds": best_ou['odds'], "Result": ""})
        if not logs_to_save:
            logs_to_save.append({"Time": current_time, "Match": match_name, "HDP": hdp_line, "Target": "NO BET", "EV_Pct": 0.0, "Investment": 0.0, "Odds": 0.0, "Result": ""})

        st.session_state['log_data'] = logs_to_save

    if 'report' in st.session_state:
        st.info("💡 Powered by Shin's Method & Dixon-Coles Distribution")
        st.text_area("Advanced Quant Report:", value=st.session_state['report'], height=250)
        if st.button("💾 บันทึกลง Log"):
            save_to_csv(st.session_state['log_data'])
            st.success("บันทึกสำเร็จ!")
            st.rerun()

with tab2:
    logs = load_logs()
    if logs is not None:
        st.subheader("📝 บันทึกผลสกอร์ (พิมพ์สกอร์ในช่อง Result เช่น 2-1)")
        # --- บรรทัดที่ถูกตัดหายไปได้รับการแก้ไขแล้วด้านล่างนี้ ---
        display_df = logs.sort_values(by='Time', ascending=False).reset_index(drop=True)
        edited_df = st.data_editor(display_df, column_config={"Result": st.column_config.TextColumn("Result (e.g. 2-1)")}, use_container_width=True, num_rows="dynamic")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("💾 Save Score & Calculate Profit"):
                edited_df.to_csv(LOG_FILE, index=False, encoding='utf-8-sig')
                st.rerun()
        with col_btn2:
            if st.button("🗑️ ล้างประวัติทั้งหมด (Clear Logs)"):
                if os.path.exists(LOG_FILE): 
                    os.remove(LOG_FILE)
                    st.warning("ลบประวัติเรียบร้อย")
                    st.rerun()
        
        logs['Net_Profit'] = logs.apply(calculate_net_profit, axis=1)
        inv_logs = logs[logs['Investment'] > 0]
        
        st.markdown("---")
        st.subheader("🏆 Performance Statistics")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("กำไรสุทธิ", f"{logs['Net_Profit'].sum():,.2f} THB")
        m2.metric("ยอดรวมลงทุน", f"{inv_logs['Investment'].sum():,.2f} THB")
        m3.metric("Win Rate", f"{(len(inv_logs[inv_logs['Net_Profit']>0])/len(inv_logs)*100 if not inv_logs.empty else 0):.1f}%")
        m4.metric("ROI", f"{(logs['Net_Profit'].sum()/inv_logs['Investment'].sum()*100 if not inv_logs.empty and inv_logs['Investment'].sum()>0 else 0):.2f}%")
        
        # ========================================================
        # ระบบกราฟ Plotly สไตล์ Modern สบายตา
        # ========================================================
        if not logs.empty:
            st.markdown("---")
            st.subheader("📉 กราฟกำไรสะสม (Equity Curve)")
            
            logs_sorted = logs.sort_values(by='Time')
            logs_sorted['Cumulative_Profit'] = logs_sorted['Net_Profit'].cumsum()

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=logs_sorted['Time'],
                y=logs_sorted['Cumulative_Profit'],
                mode='lines',
                line=dict(color='#00FF7F', width=3, shape='spline'), 
                fill='tozeroy', 
                fillcolor='rgba(0, 255, 127, 0.15)',
                name='กำไรสะสม',
                hovertemplate='<b>วันที่/เวลา:</b> %{x}<br><b>กำไรสะสม:</b> %{y:,.2f} THB<extra></extra>'
            ))

            fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False, title="", showticklabels=True),
                yaxis=dict(showgrid=True, gridcolor='rgba(128, 128, 128, 0.2)', title="ยอดเงิน (THB)", zeroline=True, zerolinecolor='rgba(255, 0, 0, 0.3)'),
                hovermode="x unified",
                margin=dict(l=0, r=0, t=30, b=0)
            )

            st.plotly_chart(fig, use_container_width=True)
            
            st.download_button("📥 Download Full CSV Report", logs.to_csv(index=False).encode('utf-8-sig'), "gem_backtest_report.csv", "text/csv")
    else:
        st.info("ยังไม่มีข้อมูลบันทึกในระบบ")
