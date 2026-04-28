import streamlit as st

# ==========================================
# 1. ฟังก์ชันสมองกล: คำนวณและสร้างเทมเพลตรายงาน
# ==========================================
def generate_gem_report(match_name, h1x2, d1x2, a1x2, hdp_line, hdp_home_water, hdp_away_water, ou_line, ou_over_water, ou_under_water, hdba_pct):
    # --- ระยะที่ 1: Devigging (1X2) ---
    i_h, i_d, i_a = 1/h1x2, 1/d1x2, 1/a1x2
    margin = (i_h + i_d + i_a) - 1
    t_ph = i_h / (1 + margin)
    t_pd = i_d / (1 + margin)
    t_pa = i_a / (1 + margin)

    # --- ระยะที่ 2: T21CB Protocol ---
    is_t21cb = (t_ph > 0.50 and hdp_line >= 0.5 and ou_line <= 2.5)
    t21cb_text = "[TRUE]" if is_t21cb else "[FALSE]"
    ev_under_penalty = 0.05 if is_t21cb else 0

    # --- ระยะที่ 3: HTP Filter ---
    delta_htp = ou_line - hdp_line
    htp_matrix = "🟡 Warning Zone (โซนเฝ้าระวัง)" if delta_htp <= 1.5 else "🟢 Normal Zone"

    # --- ระยะที่ 4: EV Calculation ---
    ev_away_raw = ((t_pa + t_pd) * hdp_away_water) - (t_ph * 1)
    ev_away_adj = ev_away_raw - (hdba_pct / 100)
    ev_home_raw = (t_ph * hdp_home_water) - ((t_pd + t_pa) * 1)

    # --- อัปเกรด: กำหนดจุดตัด Margin of Safety ที่ 3% (0.03) ---
    MIN_EDGE = 0.03 
    is_home_invest = ev_home_raw >= MIN_EDGE
    is_away_invest = ev_away_adj >= MIN_EDGE
    is_any_invest = is_home_invest or is_away_invest

    # หาสื่อความหมายของชื่อทีม
    teams = match_name.split('VS')
    team_home = teams[0].strip() if len(teams) > 1 else "เจ้าบ้าน"
    team_away = teams[1].strip() if len(teams) > 1 else "ทีมเยือน"

    # --- สร้างเงื่อนไขข้อความแบบไดนามิก ---
    home_status_text = "🟢 (Value Discovery - ผ่านเกณฑ์ลงทุน)" if is_home_invest else ("🟡 (บวกบางเกินไป Margin of Safety ต่ำ - ไม่คุ้มเสี่ยง)" if ev_home_raw > 0 else "🔴 (Value Trap - โดนหัก Margin จนติดลบ)")
    away_status_text = "🟢 (ทะลุเข้าสู่ PROFIT ZONE - ผ่านเกณฑ์ลงทุน)" if is_away_invest else ("🟡 (บวกบางเกินไป - ไม่คุ้มเสี่ยง)" if ev_away_adj > 0 else "🔴 (ร่วงลงสู่ DEAD ZONE - ไม่คุ้มเสี่ยง)")

    report = f"""📊 รายงานผลการวิเคราะห์ (GEM System 5.5 - The Variance Control)
คู่แข่งขัน: {match_name}

ระยะที่ 1: การสกัดราคาจริงด้วยอัลกอริทึม Power Margin (Devigging) 🚨
จากราคาพูล 1X2 (เหย้า {h1x2:.2f} / เสมอ {d1x2:.2f} / เยือน {a1x2:.2f}) เครื่องยนต์ทำการสแกนและพบกำแพงหัก Margin (ค่าต๋ง) สำหรับแมตช์นี้เอาไว้ที่ {margin*100:.2f}% {"ยังคงเกาะหนึบอยู่ในระดับ Predatory Market (ตลาดกินรวบ)" if margin > 0.09 else "อยู่ในระดับมาตรฐาน"}
เมื่อทำการรีดค่าต๋ง {margin*100:.2f}% ออกไป เราได้ความน่าจะเป็นที่แท้จริง (True Market Probability) ดังนี้:
โอกาส {team_home} ชนะ: {t_ph*100:.2f}%
โอกาส เสมอ: {t_pd*100:.2f}%
โอกาส {team_away} ชนะ: {t_pa*100:.2f}%

ระยะที่ 2: โปรโตคอล T21CB (The 2-1 Curse Breaker) 🚨
Home Dominance Factor: โอกาสชนะของเจ้าบ้านเกิน 50% หรือไม่? ➡️ {t21cb_text} ({t_ph*100:.2f}%)
Handicap Pressure: เจ้าบ้านต่อแพงตั้งแต่ 0.5 หรือไม่? ➡️ {"[TRUE]" if hdp_line >= 0.5 else "[FALSE]"} (ต่อ {hdp_line})
Under Trap Line: สกอร์รวมเปิดมากดดันที่ <= 2.5 หรือไม่? ➡️ {"[TRUE]" if ou_line <= 2.5 else "[FALSE]"} (เรตเปิดมาที่ {ou_line})
ผลการทำงาน: ระบบ {"\"ถูกกระตุ้นการทำงาน 100%\" (สกอร์ 2-1 จะทำลายบิลหน้าต่ำจนพังพินาศ)" if is_t21cb else "\"ไม่ถูกกระตุ้นการทำงาน\""}

ระยะที่ 3: โปรโตคอล HTP Filter (จับผิด Handicap-Total Paradox) ⚡
|AH|line = {hdp_line}
O/U line = {ou_line}
ΔHTP = {ou_line} - {hdp_line} = {delta_htp:.2f}
ผลลัพธ์ HTP Matrix: ตกอยู่ใน {htp_matrix}

ระยะที่ 4: การคำนวณ Expected Value (AH Value Analysis) 🛡️
เจาะตลาดแฮนดิแคปสู้กับกำแพงค่าต๋ง {margin*100:.2f}% ด้วยสมการ EV (ต้องการ Margin of Safety > 3%):

{team_home} ต่อ {hdp_line} (ค่าน้ำ {hdp_home_water}):
EV ≈ {ev_home_raw*100:.2f}%
{home_status_text}

{team_away} รอง {hdp_line} (ค่าน้ำ {hdp_away_water}):
หักลบค่าเสียเปรียบของทีมเยือน (HDBA) ที่ {hdba_pct:.2f}%
EV_adj ≈ {ev_away_adj*100:.2f}% 
{away_status_text}

💡 บทสรุปและสัญญาณการลงทุน (GEM Signal 5.5)
🔥 สัญญาณลงทุนหลัก: {"🔥 INVEST (พบช่องโหว่ทำกำไร)" if is_any_invest else "🚫 NO BET (กักกันเงินทุน - เสี่ยงเกินไป)"}
เครื่องยนต์ GEM System 5.5 สั่ง {"ลุย:" if is_any_invest else "Veto แบบ 100% ไร้ข้อกังขา:"}
ฝั่งต่อ ({team_home}): {"มีค่า EV ทะลุเกณฑ์ 3% น่าลงทุน" if is_home_invest else ("แม้ EV เป็นบวกแต่กำไรบางเกินไป สู้ค่าต๋งไม่ไหว" if ev_home_raw > 0 else "ค่าน้ำแย่จน EV ติดลบ")}
ฝั่งรอง ({team_away}): {"ค่า EV หัก HDBA แล้วยังเกิน 3% ทรงพลังมาก" if is_away_invest else ("น้ำล้นคือเหยื่อล่อ สู้แรงกดดันทีมเยือนไม่ไหว" if ev_away_adj > 0 else "ติดลบยับเยิน")}

🚨 สถานะเดินเงิน: {"Standard Kelly" if is_any_invest else "เซฟเงินต้น 100% (Hold your bankroll)"}
"""
    return report

