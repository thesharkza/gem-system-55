import streamlit as st
import pandas as pd
import numpy as np
import math
import json
import os
import google.generativeai as genai
from datetime import datetime, timedelta, timezone
from PIL import Image
import plotly.graph_objects as go
from supabase import create_client, Client

# ==========================================
# 0. ระบบตั้งค่าการเชื่อมต่อ (Config & Supabase)
# ==========================================
st.set_page_config(page_title="GEM System 55 - Quant Fund", layout="wide")

# เชื่อมต่อ Supabase ผ่าน Secrets
try:
    url: str = st.secrets["SUPABASE_URL"]
    key: str = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("⚠️ ไม่สามารถเชื่อมต่อ Supabase ได้ กรุณาตรวจสอบ Secrets (SUPABASE_URL, SUPABASE_KEY)")

# ระบบตั้งค่าตัวแปร (Session State Init)
def init_session_state():
    defaults = {
        'match_name': "ชื่อคู่แข่งขัน",
        'h1x2_val': 1.0, 'd1x2_val': 1.0, 'a1x2_val': 1.0,
        'hdp_line_val': 0.0, 'hdp_h_w_val': 0.0, 'hdp_a_w_val': 0.0,
        'ou_line_val': 2.5, 'ou_over_w_val': 0.0, 'ou_under_w_val': 0.0,
        'lh_s': 0, 'la_s': 0, 'rc_h': False, 'rc_a': False, 'current_min': 45,
        'pre_h': 2.0, 'pre_d': 3.0, 'pre_a': 3.0, 'pre_ou': 2.5,
        'live_hdp': 0.0, 'live_hdp_h': 0.9, 'live_hdp_a': 0.9,
        'live_ou': 2.5, 'live_ou_over': 0.9, 'live_ou_under': 0.9
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

init_session_state()

# ฟังก์ชันสำหรับปุ่มล้างค่าหน้า IN-PLAY
def clear_inplay_data():
    inplay_defaults = {
        'lh_s': 0, 'la_s': 0, 'rc_h': False, 'rc_a': False, 'current_min': 45,
        'pre_h': 2.0, 'pre_d': 3.0, 'pre_a': 3.0, 'pre_ou': 2.5,
        'live_hdp': 0.0, 'live_hdp_h': 0.9, 'live_hdp_a': 0.9,
        'live_ou': 2.5, 'live_ou_over': 0.9, 'live_ou_under': 0.9
    }
    for k, v in inplay_defaults.items():
        st.session_state[k] = v

def adj_hdp(v): st.session_state.live_hdp += v
def adj_ou(v): st.session_state.live_ou += v

# ==========================================
# 1. ฟังก์ชันจัดการข้อมูล (Supabase Engine)
# ==========================================
def load_logs():
    try:
        response = supabase.table("investment_logs").select("*").order("Time", desc=True).execute()
        if response.data:
            df = pd.DataFrame(response.data)
            for col in ['EV_Pct', 'Investment', 'Odds', 'Closing_Odds']:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            return df
        return pd.DataFrame(columns=['id', 'Time', 'Match', 'HDP', 'Target', 'EV_Pct', 'Investment', 'Odds', 'Closing_Odds', 'Result'])
    except: return pd.DataFrame()

def save_to_supabase(new_data_list):
    try: supabase.table("investment_logs").insert(new_data_list).execute()
    except Exception as e: st.error(f"Save Error: {e}")

def calculate_net_profit(row):
    try:
        res, inv, odds = str(row['Result']), float(row['Investment']), float(row['Odds'])
        if res == 'Win': return inv * (odds - 1)
        if res == 'Half Win': return (inv * (odds - 1)) / 2
        if res == 'Half Loss': return -inv / 2
        if res == 'Loss': return -inv
        return 0.0
    except: return 0.0

def calculate_clv(row):
    try:
        if float(row['Closing_Odds']) > 1.0:
            return ((float(row['Odds']) / float(row['Closing_Odds'])) - 1) * 100
        return 0.0
    except: return 0.0

# ==========================================
# 2. กลไกคณิตศาสตร์ (Quant Engine)
# ==========================================
def shin_devig(h, d, a):
    pi = [1/h, 1/d, 1/a]
    sum_pi = sum(pi)
    low, high = 0.0, 1.0
    for _ in range(50):
        z = (low + high) / 2
        try:
            p = [(math.sqrt(z**2 + 4*(1-z)*pi_i) - z) / (2*(1-z)) for pi_i in pi]
            if sum(p) > 1: low = z
            else: high = z
        except ZeroDivisionError: break
    
    try:
        p = [(math.sqrt(z**2 + 4*(1-z)*pi_i) - z) / (2*(1-z)) for pi_i in pi]
    except ZeroDivisionError: p = [pi_i / sum_pi for pi_i in pi]
    
    s_p = sum(p)
    return p[0]/s_p, p[1]/s_p, p[2]/s_p

def calc_dixon_coles_matrix(lambda_h, lambda_a, max_goals=9):
    # ปรับจูนค่า rho สำหรับการแก้ bias สกอร์ต่ำ
    rho = -0.10 
    matrix = np.zeros((max_goals + 1, max_goals + 1))
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            prob_h = (math.exp(-lambda_h) * (lambda_h**i)) / math.factorial(i)
            prob_a = (math.exp(-lambda_a) * (lambda_a**j)) / math.factorial(j)
            prob = prob_h * prob_a
            
            # Dixon-Coles Adjustment
            if i == 0 and j == 0: prob *= (1 - lambda_h * lambda_a * rho)
            elif i == 0 and j == 1: prob *= (1 + lambda_h * rho)
            elif i == 1 and j == 0: prob *= (1 + lambda_a * rho)
            elif i == 1 and j == 1: prob *= (1 - rho)
            
            matrix[i, j] = max(prob, 0)
    return matrix / matrix.sum()

def calc_advanced_ah_ev(matrix, hdp, odds, target):
    # hdp input as float (e.g. -0.25)
    win_p, half_win_p, push_p, half_loss_p, loss_p = 0.0, 0.0, 0.0, 0.0, 0.0
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            diff = i - j
            res = diff + hdp
            if res > 0.25: win_p += matrix[i, j]
            elif res == 0.25: half_win_p += matrix[i, j]
            elif res == 0.0: push_p += matrix[i, j]
            elif res == -0.25: half_loss_p += matrix[i, j]
            else: loss_p += matrix[i, j]
            
    if target == "เจ้าบ้าน":
        return (win_p * (odds-1)) + (half_win_p * (odds-1)*0.5) - (half_loss_p * 0.5) - loss_p
    else: # ทีมเยือน (hdp ต้องกลับเครื่องหมาย)
        # สำหรับทีมเยือน เราใช้ matrix[j, i] หรือกลับค่า diff
        # แต่เพื่อความง่าย เราคำนวณ win_p ของเจ้าบ้านแล้วหา EV ฝั่งเยือน
        return (loss_p * (odds-1)) + (half_loss_p * (odds-1)*0.5) - (half_win_p * 0.5) - win_p

def calc_advanced_ou_ev(matrix, line, odds, target):
    over_p, push_p, under_p = 0.0, 0.0, 0.0
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            total = i + j
            if total > line: over_p += matrix[i, j]
            elif total == line: push_p += matrix[i, j]
            else: under_p += matrix[i, j]
            
    if target == "สูง": return (over_p * (odds-1)) - under_p
    else: return (under_p * (odds-1)) - over_p

# ==========================================
# 3. AI Quant Decision Engine
# ==========================================
def ai_quant_decision_engine(match_info, base_ev, gem_rules):
    prompt = f"""คุณคือ Chief Risk Officer ของกองทุน Quant
ข้อมูลคู่: {match_info}
Base EV (Math): {base_ev*100:.2f}%
GEM Rules: {gem_rules}

วิเคราะห์และตอบเป็น JSON เท่านั้น:
{{"pros_analysis": "...", "cons_analysis": "...", "rule_triggered": "...", "impact_score": 0.0, "final_decision": true/false, "final_comment": "...", "confidence_level": 1-5}}"""

    for attempt in range(3):
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            res_text = response.text.strip()
            
            if not res_text: raise ValueError("Empty AI Response")
            
            # Clean JSON
            bt = chr(96) * 3
            res_text = res_text.replace(bt + "json", "").replace(bt, "").strip()
            start_idx = res_text.find('{')
            end_idx = res_text.rfind('}')
            
            if start_idx != -1 and end_idx != -1:
                json_str = res_text[start_idx:end_idx+1]
                try:
                    return json.loads(json_str)
                except: raise ValueError("Invalid JSON")
            else: raise ValueError("JSON Brackets not found")
        except Exception as e:
            if attempt == 2:
                return {"pros_analysis": "Error", "cons_analysis": str(e), "rule_triggered": "Fallback", "impact_score": 0.0, "final_decision": base_ev >= 0.08, "final_comment": "System Fallback", "confidence_level": 3}
            import time
            time.sleep(1)

# ==========================================
# 4. ส่วนแสดงผล UI
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs(["🚀 Pre-Match Terminal", "📊 Dashboard & AI", "⚡ IN-PLAY LIVE", "🧪 Backtest (RPS)"])

# --- TAB 1: Pre-Match ---
with tab1:
    st.title("🏹 GEM System Sniper Terminal")
    # ... (ส่วนกรอกข้อมูล Pre-match ของคุณ) ...

# --- TAB 2: Dashboard (Cloud & Advanced Analytics) ---
with tab2:
    logs = load_logs()
    if not logs.empty:
        st.subheader("📝 บันทึกผลบน Cloud (Supabase)")
        display_df = logs.sort_values(by='Time', ascending=False).reset_index(drop=True)
        edited_df = st.data_editor(display_df, column_config={
            "Closing_Odds": st.column_config.NumberColumn("Closing Odds", format="%.2f"),
            "Result": st.column_config.SelectboxColumn("Result", options=["Win", "Half Win", "Push", "Half Loss", "Loss", ""])
        }, use_container_width=True, key="dashboard_editor")

        c_b1, c_b2 = st.columns(2)
        if c_b1.button("💾 Sync to Cloud"):
            with st.spinner("Updating..."):
                for _, row in edited_df.iterrows():
                    supabase.table("investment_logs").update({
                        "Closing_Odds": float(row['Closing_Odds']), 
                        "Result": str(row['Result'])
                    }).eq("id", row['id']).execute()
                st.success("Cloud Updated!")
                st.rerun()
            
        if c_b2.button("🗑️ Clear Local Cache"): st.rerun()

        logs['Net_Profit'] = logs.apply(calculate_net_profit, axis=1)
        logs['CLV_Pct'] = logs.apply(calculate_clv, axis=1)

        st.markdown("---")
        view_mode = st.radio("Analytics View:", ["🌍 All", "🚀 Pre-Match", "⚡ In-Play"], horizontal=True)
        
        if view_mode == "⚡ In-Play": f_logs = logs[logs['Match'].str.contains(r'\[LIVE\]', na=False)]
        elif view_mode == "🚀 Pre-Match": f_logs = logs[~logs['Match'].str.contains(r'\[LIVE\]', na=False)]
        else: f_logs = logs

        inv_logs = f_logs[f_logs['Investment'] > 0]
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Net Profit", f"{f_logs['Net_Profit'].sum():,.2f} THB")
        m2.metric("Accumulated", f"{inv_logs['Investment'].sum():,.2f} THB")
        m3.metric("Win Rate", f"{(len(inv_logs[inv_logs['Net_Profit']>0])/len(inv_logs)*100 if not inv_logs.empty else 0):.1f}%")
        m4.metric("ROI", f"{(f_logs['Net_Profit'].sum()/inv_logs['Investment'].sum()*100 if not inv_logs.empty and inv_logs['Investment'].sum()>0 else 0):.2f}%")
        m5.metric("Avg CLV", f"{inv_logs['CLV_Pct'].mean():.2f}%" if not inv_logs.empty else "0.00%")

        if not f_logs.empty:
            l_s = f_logs.sort_values(by='Time')
            l_s['Cum_Profit'] = l_s['Net_Profit'].cumsum()
            color = '#FF8C00' if "In" in view_mode else '#00FF7F'
            fig = go.Figure(go.Scatter(x=l_s['Time'], y=l_s['Cum_Profit'], mode='lines', fill='tozeroy', line=dict(color=color, width=3)))
            fig.update_layout(title=f"Equity Curve - {view_mode}", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("---")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("#### 📊 Profit by Target")
                st.bar_chart(l_s.groupby('Target')['Net_Profit'].sum(), color=color)
            with col_b:
                st.markdown("#### 🎯 Win Rate by Odds Range")
                l_s['Odds_Bin'] = pd.cut(l_s['Odds'], bins=[0, 1.8, 2.0, 2.2, 5.0], labels=['<1.8', '1.8-2.0', '2.0-2.2', '>2.2'])
                wr = (l_s[l_s['Net_Profit']>0].groupby('Odds_Bin', observed=False).size() / l_s.groupby('Odds_Bin', observed=False).size() * 100).fillna(0)
                st.bar_chart(wr, color=color)

# --- TAB 3: IN-PLAY LIVE ---
with tab3:
    with st.expander("👁️ AI Live Vision", expanded=False):
        # AI Vision logic here (ดักจับ JSON Error ตามที่แก้ให้ก่อนหน้า)
        pass

    col_l1, col_l2 = st.columns(2)
    with col_l1:
        st.subheader("🏁 Game State")
        c_h1, c_h2 = st.columns(2)
        cur_h = c_h1.number_input("Score H", min_value=0, key="lh_s")
        rc_h = c_h2.checkbox("🟥 Home RC", key="rc_h")
        c_a1, c_a2 = st.columns(2) # 🌟 Fix: เพิ่ม c_a1, c_a2
        cur_a = c_a1.number_input("Score A", min_value=0, key="la_s")
        rc_a = c_a2.checkbox("🟥 Away RC", key="rc_a")
        cur_min = st.slider("Minute", 0, 120, key="current_min")
    with col_l2:
        st.subheader("💡 Pre-match Odds")
        p_h = st.number_input("H(Pre)", key="pre_h")
        p_d = st.number_input("D(Pre)", key="pre_d")
        p_a = st.number_input("A(Pre)", key="pre_a")
        p_ou = st.number_input("OU(Pre)", key="pre_ou")

    st.markdown("---")
    st.subheader("💰 Live Prices")
    cl1, cl2 = st.columns(2)
    with cl1:
        st.markdown("Live HDP")
        bh1, bh2, bh3 = st.columns([1,2,1])
        bh1.button("-0.25", key="h_sub", on_click=adj_hdp, args=(-0.25,))
        l_hdp = bh2.number_input("HDP", key="live_hdp", label_visibility="collapsed")
        bh3.button("+0.25", key="h_add", on_click=adj_hdp, args=(0.25,))
        st.number_input("Water H", key="live_hdp_h")
        st.number_input("Water A", key="live_hdp_a")
    with cl2:
        st.markdown("Live O/U")
        bo1, bo2, bo3 = st.columns([1,2,1])
        bo1.button("-0.25", key="o_sub", on_click=adj_ou, args=(-0.25,))
        l_ou = bo2.number_input("OU", key="live_ou", label_visibility="collapsed")
        bo3.button("+0.25", key="o_add", on_click=adj_ou, args=(0.25,))
        st.number_input("Water Over", key="live_ou_over")
        st.number_input("Water Under", key="live_ou_under")

    c_btn1, c_btn2 = st.columns([4, 1])
    submit_live = c_btn1.button("🎯 ENGAGE SNIPER", use_container_width=True, type="primary")
    c_btn2.button("🗑️ Clear", use_container_width=True, on_click=clear_inplay_data)

    if submit_live:
        # 1. Devig Pre-match to get Lambda
        prob_h, prob_d, prob_a = shin_devig(st.session_state.pre_h, st.session_state.pre_d, st.session_state.pre_a)
        # 2. Logic to calculate In-play EV & AI Approval (บันทึกลง Supabase พร้อม [LIVE])
        # [แทรกส่วนคำนวณและบันทึกข้อมูลที่นี่]
        st.info("Sniper calculations and saving to Supabase would proceed here.")

# --- TAB 4: Backtest ---
with tab4:
    st.header("🧪 Backtest Evaluation")
    if not logs.empty:
        # Brier Score & Accuracy logic
        pass
