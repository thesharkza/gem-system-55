import streamlit as st
import pandas as pd
import os
import re
from datetime import datetime

# --- CONFIG ---
st.set_page_config(page_title="GEM System 5.6.18", layout="wide")
LOG_FILE = "gem_history_log.csv"

# ==========================================
# 1. ระบบจัดการฐานข้อมูล (Robust & Type-Safe)
# ==========================================
def save_to_csv(data_dict):
    df_new = pd.DataFrame([data_dict])
    if not os.path.isfile(LOG_FILE):
        df_new.to_csv(LOG_FILE, index=False, encoding='utf-8-sig')
    else:
        df_new.to_csv(LOG_FILE, mode='a', index=False, header=False, encoding='utf-8-sig')

def load_logs():
    if os.path.exists(LOG_FILE):
        try:
            df_logs = pd.read_csv(LOG_FILE, on_bad_lines='skip', encoding='utf-8-sig')
            # บังคับประเภทข้อมูลเพื่อป้องกัน st.data_editor พัง
            df_logs['Match'] = df_logs['Match'].astype(str)
            df_logs['Target'] = df_logs['Target'].astype(str)
            df_logs['Result'] = df_logs['Result'].fillna("").astype(str)
            df_logs['HDP'] = pd.to_numeric(df_logs['HDP'], errors='coerce').fillna(0.0)
            df_logs['EV_Pct'] = pd.to_numeric(df_logs['EV_Pct'], errors='coerce').fillna(0.0)
            df_logs['Investment'] = pd.to_numeric(df_logs['Investment'], errors='coerce').fillna(0.0)
            df_logs['Odds'] = pd.to_numeric(df_logs.get('Odds', 1.90), errors='coerce').fillna(1.90)
            df_logs['Time'] = pd.to_datetime(df_logs['Time'], errors='coerce')
            return df_logs.dropna(subset=['Time'])
        except Exception as e:
            st.error(f"⚠️ ไม่สามารถโหลด Log ได้: {e}")
            return None
    return None

def calculate_net_profit(row):
    """ตัดสินผลแพ้ชนะและคำนวณกำไรสุทธิแบบ AH/OU Logic"""
    try:
        if pd.isna(row['Result']) or row['Result'] == "" or row['Investment'] <= 0:
            return 0.0
        
        # แกะสกอร์ (เช่น "2-1")
        scores = re.findall(r'\d+', str(row['Result']))
        if len(scores) < 2: return 0.0
        h_score, a_score = int(scores[0]), int(scores[1])
        
        hdp, target, odds, invest = float(row['HDP']), row['Target'], float(row['Odds']), float(row['Investment'])
        diff = h_score - a_score
        
        # คำนวณหา Net Margin (ความได้เปรียบหลังจบเกม)
        if target == "เจ้าบ้าน": net_margin = diff - hdp
        elif target == "ทีมเยือน": net_margin = (a_score - h_score) + hdp
        elif target == "สูง": net_margin = (h_score + a_score) - hdp
        elif target == "ต่ำ": net_margin = hdp - (h_score + a_score)
        else: return 0.0

        # ตัดสินผลคูณเงินรางวัล
        if net_margin > 0.25: return invest * (odds - 1)  # ชนะเต็ม
        elif net_margin == 0.25: return (invest * (odds - 1)) / 2 # ชนะครึ่ง
        elif net_margin == 0: return 0.0 # เสมอคืนทุน
        elif net_margin == -0.25: return -(invest / 2) # เสียครึ่ง
        else: return -invest # แพ้เต็ม
    except:
        return 0.0

# ==========================================
# 2. ฟังก์ชันสมองกล (Universal Engine)
# ==========================================
def calc_universal_ev(hdp, p_win, p_draw, p_loss, odds, is_fav):
    b = odds - 1 
    if hdp % 1 == 0 and hdp > 0:
        if is_fav: return (p_win * 0.55 * b) - ((p_draw + p_loss) * 1)
        else: return ((p_win + p_draw) * b) - (p_loss * 0.55 * 1)
    elif hdp == 0:
        return (p_win * b) - (p_loss * 1)
    elif hdp % 1 == 0.5:
        if is_fav: return (p_win * b) - ((p_draw + p_loss) * 1)
        else: return ((p_win + p_draw) * b) - (p_loss * 1)
    elif hdp % 1 == 0.25:
        if is_fav: return (p_win * b) - (p_draw * 0.5) - (p_loss * 1)
        else: return (p_win * b) + (p_draw * b/2) - (p_loss * 1)
    elif hdp % 1 == 0.75:
        if is_fav: return (p_win * 0.5 * b) + (p_win * 0.5 * b/2) - ((p_draw + p_loss) * 1)
        else: return ((p_win + p_draw) * b) - (p_loss * 0.5 * 0.5) - (p_loss * 0.5 * 1)
    return (p_win * b) - ((p_draw + p_loss) * 1)

# ==========================================
# 3. UI - Main Layout
# ==========================================
st.title("📊 GEM System 5.6.18: Ultimate Backtest Suite")

