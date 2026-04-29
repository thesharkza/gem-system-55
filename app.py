import streamlit as st
import pandas as pd
import os
from datetime import datetime
import plotly.express as px # ต้องลง plotly เพิ่ม (ถ้ายังไม่มี)

# --- SETTING ---
st.set_page_config(page_title="GEM System 5.6.8", layout="wide")

# ==========================================
# 1. ระบบฐานข้อมูล (Log Database)
# ==========================================
LOG_FILE = "gem_history_log.csv"

def save_to_csv(data_dict):
    df = pd.DataFrame([data_dict])
    if not os.path.isfile(LOG_FILE):
        df.to_csv(LOG_FILE, index=False, encoding='utf-8-sig')
    else:
        df.to_csv(LOG_FILE, mode='a', index=False, header=False, encoding='utf-8-sig')

def load_logs():
    if os.path.exists(LOG_FILE):
        df = pd.read_csv(LOG_FILE)
        # แปลงเวลาให้เป็น format ที่คำนวณได้
        df['Time'] = pd.to_datetime(df['Time'])
        return df
    return None

# ==========================================
# 2. ฟังก์ชันสมองกล (Universal Engine)
# ==========================================
def calc_universal_ev(hdp, p_win, p_draw, p_loss, odds, is_fav):
    b = odds - 1 
    if hdp % 1 == 0 and hdp > 0:
        if is_fav:
            p_win_clear = p_win * 0.55
            return (p_win_clear * b) - ((p_draw + p_loss) * 1)
        else:
            p_loss_clear = p_loss * 0.55
            return ((p_win + p_draw) * b) - (p_loss_clear * 1)
    elif hdp == 0:
        return (p_win * b) - (p_loss * 1)
    elif hdp % 1 == 0.5:
        if is_fav: return (p_win * b) - ((p_draw + p_loss) * 1)
        else: return ((p_win + p_draw) * b) - (p_loss * 1)
    elif hdp % 1 == 0.25:
        if is_fav: return (p_win * b) - (p_draw * 0.5) - (p_loss * 1)
        else: return (p_win * b) + (p_draw * b/2) - (p_loss * 1)
    elif hdp % 1 == 0.75:
        if is_fav:
            return (p_win * 0.5 * b) + (p_win * 0.5 * b/2) - ((p_draw + p_loss) * 1)
        else:
            return ((p_win + p_draw) * b) - (p_loss * 0.5 * 0.5) - (p_loss * 0.5 * 1)
    return (p_win * b) - ((p_draw + p_loss) * 1)

# ==========================================
# 3. ส่วน UI - TABS System
# ==========================================
st.title("📊 GEM System Betting Soccer")

tab1, tab2 = st.tabs(["🚀 Analysis Terminal", "📈 Dashboard & History"])

