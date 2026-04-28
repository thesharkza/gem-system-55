import streamlit as st

# ==========================================
# 1. ฟังก์ชันสมองกล (Patch 5.5.3: Kelly Criterion Integration)
# ==========================================
def generate_gem_report(match_name, h1x2, d1x2, a1x2, hdp_line, hdp_home_water, hdp_away_water, ou_line, ou_over_water, ou_under_water, hdba_pct, total_bankroll):
    # --- ระยะที่ 1: Devigging (1X2) ---
    i_h, i_d, i_a = 1/h1x2, 1/d1x2, 1/a1x2
    margin = (i_h + i_d + i_a) - 1
    t_ph = i_h / (1 + margin)
    t_pd = i_d / (1 + margin)
    t_pa = i_a / (1 + margin)

    teams = match_name.split('VS')
    team_home = teams[0].strip() if len(teams) > 1 else "เจ้าบ้าน"
    team_away = teams[1].strip() if len(teams) > 1 else "ทีมเยือน"

    # --- ตรวจสอบสถานะทีมต่อ/ทีมรอง ---
    is_home_fav = t_ph >= t_pa
    hdp_val = abs(hdp_line)

    # --- ระยะที่ 4: EV & Kelly Calculation ---
    # หมายเหตุ: ในสูตร Kelly, b คือ "ราคาจ่ายสุทธิ" (ซึ่งก็คือค่าน้ำที่เรากรอก)
    if is_home_fav:
        ev_fav_raw = (t_ph * hdp_home_water) - ((t_pd + t_pa) * 1)
        ev_und_raw = ((t_pa + t_pd) * hdp_away_water) - (t_ph * 1)
        team_fav, team_und = team_home, team_away
        water_fav, water_und = hdp_home_water, hdp_away_water
        ev_fav_adj = ev_fav_raw 
        ev_und_adj = ev_und_raw - (hdba_pct / 100)
        final_b_fav = hdp_home_water
        final_b_und = hdp_away_water
    else:
        ev_fav_raw = (t_pa * hdp_away_water) - ((t_ph + t_pd) * 1)
        ev_und_raw = ((t_ph + t_pd) * hdp_home_water) - (t_pa * 1)
        team_fav, team_und = team_away, team_home
        water_fav, water_und = hdp_away_water, hdp_home_water
        ev_fav_adj = ev_fav_raw - (hdba_pct / 100)
        ev_und_adj = ev_und_raw
        final_b_fav = hdp_away_water
        final_b_und = hdp_home_water

    # --- ระบบคำนวณ Kelly Criterion (Half-Kelly 50%) ---
    def calc_kelly_amt(ev, b, bankroll):
        if ev <= 0 or b <= 0: return 0, 0
        full_k_pct = ev / b
        half_k_pct = full_k_pct * 0.5 # ใช้ Half-Kelly เพื่อความปลอดภัย
        # จำกัดการลงเงินไม่เกิน 10% ของพอร์ตต่อไม้เพื่อป้องกันความเสี่ยงสูงสุด
        safe_k_pct = min(half_k_pct, 0.10) 
        return safe_k_pct * 100, safe_k_pct * bankroll

    # คำนวณเงินลงทุน
    fav_k_pct, fav_k_money = calc_kelly_amt(ev_fav_adj, final_b_fav, total_bankroll)
    und_k_pct, und_k_money = calc_kelly_amt(ev_und_adj, final_b_und, total_bankroll)

    # --- เช็ค Margin of Safety (3%) ---
    MIN_EDGE = 0.03 
    is_fav_invest = ev_fav_adj >= MIN_EDGE
    is_und_invest = ev_und_adj >= MIN_EDGE
    is_any_invest = is_fav_invest or is_und_invest

    report = f"""📊 รายงานผลการวิเคราะห์ (GEM System 5.5.3 - The Kelly Module)
คู่แข่งขัน: {match_name} | ทุนเริ่มต้น: {total_bankroll:,.2f} THB

ระยะที่ 1-3: สรุปโครงสร้างราคา 🚨
Margin: {margin*100:.2f}% | สถานะ T21CB: {"ถูกกระตุ้น" if (t_ph > 0.5 and hdp_val >= 0.5 and ou_line <= 2.5) else "ปกติ"}
True Prob: {team_home} {t_ph*100:.1f}% | เสมอ {t_pd*100:.1f}% | {team_away} {t_pa*100:.1f}%

ระยะที่ 4: การคำนวณ Expected Value & Money Management 🛡️
(เกณฑ์การลงทุน: EV ต้อง > 3% | ใช้กลยุทท์ Half-Kelly 50% ในการเดินเงิน)

1. {team_fav} (ต่อ {hdp_val}) ค่าน้ำ {water_fav}:
   - EV_adj: {ev_fav_adj*100:.2f}%
   - สถานะ: {"🟢 ผ่านเกณฑ์" if is_fav_invest else "🔴 ไม่ผ่านเกณฑ์"}
   - คำแนะนำ: {"ลงทุน " + str(round(fav_k_pct, 2)) + "% ของพอร์ต" if is_fav_invest else "งดลงทุน"}

2. {team_und} (รอง {hdp_val}) ค่าน้ำ {water_und}:
   - EV_adj: {ev_und_adj*100:.2f}%
   - สถานะ: {"🟢 ผ่านเกณฑ์" if is_und_invest else "🔴 ไม่ผ่านเกณฑ์"}
   - คำแนะนำ: {"ลงทุน " + str(round(und_k_pct, 2)) + "% ของพอร์ต" if is_und_invest else "งดลงทุน"}

💡 บทสรุปและคำสั่งเดินเงิน (GEM Signal 5.5.3)
--------------------------------------------------
🔥 สัญญาณหลัก: {"🔥 INVEST" if is_any_invest else "🚫 NO BET"}
🎯 เป้าหมาย: {"ฝั่งรอง " + team_und if is_und_invest else ("ฝั่งต่อ " + team_fav if is_fav_invest else "N/A")}
💰 จำนวนเงินที่ควรลงทุน: {max(fav_k_money, und_k_money):,.2f} THB
--------------------------------------------------
*(คำนวณจากความได้เปรียบ {max(ev_fav_adj, ev_und_adj)*100:.2f}% สู้กับราคาจ่าย {max(final_b_fav, final_b_und):.2f})*
🚨 สถานะ: {"Standard Kelly 50% (เดินเงินแบบเน้นความปลอดภัย)" if is_any_invest else "Hold your bankroll 100%"}
"""
    return report