tab1, tab2 = st.tabs(["🚀 Analysis Terminal", "📈 Performance Dashboard"])

with tab1:
    st.sidebar.header("💰 Portfolio")
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
        ou_line = st.number_input("เรตสกอร์รวม (O/U)", value=2.0, step=0.25)
        ou_over_w = st.number_input("น้ำหน้าสูง (Over)", value=0.0)
        ou_under_w = st.number_input("น้ำหน้าต่ำ (Under)", value=0.0)
        hdba_val = st.slider("⚖️ HDBA Penalty %", 0.0, 10.0, 1.5)
        st.info("Remark: ลีกมาตรฐานยุโรป 1.5 | บอลถ้วยที่ต้องบินข้ามประเทศ 2.5-3.0 | โบลิเวีย/เอกวาดอร์ (ที่ราบสูง) 4.5+")

    if st.button("🚀 ANALYZE & CALCULATE"):
        def fix(o): return o + 1.0 if o < 1.1 else o
        h_o, d_o, a_o = fix(h1x2), fix(d1x2), fix(a1x2)
        hw_o, aw_o, ow_o, uw_o = fix(hdp_h_w), fix(hdp_a_w), fix(ou_over_w), fix(ou_under_w)
        
        # --- ใช้ชื่อตัวแปรใหม่ prob_d เพื่อไม่ให้ทับกับ Pandas pd ---
        m_1x2 = (1/h_o + 1/d_o + 1/a_o) - 1
        prob_h, prob_d, prob_a = (1/h_o)/(1+m_1x2), (1/d_o)/(1+m_1x2), (1/a_o)/(1+m_1x2)
        m_ou = (1/ow_o + 1/uw_o) - 1
        prob_over, prob_under = (1/ow_o)/(1+m_ou), (1/uw_o)/(1+m_ou)
        
        is_h_fav = prob_h >= prob_a
        ev_h = calc_universal_ev(hdp_line, prob_h, prob_d, prob_a, hw_o, is_h_fav)
        ev_a = calc_universal_ev(hdp_line, prob_a, prob_d, prob_h, aw_o, not is_h_fav) - (hdba_val/100)
        ev_over, ev_under = (prob_over * (ow_o-1)) - (prob_under * 1), (prob_under * (uw_o-1)) - (prob_over * 1)

        def get_k(ev, odds, bank):
            if ev < 0.03: return 0.0
            b_k, p_k = odds - 1, (ev + 1) / odds
            k_pct = ((b_k * p_k) - (1 - p_k)) / b_k
            return min(k_pct * 0.5, 0.10) * bank

        res_list = [{"n": "เจ้าบ้าน", "ev": ev_h, "odds": hw_o}, {"n": "ทีมเยือน", "ev": ev_a, "odds": aw_o},
                    {"n": "สูง", "ev": ev_over, "odds": ow_o}, {"n": "ต่ำ", "ev": ev_under, "odds": uw_o}]
        best = max(res_list, key=lambda x: x['ev'])
        k_money = get_k(best['ev'], best['odds'], total_bankroll)

        st.session_state['report'] = f"📊 GEM System 5.6.18\nคู่: {match_name}\nสรุป: {'🔥 INVEST' if best['ev']>=0.03 else '🚫 NO BET'}\nเป้าหมาย: {best['n'] if best['ev']>=0.03 else 'N/A'}\nยอดเงิน: {k_money:,.2f} THB"
        st.session_state['log_data'] = {"Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Match": match_name, "HDP": hdp_line, "Target": best['n'], "EV_Pct": round(best['ev']*100, 2), "Investment": round(k_money, 2), "Odds": best['odds'], "Result": ""}

    if 'report' in st.session_state:
        st.text_area("Report:", value=st.session_state['report'], height=130)
        if st.button("💾 บันทึกลง Log"):
            save_to_csv(st.session_state['log_data']); st.success("บันทึกสำเร็จ!"); st.rerun()

with tab2:
    logs = load_logs()
    if logs is not None:
        st.subheader("📝 บันทึกผลสกอร์ (พิมพ์สกอร์ในช่อง Result เช่น 2-1)")
        
        # เตรียมข้อมูลสำหรับแก้ไข
        display_df = logs.sort_values(by='Time', ascending=False).reset_index(drop=True)
        edited_df = st.data_editor(display_df, column_config={"Result": st.column_config.TextColumn("Result (e.g. 2-1)", help="กรอกสกอร์เพื่อคำนวณกำไร")}, use_container_width=True, num_rows="dynamic")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("💾 Save Score & Calculate Profit"):
                edited_df.to_csv(LOG_FILE, index=False, encoding='utf-8-sig'); st.rerun()
        with col_btn2:
            if st.button("🗑️ ล้างประวัติทั้งหมด (Clear Logs)"):
                if os.path.exists(LOG_FILE): os.remove(LOG_FILE); st.warning("ลบประวัติเรียบร้อย"); st.rerun()

        # คำนวณสถิติจากผลจริง
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