# --- TAB 1: วิเคราะห์ราคาบอล ---
with tab1:
    st.sidebar.header("💰 Portfolio Management")
    total_bankroll = st.sidebar.number_input("เงินทุนทั้งหมด (THB)", min_value=0.0, value=10000.0, step=1000.0)

    match_name = st.text_input("📝 คู่แข่งขัน", "ชื่อคู่แข่งขัน")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1. ตลาดราคาพูล & AH")
        h1x2 = st.number_input("เหย้า (1X2)", value=1.0, key="h1")
        d1x2 = st.number_input("เสมอ (1X2)", value=1.0, key="d1")
        a1x2 = st.number_input("เยือน (1X2)", value=1.0, key="a1")
        hdp_line = st.number_input("เรตต่อรอง (HDP)", value=0.0, step=0.25, key="hdp")
        hdp_h_w = st.number_input("น้ำเจ้าบ้าน", value=0.0, key="hw")
        hdp_a_w = st.number_input("น้ำทีมเยือน", value=0.0, key="aw")

    with col2:
        st.subheader("2. ตลาดสกอร์รวม (O/U)")
        ou_line = st.number_input("เรตสกอร์รวม (O/U)", value=2.0, step=0.25, key="ou")
        ou_over_w = st.number_input("น้ำหน้าสูง (Over)", value=0.0, key="ow")
        ou_under_w = st.number_input("น้ำหน้าต่ำ (Under)", value=0.0, key="uw")
        hdba_val = st.slider("⚖️ HDBA Penalty %", 0.0, 10.0, 1.5)
        st.markdown("---")
        st.markdown("Remark HDBA")
        st.markdown("-หากเป็นลีกมาตรฐานยุโรป (พรีเมียร์ลีก, ลาลีกา) การเดินทางสะดวก ให้ใส่ HDBA = 1.5 (Base 1.0 + กองเชียร์ 0.5)")
        st.markdown("-หากเป็นบอลถ้วยละตินอเมริกาที่ต้องบินข้ามประเทศ ให้ยืนพื้น HDBA = 2.5 ถึง 3.0 ไว้ก่อนเลย")
        st.markdown("-หากไปเยือน โบลิเวีย หรือ เอกวาดอร์ (ที่ราบสูง) ให้กด HDBA = 4.5 หรือ 5.0 ได้เลยครับ")
        
    if st.button("🚀 ANALYZE & CALCULATE"):
        # Logic Calculation (เหมือน 5.6.7)
        def fix(o): return o+1.0 if o < 1.1 else o
        h, d, a = fix(h1x2), fix(d1x2), fix(a1x2)
        hw_f, aw_f = fix(hdp_h_w), fix(hdp_a_w)
        ow_f, uw_f = fix(ou_over_w), fix(ou_under_w)
        
        m_1x2 = (1/h + 1/d + 1/a) - 1
        ph, pd, pa = (1/h)/(1+m_1x2), (1/d)/(1+m_1x2), (1/a)/(1+m_1x2)
        m_ou = (1/ow_f + 1/uw_f) - 1
        po, pu = (1/ow_f)/(1+m_ou), (1/uw_f)/(1+m_ou)
        
        is_h_fav = ph >= pa
        ev_h = calc_universal_ev(hdp_line, ph, pd, pa, hw_f, is_h_fav)
        ev_a = calc_universal_ev(hdp_line, pa, pd, ph, aw_f, not is_h_fav) - (hdba_val/100)
        ev_over = (po * (ow_f-1)) - (pu * 1)
        ev_under = (pu * (uw_f-1)) - (po * 1)

        def get_k(ev, odds, bank):
            if ev < 0.03: return 0, 0
            b_k, p_k = odds - 1, (ev + 1) / odds
            k_pct = ((b_k * p_k) - (1 - p_k)) / b_k
            safe_k = min(k_pct * 0.5, 0.10)
            return safe_k * 100, safe_k * bank

        res_list = [{"n": "เจ้าบ้าน", "ev": ev_h, "odds": hw_f}, {"n": "ทีมเยือน", "ev": ev_a, "odds": aw_f},
                    {"n": "สูง", "ev": ev_over, "odds": ow_f}, {"n": "ต่ำ", "ev": ev_under, "odds": uw_f}]
        best = max(res_list, key=lambda x: x['ev'])
        k_pct, k_money = get_k(best['ev'], best['odds'], total_bankroll)

        report_text = f"""📊 GEM System Betting Soccer
คู่: {match_name}

สถิติจริง 🚨
- True Prob: เหย้า {ph*100:.1f}% | เสมอ {pd*100:.1f}% | เยือน {pa*100:.1f}%

วิเคราะห์ EV (AH {hdp_line}) 🛡️
- เจ้าบ้าน: EV {ev_h*100:.2f}% | ทีมเยือน: EV {ev_a*100:.2f}%
- สกอร์รวม {ou_line}: สูง {ev_over*100:.2f}% | ต่ำ {ev_under*100:.2f}%

💡 สรุป: {"🔥 INVEST" if best['ev'] >= 0.03 else "🚫 NO BET"}
🎯 เป้าหมาย: {best['n'] if best['ev'] >= 0.03 else "N/A"}
💰 ยอดเงิน: {k_money:,.2f} THB
"""
        st.session_state['report'] = report_text
        st.session_state['log_data'] = {
            "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Match": match_name, "HDP": hdp_line, "Target": best['n'], 
            "EV_Pct": round(best['ev'] * 100, 2), "Investment": round(k_money, 2)
        }

    if 'report' in st.session_state:
        st.text_area("Final Report:", value=st.session_state['report'], height=300)
        if st.button("💾 บันทึกข้อมูล (Save Log)"):
            save_to_csv(st.session_state['log_data'])
            st.success("บันทึกเรียบร้อย!")
            st.balloons()

# --- TAB 2: DASHBOARD & HISTORY ---
with tab2:
    logs = load_logs()
    if logs is not None:
        # ตรวจสอบว่ามีคอลัมน์ที่ต้องการไหม ถ้าไม่มีให้สร้างหลอกๆ ไว้ป้องกัน Error
        if 'EV_Pct' not in logs.columns and 'EV' in logs.columns:
            logs['EV_Pct'] = logs['EV'] # Copy ค่าจากชื่อเก่ามาชื่อใหม่
        
        if 'EV_Pct' in logs.columns:
            st.subheader("📌 สรุปภาพรวมสถิติ")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("จำนวนไม้ทั้งหมด", len(logs))
            c2.metric("ยอดรวมการลงทุน", f"{logs['Investment'].sum():,.2f} บาท")
            c3.metric("ค่าเฉลี่ย EV", f"{logs['EV_Pct'].mean():.2f}%")
            
            # ป้องกัน Error กรณีหา mode ไม่เจอ
            popular_target = logs['Target'].mode()[0] if not logs['Target'].empty else "N/A"
            c4.metric("เป้าหมายยอดนิยม", popular_target)

            # กราฟแสดงการลงทุนย้อนหลัง
            st.subheader("📈 กราฟแสดงยอดเงินลงทุนสะสม")
            logs['Cumulative_Invest'] = logs['Investment'].cumsum()
            
            # ใช้ st.line_chart แทน plotly ชั่วคราวถ้ายังไม่แก้ requirements.txt
            chart_data = logs.set_index('Time')['Cumulative_Invest']
            st.line_chart(chart_data)

            # ตาราง Log ย้อนหลัง
            st.subheader("📂 ประวัติการวิเคราะห์ (Log History)")
            st.dataframe(logs.sort_values(by='Time', ascending=False), use_container_width=True)
        else:
            st.error("❌ รูปแบบไฟล์ Log ไม่ถูกต้อง กรุณาลบไฟล์ gem_history_log.csv แล้วบันทึกใหม่")
        
        # ปุ่มล้างข้อมูล
        if st.button("🗑️ ล้างประวัติทั้งหมด (Clear Logs)"):
            if os.path.exists(LOG_FILE):
                os.remove(LOG_FILE)
                st.rerun() # ใช้ st.rerun() แทนเพื่อให้แอปรีเฟรชตัวเอง
    else:
        st.info("ยังไม่มีข้อมูลใน Log กรุณาทำการวิเคราะห์และกดบันทึกก่อนครับ")
