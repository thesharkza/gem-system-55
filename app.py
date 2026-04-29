import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- SETTING ---
st.set_page_config(page_title="GEM Quant Terminal 5.6.5", layout="wide")

# --- CORE MATH ENGINE ---
def calc_universal_ev(hdp, p_win, p_draw, p_loss, odds, is_fav):
    b = odds - 1 
    if hdp % 1 == 0: # เลขกลม (0, 1, 2)
        if hdp == 0: return (p_win * b) - (p_loss * 1)
        if is_fav: return (p_win * 0.55 * b) - ((p_draw + p_loss) * 1) # ชนะขาด 55%
        return ((p_win + p_draw) * b) - (p_loss * 0.55 * 1)
    elif hdp % 1 == 0.5: # เลขครึ่ง
        if is_fav: return (p_win * b) - ((p_draw + p_loss) * 1)
        return ((p_win + p_draw) * b) - (p_loss * 1)
    elif hdp % 1 == 0.25: # ควบต่ำ
        if is_fav: return (p_win * b) - (p_draw * 0.5) - (p_loss * 1)
        return (p_win * b) + (p_draw * b/2) - (p_loss * 1)
    elif hdp % 1 == 0.75: # ควบสูง
        if is_fav: return (p_win * 0.5 * b) + (p_win * 0.5 * b/2) - ((p_draw + p_loss) * 1)
        return ((p_win + p_draw) * b) - (p_loss * 0.5 * 0.5) - (p_loss * 0.5 * 1)
    return (p_win * b) - ((p_draw + p_loss) * 1)

# --- LOGGING SYSTEM ---
def save_log(data):
    fname = "gem_history_log.csv"
    df = pd.DataFrame([data])
    if not os.path.isfile(fname):
        df.to_csv(fname, index=False, encoding='utf-8-sig')
    else:
        df.to_csv(fname, mode='a', index=False, header=False, encoding='utf-8-sig')

# --- UI APP ---
st.title("📊 GEM System 5.6.5: Professional Quant Terminal")
st.markdown("---")

# Input Side
col1, col2 = st.columns(2)
with col1:
    m_name = st.text_input("Match Name", "Team A VS Team B")
    h1, d1, a1 = st.number_input("Home Odds (1X2)", 1.0), st.number_input("Draw Odds", 1.0), st.number_input("Away Odds", 1.0)
    bankroll = st.number_input("Total Bankroll (THB)", 10000)

with col2:
    hdp = st.number_input("Handicap Line (e.g. 0.25, 0.75)", 0.0, step=0.25)
    hw, aw = st.number_input("Home AH Odds", 0.0), st.number_input("Away AH Odds", 0.0)
    hdba = st.slider("HDBA Penalty (%)", 0.0, 5.0, 1.5)

# Processing
if st.button("🚀 ANALYZE & CALCULATE"):
    # Fix & Devig
    def fix(o): return o+1.0 if o < 1.1 else o
    h, d, a, hw_f, aw_f = fix(h1), fix(d1), fix(a1), fix(hw), fix(aw)
    m = (1/h + 1/d + 1/a) - 1
    ph, pd, pa = (1/h)/(1+m), (1/d)/(1+m), (1/a)/(1+m)
    
    # EV Logic
    is_h_fav = ph >= pa
    ev_h = calc_universal_ev(hdp, ph, pd, pa, hw_f, is_h_fav)
    ev_a = calc_universal_ev(hdp, pa, pd, ph, aw_f, not is_h_fav) - (hdba/100)
    
    # Result UI
    best_n = "เจ้าบ้าน" if ev_h > ev_a else "ทีมเยือน"
    best_ev = max(ev_h, ev_a)
    
    st.write(f"### ผลวิเคราะห์: {'🔥 INVEST' if best_ev >= 0.03 else '🚫 NO BET'}")
    st.info(f"โอกาสชนะจริง: เหย้า {ph*100:.1f}% | เสมอ {pd*100:.1f}% | เยือน {pa*100:.1f}%")
    st.success(f"Best Target: {best_n} | EV: {best_ev*100:.2f}%")
    
    # Save Button
    log_entry = {"Time": datetime.now(), "Match": m_name, "HDP": hdp, "Target": best_n, "EV": best_ev}
    if st.button("💾 บันทึกลง Log"):
        save_log(log_entry)
        st.balloons()
        st.dataframe(history_df.tail(10)) # โชว์ 10 รายการล่าสุด
    else:
        st.info("ยังไม่มีประวัติการบันทึก")
