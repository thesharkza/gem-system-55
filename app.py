import streamlit as st
import pandas as pd
import os
import re
import math
from datetime import datetime

# --- CONFIG ---
st.set_page_config(page_title="GEM System 6.0.3 (Pro Tool)", layout="wide")
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
    """ฟังก์ชันแปลงเรตราคา เช่น '0.5/1' -> 0.75, '2.5/3' -> 2.75"""
    line_str = line_str.replace('+', '')
    is_negative = '-' in line_str
    line_str = line_str.replace('-', '')
    try:
        if '/' in line_str:
            parts = line_str.split('/')
            val = (float(parts[0]) + float(parts[1])) / 2.0
        else:
            val = float(line_str)
        return -val if is_negative else val
    except:
        return 0.0

# ==========================================
# 1. ระบบคณิตศาสตร์ขั้นสูง (Pure Quant Engine)
# ==========================================
def power_devig(o_h, o_d, o_a):
    low, high = 0.0, 5.0
    for _ in range(20):
        k = (low + high) / 2
        implied_sum = (1/o_h)**k + (1/o_d)**k + (1/o_a)**k
        if implied_sum > 1: low = k
        else: high = k
    return (1/o_h)**k, (1/o_d)**k, (1/o_a)**k

def poisson(k, lam):
    return (lam**k * math.exp(-lam)) / math.factorial(k)

def calc_poisson_matrix(p_h, p_d, p_a, total_goals):
    lam_h = total_goals * (p_h + (p_d * 0.5))
    lam_a = total_goals * (p_a + (p_d * 0.5))
    matrix = [[poisson(i, lam_h) * poisson(j, lam_a) for j in range(6)] for i in range(6)]
    
    p_h_win_by_2plus = sum(matrix[i][j] for i in range(6) for j in range(6) if i - j >= 2)
    p_h_win_by_1 = sum(matrix[i][j] for i in range(6) for j in range(6) if i - j == 1)
    p_draw = sum(matrix[i][i] for i in range(6))
    p_a_win_by_1 = sum(matrix[i][j] for i in range(6) for j in range(6) if j - i == 1)
    p_a_win_by_2plus = sum(matrix[i][j] for i in range(6) for j in range(6) if j - i >= 2)
    
    total_sum = p_h_win_by_2plus + p_h_win_by_1 + p_draw + p_a_win_by_1 + p_a_win_by_2plus
    return (p_h_win_by_2plus/total_sum, p_h_win_by_1/total_sum, p_draw/total_sum, 
            p_a_win_by_1/total_sum, p_a_win_by_2plus/total_sum)

def calc_advanced_ah_ev(hdp, h_w2, h_w1, draw, a_w1, a_w2, odds, is_home):
    b = odds - 1
    if is_home: w2, w1, d, l1, l2 = h_w2, h_w1, draw, a_w1, a_w2
    else: w2, w1, d, l1, l2 = a_w2, a_w1, draw, h_w1, h_w2

    hdp_abs = abs(hdp)
    
    if hdp_abs == 0: return ((w2 + w1) * b) - ((l1 + l2) * 1)
    elif hdp_abs == 0.25: return ((w2 + w1) * b) - (d * 0.5) - ((l1 + l2) * 1)
    elif hdp_abs == 0.5: return ((w2 + w1) * b) - ((d + l1 + l2) * 1)
    elif hdp_abs == 0.75: return (w2 * b) + (w1 * (b/2)) - ((d + l1 + l2) * 1)
    elif hdp_abs == 1.0: return (w2 * b) + (w1 * 0) - ((d + l1 + l2) * 1)
    elif hdp_abs == 1.25: return (w2 * b) - (w1 * 0.5) - ((d + l1 + l2) * 1)
    
    if not is_home: 
        if hdp_abs == 0.25: return ((w2+w1)*b) + (d*(b/2)) - ((l1+l2)*1)
        elif hdp_abs == 0.5: return ((w2+w1+d)*b) - ((l1+l2)*1)
        elif hdp_abs == 0.75: return ((w2+w1+d)*b) - (l1*(1/2)) - (l2*1)
        elif hdp_abs == 1.0: return ((w2+w1+d)*b) - (l2*1)
    return 0.0

