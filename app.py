import streamlit as st

# ==========================================
# 1. ฟังก์ชันสมองกล (Patch 5.5.2: Auto-Detect Favorite/Underdog)
# ==========================================
def generate_gem_report(match_name, h1x2, d1x2, a1x2, hdp_line, hdp_home_water, hdp_away_water, ou_line, ou_over_water, ou_under_water, hdba_pct):
    # --- ระยะที่ 1: Devigging (1X2) ---
    i_h, i_d, i_a = 1/h1x2, 1/d1x2, 1/a1x2
    margin = (i_h + i_d + i_a) - 1
    t_ph = i_h / (1 + margin)
    t_pd = i_d / (1 + margin)
    t_pa = i_a / (1 + margin)

    teams = match_name.split('VS')
    team_home = teams[0].strip() if len(teams) > 1 else "เจ้าบ้าน"
    team_away = teams[1].strip() if len(teams) > 1 else "ทีมเยือน"

    # --- ตรวจสอบว่าใครเป็นทีมต่อ (Favorite) ---
    is_home_fav = t_ph >= t_pa
    hdp_val = abs(hdp_line) # บังคับให้ราคาต่อเป็นบวกเสมอเวลาแสดงผล

    # --- ระยะที่ 4: EV Calculation (แยกกรณีเจ้าบ้านต่อ vs ทีมเยือนต่อ) ---
    if is_home_fav:
        # เจ้าบ้านต่อ
        ev_home_raw = (t_ph * hdp_home_water) - ((t_pd + t_pa) * 1)
        ev_away_raw = ((t_pa + t_pd) * hdp_away_water) - (t_ph * 1)
        
        team_fav_name, team_und_name = team_home, team_away
        ev_fav_raw, ev_und_raw = ev_home_raw, ev_away_raw
        water_fav, water_und = hdp_home_water, hdp_away_water
        
        # HDBA คิดเฉพาะตอนทีมเยือนเป็นทีมรอง
        ev_und_adj = ev_und_raw - (hdba_pct / 100)
        ev_fav_adj = ev_fav_raw 
    else:
        # ทีมเยือนต่อ
        ev_away_raw = (t_pa * hdp_away_water) - ((t_ph + t_pd) * 1)
        ev_home_raw = ((t_ph + t_pd) * hdp_home_water) - (t_pa * 1)
        
        team_fav_name, team_und_name = team_away, team_home
        ev_fav_raw, ev_und_raw = ev_away_raw, ev_home_raw
        water_fav, water_und = hdp_away_water, hdp_home_water
        
        # HDBA คิดเป็นความเหนื่อยล้าของทีมเยือน (ที่เป็นทีมต่อ)
        ev_fav_adj = ev_fav_raw - (hdba_pct / 100)
        ev_und_adj = ev_und_raw # เจ้าบ้านไม่มี HDBA

    # --- ระยะที่ 2: T21CB Protocol ---
    is_t21cb = (t_ph > 0.50 and hdp_val >= 0.5 and ou_line <= 2.5)
    t21cb_text = "[TRUE]" if is_t21cb else "[FALSE]"

    # --- ระยะที่ 3: HTP Filter ---
    delta_htp = abs(ou_line - hdp_val)
    htp_matrix = "🟡 Warning Zone (โซนเฝ้าระวัง)" if delta_htp <= 1.5 else "🟢 Normal Zone"

    # --- เช็ค Margin of Safety (Minimum Edge 3%) ---
    MIN_EDGE = 0.03 
    is_fav_invest = ev_fav_adj >= MIN_EDGE
    is_und_invest = ev_und_adj >= MIN_EDGE
    is_any_invest = is_fav_invest or is_und_invest

    # สร้างคำตัดสิน
    fav_status = "🟢 (ผ่านเกณฑ์ลงทุน)" if is_fav_invest else ("🟡 (บวกบางเกินไป - ไม่คุ้มเสี่ยง)" if ev_fav_adj > 0 else "🔴 (Value Trap - ติดลบ)")
    und_status = "🟢 (ผ่านเกณฑ์ลงทุน)" if is_und_invest else ("🟡 (บวกบางเกินไป - ไม่คุ้มเสี่ยง)" if ev_und_adj > 0 else "🔴 (DEAD ZONE - ติดลบ)")

    report = f"""📊 รายงานผลการวิเคราะห์ (GEM System 5.5.2 - Auto Switch Logic)
คู่แข่งขัน: {match_name}

ระยะที่ 1: การสกัดราคาจริงด้วยอัลกอริทึม Power Margin (Devigging) 🚨
จากราคาพูล 1X2 (เหย้า {h1x2:.2f} / เสมอ {d1x2:.2f} / เยือน {a1x2:.2f}) เครื่องยนต์พบ Margin สำหรับแมตช์นี้ที่ {margin*100:.2f}%
ความน่าจะเป็นที่แท้จริง (True Market Probability):
โอกาส {team_home} ชนะ: {t_ph*100:.2f}%
โอกาส เสมอ: {t_pd*100:.2f}%
โอกาส {team_away} ชนะ: {t_pa*100:.2f}%
(กระดานนี้ {team_fav_name} เป็นทีมต่อ ด้วยโอกาสชนะ {max(t_ph, t_pa)*100:.2f}%)

ระยะที่ 2: โปรโตคอล T21CB (The 2-1 Curse Breaker) 🚨
Home Dominance Factor: โอกาสชนะของเจ้าบ้านเกิน 50% หรือไม่? ➡️ {t21cb_text} ({t_ph*100:.2f}%)
Handicap Pressure: เจ้าบ้านต่อแพงตั้งแต่ 0.5 หรือไม่? ➡️ {"[TRUE]" if (is_home_fav and hdp_val >= 0.5) else "[FALSE]"}
Under Trap Line: สกอร์รวมเปิดมากดดันที่ <= 2.5 หรือไม่? ➡️ {"[TRUE]" if ou_line <= 2.5 else "[FALSE]"}
ผลการทำงาน: ระบบ {"\"ถูกกระตุ้นการทำงาน 100%\"" if is_t21cb else "\"ไม่ถูกกระตุ้นการทำงาน\""}

ระยะที่ 3: โปรโตคอล HTP Filter (จับผิด Handicap-Total Paradox) ⚡
|AH|line = {hdp_val}
O/U line = {ou_line}
ΔHTP = {ou_line} - {hdp_val} = {delta_htp:.2f}
ผลลัพธ์ HTP Matrix: ตกอยู่ใน {htp_matrix}

ระยะที่ 4: การคำนวณ Expected Value (AH Value Analysis) 🛡️
คำนวณ EV หักลบค่าต๋ง {margin*100:.2f}% (ต้องการ Margin of Safety > 3%):

{team_fav_name} (ต่อ {hdp_val}) ค่าน้ำ {water_fav}:
{"หักลบค่าเสียเปรียบของทีมเยือน (HDBA) ที่ "+str(hdba_pct)+"%" if not is_home_fav else ""}
EV_adj ≈ {ev_fav_adj*100:.2f}%
{fav_status}

{team_und_name} (รอง {hdp_val}) ค่าน้ำ {water_und}:
{"หักลบค่าเสียเปรียบของทีมเยือน (HDBA) ที่ "+str(hdba_pct)+"%" if is_home_fav else ""}
EV_adj ≈ {ev_und_adj*100:.2f}% 
{und_status}

💡 บทสรุปและสัญญาณการลงทุน (GEM Signal 5.5.2)
🔥 สัญญาณลงทุนหลัก: {"🔥 INVEST (พบช่องโหว่ทำกำไร)" if is_any_invest else "🚫 NO BET (กักกันเงินทุน - เสี่ยงเกินไป)"}
ฝั่งต่อ ({team_fav_name}): {"ผ่านเกณฑ์ EV > 3% น่าลงทุน" if is_fav_invest else "ไม่ผ่านเกณฑ์การลงทุน"}
ฝั่งรอง ({team_und_name}): {"ผ่านเกณฑ์ EV > 3% น่าลงทุน" if is_und_invest else "ไม่ผ่านเกณฑ์การลงทุน"}

🚨 สถานะเดินเงิน: {"Standard Kelly" if is_any_invest else "เซฟเงินต้น 100% (Hold your bankroll)"}
"""
    return report