# ==========================================
# 2. UI Layout
# ==========================================
st.set_page_config(page_title="GEM System 5.5.3", layout="wide")
st.title("⚽ GEM System 5.5.3 - Kelly Module")
st.markdown("ระบบคำนวณสถิติและบริหารเงินลงทุน (Money Management)")

# เพิ่มช่องกรอกเงินทุน
total_bankroll = st.sidebar.number_input("💰 ทุนทั้งหมดของคุณ (THB)", min_value=0.0, value=10000.0, step=1000.0)

match_name_input = st.text_input("📝 ชื่อคู่การแข่งขัน", "โตเกียวเวอร์ดี้ VS คาชิม่า แอนท์เลอร์ส")

col1, col2, col3 = st.columns(3)
with col1:
    st.subheader("1. ราคาพูล 1X2")
    h_odds = st.number_input("เหย้า", value=3.75, format="%.2f")
    d_odds = st.number_input("เสมอ", value=3.03, format="%.2f")
    a_odds = st.number_input("เยือน", value=1.97, format="%.2f")

with col2:
    st.subheader("2. ตลาดแฮนดิแคป")
    hdp_line = st.number_input("HDP", value=0.50, format="%.2f")
    hdp_home = st.number_input("น้ำเจ้าบ้าน", value=0.93, format="%.2f")
    hdp_away = st.number_input("น้ำทีมเยือน", value=0.97, format="%.2f")

with col3:
    st.subheader("3. ตลาดสกอร์รวม")
    ou_line = st.number_input("O/U", value=2.00, format="%.2f")
    ou_over = st.number_input("น้ำสูง", value=0.81, format="%.2f")
    ou_under = st.number_input("น้ำต่ำ", value=1.06, format="%.2f")
    
st.markdown("---")    
st.markdown("Remark HDBA")
st.markdown("-หากเป็นลีกมาตรฐานยุโรป (พรีเมียร์ลีก, ลาลีกา) การเดินทางสะดวก ให้ใส่ HDBA = 1.5 (Base 1.0 + กองเชียร์ 0.5)")
st.markdown("-หากเป็นบอลถ้วยละตินอเมริกาที่ต้องบินข้ามประเทศ ให้ยืนพื้น HDBA = 2.5 ถึง 3.0 ไว้ก่อนเลย")
st.markdown("-หากไปเยือน โบลิเวีย หรือ เอกวาดอร์ (ที่ราบสูง) ให้กด HDBA = 4.5 หรือ 5.0 ได้เลยครับ")
hdba_val = st.slider("⚖️ HDBA Penalty %", 0.0, 10.0, 1.5, 0.1)

if st.button("🚀 คำนวณแผนการลงทุน", type="primary"):
    report = generate_gem_report(match_name_input, h_odds, d_odds, a_odds, hdp_line, hdp_home, hdp_away, ou_line, ou_over, ou_under, hdba_val, total_bankroll)
    st.success("✅ วิเคราะห์สำเร็จ!")
    st.code(report, language="text")
