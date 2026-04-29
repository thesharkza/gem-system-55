import streamlit as st
import pandas as pd
import os
import re
import math
from datetime import datetime

# --- CONFIG ---
st.set_page_config(page_title="GEM System 6.0.0 (Quant)", layout="wide")
LOG_FILE = "gem_history_log.csv"

# ==========================================
# 1. ระบบคณิตศาสตร์ขั้นสูง (The Quant Engine)
# ==========================================

def power_devig(o_h, o_d, o_a):
    """ถอดค่าต๋งด้วย Power Method (แก้ปัญหา Favorite-Longshot Bias)"""
    low, high = 0.0, 5.0
    for _ in range(20): # Binary Search หาค่า k
        k = (low + high) / 2
        implied_sum = (1/o_h)**k + (1/o_d)**k + (1/o_a)**k
        if implied_sum > 1: low = k
        else: high = k
    return (1/o_h)**k, (1/o_d)**k, (1/o_a)**k

def poisson(k, lam):
    """ฟังก์ชันการแจกแจงแบบปัวซง (Poisson Distribution)"""
    return (lam**k * math.exp(-lam)) / math.factorial(k)

def calc_poisson_matrix(p_h, p_d, p_a, total_goals):
    """แปลง True Prob และเรต O/U เป็นตารางสกอร์ xG เพื่อหาโอกาสผลต่างประตู"""
    # ประมาณการค่า xG (Expected Goals) เบื้องต้น
    lam_h = total_goals * (p_h + (p_d * 0.5)) / (p_h + p_a + p_d)
    lam_a = total_goals * (p_a + (p_d * 0.5)) / (p_h + p_a + p_d)
    
    # ถ้าทีมต่อจัด มีโอกาสยิงเยอะกว่า
    if p_h > p_a: lam_h = lam_h * 1.1; lam_a = lam_a * 0.9
    else: lam_a = lam_a * 1.1; lam_h = lam_h * 0.9

    # สร้าง Matrix จำลองสกอร์ 0-5 ประตู
    matrix = [[poisson(i, lam_h) * poisson(j, lam_a) for j in range(6)] for i in range(6)]
    
    # คำนวณความน่าจะเป็นของผลต่างประตู
    p_h_win_by_2plus = sum(matrix[i][j] for i in range(6) for j in range(6) if i - j >= 2)
    p_h_win_by_1 = sum(matrix[i][j] for i in range(6) for j in range(6) if i - j == 1)
    p_draw = sum(matrix[i][i] for i in range(6))
    p_a_win_by_1 = sum(matrix[i][j] for i in range(6) for j in range(6) if j - i == 1)
    p_a_win_by_2plus = sum(matrix[i][j] for i in range(6) for j in range(6) if j - i >= 2)
    
    # Normalization ให้รวมกันได้ 1 (100%)
    total_sum = p_h_win_by_2plus + p_h_win_by_1 + p_draw + p_a_win_by_1 + p_a_win_by_2plus
    return (p_h_win_by_2plus/total_sum, p_h_win_by_1/total_sum, p_draw/total_sum, 
            p_a_win_by_1/total_sum, p_a_win_by_2plus/total_sum)