# ==========================================
# 2. ส่วนของหน้าจอโปรแกรม (UI Layout)
# ==========================================
st.set_page_config(page_title="GEM System 5.5", layout="wide")
st.title("⚽ GEM System 5.5 - Automated Report Generator")
st.markdown("ระบบคำนวณและออกรายงานสถิติหน้ากระดานฟุตบอลส่วนตัว")

# Layout สำหรับกรอกข้อมูล
match_name_input = st.text_input("📝 ชื่อคู่การแข่งขัน (รูปแบบ: เหย้า VS เยือน)", "โอ.ฮิกกิ้นส์ VS บอสตัน ริเวอร์")

col1, col2, col3 = st.columns(3)
with col1:
    st.subheader("1. ราคาพูล 1X2")
    h_odds = st.number_input("เหย้า (Home)", min_value=1.01, value=1.62, format="%.2f")
    d_odds = st.number_input("เสมอ (Draw)", min_value=1.01, value=3.49, format="%.2f")
    a_odds = st.number_input("เยือน (Away)", min_value=1.01, value=5.00, format="%.2f")

with col2:
    st.subheader("2. ตลาดแฮนดิแคป (AH)")
    hdp_line = st.number_input("เรตต่อรอง (HDP)", value=0.75, step=0.25, format="%.2f")
    hdp_home = st.number_input("น้ำฝั่งต่อ (เหย้า)", value=0.82, format="%.2f")
    hdp_away = st.number_input("น้ำฝั่งรอง (เยือน)", value=1.08, format="%.2f")

