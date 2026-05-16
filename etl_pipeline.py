import os
import requests

# 💡 กรุณาใส่ API Key ที่คัดลอกจากหน้า Dashboard ของเว็บหลักมาวางตรงนี้เลยครับ
API_KEY = "bebb0ec6f1decaa007954e2b5c67fb5c"

# ยิงเข้าโดเมนหลักสายตรงที่คุณระบุมา
url = "https://v3.football.api-sports.io/status"
headers = {
    "x-apisports-key": API_KEY,
    "x-apisports-host": "v3.football.api-sports.io"
}

print("=========================================")
print(" 📡 OFFICIAL DOMAIN PING & ACCESS CHECK")
print("=========================================")

try:
    response = requests.get(url, headers=headers, timeout=10)
    print(f"📡 Response Code จากเซิร์ฟเวอร์หลัก: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        errors = data.get('errors', [])
        
        if errors:
            print(f"❌ เซิร์ฟเวอร์ปฏิเสธการเข้าถึง: {errors}")
            print("💡 คำแนะนำ: ตรวจเช็คว่าก็อปปี้คีย์มาขาดหรือเกิน หรือสลับกับคีย์ของ RapidAPI หรือเปล่า")
        else:
            account_info = data.get('response', {}).get('subscription', {})
            requests_info = data.get('response', {}).get('requests', {})
            
            print("\n✅ [SUCCESS] ท่อข้อมูลหลักเชื่อมต่อสำเร็จ!")
            print(f"👤 แพ็กเกจที่เปิดใช้งาน: {account_info.get('plan')}")
            print(f"📊 สถิติจราจรคำขอวันนี้: ใช้ไปแล้ว {requests_info.get('current')} / {requests_info.get('limit_day')} ครั้ง")
            print("\n👉 ตอนนี้ให้ลองเปิดหน้าเว็บ dashboard.api-football.com ดูครับ ยอดต้องขยับแล้วแน่นอน!")
    else:
        print(f"❌ โดนระบบเครือข่ายบล็อกกลางทาง (Status: {response.status_code})")
except Exception as e:
    print(f"❌ พังระเบิดก่อนหลุดออกจากเครื่อง: {e}")