def calc_advanced_ah_ev(hdp, h_w2, h_w1, draw, a_w1, a_w2, odds, is_home):
    """คำนวณ EV ตามโอกาสของผลต่างประตูที่แท้จริง (เลิกใช้ 50/50 เดาสุ่ม)"""
    b = odds - 1
    if is_home:
        w2, w1, d, l1, l2 = h_w2, h_w1, draw, a_w1, a_w2
    else:
        # สลับฝั่งถ้าคำนวณให้ทีมเยือน
        w2, w1, d, l1, l2 = a_w2, a_w1, draw, h_w1, h_w2

    # แปลง HDP เชิงบวกให้มองมุมทีมต่อ
    hdp_abs = abs(hdp)
    
    if hdp_abs == 0:
        return ((w2 + w1) * b) - ((l1 + l2) * 1)
    elif hdp_abs == 0.25:
        # ต่อ 0.25: ชนะ=ได้เต็ม, เสมอ=เสียครึ่ง, แพ้=เสียเต็ม
        return ((w2 + w1) * b) - (d * 0.5) - ((l1 + l2) * 1)
    elif hdp_abs == 0.5:
        # ต่อ 0.5: ชนะ=ได้เต็ม, เสมอ/แพ้=เสียเต็ม
        return ((w2 + w1) * b) - ((d + l1 + l2) * 1)
    elif hdp_abs == 0.75:
        # ต่อ 0.75: ชนะ 2+=ได้เต็ม, ชนะ 1=ได้ครึ่ง, เสมอ/แพ้=เสียเต็ม
        return (w2 * b) + (w1 * (b/2)) - ((d + l1 + l2) * 1)
    elif hdp_abs == 1.0:
        # ต่อ 1.0: ชนะ 2+=ได้เต็ม, ชนะ 1=เจ๊า, เสมอ/แพ้=เสียเต็ม
        return (w2 * b) + (w1 * 0) - ((d + l1 + l2) * 1)
    elif hdp_abs == 1.25:
        # ต่อ 1.25: ชนะ 2+=ได้เต็ม, ชนะ 1=เสียครึ่ง, เสมอ/แพ้=เสียเต็ม
        return (w2 * b) - (w1 * 0.5) - ((d + l1 + l2) * 1)
    
    # Fallback สำหรับเรตแปลกๆ หรือเรตรอง (รับแต้มต่อ)
    if not is_home: # มุมทีมรอง
        if hdp_abs == 0.25: return ((w2+w1)*b) + (d*(b/2)) - ((l1+l2)*1)
        elif hdp_abs == 0.5: return ((w2+w1+d)*b) - ((l1+l2)*1)
        elif hdp_abs == 0.75: return ((w2+w1+d)*b) - (l1*(1/2)) - (l2*1)
        elif hdp_abs == 1.0: return ((w2+w1+d)*b) - (l2*1)
        
    return 0.0 # Safety fallback

# ==========================================
# 2. ระบบฐานข้อมูลและ Backtest (เดิม)
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
st.title("📊 GEM System 6.0: The Quant Revival (Poisson Edition)")

tab1, tab2 = st.tabs(["🚀 Advanced Terminal", "📈 Performance Dashboard"])

