import streamlit as st

# ==========================================
# 1. ฟังก์ชันสมองกล (Patch 5.5.4: Total Market Integration)
# ==========================================
def generate_gem_report(match_name, h1x2, d1x2, a1x2, hdp_line, hdp_home_water, hdp_away_water, ou_line, ou_over_water, ou_under_water, hdba_pct, total_bankroll):
    # --- ระยะที่ 1: Devigging (1X2 & O/U) ---
    # 1X2 Market
    i_h, i_d, i_a = 1/h1x2, 1/d1x2, 1/a1x2
    m_1x2 = (i_h + i_d + i_a) - 1
    t_ph, t_pd, t_pa = i_h/(1+m_1x2), i_d/(1+m_1x2), i_a/(1+m_1x2)

    # O/U Market
    i_over, i_under = 1/ou_over_water, 1/ou_under_water
    m_ou = (i_over + i_under) - 1
    t_p_over, t_p_under = i_over/(1+m_ou), i_under/(1+m_ou)

    teams = match_name.split('VS')
    team_home = teams[0].strip() if len(teams) > 1 else "เจ้าบ้าน"
    team_away = teams[1].strip() if len(teams) > 1 else "ทีมเยือน"

    # --- ตรวจสอบสถานะทีมต่อ/ทีมรอง ---
    is_home_fav = t_ph >= t_pa
    hdp_val = abs(hdp_line)

    # --- ระยะที่ 2: T21CB Protocol ---
    is_t21cb = (t_ph > 0.50 and hdp_val >= 0.5 and ou_line <= 2.5)

    # --- ระยะที่ 4: EV Calculation ---
    # 4.1 ตลาดแฮนดิแคป (AH)
    if is_home_fav:
        ev_fav_raw = (t_ph * hdp_home_water) - ((t_pd + t_pa) * 1)
        ev_und_raw = ((t_pa + t_pd) * hdp_away_water) - (t_ph * 1)
        team_fav, team_und = team_home, team_away
        water_fav, water_und = hdp_home_water, hdp_away_water
        ev_fav_adj, ev_und_adj = ev_fav_raw, ev_und_raw - (hdba_pct / 100)
    else:
        ev_fav_raw = (t_pa * hdp_away_water) - ((t_ph + t_pd) * 1)
        ev_und_raw = ((t_ph + t_pd) * hdp_home_water) - (t_pa * 1)
        team_fav, team_und = team_away, team_home
        water_fav, water_und = hdp_away_water, hdp_home_water
        ev_fav_adj, ev_und_adj = ev_fav_raw - (hdba_pct / 100), ev_und_raw

    # 4.2 ตลาดสกอร์รวม (O/U)
    ev_over = (t_p_over * ou_over_water) - (t_p_under * 1)
    ev_under = (t_p_under * ou_under_water) - (t_p_over * 1)
    # กฎ T21CB ลงโทษหน้าต่ำ
    if is_t21cb: ev_under -= 0.05

    # --- ระบบคำนวณ Kelly Criterion (Half-Kelly 50%) ---
    def calc_k(ev, b, bank):
        if ev < 0.03: return 0, 0 # ต้องผ่านเกณฑ์ Margin of Safety 3%
        pct = (ev / b) * 0.5
        safe_pct = min(pct, 0.10) # Max 10%
        return safe_pct * 100, safe_pct * bank

    f_k_pct, f_k_m = calc_k(ev_fav_adj, water_fav, total_bankroll)
    u_k_pct, u_k_m = calc_k(ev_und_adj, water_und, total_bankroll)
    o_k_pct, o_k_m = calc_k(ev_over, ou_over_water, total_bankroll)
    un_k_pct, un_k_m = calc_k(ev_under, ou_under_water, total_bankroll)

    # ค้นหาตัวเลือกที่ดีที่สุด (Best Bet)
    options = [
        {"name": f"ต่อ {team_fav}", "ev": ev_fav_adj, "money": f_k_m},
        {"name": f"รอง {team_und}", "ev": ev_und_adj, "money": u_k_m},
        {"name": "สูง (Over)", "ev": ev_over, "money": o_k_m},
        {"name": "ต่ำ (Under)", "ev": ev_under, "money": un_k_m}
    ]
    best_bet = max(options, key=lambda x: x['ev'])
    is_any_invest = best_bet['ev'] >= 0.03

    report = f"""📊 รายงานวิเคราะห์ GEM System 5.5.4 (Total Integration)
คู่: {match_name} | ทุน: {total_bankroll:,.0f} THB

ระยะที่ 1-2: โครงสร้างราคาและกับดัก 🚨
- Margin 1X2: {m_1x2*100:.2f}% | Margin O/U: {m_ou*100:.2f}%
- True Prob: {team_home} {t_ph*100:.1f}% | เสมอ {t_pd*100:.1f}% | {team_away} {t_pa*100:.1f}%
- สถานะ T21CB: {"🚨 ตรวจพบกับดัก (หัก EV หน้าต่ำ 5%)" if is_t21cb else "✅ ปกติ"}

ระยะที่ 3: วิเคราะห์ตลาดแฮนดิแคป (AH) 🛡️
- {team_fav} (ต่อ {hdp_val}): EV {ev_fav_adj*100:.2f}% | แนะนำ: {"ลงทุน "+str(round(f_k_pct,1))+"%" if f_k_pct>0 else "งดลงทุน"}
- {team_und} (รอง {hdp_val}): EV {ev_und_adj*100:.2f}% | แนะนำ: {"ลงทุน "+str(round(u_k_pct,1))+"%" if u_k_pct>0 else "งดลงทุน"}

ระยะที่ 4: วิเคราะห์ตลาดสกอร์รวม (O/U) ⚡
- สูง (Over) {ou_line}: EV {ev_over*100:.2f}% | แนะนำ: {"ลงทุน "+str(round(o_k_pct,1))+"%" if o_k_pct>0 else "งดลงทุน"}
- ต่ำ (Under) {ou_line}: EV {ev_under*100:.2f}% | แนะนำ: {"ลงทุน "+str(round(un_k_pct,1))+"%" if un_k_pct>0 else "งดลงทุน"}

💡 บทสรุปและคำสั่งเดินเงิน (Best Value Selector)
--------------------------------------------------
🔥 สัญญาณหลัก: {"🔥 INVEST" if is_any_invest else "🚫 NO BET"}
🎯 ตัวเลือกที่ดีที่สุด: {best_bet['name'] if is_any_invest else "N/A"}
💰 จำนวนเงินที่ควรลงทุน: {best_bet['money'] if is_any_invest else 0:,.2f} THB
--------------------------------------------------
🚨 กลยุทธ์: Half-Kelly 50% (Margin of Safety 3%)
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