# ==========================================
# 2. ระบบฐานข้อมูลและ Backtest
# ==========================================
def save_to_csv(data_dict):
    df_new = pd.DataFrame([data_dict])
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
st.title("📊 GEM System 6.0.3: Pro Tool Edition")

tab1, tab2 = st.tabs(["🚀 Advanced Terminal", "📈 Performance Dashboard"])

with tab1:
    st.sidebar.header("💰 Portfolio Management")
    total_bankroll = st.sidebar.number_input("เงินทุนทั้งหมด (THB)", min_value=0.0, value=10000.0)
    
    # --- ส่วนที่ปรับปรุงใหม่: Smart Auto-Fill แบบ 2 ปุ่ม ---
    with st.expander("⚡ วางข้อความที่นี่เพื่อสกัดข้อมูลอัตโนมัติ (Smart Auto-Fill)", expanded=True):
        st.text_area("📋 ก๊อปปี้ราคาทั้งก้อนมาวางตรงนี้...", height=150, key="raw_text")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🪄 สกัดข้อมูล (Extract)", use_container_width=True):
                try:
                    raw = st.session_state.raw_text
                    
                    # 1. ชื่อคู่แข่งขัน
                    m_vs = re.search(r'(.*VS.*)', raw)
                    if m_vs: st.session_state.match_name = m_vs.group(1).strip()
                    
                    # 2. เหย้า 1X2 & HDP น้ำ (หาคำว่า "เหย้า" ที่ขึ้นต้นบรรทัด)
                    h_matches = re.findall(r'^\s*เหย้า\s+([0-9.]+)', raw, re.MULTILINE)
                    if len(h_matches) >= 1: st.session_state.h1x2_val = float(h_matches[0]) 
                    if len(h_matches) >= 2: st.session_state.hdp_h_w_val = float(h_matches[1]) 
                    
                    # 3. เสมอ 1X2
                    d_matches = re.findall(r'^\s*เสมอ\s+([0-9.]+)', raw, re.MULTILINE)
                    if len(d_matches) >= 1: st.session_state.d1x2_val = float(d_matches[0])
                    
                    # 4. เยือน 1X2 & HDP น้ำ
                    a_matches = re.findall(r'^\s*เยือน\s+([0-9.]+)', raw, re.MULTILINE)
                    if len(a_matches) >= 1: st.session_state.a1x2_val = float(a_matches[0]) 
                    if len(a_matches) >= 2: st.session_state.hdp_a_w_val = float(a_matches[1]) 
                    
                    # 5. AH เรตต่อรอง
                    ah_match = re.search(r'^\s*AH\s+([+-]?[0-9./]+)', raw, re.MULTILINE)
                    if ah_match: st.session_state.hdp_line_val = parse_line(ah_match.group(1))
                    
                    # 6. สูง/ต่ำ เรต (O/U)
                    ou_match = re.search(r'^\s*สูง/ต่ำ\s+([0-9./]+)', raw, re.MULTILINE)
                    if ou_match: st.session_state.ou_line_val = parse_line(ou_match.group(1))
                    
                    # 7. สูง น้ำ (ป้องกันไม่ให้ไปชนกับคำว่า สูง/ต่ำ)
                    o_match = re.search(r'^\s*สูง\s+([0-9.]+)', raw, re.MULTILINE)
                    if o_match: st.session_state.ou_over_w_val = float(o_match.group(1))
                    
                    # 8. ต่ำ น้ำ
                    u_match = re.search(r'^\s*ต่ำ\s+([0-9.]+)', raw, re.MULTILINE)
                    if u_match: st.session_state.ou_under_w_val = float(u_match.group(1))
                    
                    st.success("✅ สกัดข้อมูลสำเร็จ! ตัวเลขวิ่งเข้าช่องเรียบร้อย")
                except Exception as e:
                    st.error(f"⚠️ รูปแบบข้อความมีปัญหา: {e}")

        with col_btn2:
            if st.button("🗑️ ล้างข้อมูล (Clear)", use_container_width=True):
                st.session_state.raw_text = ""
                st.session_state.match_name = "ชื่อคู่แข่งขัน"
                st.session_state.h1x2_val = 1.0
                st.session_state.d1x2_val = 1.0
                st.session_state.a1x2_val = 1.0
                st.session_state.hdp_line_val = 0.0
                st.session_state.hdp_h_w_val = 0.0
                st.session_state.hdp_a_w_val = 0.0
                st.session_state.ou_line_val = 2.5
                st.session_state.ou_over_w_val = 0.0
                st.session_state.ou_under_w_val = 0.0
                st.rerun()

    # --- ช่อง Input (เชื่อมกับ Auto-fill ผ่าน key) ---
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
        st.subheader("2. ตลาด O/U & HDBA")
        ou_line = st.number_input("เรตสกอร์รวม (O/U)", format="%.2f", step=0.25, key="ou_line_val")
        ou_over_w = st.number_input("น้ำหน้าสูง (Over)", format="%.2f", key="ou_over_w_val")
        ou_under_w = st.number_input("น้ำหน้าต่ำ (Under)", format="%.2f", key="ou_under_w_val")
        hdba_val = st.slider("⚖️ HDBA Penalty %", 0.0, 10.0, 1.5)
        st.info("Remark: ลีกมาตรฐานยุโรป 1.5 | บอลถ้วยที่ต้องบินข้ามประเทศ 2.5-3.0 | โบลิเวีย ,เอกวาดอร์ (ที่ราบสูง) 4.5+")

    if st.button("🚀 ANALYZE WITH PURE MATH"):
        def fix(o): return o + 1.0 if o < 1.1 else o
        h_o, d_o, a_o = fix(h1x2), fix(d1x2), fix(a1x2)
        hw_o, aw_o, ow_o, uw_o = fix(hdp_h_w), fix(hdp_a_w), fix(ou_over_w), fix(ou_under_w)
        
        prob_h, prob_d, prob_a = power_devig(h_o, d_o, a_o)
        m_ou = (1/ow_o + 1/uw_o) - 1
        prob_over, prob_under = (1/ow_o)/(1+m_ou), (1/uw_o)/(1+m_ou)
        
        hw2, hw1, d_exact, aw1, aw2 = calc_poisson_matrix(prob_h, prob_d, prob_a, ou_line)
        
        is_h_fav = prob_h >= prob_a
        ev_h = calc_advanced_ah_ev(hdp_line, hw2, hw1, d_exact, aw1, aw2, hw_o, is_home=True)
        ev_a = calc_advanced_ah_ev(hdp_line, hw2, hw1, d_exact, aw1, aw2, aw_o, is_home=False) - (hdba_val/100)
        
        ev_over = (prob_over * (ow_o-1)) - (prob_under * 1)
        ev_under = (prob_under * (uw_o-1)) - (prob_over * 1)

        def get_defensive_k(ev, odds, bank):
            if ev < 0.05: return 0.0
            b_k, p_k = odds - 1, (ev + 1) / odds
            k_pct = ((b_k * p_k) - (1 - p_k)) / b_k
            return min(k_pct * 0.25, 0.05) * bank

        res_list = [{"n": "เจ้าบ้าน", "ev": ev_h, "odds": hw_o}, {"n": "ทีมเยือน", "ev": ev_a, "odds": aw_o},
                    {"n": "สูง", "ev": ev_over, "odds": ow_o}, {"n": "ต่ำ", "ev": ev_under, "odds": uw_o}]
        best = max(res_list, key=lambda x: x['ev'])
        k_money = get_defensive_k(best['ev'], best['odds'], total_bankroll)

        st.session_state['report'] = f"""📊 GEM System 6.0.3: Pro Tool
คู่: {match_name}
✅ True Prob: เหย้า {prob_h*100:.1f}% | เสมอ {prob_d*100:.1f}% | เยือน {prob_a*100:.1f}%
🔬 Poisson Score Analysis:
- ยิงขาด 2 ลูก+: เจ้าบ้าน {hw2*100:.1f}% | ทีมเยือน {aw2*100:.1f}%
- ยิงเฉือน 1 ลูก: เจ้าบ้าน {hw1*100:.1f}% | ทีมเยือน {aw1*100:.1f}%

สรุป: {"🔥 INVEST" if best['ev']>=0.05 else "🛡️ NO BET (Defensive Mode)"}
เป้าหมาย: {best['n'] if best['ev']>=0.05 else "N/A"} (EV: {best['ev']*100:.2f}%)
ยอดเงินที่ปลอดภัย: {k_money:,.2f} THB
"""
        st.session_state['log_data'] = {"Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Match": match_name, "HDP": hdp_line, "Target": best['n'], "EV_Pct": round(best['ev']*100, 2), "Investment": round(k_money, 2), "Odds": best['odds'], "Result": ""}

    if 'report' in st.session_state:
        st.info("💡 ข้อสังเกต: ระบบประมวลผลด้วย Pure Math ป้องกันบวกหลอก (EV > 5%)")
        st.text_area("Advanced Quant Report:", value=st.session_state['report'], height=250)
        if st.button("💾 บันทึกลง Log"):
            save_to_csv(st.session_state['log_data']); st.success("บันทึกสำเร็จ!"); st.rerun()

