import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- CONFIG ---
st.set_page_config(page_title="GEM System 5.6.10", layout="wide")
LOG_FILE = "gem_history_log.csv"

# ==========================================
# 1. ระบบจัดการฐานข้อมูล (เปลี่ยนชื่อ Prob เพื่อไม่ให้ทับกับ pd)
# ==========================================
def save_to_csv(data_dict):
    if not os.path.isfile(LOG_FILE):
        pd.DataFrame([data_dict]).to_csv(LOG_FILE, index=False, encoding='utf-8-sig')
    else:
        pd.DataFrame([data_dict]).to_csv(LOG_FILE, mode='a', index=False, header=False, encoding='utf-8-sig')

def load_logs():
    if os.path.exists(LOG_FILE):
        df = pd.read_csv(LOG_FILE)
        df['Time'] = pd.to_datetime(df['Time'])
        return df
    return None

# ==========================================
# 2. ฟังก์ชันสมองกล (Universal AH Engine)
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
# 3. UI - TABS System
# ==========================================
st.title("📊 GEM System 5.6.10: Stable Dashboard")

tab1, tab2 = st.tabs(["🚀 Analysis Terminal", "📈 Dashboard History"])

with tab1:
    st.sidebar.header("💰 Portfolio Management")
    total_bankroll = st.sidebar.number_input("เงินทุนทั้งหมด (THB)", min_value=0.0, value=10000.0, step=1000.0)

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
        st.subheader("2. ตลาดสกอร์รวม (O/U)")
        ou_line = st.number_input("เรตสกอร์รวม (O/U)", value=2.0, step=0.25)
        ou_over_w = st.number_input("น้ำหน้าสูง (Over)", value=0.0)
        ou_under_w = st.number_input("น้ำหน้าต่ำ (Under)", value=0.0)
        hdba_val = st.slider("⚖️ HDBA Penalty %", 0.0, 10.0, 1.5)
        st.markdown("---")
        st.markdown("Remark HDBA")
        st.markdown("-หากเป็นลีกมาตรฐานยุโรป (พรีเมียร์ลีก, ลาลีกา) การเดินทางสะดวก ให้ใส่ HDBA = 1.5 (Base 1.0 + กองเชียร์ 0.5)")
        st.markdown("-หากเป็นบอลถ้วยละตินอเมริกาที่ต้องบินข้ามประเทศ ให้ยืนพื้น HDBA = 2.5 ถึง 3.0 ไว้ก่อนเลย")
        st.markdown("-หากไปเยือน โบลิเวีย หรือ เอกวาดอร์ (ที่ราบสูง) ให้กด HDBA = 4.5 หรือ 5.0 ได้เลยครับ")

    if st.button("🚀 ANALYZE & CALCULATE"):
        def fix(o): return o + 1.0 if o < 1.1 else o
        # แก้ไขชื่อตัวแปรที่ดึงจาก Input ให้ตรงกัน
        h_o, d_o, a_o = fix(h1x2), fix(d1x2), fix(a1x2)
        hw_o, aw_o = fix(hdp_h_w), fix(hdp_a_w)
        ow_o, uw_o = fix(ou_over_w), fix(ou_under_w)
        
        # Devigging (ใช้ชื่อ prob_h, prob_d เพื่อป้องกันการทับซ้อนกับ pd)
        margin_1x2 = (1/h_o + 1/d_o + 1/a_o) - 1
        prob_h, prob_d, prob_a = (1/h_o)/(1+margin_1x2), (1/d_o)/(1+margin_1x2), (1/a_o)/(1+margin_1x2)
        
        margin_ou = (1/ow_o + 1/uw_o) - 1
        prob_over, prob_under = (1/ow_o)/(1+margin_ou), (1/uw_o)/(1+margin_ou)
        
        # EV Calculation
        is_h_fav = prob_h >= prob_a
        ev_h = calc_universal_ev(hdp_line, prob_h, prob_d, prob_a, hw_o, is_h_fav)
        ev_a = calc_universal_ev(hdp_line, prob_a, prob_d, prob_h, aw_o, not is_h_fav) - (hdba_val/100)
        ev_over = (prob_over * (ow_o-1)) - (prob_under * 1)
        ev_under = (prob_under * (uw_o-1)) - (prob_over * 1)

        # Kelly Money Management
        def get_k(ev, odds, bank):
            if ev < 0.03: 
                return 0.0 # คืนค่าเป็น Float ตัวเดียวป้องกัน TypeError
            
            b_k = odds - 1
            p_k = (ev + 1) / odds
            k_pct = ((b_k * p_k) - (1 - p_k)) / b_k
            
            # ปรับปรุงความปลอดภัย: Half-Kelly และจำกัดไม่เกิน 10% ของพอร์ต
            safe_k = min(k_pct * 0.5, 0.10) 
            
            # ตรวจสอบเผื่อค่าติดลบ
            if safe_k < 0:
                return 0.0
                
            return safe_k * bank

        # หาเป้าหมายที่ดีที่สุด
        res_list = [
            {"n": "เจ้าบ้าน", "ev": ev_h, "odds": hw_o},
            {"n": "ทีมเยือน", "ev": ev_a, "odds": aw_o},
            {"n": "สูง", "ev": ev_over, "odds": ow_o},
            {"n": "ต่ำ", "ev": ev_under, "odds": uw_o}
        ]
        best = max(res_list, key=lambda x: x['ev'])
        
        # เรียกใช้ฟังก์ชันที่แก้แล้ว
        k_money = get_k(best['ev'], best['odds'], total_bankroll)

        # เก็บผลลัพธ์ลง Session
        st.session_state['report'] = f"""📊 GEM System 5.6.10
คู่: {match_name}
สถิติจริง: เหย้า {prob_h*100:.1f}% | เสมอ {prob_d*100:.1f}% | เยือน {prob_a*100:.1f}%
สรุป: {"🔥 INVEST" if best['ev']>=0.03 else "🚫 NO BET"}
เป้าหมาย: {best['n'] if best['ev']>=0.03 else "N/A"}
ยอดเงิน: {k_money:,.2f} THB
"""
        st.session_state['log_data'] = {
            "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Match": match_name, "HDP": hdp_line, "Target": best['n'], 
            "EV_Pct": round(best['ev'] * 100, 2), "Investment": round(k_money, 2)
        }

    if 'report' in st.session_state:
        st.text_area("Final Report:", value=st.session_state['report'], height=200)
        if st.button("💾 บันทึกข้อมูลลง Log"):
            save_to_csv(st.session_state['log_data'])
            st.success("บันทึกเรียบร้อย!")
            st.balloons()

