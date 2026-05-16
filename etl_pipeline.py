import os
import requests
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

# ==========================================
# 1. 🔑 ตั้งค่ากุญแจเชื่อมต่อ (CONFIGURATION)
# ==========================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://xbzhxrbmvzfsgzyjfgfx.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_i8bVKar9GNf0qZ4ebqYMNg_RWgqKjq2")

# 🚨 วาง API Token ที่ได้จากอีเมลของ Football-Data.org ตรงนี้เลยครับ
FOOTBALL_DATA_API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY", "11d8346e31644fb1ae18f39ae3851d53")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

headers = {
    "X-Auth-Token": FOOTBALL_DATA_API_KEY
}

# ==========================================
# 📊 HELPER: คำนวณสถิติรุก-รับจำลองจากตารางคะแนน (Poisson Base)
# ==========================================
def get_league_model_stats(league_code="PL"):
    """ ดึงตารางคะแนนมาทำแบบจำลองความแข็งแกร่งรุก/รับเพื่อจำลองเป็นค่า xG """
    url = f"https://api.football-data.org/v4/competitions/{league_code}/standings"
    try:
        res = requests.get(url, headers=headers, timeout=12)
        if res.status_code != 200: return {}
        
        data = res.json()
        standings = data.get('standings', [])[0].get('table', [])
        
        # รวบรวมข้อมูลสถิติมหาภาคของลีค
        team_stats = {}
        total_goals = 0
        total_matches = 0
        
        for row in standings:
            team_name = row['team']['name']
            played = row['playedGames']
            gf = row['goalsFor']
            ga = row['goalsAgainst']
            
            if played > 0:
                team_stats[team_name] = {
                    "avg_gf": gf / played,
                    "avg_ga": ga / played
                }
                total_goals += gf
                total_matches += played
                
        # หาค่าเฉลี่ยกลางประจำลีก (League Average)
        league_avg_goals = (total_goals / total_matches) if total_matches > 0 else 1.3
        
        return {
            "teams": team_stats,
            "league_avg": league_avg_goals
        }
    except:
        return {}

# ==========================================
# 2. 📡 EXTRACT & TRANSFORM (ดึงโปรแกรมเตะและประมวลผล xG)
# ==========================================
def fetch_football_data_pipeline():
    tz_th = timezone(timedelta(hours=7))
    today_str = datetime.now(tz_th).strftime("%Y-%m-%d")
    
    print(f"=========================================")
    print(f"📅 เริ่มสแกนค่ายใหม่ Football-Data.org: {today_str}")
    print(f"=========================================")
    
    # 💡 เราจะเจาะพรีเมียร์ลีก (PL) เป็นหลัก หากต้องการเพิ่มลีคอื่นสามารถวนลูปเพิ่มลีคโค้ดได้ครับ (เช่น PD = ลาลีกา, BL1 = บุนเดสลีกา)
    league_code = "PL"
    
    # ดึงสถิติตารางคะแนนมารอทำสมาร์ทโมเดล
    print("📊 กำลังวิเคราะห์พลังโครงสร้างตารางคะแนนลีก...")
    model_stats = get_league_model_stats(league_code)
    
    # ดึงโปรแกรมเตะของวันนี้
    url = f"https://api.football-data.org/v4/competitions/{league_code}/matches"
    querystring = {"dateFrom": today_str, "dateTo": today_str}
    
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=12)
        if response.status_code != 200:
            print(f"❌ ดึงข้อมูลล้มเหลว คีย์อาจผิดพลาด (Status {response.status_code})")
            return []
            
        data = response.json()
        matches = data.get('matches', [])
        print(f"✅ พบโปรแกรมเตะวันนี้ทั้งหมด {len(matches)} คู่ ในลีก {league_code}")
        
        records_to_load = []
        
        for m in matches:
            fixture_id = m['id']
            home_team = m['homeTeam']['name']
            away_team = m['awayTeam']['name']
            
            # ตรรกะ Quant: คำนวณ xG จำลองตามฟอร์มการทำประตูจริงในตารางคะแนน
            xg_home = 1.50  # ค่าตั้งต้นมาตรฐาน
            xg_away = 1.20
            
            if model_stats and home_team in model_stats['teams'] and away_team in model_stats['teams']:
                # ⚙️ คำนวณแบบจำลองคณิตศาสตร์ Poisson (พลังรุกทีมเหย้า x พลังรับทีมเยือน x ค่าเฉลี่ยลีค)
                h_attack = model_stats['teams'][home_team]['avg_gf'] / model_stats['league_avg']
                a_defense = model_stats['teams'][away_team]['avg_ga'] / model_stats['league_avg']
                xg_home = h_attack * a_defense * model_stats['league_avg']
                
                # พลังรุกทีมเยือน x พลังรับทีมเหย้า x ค่าเฉลี่ยลีค
                a_attack = model_stats['teams'][away_team]['avg_gf'] / model_stats['league_avg']
                h_defense = model_stats['teams'][home_team]['avg_ga'] / model_stats['league_avg']
                xg_away = a_attack * h_defense * model_stats['league_avg']
            
            print(f"🚀 แมตช์: {home_team} VS {away_team} -> Simulated xG [{xg_home:.2f} - {xg_away:.2f}]")
            
            record = {
                "fixture_id": fixture_id,
                "match_date": today_str,
                "match_name": f"{home_team} VS {away_team}",
                "xg_home": round(xg_home, 2),
                "xg_away": round(xg_away, 2),
                "h1x2": 1.0, "d1x2": 1.0, "a1x2": 1.0,
                "hdp_line": 0.0, "hdp_h": 0.0, "hdp_a": 0.0,
                "ou_line": 2.5, "ou_over": 0.0, "ou_under": 0.0
            }
            records_to_load.append(record)
            
        return records_to_load
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในระบบ: {e}")
        return []

# ==========================================
# 3. 💾 LOAD (อัปเดตข้อมูลเข้าคลังแสง Supabase)
# ==========================================
def load_to_database(matches):
    if not matches:
        print("⚠️ ยกเลิกการจัดเก็บ: ไม่มีคู่แข่งขันที่บันทึกข้อมูลในวันนี้")
        return
        
    print("🧹 ล้างคลังข้อมูลเก่าออกชั่วคราว...")
    try:
        supabase.table("daily_matches").delete().neq("match_date", "1970-01-01").execute()
    except: pass

    print(f"💾 กำลังยิงข้อมูล {len(matches)} คู่ เข้าสู่ Supabase...")
    try:
        supabase.table("daily_matches").insert(matches).execute()
        print("✅ [SUCCESS] ย้ายฐานค่ายใหม่เสร็จสิ้น! ข้อมูลพร้อมใช้งานใน GEM System 55")
    except Exception as e:
        print(f"❌ โหลดลงฐานข้อมูลล้มเหลว: {e}")

if __name__ == "__main__":
    records = fetch_football_data_pipeline()
    load_to_database(records)
