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
            p_win_by_1 = p_win * 0.5
            p_win_by_2 = p_win * 0.5
            return (p_win_by_2 * b) + (p_win_by_1 * b/2) - ((p_draw + p_loss) * 1)
        else:
            p_loss_by_1 = p_loss * 0.5
            p_loss_by_2 = p_loss * 0.5
            return ((p_win + p_draw) * b) - (p_loss_by_1 * 0.5) - (p_loss_by_2 * 1)
    return (p_win * b) - ((p_draw + p_loss) * 1)

# ==========================================
# 3. UI Layout & Input
# ==========================================
st.set_page_config(page_title="GEM System 5.6.6", layout="wide")
st.title("⚽ GEM System Patch 5.6.6: Stable Engine")

st.sidebar.header("💰 Portfolio Management")
total_bankroll = st.sidebar.number_input("เงินทุนทั้งหมด (THB)", min_value=0.0, value=10000.0, step=1000.0)

match_name = st.text_input("📝 คู่แข่งขัน", "โตเกียวเวอร์ดี้ VS คาชิม่า แอนท์เลอร์ส")

col1, col2 = st.columns(2)
with col1:
    st.subheader("1. ตลาดราคาพูล & AH")
    h1x2 = st.number_input("เหย้า (1X2)", value=3.75)
    d1x2 = st.number_input("เสมอ (1X2)", value=3.03)
    a1x2 = st.number_input("เยือน (1X2)", value=1.97)
    hdp_line = st.number_input("เรตต่อรอง (HDP)", value=0.5)
    hdp_h_w = st.number_input("น้ำเจ้าบ้าน", value=0.93)
    hdp_a_w = st.number_input("น้ำทีมเยือน", value=0.97)

with col2:
    st.subheader("2. ตลาดสกอร์รวม (O/U)")
    ou_line = st.number_input("เรตสกอร์รวม (O/U)", value=2.0)
    ou_over_w = st.number_input("น้ำหน้าสูง (Over)", value=0.81)
    ou_under_w = st.number_input("น้ำหน้าต่ำ (Under)", value=1.06)
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
    # แก้ไขชื่อตัวแปรให้ตรงกับ Input ด้านบน
    h, d, a = fix(h1x2), fix(d1x2), fix(a1x2)
    hw_f, aw_f = fix(hdp_h_w), fix(hdp_a_w)
    
    m = (1/h + 1/d + 1/a) - 1
    ph, pd, pa = (1/h)/(1+m), (1/d)/(1+m), (1/a)/(1+m)
    
    is_h_fav = ph >= pa
    ev_h = calc_universal_ev(hdp_line, ph, pd, pa, hw_f, is_h_fav)
    ev_a = calc_universal_ev(hdp_line, pa, pd, ph, aw_f, not is_h_fav) - (hdba_val/100)
    
    best_n = "เจ้าบ้าน" if ev_h > ev_a else "ทีมเยือน"
    best_ev = max(ev_h, ev_a)

    # เก็บผลลัพธ์ลง Session State
    st.session_state['analysis_result'] = {
        "Match": match_name,
        "True_Prob_H": ph,
        "True_Prob_D": pd,
        "True_Prob_A": pa,
        "HDP": hdp_line,
        "Target": best_n,
        "EV": best_ev,
        "Money": (best_ev * total_bankroll) if best_ev >= 0.03 else 0
    }

    st.write(f"### ผลวิเคราะห์: {'🔥 INVEST' if best_ev >= 0.03 else '🚫 NO BET'}")
    st.success(f"Best Target: {best_n} | EV: {best_ev*100:.2f}%")

# ==========================================
# 5. Logging (Save to CSV)
# ==========================================
if 'analysis_result' in st.session_state:
    res = st.session_state['analysis_result']
    if st.button("💾 บันทึกลง Log"):
        log_entry = {
            "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Match": res["Match"],
            "HDP": res["HDP"],
            "Prob_H": round(res["True_Prob_H"] * 100, 2),
            "Target": res["Target"],
            "EV": round(res["EV"] * 100, 2),
            "Investment": round(res["Money"], 2)
        }
        # เรียกชื่อฟังก์ชันให้ถูก (save_to_csv)
        save_to_csv(log_entry)
        st.success("บันทึกข้อมูลเรียบร้อยแล้ว!")
        st.balloons()
