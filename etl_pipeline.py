import os
import requests
import re
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

# ==========================================
# 1. 🔑 ตั้งค่ากุญแจเชื่อมต่อ (CONFIGURATION)
# ==========================================
# แนะนำ: ถ้าเทสในคอมตัวเอง ให้เอาคีย์มาวางทับในเครื่องหมายคำพูดได้เลย 
# แต่ถ้ารันบน GitHub Actions ให้ใช้ os.environ.get() ดึงค่าจาก Secrets ครับ
SUPABASE_URL = os.environ.get("SUPABASE_URL", "ใส่_URL_SUPABASE_ของคุณที่นี่")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "ใส่_KEY_SUPABASE_ของคุณที่นี่")
RAPID_API_KEY = os.environ.get("RAPID_API_KEY", "ใส่_API_KEY_ของ_RAPIDAPI_ที่นี่")

# สร้างการเชื่อมต่อกับฐานข้อมูล
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 🛠️ HELPER: ตัวแปลงค่าน้ำเอเชีย
# ==========================================
def parse_line(s):
    s = str(s).replace(' ', '').replace('+', '').replace('Over', '').replace('Under', '')
    neg = '-' in s
    s = s.replace('-', '')
    try:
        if '/' in s or ',' in s:
            sep = '/' if '/' in s else ','
            return (-1 if neg else 1) * ((float(s.split(sep)[0]) + float(s.split(sep)[1])) / 2)
        return float(s) * (-1 if neg else 1)
    except:
        return 0.0

# ==========================================
# 2. 📡 EXTRACT & TRANSFORM (ดึงและแปลงข้อมูล)
# ==========================================
def fetch_today_odds():
    tz_th = timezone(timedelta(hours=7))
    today_str = datetime.now(tz_th).strftime("%Y-%m-%d")
    
    print(f"📡 [EXTRACT] กำลังสแกนราคาฟุตบอลของวันที่ {today_str} จาก API-Football...")
    
    url = "https://api-football-v1.p.rapidapi.com/v3/odds"
    headers = {
        "X-RapidAPI-Key": RAPID_API_KEY,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
    }
    # ดึงเฉพาะราคาจากบ่อน Bet365 (bookmaker=8)
    querystring = {"date": today_str, "bookmaker": "8", "timezone": "Asia/Bangkok"}
    
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=20)
        if response.status_code != 200:
            print(f"❌ API Error: โดนบล็อกหรือคีย์ผิด (Status {response.status_code})")
            return [], today_str
            
        data = response.json()
        matches_to_load = []
        
        print(f"⚙️ [TRANSFORM] พบข้อมูล {len(data.get('response', []))} คู่ กำลังแปลงโครงสร้าง...")
        
        for match in data.get('response', []):
            fixture_id = match['fixture']['id']
            home_team = match['fixture']['teams']['home']['name']
            away_team = match['fixture']['teams']['away']['name']
            
            # โครงสร้างพื้นฐานที่จะโยนเข้า Supabase
            match_record = {
                "fixture_id": fixture_id,
                "match_date": today_str,
                "match_name": f"{home_team} VS {away_team}",
                "h1x2": 1.0, "d1x2": 1.0, "a1x2": 1.0,
                "hdp_line": 0.0, "hdp_h": 0.0, "hdp_a": 0.0,
                "ou_line": 2.5, "ou_over": 0.0, "ou_under": 0.0,
                "xg_home": 0.0, "xg_away": 0.0 # xG เซ็ตเป็น 0 ไว้ก่อน ค่อยอัปเดตตอน Live
            }
            
            # คุ้ยหาราคาใน JSON
            bets = match['bookmakers'][0]['bets']
            for bet in bets:
                try:
                    if bet['name'] == "Match Winner":
                        for val in bet['values']:
                            if val['value'] == 'Home': match_record['h1x2'] = float(val['odd'])
                            elif val['value'] == 'Draw': match_record['d1x2'] = float(val['odd'])
                            elif val['value'] == 'Away': match_record['a1x2'] = float(val['odd'])
                            
                    elif bet['name'] == "Asian Handicap":
                        match_record['hdp_line'] = parse_line(bet['values'][0]['value'])
                        match_record['hdp_h'] = float(bet['values'][0]['odd'])
                        match_record['hdp_a'] = float(bet['values'][1]['odd'])
                        
                    elif bet['name'] == "Goals Over/Under":
                        match_record['ou_line'] = parse_line(bet['values'][0]['value'])
                        match_record['ou_over'] = float(bet['values'][0]['odd'])
                        match_record['ou_under'] = float(bet['values'][1]['odd'])
                except (IndexError, KeyError, ValueError):
                    continue # ข้ามราคาที่พังหรือดึงไม่ได้
                    
            matches_to_load.append(match_record)
            
        return matches_to_load, today_str
        
    except Exception as e:
        print(f"❌ [ERROR] ระบบขัดข้องระหว่างดึง API: {e}")
        return [], today_str

# ==========================================
# 3. 💾 LOAD (โหลดเข้า Supabase)
# ==========================================
def load_to_database(matches, today_str):
    if not matches:
        print("⚠️ ยกเลิกการบันทึก: ไม่มีข้อมูลค่าน้ำ")
        return
        
    # ล้างข้อมูลของวันนี้ที่อาจเคยดึงไปแล้ว (เพื่อไม่ให้เบิ้ล) หรือล้างข้อมูลเก่า
    print("🧹 [CLEANUP] กำลังล้างข้อมูลเก่าออกจากคลังแสง...")
    try:
        supabase.table("daily_matches").delete().neq("match_date", today_str).execute()
        # ถ้าต้องการให้ดึงทับคู่เดิมของวันนี้ด้วยเวลาเซ็ตราคาใหม่ ให้ใช้ upsert ในคำสั่งถัดไป
    except Exception as e:
        print(f"⚠️ Warning: ล้างข้อมูลเก่าไม่สำเร็จ ({e})")

    print(f"💾 [LOAD] กำลังยิงข้อมูล {len(matches)} คู่ เข้าสู่ Supabase...")
    try:
        # ใช้ upsert เพื่อกัน error กรณี fixture_id ซ้ำ มันจะอัปเดตราคาให้ใหม่แทน
        response = supabase.table("daily_matches").upsert(matches).execute()
        print("✅ [SUCCESS] ภารกิจ ETL เสร็จสมบูรณ์! ข้อมูลพร้อมใช้งานใน GEM System")
    except Exception as e:
        print(f"❌ [ERROR] บันทึกข้อมูลลงฐานข้อมูลล้มเหลว: {e}")

# ==========================================
# 🚀 สั่งรันโปรแกรม
# ==========================================
if __name__ == "__main__":
    print("=========================================")
    print("  🚀 STARTING GEM SYSTEM ETL PIPELINE")
    print("=========================================")
    
    matches_data, date_str = fetch_today_odds()
    load_to_database(matches_data, date_str)
