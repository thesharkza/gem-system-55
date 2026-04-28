import streamlit as st

# ==========================================
# 1. ฟังก์ชันสมองกล (Patch 5.5.6: The Ultimate Brain)
# ==========================================
def generate_gem_report(match_name, h1x2, d1x2, a1x2, hdp_line, hdp_h_w, hdp_a_w, ou_line, ou_o_w, ou_u_w, hdba_pct, total_bankroll):
    
    def fix_odds(o):
        return o + 1.0 if o < 1.1 else o 

    # แปลงค่าน้ำให้เป็นระบบเดียวกันทั้งหมด
    h1, d1, a1 = fix_odds(h1x2), fix_odds(d1x2), fix_odds(a1x2)
    h_w, a_w = fix_odds(hdp_h_w), fix_odds(hdp_a_w)
    o_w, u_w = fix_odds(ou_o_w), fix_odds(ou_u_w)

    # ระยะที่ 1: Devigging (หาโอกาสชนะที่แท้จริง)
    m_1x2 = (1/h1 + 1/d1 + 1/a1) - 1
    p_h, p_d, p_a = (1/h1)/(1+m_1x2), (1/d1)/(1+m_1x2), (1/a1)/(1+m_1x2)
    
    m_ou = (1/o_w + 1/u_w) - 1
    p_o, p_u = (1/o_w)/(1+m_ou), (1/u_w)/(1+m_ou)

    # ระยะที่ 4: คำนวณ EV แบบ Matrix (แก้บั๊กสลับฝั่งถาวร)
    # ฝั่งเจ้าบ้าน (Home)
    ev_h = (p_h * (h_w-1)) - ((p_d + p_a) * 1)
    # ฝั่งทีมเยือน (Away) + หัก HDBA
    ev_a = (p_a * (a_w-1)) - ((p_h + p_d) * 1) - (hdba_pct/100)
    
    # ฝั่งสกอร์รวม
    ev_over = (p_o * (o_w-1)) - (p_u * 1)
    ev_under = (p_u * (u_w-1)) - (p_o * 1)
    # กฎ T21CB
    if p_h > 0.5 and ou_line <= 2.5: ev_under -= 0.05

    def get_k(ev, odds, bank):
        if ev < 0.03: return 0, 0
        p_win = (ev + 1) / odds
        b = odds - 1
        k_pct = ( (b * p_win) - (1 - p_win) ) / b
        safe_k = min(k_pct * 0.5, 0.10) # Half-Kelly & Cap 10%
        return max(0, safe_k * 100), max(0, safe_k * bank)

    h_k_p, h_k_m = get_k(ev_h, h_w, total_bankroll)
    a_k_p, a_k_m = get_k(ev_a, a_w, total_bankroll)
    o_k_p, o_k_m = get_k(ev_over, o_w, total_bankroll)
    u_k_p, u_k_m = get_k(ev_under, u_w, total_bankroll)

    res = [
        {"n": "เจ้าบ้าน (Home)", "ev": ev_h, "m": h_k_m, "p": h_k_p},
        {"n": "ทีมเยือน (Away)", "ev": ev_a, "m": a_k_m, "p": a_k_p},
        {"n": "สูง (Over)", "ev": ev_over, "m": o_k_m, "p": o_k_p},
        {"n": "ต่ำ (Under)", "ev": ev_under, "m": u_k_m, "p": u_k_p}
    ]
    best = max(res, key=lambda x: x['ev'])

    return f"""📊 GEM System 5.5.6 (The Ultimate Brain)
คู่: {match_name}

สถิติจริง 🚨
- Margin 1X2: {m_1x2*100:.2f}% | O/U: {m_ou*100:.2f}%
- True Prob: เหย้า {p_h*100:.1f}% | เสมอ {p_d*100:.1f}% | เยือน {p_a*100:.1f}%

ความคุ้มค่า (Margin of Safety 3%) 🛡️
- เจ้าบ้าน: EV {ev_h*100:.2f}% | {"ลงทุน "+str(round(h_k_p,1))+"%" if h_k_p>0 else "งด"}
- ทีมเยือน: EV {ev_a*100:.2f}% | {"ลงทุน "+str(round(a_k_p,1))+"%" if a_k_p>0 else "งด"}
- สูง: EV {ev_over*100:.2f}% | {"ลงทุน "+str(round(o_k_p,1))+"%" if o_k_p>0 else "งด"}
- ต่ำ: EV {ev_under*100:.2f}% | {"ลงทุน "+str(round(u_k_p,1))+"%" if u_k_p>0 else "งด"}

💡 สรุป: {"🔥 INVEST" if best['ev']>=0.03 else "🚫 NO BET"}
🎯 เป้าหมาย: {best['n'] if best['ev']>=0.03 else "N/A"}
💰 ยอดเงิน: {best['m'] if best['ev']>=0.03 else 0:,.2f} THB
"""
    return report

# ==========================================
# 2. UI Layout
# ==========================================
st.set_page_config(page_title="GEM System 5.5.4", layout="wide")
st.title("⚽ GEM System 5.5.4 - Total Market Integration")
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

if st.button("🚀 สแกนตลาดทั้งหมด", type="primary"):
    report = generate_gem_report(match_name, h1x2, d1x2, a1x2, hdp_line, hdp_h_w, hdp_a_w, ou_line, ou_over_w, ou_under_w, hdba_val, total_bankroll)
    st.code(report, language="text")