with col3:
    st.subheader("3. ตลาดสกอร์รวม (O/U)")
    ou_line = st.number_input("เรตสกอร์รวม (O/U)", value=2.25, step=0.25, format="%.2f")
    ou_over = st.number_input("น้ำหน้าสูง (Over)", value=0.93, format="%.2f")
    ou_under = st.number_input("น้ำหน้าต่ำ (Under)", value=0.95, format="%.2f")

st.markdown("---")
st.markdown("Remark HDBA")
st.markdown("-หากเป็นลีกมาตรฐานยุโรป (พรีเมียร์ลีก, ลาลีกา) การเดินทางสะดวก ให้ใส่ HDBA = 1.5 (Base 1.0 + กองเชียร์ 0.5)")
st.markdown("-หากเป็นบอลถ้วยละตินอเมริกาที่ต้องบินข้ามประเทศ ให้ยืนพื้น HDBA = 2.5 ถึง 3.0 ไว้ก่อนเลย")
st.markdown("-หากไปเยือน โบลิเวีย หรือ เอกวาดอร์ (ที่ราบสูง) ให้กด HDBA = 4.5 หรือ 5.0 ได้เลยครับ")
hdba_val = st.slider("⚖️ HDBA Penalty (ค่าประเมินความเสียเปรียบของทีมเยือน %)", min_value=0.0, max_value=10.0, value=3.5, step=0.1)

# ปุ่มกดให้เริ่มทำงาน
if st.button("🚀 ประมวลผลและสร้างรายงาน (Generate Report)", type="primary"):
    
    # 1. ส่งตัวเลขไปให้สมองกลคำนวณ
    final_report = generate_gem_report(
        match_name_input, h_odds, d_odds, a_odds, 
        hdp_line, hdp_home, hdp_away, 
        ou_line, ou_over, ou_under, hdba_val
    )
    
    # 2. แสดงข้อความสำเร็จ
    st.success("✅ สร้างรายงานสำเร็จ! สามารถกดไอคอน Copy มุมขวาบนของกล่องข้อความด้านล่างได้เลย")
    
    # 3. แสดงรายงานในกล่องข้อความ (st.code จะสร้างปุ่ม Copy ให้อัตโนมัติ)
    st.code(final_report, language="text")
