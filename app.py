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

def clear_inplay_data():
    keys = ['lh_s', 'la_s', 'rc_h', 'rc_a', 'current_min', 'pre_h', 'pre_d', 'pre_a', 'pre_ou', 
            'live_hdp', 'live_hdp_h', 'live_hdp_a', 'live_ou', 'live_ou_over', 'live_ou_under']
    for k in keys:
        st.session_state[k] = 0 if 's' in k or 'min' in k else (False if 'rc' in k else 0.0)
    st.session_state['current_min'] = 45 # Default reset

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

# ... (ฟังก์ชัน Poisson/Matrix อื่นๆ คงเดิมตามโครงสร้าง Dixon-Coles ของคุณ) ...
# [ขออนุญาตละส่วนคำนวณ Matrix ไว้เพื่อความกระชับ แต่ให้คงโค้ดส่วนนี้ไว้ในไฟล์จริง]

# ==========================================
# 3. ส่วนแสดงผลหลัก (UI)
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs(["🚀 Pre-Match Terminal", "📊 Dashboard & AI", "⚡ IN-PLAY LIVE", "🧪 Backtest (RPS)"])

# --- TAB 2: Dashboard (Cloud Mode) ---
with tab2:
    logs = load_logs()
    if not logs.empty:
        st.subheader("📝 บันทึกผลบน Cloud (Supabase)")
        display_df = logs.sort_values(by='Time', ascending=False).reset_index(drop=True)
        edited_df = st.data_editor(display_df, column_config={
            "Closing_Odds": st.column_config.NumberColumn("Closing Odds", format="%.2f"),
            "Result": st.column_config.SelectboxColumn("Result", options=["Win", "Half Win", "Push", "Half Loss", "Loss", ""])
        }, use_container_width=True, key="editor")

        c_b1, c_b2 = st.columns(2)
        if c_b1.button("💾 Sync to Cloud"):
            for _, row in edited_df.iterrows():
                supabase.table("investment_logs").update({
                    "Closing_Odds": float(row['Closing_Odds']), 
                    "Result": str(row['Result'])
                }).eq("id", row['id']).execute()
            st.rerun()
            
        if c_b2.button("🗑️ Reset Database (Danger)"):
            if st.checkbox("ยืนยันการลบข้อมูลทั้งหมดในฐานข้อมูล"):
                supabase.table("investment_logs").delete().neq("id", 0).execute()
                st.rerun()

        logs['Net_Profit'] = logs.apply(calculate_net_profit, axis=1)
        logs['CLV_Pct'] = logs.apply(calculate_clv, axis=1)

        st.markdown("---")
        view_mode = st.radio("Analytics View:", ["🌍 All", "🚀 Pre-Match", "⚡ In-Play"], horizontal=True)
        
        if view_mode == "⚡ In-Play": f_logs = logs[logs['Match'].str.contains(r'\[LIVE\]', na=False)]
        elif view_mode == "🚀 Pre-Match": f_logs = logs[~logs['Match'].str.contains(r'\[LIVE\]', na=False)]
        else: f_logs = logs

        inv_logs = f_logs[f_logs['Investment'] > 0]
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Net Profit", f"{f_logs['Net_Profit'].sum():,.2f}")
        m3.metric("Win Rate", f"{(len(inv_logs[inv_logs['Net_Profit']>0])/len(inv_logs)*100 if not inv_logs.empty else 0):.1f}%")
        m5.metric("Avg CLV", f"{inv_logs['CLV_Pct'].mean():.2f}%" if not inv_logs.empty else "0.00%")

        if not f_logs.empty:
            l_s = f_logs.sort_values(by='Time')
            l_s['Cum_Profit'] = l_s['Net_Profit'].cumsum()
            color = '#FF8C00' if "In" in view_mode else '#00FF7F'
            fig = go.Figure(go.Scatter(x=l_s['Time'], y=l_s['Cum_Profit'], mode='lines', fill='tozeroy', line=dict(color=color)))
            st.plotly_chart(fig, use_container_width=True)

# --- TAB 3: IN-PLAY LIVE (Sniper Mode) ---
with tab3:
    with st.expander("👁️ AI Live Vision", expanded=False):
        # ... (โค้ด AI Vision ที่ปรับปรุงการดักจับ JSON Error แล้ว) ...
        pass

    col_l1, col_l2 = st.columns(2)
    with col_l1:
        st.subheader("🏁 Game State")
        c_h1, c_h2 = st.columns(2)
        cur_h = c_h1.number_input("Score H", min_value=0, key="lh_s")
        cur_a = c_a1.number_input("Score A", min_value=0, key="la_s")
        cur_min = st.slider("Minute", 0, 120, key="current_min")
    
    # ... (ส่วนประกอบราคา Live HDP/OU) ...

    c_btn1, c_btn2 = st.columns([4, 1])
    submit_live = c_btn1.button("🎯 ENGAGE SNIPER", use_container_width=True, type="primary")
    c_btn2.button("🗑️ Clear", use_container_width=True, on_click=clear_inplay_data)

    if submit_live:
        # บันทึกบิลลง Supabase พร้อมแท็ก [LIVE] เมื่อ AI อนุมัติ
        # [แทรกโค้ด AI Decision และ save_to_supabase ที่นี่]
        pass

# --- TAB 4: Backtest (RPS/Brier) ---
with tab4:
    # ... (โค้ด Backtest ที่ดึงข้อมูลจาก load_logs() มาประมวลผล) ...
    pass