# ==========================================
# 2. ส่วนของหน้าจอโปรแกรม (UI Layout)
# ==========================================
st.set_page_config(page_title="GEM System 5.5.2", layout="wide")
st.title("⚽ GEM System 5.5.2 - Automated Quant Terminal")
st.markdown("ระบบคำนวณสถิติฟุตบอลส่วนตัว (Patch: Auto-Detect Favorite/Underdog)")

match_name_input = st.text_input("📝 ชื่อคู่การแข่งขัน (รูปแบบ: เหย้า VS เยือน)", "โตเกียวเวอร์ดี้ VS คาชิม่า แอนท์เลอร์ส")

col1, col2, col3 = st.columns(3)
with col1:
    st.subheader("1. ราคาพูล 1X2")
    h_odds = st.number_input("เหย้า (Home)", min_value=1.01, value=3.75, format="%.2f")
    d_odds = st.number_input("เสมอ (Draw)", min_value=1.01, value=3.03, format="%.2f")
    a_odds = st.number_input("เยือน (Away)", min_value=1.01, value=1.97, format="%.2f")

with col2:
    st.subheader("2. ตลาดแฮนดิแคป (AH)")
    hdp_line = st.number_input("เรตต่อรอง (HDP ใส่เป็นค่าบวกได้เลย)", value=0.50, step=0.25, format="%.2f")
    hdp_home = st.number_input("น้ำฝั่งเจ้าบ้าน", value=0.93, format="%.2f")
    hdp_away = st.number_input("น้ำฝั่งทีมเยือน", value=0.97, format="%.2f")

