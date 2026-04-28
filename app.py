import streamlit as st

# ==========================================
# 1. ฟังก์ชันสมองกล (Patch 5.6.0: Universal AH Engine)
# ==========================================
def calc_universal_ev(hdp, p_win, p_draw, p_loss, odds, is_fav):
    """
    ฟังก์ชันคำนวณ EV แบบครอบจักรวาล รองรับทุกราคาแฮนดิแคป
    """
    b = odds - 1  # กำไรสุทธิ
    
    # 1. กลุ่มราคาเลขกลม (0, 1, 2, 3...)
    if hdp % 1 == 0:
        return (p_win * b) - (p_loss * 1)
    
    # 2. กลุ่มราคาเลขครึ่ง (0.5, 1.5, 2.5...)
    elif hdp % 1 == 0.5:
        if is_fav: return (p_win * b) - ((p_draw + p_loss) * 1)
        else: return ((p_win + p_draw) * b) - (p_loss * 1)
        
    # 3. กลุ่มราคาควบ (0.25, 1.25, 2.25...) - เน้นผลเสมอ
    elif hdp % 0.5 == 0.25:
        # ถ้าราคาลงท้ายด้วย .25 (เช่น 0.25, 1.25)
        if is_fav: return (p_win * b) - (p_draw * 0.5) - (p_loss * 1) # ต่อ: เสมอเสียครึ่ง
        else: return (p_win * b) + (p_draw * b/2) - (p_loss * 1) # รอง: เสมอกินครึ่ง
        
    # 4. กลุ่มราคาควบ (0.75, 1.75, 2.75...) - เน้นผลชนะห่าง 1 ลูก
    # หมายเหตุ: ในระบบ 1X2 พื้นฐาน เราจะใช้ Conservative Logic (ปลอดภัยไว้ก่อน)
    elif hdp % 0.5 == 0.75:
        if is_fav: return (p_win * b * 0.7) - ((p_draw + p_loss) * 1) # ต่อ: ชนะลูกเดียวอาจได้ไม่เต็ม
        else: return ((p_win + p_draw) * b) - (p_loss * 0.5) # รอง: แพ้ลูกเดียวเสียครึ่ง
        
    return (p_win * b) - ((p_draw + p_loss) * 1) # Default

def generate_gem_report(match_name, h1x2, d1x2, a1x2, hdp_line, hdp_h_w, hdp_a_w, ou_line, ou_o_w, ou_u_w, hdba_pct, total_bankroll):
    # Fix Odds System
    def f_o(o): return o + 1.0 if o < 1.1 else o 
    h1, d1, a1 = f_o(h1x2), f_o(d1x2), f_o(a1x2)
    h_w, a_w, o_w, u_w = f_o(hdp_h_w), f_o(hdp_a_w), f_o(ou_o_w), f_o(ou_u_w)

    # Devigging 1X2
    m_1x2 = (1/h1 + 1/d1 + 1/a1) - 1
    p_h, p_d, p_a = (1/h1)/(1+m_1x2), (1/d1)/(1+m_1x2), (1/a1)/(1+m_1x2)
    
    # Devigging O/U
    m_ou = (1/o_w + 1/u_w) - 1
    p_o, p_u = (1/o_w)/(1+m_ou), (1/u_w)/(1+m_ou)

    # AH EV Calculation (Using Universal Engine)
    is_h_fav = p_h >= p_a
    ev_h = calc_universal_ev(hdp_line, p_h, p_d, p_a, h_w, is_h_fav)
    ev_a = calc_universal_ev(hdp_line, p_a, p_d, p_h, a_w, not is_h_fav)
    
    # หัก HDBA เฉพาะทีมเยือน
    if is_h_fav: ev_a -= (hdba_pct/100)
    else: ev_a -= (hdba_pct/100) # ทีมเยือนเป็นต่อก็ต้องหักค่าเดินทาง

    # O/U EV
    ev_over = (p_o * (o_w-1)) - (p_u * 1)
    ev_under = (p_u * (u_w-1)) - (p_o * 1)
    if p_h > 0.5 and ou_line <= 2.5: ev_under -= 0.05

    # Kelly Criterion
    def get_k(ev, odds, bank):
        if ev < 0.03: return 0, 0
        k_pct = (( (odds-1) * ((ev+1)/odds) ) - (1 - ((ev+1)/odds))) / (odds-1)
        safe_k = min(k_pct * 0.5, 0.10)
        return safe_k * 100, safe_k * bank

    h_k_p, h_k_m = get_k(ev_h, h_w, total_bankroll)
    a_k_p, a_k_m = get_k(ev_a, a_w, total_bankroll)
    o_k_p, o_k_m = get_k(ev_over, o_w, total_bankroll)
    u_k_p, u_k_m = get_k(ev_under, u_w, total_bankroll)

    res = [{"n": "เจ้าบ้าน", "ev": ev_h, "m": h_k_m, "p": h_k_p},
           {"n": "ทีมเยือน", "ev": ev_a, "m": a_k_m, "p": a_k_p},
           {"n": "สูง", "ev": ev_over, "m": o_k_m, "p": o_k_p},
           {"n": "ต่ำ", "ev": ev_under, "m": u_k_m, "p": u_k_p}]
    best = max(res, key=lambda x: x['ev'])

    return f"""📊 GEM System Patch 5.6.0: Universal AH Engine
คู่: {match_name}

สถิติจริง 🚨
- True Prob: เหย้า {p_h*100:.1f}% | เสมอ {p_d*100:.1f}% | เยือน {p_a*100:.1f}%

วิเคราะห์ EV (แก้ไขกฎ 0.25 แล้ว) 🛡️
- เจ้าบ้าน (ต่อ 0.25): EV {ev_h*100:.2f}%
- ทีมเยือน (รอง 0.25): EV {ev_a*100:.2f}%
- สูง/ต่ำ {ou_line}: สูง {ev_over*100:.2f}% | ต่ำ {ev_under*100:.2f}%

💡 สรุป: {"🔥 INVEST" if best['ev']>=0.03 else "🚫 NO BET"}
🎯 เป้าหมาย: {best['n'] if best['ev']>=0.03 else "N/A"}
💰 ยอดเงิน: {best['m'] if best['ev']>=0.03 else 0:,.2f} THB
"""
    return report

# ==========================================
# 2. UI Layout
# ==========================================
st.set_page_config(page_title="GEM System 5.5.4", layout="wide")
st.title("⚽ GEM System Patch 5.6.0: Universal AH Engine")
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
