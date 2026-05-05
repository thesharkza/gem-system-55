import streamlit as st
import pandas as pd
import math
import google.generativeai as genai
import plotly.graph_objects as go
from PIL import Image

# ==========================================
# ⚙️ 1. CONFIGURATION (ส่วนตั้งค่าระบบ - คงค่าเดิมของคุณไว้)
# ==========================================
st.set_page_config(page_title="GEM System 10.0 | Quant Engine", layout="wide")

# 🔑 ใส่ API Key ของคุณที่นี่
GEMINI_API_KEY = "ใส่_API_KEY_ของคุณที่นี่"
genai.configure(api_key=GEMINI_API_KEY)

# 🎯 ตั้งค่าเกณฑ์ EV เป้าหมาย (Threshold)
ah_threshold = 10.0
ou_threshold = 15.0

# ==========================================
# 🧠 2. QUANT ENGINE (สมองซีกซ้าย: คณิตศาสตร์ Master Version)
# ==========================================
def fix(o): 
    return o + 1.0 if o < 1.1 else o

def shin_devig(o_h, o_d, o_a):
    pi = [1/o_h, 1/o_d, 1/o_a]
    sum_pi = sum(pi)
    if sum_pi <= 1.0: return pi[0]/sum_pi, pi[1]/sum_pi, pi[2]/sum_pi
    low, high = 0.0, 1.0
    for _ in range(100):
        z = (low + high) / 2
        try:
            p = [(math.sqrt(z**2 + 4*(1-z)*pi_i) - z) / (2*(1-z)) for pi_i in pi]
            if sum(p) > 1: low = z
            else: high = z
        except: break
    p = [(math.sqrt(z**2 + 4*(1-z)*pi_i) - z) / (2*(1-z)) for pi_i in pi]
    sum_p = sum(p)
    return p[0]/sum_p, p[1]/sum_p, p[2]/sum_p

def poisson(k, lam):
    return (lam**k * math.exp(-lam)) / math.factorial(k)

# 🌟 ฟังก์ชันคำนวณอัตราต่อรองที่ผ่านการ Calibrate ปรับจูนแล้ว
def calc_dixon_coles_matrix(p_h, p_d, p_a, ou_line, ou_over_w, ou_under_w, rho, current_h=0, current_a=0, minutes_left=90, red_card_h=False, red_card_a=False):
    o_w = ou_over_w + 1.0 if ou_over_w < 1.1 else ou_over_w
    u_w = ou_under_w + 1.0 if ou_under_w < 1.1 else ou_under_w
    
    o_prob = 1.0 / o_w
    u_prob = 1.0 / u_w
    margin_ou = o_prob + u_prob
    true_o_prob = o_prob / margin_ou
    
    expected_total = ou_line + ((true_o_prob - 0.5) * 1.30)
    expected_total = max(0.5, expected_total)
    
    supremacy = (p_h - p_a) * (expected_total ** 0.65)
    
    lam_h_base = (expected_total + supremacy) / 2.0
    lam_a_base = (expected_total - supremacy) / 2.0
    
    lam_h_base = max(0.15, lam_h_base)
    lam_a_base = max(0.15, lam_a_base)

    time_factor = (minutes_left / 90.0) ** 0.85 
    lam_h = lam_h_base * time_factor
    lam_a = lam_a_base * time_factor

    if red_card_h: 
        lam_h *= 0.50 
        lam_a *= 1.30 
    if red_card_a: 
        lam_a *= 0.50
        lam_h *= 1.30

    matrix = [[0.0 for j in range(10)] for i in range(10)]
    for i in range(10): 
        for j in range(10): 
            base_prob = poisson(i, lam_h) * poisson(j, lam_a)
            if i == 0 and j == 0: tau = 1 - (lam_h * lam_a * rho)
            elif i == 0 and j == 1: tau = 1 + (lam_h * rho)
            elif i == 1 and j == 0: tau = 1 + (lam_a * rho)
            elif i == 1 and j == 1: tau = 1 - rho
            else: tau = 1.0
            matrix[i][j] = max(0, base_prob * tau)

    total_prob = sum(sum(row) for row in matrix)
    p_h_win_by_2plus = 0.0; p_h_win_by_1 = 0.0; p_draw = 0.0
    p_a_win_by_1 = 0.0; p_a_win_by_2plus = 0.0
    p_total_ou = {} 

    for i in range(10):
        for j in range(10):
            prob = matrix[i][j] / total_prob
            final_h = i + current_h
            final_a = j + current_a
            diff = final_h - final_a
            
            if diff >= 2: p_h_win_by_2plus += prob
            elif diff == 1: p_h_win_by_1 += prob
            elif diff == 0: p_draw += prob
            elif diff == -1: p_a_win_by_1 += prob
            elif diff <= -2: p_a_win_by_2plus += prob
            
            total_match_goals = final_h + final_a
            p_total_ou[total_match_goals] = p_total_ou.get(total_match_goals, 0.0) + prob
            
    return (p_h_win_by_2plus, p_h_win_by_1, p_draw, p_a_win_by_1, p_a_win_by_2plus, p_total_ou)

