import streamlit as st

# ==========================================
# 1. ฟังก์ชันสมองกล (Patch 5.5.5: The Odds Standardizer)
# ==========================================
def generate_gem_report(match_name, h1x2, d1x2, a1x2, hdp_line, hdp_h_w, hdp_a_w, ou_line, ou_o_w, ou_u_w, hdba_pct, total_bankroll):
    
    # --- ฟังก์ชันแก้บั๊กค่าน้ำ (ปรับจาก HK/Malay เป็น Decimal) ---
    def fix_odds(o):
        # ถ้าค่าที่กรอกมาน้อยกว่า 1.0 เช่น 0.93 ให้บวก 1 เป็น 1.93
        # ถ้ากรอกมา 1.05 ให้ถือว่าเป็นราคา Decimal อยู่แล้ว (แทง 1 ได้กำไร 1.05)
        # แต่ถ้าบ่อนใช้ราคา Decimal แบบรวมทุน เช่น 2.05 ระบบก็จะเข้าใจได้
        return o + 1.0 if o < 1.1 else o 

    h1, d1, a1 = fix_odds(h1x2), fix_odds(d1x2), fix_odds(a1x2)
    hdp_h, hdp_a = fix_odds(hdp_h_w), fix_odds(hdp_a_w)
    ou_o, ou_u = fix_odds(ou_o_w), fix_odds(ou_u_w)

    # --- ระยะที่ 1: Devigging ---
    i_h, i_d, i_a = 1/h1, 1/d1, 1/a1
    m_1x2 = (i_h + i_d + i_a) - 1
    t_ph, t_pd, t_pa = i_h/(1+m_1x2), i_d/(1+m_1x2), i_a/(1+m_1x2)

    i_over, i_under = 1/ou_o, 1/ou_u
    m_ou = (i_over + i_under) - 1
    t_p_o, t_p_u = i_over/(1+m_ou), i_under/(1+m_ou)

    teams = match_name.split('VS')
    t_home, t_away = teams[0].strip(), teams[1].strip()
    is_home_fav = t_ph >= t_pa

    # --- ระยะที่ 4: EV Calculation ---
    if is_home_fav:
        # กำไรสุทธิ (b) คือ ค่าน้ำ - 1 (ถ้าค่าน้ำที่ fix แล้วคือ 1.93 กำไรคือ 0.93)
        b_fav, b_und = hdp_h - 1, hdp_a - 1
        ev_fav = (t_ph * b_fav) - ((t_pd + t_pa) * 1)
        ev_und = ((t_pa + t_pd) * b_und) - (t_ph * 1)
        ev_und_adj = ev_und - (hdba_pct / 100)
        ev_fav_adj = ev_fav
    else:
        b_fav, b_und = hdp_a - 1, hdp_h - 1
        ev_fav = (t_pa * b_fav) - ((t_ph + t_pd) * 1)
        ev_und = ((t_ph + t_pd) * b_und) - (t_pa * 1)
        ev_fav_adj = ev_fav - (hdba_pct / 100)
        ev_und_adj = ev_und

    # O/U EV
    b_over, b_under = ou_o - 1, ou_u - 1
    ev_o = (t_p_o * b_over) - (t_p_u * 1)
    ev_u = (t_p_u * b_under) - (t_p_o * 1)
    if (t_ph > 0.5 and abs(hdp_line) >= 0.5 and ou_line <= 2.5): ev_u -= 0.05

    # --- Kelly 50% ---
    def calc_k(ev, b, bank):
        if ev < 0.03: return 0, 0
        pct = (ev / b) * 0.5
        safe_pct = min(pct, 0.10)
        return safe_pct * 100, safe_pct * bank

    f_k_p, f_k_m = calc_k(ev_fav_adj, b_fav if is_home_fav else b_fav, total_bankroll)
    u_k_p, u_k_m = calc_k(ev_und_adj, b_und if is_home_fav else b_und, total_bankroll)
    o_k_p, o_k_m = calc_k(ev_o, b_over, total_bankroll)
    un_k_p, un_k_m = calc_k(ev_u, b_under, total_bankroll)

    # สรุป Best Bet
    options = [
        {"name": f"ต่อ {t_home if is_home_fav else t_away}", "ev": ev_fav_adj, "money": f_k_m},
        {"name": f"รอง {t_away if is_home_fav else t_home}", "ev": ev_und_adj, "money": u_k_m},
        {"name": "สูง (Over)", "ev": ev_o, "money": o_k_m},
        {"name": "ต่ำ (Under)", "ev": ev_u, "money": un_k_m}
    ]
    best = max(options, key=lambda x: x['ev'])
    
    return f"""📊 GEM System 5.5.5 (The Odds Standardizer)
คู่: {match_name}

ระยะที่ 1-2: สถิติจริง 🚨
- Margin 1X2: {m_1x2*100:.2f}% | Margin O/U: {m_ou*100:.2f}%
- True Prob: {t_home} {t_ph*100:.1f}% | เสมอ {t_pd*100:.1f}% | {t_away} {t_pa*100:.1f}%

ระยะที่ 3-4: วิเคราะห์ความคุ้มค่า 🛡️
- ต่อ: EV {ev_fav_adj*100:.2f}% | {"ลงเงิน "+str(round(f_k_p,1))+"%" if f_k_p>0 else "งด"}
- รอง: EV {ev_und_adj*100:.2f}% | {"ลงเงิน "+str(round(u_k_p,1))+"%" if u_k_p>0 else "งด"}
- สูง: EV {ev_o*100:.2f}% | {"ลงเงิน "+str(round(o_k_p,1))+"%" if o_k_p>0 else "งด"}
- ต่ำ: EV {ev_u*100:.2f}% | {"ลงเงิน "+str(round(un_k_p,1))+"%" if un_k_p>0 else "งด"}

💡 บทสรุป: {"🔥 INVEST" if best['ev']>=0.03 else "🚫 NO BET"}
🎯 ตัวเลือกที่ดีที่สุด: {best['name'] if best['ev']>=0.03 else "N/A"}
💰 จำนวนเงิน: {best['money'] if best['ev']>=0.03 else 0:,.2f} THB
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