with tab2:
    logs = load_logs()
    if logs is not None:
        st.subheader("📈 ระบบตรวจสอบและพัฒนาผลงาน (Backtesting)")
        
        # 1. ปุ่มดาวน์โหลดไฟล์ลงเครื่อง
        csv_data = logs.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 Download CSV for Excel (Backtest)",
            data=csv_data,
            file_name=f"gem_backtest_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )
        
        st.markdown("---")
        
        # 2. สรุปภาพรวมสถิติ
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("จำนวนไม้", len(logs))
        col_m2.metric("ยอดลงทุนรวม", f"{logs['Investment'].sum():,.2f}")
        col_m3.metric("ค่าเฉลี่ย EV", f"{logs['EV_Pct'].mean():.2f}%")
        
        # 3. แสดงตารางประวัติ (พร้อมช่องให้คุณไปเติมผลเองใน Excel)
        st.subheader("📂 ประวัติการวิเคราะห์")
        st.write("💡 *คำแนะนำ: ดาวน์โหลดไฟล์ไปเปิดใน Excel แล้วเพิ่มคอลัมน์ 'Actual Result' เพื่อคำนวณกำไรจริงครับ*")
        st.dataframe(logs.sort_values(by='Time', ascending=False), use_container_width=True)
        
        # 4. กราฟแสดงทิศทางการลงทุน
        st.subheader("📊 กราฟการลงทุนสะสม")
        logs['Cumulative_Invest'] = logs['Investment'].cumsum()
        st.line_chart(logs.set_index('Time')['Cumulative_Invest'])

        # 5. ปุ่มล้างข้อมูล
        if st.button("🗑️ ล้างประวัติ (Clear Logs)"):
            if os.path.exists(LOG_FILE):
                os.remove(LOG_FILE)
                st.rerun()
    else:
        st.info("ยังไม่มีข้อมูลบันทึกในระบบ")
