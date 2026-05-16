import os
import requests
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

# ==========================================
# 1. 🔑 CONFIGURATION
# ==========================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://xbzhxrbmvzfsgzyjfgfx.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_i8bVKar9GNf0qZ4ebqYMNg_RWgqKjq2")
FOOTBALL_DATA_API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY", "11d8346e31644fb1ae18f39ae3851d53")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}

# ==========================================
# 📊 OFFLINE RATING MATRIX (ลดการยิง API ซ้ำซ้อน ป้องกัน Delay)
# ==========================================
# สถิติความแข็งแกร่งเฉลี่ยประตูลูกรุก-ลูกรับ (ดึงจากฐานตารางคะแนนปัจจุบัน)
LEAGUE_MODEL_STATS = {
    "Arsenal": {"avg_gf": 2.10, "avg_ga": 0.85},
    "Aston Villa": {"avg_gf": 1.70, "avg_ga": 1.35},
    "Chelsea": {"avg_gf": 1.85, "avg_ga": 1.45},
    "Liverpool": {"avg_gf": 2.25, "avg_ga": 1.05},
    "Manchester City": {"avg_gf": 2.45, "avg_ga": 1.00},
    "Manchester United": {"avg_gf": 1.55, "avg_ga": 1.40},
    "Newcastle": {"avg_gf": 2.00, "avg_ga": 1.50},
    "Tottenham": {"avg_gf": 1.95, "avg_ga": 1.55},
    "league_avg": 1.45
}

# ==========================================
# 2. 📡 FAST DATA PIPELINE (ยิงหมัดเดียวจบ)
# ==========================================
def fetch_football_data_pipeline():
    tz_th = timezone(timedelta(hours=7))
    
    # 💡 จุดทดสอบ: หากต้องการเทสย้อนหลังให้เปิดใช้วันที่ฟิกซ์, หากรันจริงให้ใช้วันปัจจุบัน
    today_str = "2026-05-10" 
    # today_str = datetime.now(tz_th).strftime("%Y-%m-%d")
    
    print(f"=========================================")
    print(f"📡 FAST SNIPER PIPELINE RUNNING: {today_str}")
    print(f"=========================================")
    
    league_code = "PL"
    
    # 🔥 ล็อคเป้าเจาะตรงรายลีคชั้นในทันที ไม่แวะดึงสถิติตารางคะแนน เพื่อตัด Delay ออกไปทั้งหมด
    url = f"https://api.football-data.org/v4/competitions/{league_code}/matches"
    querystring = {"dateFrom": today_str, "dateTo": today_str}
    
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=8)
        if response.status_code != 200:
            print(f"❌ API พังหรือโควต้าเต็ม (Status Code: {response.status_code})")
            return []
            
        data = response.json()
        matches = data.get('matches', [])
        print(f"✅ ดึงเสร็จสิ้นในเสี้ยววินาที! พบโปรแกรมแข่งขันทั้งหมด {len(matches)} คู่")
        
        records_to_load = []
        
        for m in matches:
            fixture_id = m['id']
            home_team = m['homeTeam']['name']
            away_team = m['awayTeam']['name']
            
            # ตัดคำว่า "FC" หรือขยะชื่อทีมออกเพื่อให้แมตช์เข้าคู่กับ Rating Matrix ง่ายขึ้น
            h_clean = home_team.replace(" FC", "").strip()
            a_clean = away_team.replace(" FC", "").strip()
            
            # ค่าเริ่มต้นมาตรฐานกรณีเจอทีมเล็กนอกเหนือเมทริกซ์
            xg_home, xg_away = 1.45, 1.20
            
            # ⚙️ คำนวณสมการ Poisson จำลองคณิตศาสตร์ทันทีหลังหลุดจากสายส่ง
            if h_clean in LEAGUE_MODEL_STATS and a_clean in LEAGUE_MODEL_STATS:
                l_avg = LEAGUE_MODEL_STATS["league_avg"]
                h_attack = LEAGUE_MODEL_STATS[h_clean]['avg_gf'] / l_avg
                a_defense = LEAGUE_MODEL_STATS[a_clean]['avg_ga'] / l_avg
                xg_home = h_attack * a_defense * l_avg
                
                a_attack = LEAGUE_MODEL_STATS[a_clean]['avg_gf'] / l_avg
                h_defense = LEAGUE_MODEL_STATS[h_clean]['avg_ga'] / l_avg
                xg_away = a_attack * h_defense * l_avg
                
            print(f"🚀 ล็อคเป้าหมาย: {h_clean} VS {a_clean} -> Simulated xG [{xg_home:.2f} - {xg_away:.2f}]")
            
            records_to_load.append({
                "fixture_id": fixture_id,
                "match_date": today_str,
                "match_name": f"{h_clean} VS {a_clean}",
                "xg_home": round(xg_home, 2),
                "xg_away": round(xg_away, 2),
                "h1x2": 1.0, "d1x2": 1.0, "a1x2": 1.0,
                "hdp_line": 0.0, "hdp_h": 0.0, "hdp_a": 0.0,
                "ou_line": 2.5, "ou_over": 0.0, "ou_under": 0.0
            })
            
        return records_to_load
    except Exception as e:
        print(f"❌ เน็ตเวิร์กขัดข้องชั่วคราว: {e}")
        return []

# ==========================================
# 3. 💾 LOAD
# ==========================================
def load_to_database(matches):
    if not matches: return
    try:
        supabase.table("daily_matches").delete().neq("match_date", "1970-01-01").execute()
        supabase.table("daily_matches").insert(matches).execute()
        print("✅ [SUCCESS] อัปเดตฐานข้อมูลด้วยระบบ Fast Pipeline สำเร็จ!")
    except Exception as e:
        print(f"❌ โหลดลง Supabase ผิดพลาด: {e}")

if __name__ == "__main__":
    records = fetch_football_data_pipeline()
    load_to_database(records)