with col3:
    st.subheader("3. ตลาดสกอร์รวม (O/U)")
    ou_line = st.number_input("เรตสกอร์รวม (O/U)", value=2.00, step=0.25, format="%.2f")
    ou_over = st.number_input("น้ำหน้าสูง (Over)", value=0.81, format="%.2f")
    ou_under = st.number_input("น้ำหน้าต่ำ (Under)", value=1.06, format="%.2f")

st.markdown("---")
st.markdown("Remark HDBA")
st.markdown("-หากเป็นลีกมาตรฐานยุโรป (พรีเมียร์ลีก, ลาลีกา) การเดินทางสะดวก ให้ใส่ HDBA = 1.5 (Base 1.0 + กองเชียร์ 0.5)")
st.markdown("-หากเป็นบอลถ้วยละตินอเมริกาที่ต้องบินข้ามประเทศ ให้ยืนพื้น HDBA = 2.5 ถึง 3.0 ไว้ก่อนเลย")
st.markdown("-หากไปเยือน โบลิเวีย หรือ เอกวาดอร์ (ที่ราบสูง) ให้กด HDBA = 4.5 หรือ 5.0 ได้เลยครับ")
hdba_val = st.slider("⚖️ HDBA Penalty (ค่าประเมินความเสียเปรียบของทีมเยือน %)", min_value=0.0, max_value=10.0, value=1.5, step=0.1)

if st.button("🚀 ประมวลผลและสร้างรายงาน (Generate Report)", type="primary"):
    final_report = generate_gem_report(
        match_name_input, h_odds, d_odds, a_odds, 
        hdp_line, hdp_home, hdp_away, 
        ou_line, ou_over, ou_under, hdba_val
    )
    st.success("✅ อัปเดตระบบ 5.5.2 แก้บั๊กสลับฝั่งเรียบร้อย! สามารถก็อปปี้รายงานด้านล่างได้เลยครับ")
    st.code(final_report, language="text")
