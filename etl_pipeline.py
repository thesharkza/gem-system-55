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
API_SPORTS_KEY = os.environ.get("API_SPORTS_KEY", "bebb0ec6f1decaa007954e2b5c67fb5c")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

headers = {
    "x-apisports-key": API_SPORTS_KEY,
    "x-apisports-host": "v3.football.api-sports.io"
}

# ==========================================
# 🛠️ HELPER: เจาะลึกสถิติ xG รายทีมจาก API
# ==========================================
def get_team_xg_average(league_id, season, team_id):
    url = "https://v3.football.api-sports.io/teams/statistics"
    querystring = {"league": str(league_id), "season": str(season), "team": str(team_id)}
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=10)
        if response.status_code == 200:
            data = response.json()
            res_data = data.get('response', {})
            # ขุดดึงค่า xG เฉลี่ยต่อนัดจาก JSON โครงสร้างหลัก
            xg_for_avg = res_data.get('goals', {}).get('for', {}).get('expected', {}).get('average', 0.0)
            return float(xg_for_avg) if xg_for_avg else 0.0
    except Exception as e:
        print(f"⚠️ ดึง xG ทีม {team_id} พลาด: {e}")
    return 0.0

# ==========================================
# 2. 📡 EXTRACT & TRANSFORM (ดึงโปรแกรม + ค้นสถิติทัพทีม)
# ==========================================
def fetch_daily_fixtures_and_team_stats():
    tz_th = timezone(timedelta(hours=7))
    today_str = datetime.now(tz_th).strftime("%Y-%m-%d")
    
    print(f"📅 กำลังสแกนตารางแข่งขันประจำวันที่ {today_str}...")
    url = "https://v3.football.api-sports.io/fixtures"
    querystring = {"date": today_str, "timezone": "Asia/Bangkok"}
    
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=15)
        if response.status_code != 200:
            print("❌ ไม่สามารถเชื่อมต่อ API ได้")
            return [], today_str
            
        data = response.json()
        fixtures = data.get('response', [])
        print(f"✅ พบโปรแกรมแข่งขันวันนี้ทั้งหมด {len(fixtures)} คู่")
        
        matches_to_load = []
        
        # ล็อคเป้าเจาะสถิติรายคู่ (ดึงล่วงหน้าได้เลย ไม่ต้องรอให้บอลเตะสด!)
        for match in fixtures:
            fixture_id = match['fixture']['id']
            league_id = match['league']['id']
            season = match['league']['season']
            
            home_id = match['teams']['home']['id']
            home_name = match['teams']['home']['name']
            
            away_id = match['teams']['away']['id']
            away_name = match['teams']['away']['name']
            
            print(f"📡 กำลังวิเคราะห์พลังรุกขุมกำลัง: {home_name} VS {away_name}")
            
            # ยิงเจาะ Endpoint สถิติระดับสโมสร
            xg_home_season = get_team_xg_average(league_id, season, home_id)
            xg_away_season = get_team_xg_average(league_id, season, away_id)
            
            record = {
                "fixture_id": fixture_id,
                "match_date": today_str,
                "match_name": f"{home_name} VS {away_name}",
                "xg_home": xg_home_season, # ใส่ xG เฉลี่ยเกมรุกทีมเหย้า
                "xg_away": xg_away_season, # ใส่ xG เฉลี่ยเกมรุกทีมเยือน
                "h1x2": 1.0, "d1x2": 1.0, "a1x2": 1.0,
                "hdp_line": 0.0, "hdp_h": 0.0, "hdp_a": 0.0,
                "ou_line": 2.5, "ou_over": 0.0, "ou_under": 0.0
            }
            matches_to_load.append(record)
            
            # หน่วงเวลา 0.5 วินาทีเพื่อป้องกันโดนเซิร์ฟเวอร์ปฏิเสธการรัวคำสั่ง
            time.sleep(0.5)
            
        return matches_to_load, today_str
    except Exception as e:
        print(f"❌ ระบบประมวลผลล้มเหลว: {e}")
        return [], today_str

# ==========================================
# 3. 💾 LOAD (โหลดเข้า Supabase)
# ==========================================
def load_to_supabase(matches, today_str):
    if not matches:
        print("⚠️ ไม่มีข้อมูลสถิติมหาภาคให้จัดเก็บ")
        return
        
    print(f"🧹 ล้างข้อมูลเก่าของตารางออก...")
    try:
        supabase.table("daily_matches").delete().neq("match_date", "1970-01-01").execute()
    except: pass

    print(f"💾 กำลังอัดฉีดข้อมูลสถิติมหาภาค {len(matches)} คู่ ลงคลาวด์ Supabase...")
    try:
        supabase.table("daily_matches").insert(matches).execute()
        print("✅ [SUCCESS] อัปเดตโครงข่ายข้อมูลสถิติรายทีมเสร็จสมบูรณ์!")
    except Exception as e:
        print(f"❌ โหลดข้อมูลลง Supabase พลาด: {e}")

if __name__ == "__main__":
    print("=========================================")
    print(" 🚀 TEAM STATISTICS DATA PIPELINE RUNNING")
    print("=========================================")
    data_records, current_date = fetch_daily_fixtures_and_team_stats()
    load_to_supabase(data_records, current_date)