with tab1:
    st.sidebar.header("💰 Portfolio Management")
    total_bankroll = st.sidebar.number_input("เงินทุนทั้งหมด (THB)", min_value=0.0, value=10000.0)
    match_name = st.text_input("📝 คู่แข่งขัน", "ชื่อคู่แข่งขัน")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1. ตลาดราคาพูล & AH")
        h1x2 = st.number_input("เหย้า (1X2)", value=1.0)
        d1x2 = st.number_input("เสมอ (1X2)", value=1.0)
        a1x2 = st.number_input("เยือน (1X2)", value=1.0)
        hdp_line = st.number_input("เรตต่อรอง (HDP)", value=0.0, step=0.25)
        hdp_h_w = st.number_input("น้ำเจ้าบ้าน", value=0.0)
        hdp_a_w = st.number_input("น้ำทีมเยือน", value=0.0)

    with col2:
        st.subheader("2. ตลาด O/U & HDBA")
        ou_line = st.number_input("เรตสกอร์รวม (O/U) *สำคัญต่อ xG*", value=2.5, step=0.25)
        ou_over_w = st.number_input("น้ำหน้าสูง (Over)", value=0.0)
        ou_under_w = st.number_input("น้ำหน้าต่ำ (Under)", value=0.0)
        hdba_val = st.slider("⚖️ HDBA Penalty %", 0.0, 10.0, 1.5)
        st.info("Remark: ลีกมาตรฐานยุโรป 1.5 | บอลถ้วยที่ต้องบินข้ามประเทศ 2.5-3.0 | โบลิเวีย/เอกวาดอร์ (ที่ราบสูง) 4.5+")

    if st.button("🚀 ANALYZE WITH POISSON ENGINE"):
        def fix(o): return o + 1.0 if o < 1.1 else o
        h_o, d_o, a_o = fix(h1x2), fix(d1x2), fix(a1x2)
        hw_o, aw_o, ow_o, uw_o = fix(hdp_h_w), fix(hdp_a_w), fix(ou_over_w), fix(ou_under_w)
        
        # 1. Devigging ด้วย Power Method (แก้ Bias)
        prob_h, prob_d, prob_a = power_devig(h_o, d_o, a_o)
        
        m_ou = (1/ow_o + 1/uw_o) - 1
        prob_over, prob_under = (1/ow_o)/(1+m_ou), (1/uw_o)/(1+m_ou)
        
        # 2. คำนวณ Poisson Matrix หาโอกาสผลต่างประตู
        hw2, hw1, d_exact, aw1, aw2 = calc_poisson_matrix(prob_h, prob_d, prob_a, ou_line)
        
        # 3. คำนวณ EV ตามสูตร AH เชิงลึก
        is_h_fav = prob_h >= prob_a
        ev_h = calc_advanced_ah_ev(hdp_line, hw2, hw1, d_exact, aw1, aw2, hw_o, is_home=True)
        ev_a = calc_advanced_ah_ev(hdp_line, hw2, hw1, d_exact, aw1, aw2, aw_o, is_home=False) - (hdba_val/100)
        
        ev_over = (prob_over * (ow_o-1)) - (prob_under * 1)
        ev_under = (prob_under * (uw_o-1)) - (prob_over * 1)

        # 4. Defensive Money Management (Quarter Kelly)
        def get_defensive_k(ev, odds, bank):
            if ev < 0.05: return 0.0 # เปลี่ยนเป็น 5% Margin of Safety
            b_k, p_k = odds - 1, (ev + 1) / odds
            k_pct = ((b_k * p_k) - (1 - p_k)) / b_k
            return min(k_pct * 0.25, 0.05) * bank # Quarter Kelly (Max 5%)

        res_list = [{"n": "เจ้าบ้าน", "ev": ev_h, "odds": hw_o}, {"n": "ทีมเยือน", "ev": ev_a, "odds": aw_o},
                    {"n": "สูง", "ev": ev_over, "odds": ow_o}, {"n": "ต่ำ", "ev": ev_under, "odds": uw_o}]
        best = max(res_list, key=lambda x: x['ev'])
        k_money = get_defensive_k(best['ev'], best['odds'], total_bankroll)

        # แสดงค่าสถานะเชิงลึกเพื่อการศึกษา
        st.session_state['report'] = f"""📊 GEM System 6.0: Poisson Engine
คู่: {match_name}
✅ True Prob (Power Method): เหย้า {prob_h*100:.1f}% | เสมอ {prob_d*100:.1f}% | เยือน {prob_a*100:.1f}%
🔬 Poisson Score Analysis:
- โอกาสยิงขาด 2 ลูกขึ้นไป: เจ้าบ้าน {hw2*100:.1f}% | ทีมเยือน {aw2*100:.1f}%
- โอกาสยิงเฉือน 1 ลูก: เจ้าบ้าน {hw1*100:.1f}% | ทีมเยือน {aw1*100:.1f}%

สรุป: {"🔥 INVEST" if best['ev']>=0.05 else "🛡️ NO BET (Defensive Mode)"}
เป้าหมาย: {best['n'] if best['ev']>=0.05 else "N/A"} (EV: {best['ev']*100:.2f}%)
ยอดเงินที่ปลอดภัย: {k_money:,.2f} THB
"""
        st.session_state['log_data'] = {"Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Match": match_name, "HDP": hdp_line, "Target": best['n'], "EV_Pct": round(best['ev']*100, 2), "Investment": round(k_money, 2), "Odds": best['odds'], "Result": ""}

    if 'report' in st.session_state:
        st.info("💡 ข้อสังเกต: ระบบปรับสู่ Defensive Mode (ต้องการ EV > 5% และเดินเงินแบบ Quarter-Kelly)")
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
