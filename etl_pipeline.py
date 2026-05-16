import os
import requests
import time
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

# ==========================================
# 1. 🔑 ตั้งค่ากุญแจเชื่อมต่อ (CONFIGURATION)
# ==========================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://xbzhxrbmvzfsgzyjfgfx.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_i8bVKar9GNf0qZ4ebqYMNg_RWgqKjq2")

# 🚨 ใส่ API KEY ของ www.api-football.com (API-SPORTS)
API_SPORTS_KEY = os.environ.get("API_SPORTS_KEY", "bebb0ec6f1decaa007954e2b5c67fb5c")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

headers = {
    "x-apisports-key": API_SPORTS_KEY,
    "x-apisports-host": "v3.football.api-sports.io"
}

# ==========================================
# 2. 📡 สเต็ป 1: ดึงโปรแกรมเตะของวันนี้
# ==========================================
def get_today_fixtures():
    tz_th = timezone(timedelta(hours=7))
    # today_str = datetime.now(tz_th).strftime("%Y-%m-%d")   <-- ใส่ # ปิดบรรทัดนี้ไว้ก่อน
    today_str = "2026-05-10"                                 <-- เพิ่มบรรทัดนี้ลงไปแทน
    
    print(f"📅 กำลังเช็คตารางแข่งขันของวันที่ {today_str}...")
    url = "https://v3.football.api-sports.io/fixtures"
    querystring = {"date": today_str, "timezone": "Asia/Bangkok"}
    
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=15)
        if response.status_code != 200:
            print(f"❌ โดนบล็อกหรือคีย์ผิด (Status {response.status_code})")
            return [], today_str
            
        data = response.json()
        matches = data.get('response', [])
        print(f"✅ พบโปรแกรมเตะวันนี้ทั้งหมด {len(matches)} คู่")
        return matches, today_str
    except Exception as e:
        print(f"❌ Error: {e}")
        return [], today_str

# ==========================================
# 3. 🎯 สเต็ป 2: เจาะลึกสถิติเฉพาะคู่ที่กำลังเตะ/เตะจบแล้ว
# ==========================================
def fetch_statistics_for_active_matches(matches, today_str):
    matches_to_update = []
    
    # สถานะที่บอลเริ่มเตะไปแล้ว (1H, 2H, HT, FT, AET, PEN ฯลฯ)
    active_statuses = ['1H', '2H', 'HT', 'FT', 'AET', 'PEN']
    
    # คัดกรองคู่ที่กำลังเตะหรือจบแล้ว เพื่อประหยัด API Quota
    target_matches = [m for m in matches if m['fixture']['status']['short'] in active_statuses]
    
    print(f"🎯 คัดกรองพบแมตช์ที่กำลังเตะหรือจบแล้ว {len(target_matches)} คู่ (เพื่อดึงสถิติ)")
    
    for match in target_matches:
        fixture_id = match['fixture']['id']
        home_team = match['teams']['home']['name']
        away_team = match['teams']['away']['name']
        
        print(f"📡 ดึงสถิติ: {home_team} VS {away_team} (ID: {fixture_id})")
        
        # ยิง API ขอสถิติของคู่นี้
        stats_url = "https://v3.football.api-sports.io/fixtures/statistics"
        stats_query = {"fixture": str(fixture_id)}
        
        try:
            res = requests.get(stats_url, headers=headers, params=stats_query, timeout=10)
            stats_data = res.json()
            
            # โครงสร้างเตรียมบันทึกลง Supabase
            record = {
                "fixture_id": fixture_id,
                "match_date": today_str,
                "match_name": f"{home_team} VS {away_team}",
                "xg_home": 0.0,
                "xg_away": 0.0
            }
            
            # ถ้ามีข้อมูลสถิติส่งกลับมา
            if stats_data.get('response') and len(stats_data['response']) >= 2:
                # สถิติทีมเหย้า
                for stat in stats_data['response'][0]['statistics']:
                    if stat['type'] == 'Expected Goals' and stat['value'] is not None:
                        record['xg_home'] = float(stat['value'])
                # สถิติทีมเยือน
                for stat in stats_data['response'][1]['statistics']:
                    if stat['type'] == 'Expected Goals' and stat['value'] is not None:
                        record['xg_away'] = float(stat['value'])
            
            matches_to_update.append(record)
            
            # ⚠️ สำคัญ: หน่วงเวลา 1 วินาที เพื่อไม่ให้เซิร์ฟเวอร์แบนเราจากการยิง API รัวเกินไป
            time.sleep(1)
            
        except Exception as e:
            print(f"⚠️ ดึงสถิติ ID {fixture_id} พลาด: {e}")
            continue
            
    return matches_to_update

# ==========================================
# 4. 💾 LOAD (อัปเดตลง Supabase)
# ==========================================
def load_stats_to_supabase(matches):
    if not matches:
        print("⚠️ ไม่มีสถิติให้บันทึก (บอลอาจจะยังไม่เริ่มเตะเลยสักคู่)")
        return
        
    print(f"💾 กำลังบันทึกสถิติ {len(matches)} คู่ ลงฐานข้อมูล Supabase...")
    try:
        # ใช้ upsert เพื่ออัปเดตทับข้อมูลเดิม ถ้า fixture_id ตรงกัน
        supabase.table("daily_matches").upsert(matches).execute()
        print("✅ [SUCCESS] อัปเดตข้อมูลสถิติ (xG) เสร็จสมบูรณ์!")
    except Exception as e:
        print(f"❌ [ERROR] บันทึกลง Supabase ล้มเหลว: {e}")

# ==========================================
# 🚀 จุดสั่งรันสคริปต์
# ==========================================
if __name__ == "__main__":
    print("=========================================")
    print("  🚀 STARTING STATS ONLY - ETL PIPELINE")
    print("=========================================")
    
    # 1. ดึงโปรแกรมเตะวันนี้ทั้งหมด
    all_fixtures, current_date = get_today_fixtures()
    
    if all_fixtures:
        # 2. คัดเฉพาะคู่ที่เตะแล้วไปดึงสถิติ
        stats_records = fetch_statistics_for_active_matches(all_fixtures, current_date)
        
        # 3. บันทึกลงฐานข้อมูล
        load_stats_to_supabase(stats_records)
