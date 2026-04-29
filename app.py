import streamlit as st
import pandas as pd
import os
from datetime import datetime

# ==========================================
# 1. ฟังก์ชันบันทึกข้อมูล (Logging Function)
# ==========================================
def save_to_csv(data_dict):
    filename = "gem_history_log.csv"
    df = pd.DataFrame([data_dict])
    if not os.path.isfile(filename):
        df.to_csv(filename, index=False, encoding='utf-8-sig')
    else:
        df.to_csv(filename, mode='a', index=False, header=False, encoding='utf-8-sig')
    return filename

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
# 3. UI Layout & Input
# ==========================================
st.set_page_config(page_title="GEM System 5.6.7", layout="wide")
st.title("⚽ GEM System Patch 5.6.7: Classic Report Mode")

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
# ==========================================
# 4. Processing & Analysis
# ==========================================
if st.button("🚀 ANALYZE & CALCULATE"):
    def fix(o): return o+1.0 if o < 1.1 else o
    h, d, a = fix(h1x2), fix(d1x2), fix(a1x2)
    hw_f, aw_f = fix(hdp_h_w), fix(hdp_a_w)
    ow_f, uw_f = fix(ou_over_w), fix(ou_under_w)
    
    # Devigging
    m_1x2 = (1/h + 1/d + 1/a) - 1
    ph, pd, pa = (1/h)/(1+m_1x2), (1/d)/(1+m_1x2), (1/a)/(1+m_1x2)
    
    m_ou = (1/ow_f + 1/uw_f) - 1
    po, pu = (1/ow_f)/(1+m_ou), (1/uw_f)/(1+m_ou)
    
    # EV Calculation
    is_h_fav = ph >= pa
    ev_h = calc_universal_ev(hdp_line, ph, pd, pa, hw_f, is_h_fav)
    ev_a = calc_universal_ev(hdp_line, pa, pd, ph, aw_f, not is_h_fav) - (hdba_val/100)
    
    ev_over = (po * (ow_f-1)) - (pu * 1)
    ev_under = (pu * (uw_f-1)) - (po * 1)

    # Kelly Criterion Money Management
    def get_k(ev, odds, bank):
        if ev < 0.03: return 0, 0
        b_k = odds - 1
        p_k = (ev + 1) / odds
        k_pct = ((b_k * p_k) - (1 - p_k)) / b_k
        safe_k = min(k_pct * 0.5, 0.10) # Half Kelly, Max 10%
        return safe_k * 100, safe_k * bank

    # หาเป้าหมายที่ดีที่สุด
    res_list = [
        {"n": "เจ้าบ้าน", "ev": ev_h, "odds": hw_f},
        {"n": "ทีมเยือน", "ev": ev_a, "odds": aw_f},
        {"n": "สูง", "ev": ev_over, "odds": ow_f},
        {"n": "ต่ำ", "ev": ev_under, "odds": uw_f}
    ]
    best = max(res_list, key=lambda x: x['ev'])
    k_pct, k_money = get_k(best['ev'], best['odds'], total_bankroll)

    # สร้าง Report แบบเดิม
    report_text = f"""📊 GEM System 5.6.7 (Universal Engine)
คู่: {match_name}

สถิติจริง 🚨
- True Prob: เหย้า {ph*100:.1f}% | เสมอ {pd*100:.1f}% | เยือน {pa*100:.1f}%

วิเคราะห์ EV (คำนวณที่เรต AH {hdp_line}) 🛡️
- เจ้าบ้าน ({"ต่อ" if is_h_fav else "รอง"}): EV {ev_h*100:.2f}%
- ทีมเยือน ({"รอง" if is_h_fav else "ต่อ"}): EV {ev_a*100:.2f}%
- สูง/ต่ำ {ou_line}: สูง {ev_over*100:.2f}% | ต่ำ {ev_under*100:.2f}%

💡 สรุป: {"🔥 INVEST" if best['ev'] >= 0.03 else "🚫 NO BET"}
🎯 เป้าหมาย: {best['n'] if best['ev'] >= 0.03 else "N/A"}
💰 ยอดเงิน: {k_money:,.2f} THB
"""
    
    st.session_state['report'] = report_text
    st.session_state['log_data'] = {
        "Match": match_name, "HDP": hdp_line, "Target": best['n'], 
        "EV": best['ev'], "Money": k_money, "PH": ph, "PD": pd, "PA": pa
    }

# แสดง Report
if 'report' in st.session_state:
    st.markdown("---")
    st.subheader("📋 Final Report")
    st.text_area("ก๊อปปี้รายงานที่นี่:", value=st.session_state['report'], height=350)
    
    if st.button("💾 บันทึกลง Log History"):
        d = st.session_state['log_data']
        log_entry = {
            "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Match": d["Match"], "HDP": d["HDP"], "Target": d["Target"],
            "EV_Pct": round(d["EV"] * 100, 2), "Investment": round(d["Money"], 2)
        }
        save_to_csv(log_entry)
        st.success("บันทึกข้อมูลเรียบร้อยแล้ว!")
        st.balloons()