with tab2:
    logs = load_logs()
    if logs is not None:
        st.subheader("📝 บันทึกผลสกอร์ (พิมพ์สกอร์ในช่อง Result เช่น 2-1)")
        display_df = logs.sort_values(by='Time', ascending=False).reset_index(drop=True)
        edited_df = st.data_editor(display_df, column_config={"Result": st.column_config.TextColumn("Result (e.g. 2-1)")}, use_container_width=True, num_rows="dynamic")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("💾 Save Score & Calculate Profit"):
                edited_df.to_csv(LOG_FILE, index=False, encoding='utf-8-sig'); st.rerun()
        with col_btn2:
            if st.button("🗑️ ล้างประวัติทั้งหมด (Clear Logs)"):
                if os.path.exists(LOG_FILE): os.remove(LOG_FILE); st.warning("ลบประวัติเรียบร้อย"); st.rerun()

        logs['Net_Profit'] = logs.apply(calculate_net_profit, axis=1)
        inv_logs = logs[logs['Investment'] > 0]
        
        st.markdown("---")
        st.subheader("🏆 Performance Statistics")
        m1, m2, m3, m4 = st.columns(4)
        total_p = logs['Net_Profit'].sum()
        total_i = inv_logs['Investment'].sum()
        win_rate = (len(inv_logs[inv_logs['Net_Profit'] > 0]) / len(inv_logs) * 100) if not inv_logs.empty else 0
        
        m1.metric("กำไร/ขาดทุนสุทธิ", f"{total_p:,.2f} THB", delta=f"{total_p:,.2f}")
        m2.metric("ยอดรวมลงทุน", f"{total_i:,.2f} THB")
        m3.metric("Win Rate", f"{win_rate:.1f}%")
        m4.metric("ROI", f"{(total_p/total_i*100 if total_i > 0 else 0):.2f}%")

        if not logs.empty:
            st.subheader("📉 กราฟกำไรสะสม (Equity Curve)")
            logs_sorted = logs.sort_values(by='Time')
            logs_sorted['Cumulative_Profit'] = logs_sorted['Net_Profit'].cumsum()
            st.line_chart(logs_sorted.set_index('Time')['Cumulative_Profit'])
            st.download_button("📥 Download Full CSV Report", logs.to_csv(index=False).encode('utf-8-sig'), "gem_backtest_report.csv", "text/csv")
    else:
        st.info("ยังไม่มีข้อมูลบันทึกในระบบ")