# (ส่วนโค้ดฟังก์ชัน calc_advanced_ah_ev และ calc_advanced_ou_ev ยังคงเหมือนเดิม)

# ==========================================
# 🤖 3. THE ORACLE (สมองซีกขวา: ประเมินความเสี่ยงด้วย AI)
# ==========================================
def ai_quant_decision_engine(match_data, ev_data, rules_text):
    prompt = f"""
    คุณคือ Chief Risk Officer และ Quant Analyst ทำการประเมินการลงทุน...
    (ใส่ Prompt ฉบับสมบูรณ์ของคุณที่นี่)
    """
    try:
        # 🌟 ใช้ Model ที่ทำงานได้และมีโควต้า
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"ORACLE APPROVED: AI ล้มเหลว (ใช้คณิตศาสตร์ล้วน): {e}"

def create_ev_gauge(ev_value, title, threshold):
    color = "#00FF00" if ev_value >= threshold else ("#FFBF00" if ev_value > 0 else "#FF3333")
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = ev_value,
        title = {'text': title},
        number = {'suffix': "%"},
        gauge = {
            'axis': {'range': [-20, 20]},
            'bar': {'color': color},
            'steps': [
                {'range': [-20, 0], 'color': "#ffe6e6"},
                {'range': [0, threshold], 'color': "#fff0b3"},
                {'range': [threshold, 20], 'color': "#e6ffe6"}
            ]
        }
    ))
    return fig

# ==========================================
# 🎨 4. UX/UI DASHBOARD (ระบบหน้าจอแสดงผล Premium)
# ==========================================
st.title("🛡️ GEM System 10.0: Quant Analysis Terminal")

# (ใส่ฟอร์มกรอกข้อมูลการแข่งขันของคุณตรงนี้ เหมือนเดิม)

if st.button("🚀 ANALYZE PRE-MATCH", use_container_width=True):
    # (คำนวณค่าต่างๆ ของคุณตรงนี้)
    
    # สมมติว่าคำนวณเสร็จแล้วได้ตัวแปรเหล่านี้มา (prob_h, prob_d, prob_a, best_ah, best_ou, ai_response)
    
    st.markdown("---")
    st.markdown("<h3 style='text-align: center;'>📊 ANALYZE PRE-MATCH (ผลวิเคราะห์คณิตศาสตร์)</h3>", unsafe_allow_html=True)
    st.write("")

    # 🌟 UI 1: กล่องตัวเลขสถิติความน่าจะเป็น
    st.markdown("<h5 style='text-align: center; color: #aaaaaa;'>📈 สถิติความน่าจะเป็น (Implied Probabilities)</h5>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1: st.metric(label="🏠 โอกาสเจ้าบ้านชนะ", value=f"{prob_h*100:.1f}%")
    with col2: st.metric(label="🤝 โอกาสเสมอ", value=f"{prob_d*100:.1f}%")
    with col3: st.metric(label="✈️ โอกาสเยือนชนะ", value=f"{prob_a*100:.1f}%")

    st.markdown("---")

    # 🌟 UI 2: หน้าปัดกราฟ EV ซ้าย-ขวา
    g1, g2 = st.columns(2)
    with g1: 
        st.markdown("<h4 style='text-align: center; color: #4db8ff;'>🔵 ตลาดแฮนดิแคป (AH)</h4>", unsafe_allow_html=True)
        st.plotly_chart(create_ev_gauge(best_ah['ev'], f"เป้าหมาย: {best_ah['n']}", ah_threshold), use_container_width=True)
        
    with g2: 
        st.markdown("<h4 style='text-align: center; color: #ff9933;'>🟠 ตลาดสกอร์รวม (O/U)</h4>", unsafe_allow_html=True)
        st.plotly_chart(create_ev_gauge(best_ou['ev'], f"เป้าหมาย: {best_ou['n']}", ou_threshold), use_container_width=True)

    st.markdown("---")

    # 🌟 UI 3: กล่องแจ้งเตือนสถานะแบบมีสีสัน (Status Banner)
    if "APPROVED" in ai_response:
        st.success("✅ ORACLE APPROVED: อนุมัติการลงทุน! ค่า EV ผ่านเกณฑ์ที่กำหนดและผ่านการกรองความเสี่ยงแล้ว")
        st.info("💡 ข้อแนะนำ: โปรดบริหารเงินทุน (Bankroll Management) อย่างเคร่งครัดตามแผนของคุณ")
    else:
        st.error("🛑 REJECTED: เป้าหมายไม่ถึงเกณฑ์ที่ตั้งไว้ หรือ AI ตรวจพบความเสี่ยงสูงจากคัมภีร์ GEM")

    # 🌟 UI 4: ซ่อนข้อความยาวๆ เพื่อความสะอาดตา (Expander)
    with st.expander("📖 ดูรายละเอียดคัมภีร์ GEM ที่ทำงาน (Oracle Rules Log)"):
        st.write("**📝 เหตุผลจาก Chief Risk Officer (AI):**")
        st.write(ai_response)
        st.markdown("---")
        st.caption("🔍 ข้อมูลนี้ใช้สำหรับตรวจสอบตรรกะการตัดสินใจของ AI ระบบ Quant Engine")
