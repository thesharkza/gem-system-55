import streamlit as st
import pandas as pd
import re
import math
import json
import time
from datetime import datetime, timezone, timedelta
import plotly.graph_objects as go
from PIL import Image
from supabase import create_client, Client

# ════════════════════════════════════════════════════════════════════════
# GEM 4.0 — "WIN RATE EDITION"
# ════════════════════════════════════════════════════════════════════════
# หลักการ 3 ข้อ (ห้ามขัด):
#   1. PROTECT BANKROLL FIRST  — fixed sizing, ไม่มี leverage
#   2. WIN RATE > EV           — primary signal คือ P(cover) ไม่ใช่ EV
#   3. LESS IS MORE            — skip มากกว่าลง, gate system เข้มงวด
#
# ตัดออกจาก v3.x: AI Oracle (Gemini), GEM Rules Knowledge base,
#                  Kelly dynamic multiplier, HDBA, Composite Score, xG
# เก็บไว้: Math Engine, Market Quality, Auto-Fit λ, Value Scanner,
#          Market Consistency Checker, Bug fixes (v3.3 AH lines, v3.4 HDBA dir N/A เพราะตัด HDBA)
# ════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="GEM 5.0 — Stat-vs-Market Edition",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ──────────────────────────────────────────────────────────────────────
# 🗄️ DATABASE CONNECTION (Supabase) — pattern verified จากระบบ v3.x เดิม
# ──────────────────────────────────────────────────────────────────────
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None

supabase: Client = init_connection()
DB_TABLE = "gem5_predictions"


def db_save_prediction(record: dict):
    """บันทึก prediction ใหม่ลง Supabase — คืน id ที่สร้าง หรือ None ถ้าพัง"""
    if not supabase:
        st.error("⚠️ ไม่สามารถเชื่อมต่อฐานข้อมูล Supabase ได้ — ตรวจ secrets (SUPABASE_URL, SUPABASE_KEY)")
        return None
    try:
        # ตัด key ภายใน (ขึ้นต้น _) และ field ที่ DB ไม่รู้จักออกก่อนส่ง
        payload = {k: v for k, v in record.items() if not k.startswith('_')}
        response = supabase.table(DB_TABLE).insert(payload).execute()
        if response.data:
            return response.data[0].get('id')
        return None
    except Exception as e:
        st.error(f"⚠️ บันทึกลงฐานข้อมูลไม่สำเร็จ: {e}")
        return None


def db_find_pending_by_match(match_name):
    """หา prediction ที่ match_name เดียวกันและยังไม่ได้กรอกผล (pending)
    คืน id ถ้าเจอ, None ถ้าไม่เจอ — ใช้สำหรับเซฟทับคู่ซ้ำ"""
    if not supabase or not match_name:
        return None
    try:
        resp = (supabase.table(DB_TABLE)
                .select("id, actual_result")
                .eq("match_name", match_name)
                .execute())
        if resp.data:
            # หาเฉพาะที่ยังไม่ settle (actual_result เป็น null)
            for row in resp.data:
                if row.get('actual_result') is None:
                    return row['id']
        return None
    except Exception:
        return None


def db_save_or_update_prediction(record: dict):
    """บันทึก prediction — ถ้ามีคู่เดียวกัน (match_name) ที่ยัง pending อยู่ ให้ทับอันเดิม
    คืน (id, was_updated: bool)"""
    if not supabase:
        st.error("⚠️ ไม่สามารถเชื่อมต่อฐานข้อมูล Supabase ได้")
        return None, False
    match_name = record.get('match_name')
    existing_id = db_find_pending_by_match(match_name)
    payload = {k: v for k, v in record.items() if not k.startswith('_')}
    try:
        if existing_id is not None:
            # ทับอันเดิม (update ทุก field การวิเคราะห์ใหม่)
            # reset field ผลให้สะอาด (เผื่อมี pnl/outcome ค้างจากการแก้ก่อนหน้า)
            payload.setdefault('pnl', None)
            payload.setdefault('bet_outcome', None)
            supabase.table(DB_TABLE).update(payload).eq("id", existing_id).execute()
            return existing_id, True
        else:
            resp = supabase.table(DB_TABLE).insert(payload).execute()
            if resp.data:
                return resp.data[0].get('id'), False
            return None, False
    except Exception as e:
        st.error(f"⚠️ บันทึกลงฐานข้อมูลไม่สำเร็จ: {e}")
        return None, False



def db_load_predictions():
    """โหลด predictions ทั้งหมดจาก Supabase เรียงล่าสุดก่อน — คืน DataFrame ว่างถ้าพัง"""
    if not supabase:
        return pd.DataFrame()
    try:
        response = supabase.table(DB_TABLE).select("*").order("created_at", desc=True).execute()
        if response.data:
            df = pd.DataFrame(response.data)
            numeric_cols = [
                'market_p_home', 'market_p_draw', 'market_p_away', 'stat_p_home', 'divergence_wl',
                'market_total', 'stat_total', 'divergence_goals', 'home_wr_5g', 'away_wr_5g',
                'ah_line', 'ah_home_odds', 'ah_away_odds', 'ou_line', 'ou_over_odds', 'ou_under_odds',
                'h1x2_odds', 'd1x2_odds', 'a1x2_odds', 'ah_overround', 'ou_overround',
                'math_lambda_home', 'math_lambda_away', 'stat_lambda_home', 'stat_lambda_away',
                'auto_fit_loss', 'stadium_temp',
                'ah_home_win_rate', 'ah_away_win_rate', 'ou_over_win_rate', 'ou_under_win_rate',
                'ah_home_gates_passed', 'ah_away_gates_passed',
                'ou_over_gates_passed', 'ou_under_gates_passed',
                'gates_passed', 'recommended_bet_size', 'bet_phase', 'bankroll_at_time',
                'actual_total_goals', 'actual_home_goals', 'actual_away_goals', 'pnl',
                'home_w', 'home_d', 'home_l', 'home_gf', 'home_ga',
                'away_w', 'away_d', 'away_l', 'away_gf', 'away_ga',
            ]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            # ── Boolean columns ── Supabase คืนมาเป็น Python bool แล้ว
            # แต่ pandas อาจเก็บเป็น object — convert ให้ชัดเจน
            bool_cols = ['all_gates_pass', 'extreme_wr_flag', 'ranking_agrees',
                        'auto_fit_used', 'auto_fit_converged']
            for col in bool_cols:
                if col in df.columns:
                    df[col] = df[col].apply(
                        lambda x: True if x is True or str(x).lower() == 'true'
                        else (False if x is False or str(x).lower() == 'false' else None)
                    )
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"⚠️ โหลดข้อมูลจากฐานข้อมูลไม่สำเร็จ: {e}")
        return pd.DataFrame()


def db_update_result(record_id, updates: dict):
    """อัปเดตผลการแข่งขัน (settle) ของ prediction ที่มีอยู่แล้ว"""
    if not supabase:
        st.error("⚠️ ไม่สามารถเชื่อมต่อฐานข้อมูล Supabase ได้")
        return False
    try:
        supabase.table(DB_TABLE).update(updates).eq("id", record_id).execute()
        return True
    except Exception as e:
        st.error(f"⚠️ อัปเดตผลไม่สำเร็จ: {e}")
        return False


def db_delete_all():
    """ลบ predictions ทั้งหมด (ใช้ระวัง — สำหรับปุ่ม Clear เท่านั้น)"""
    if not supabase:
        return False
    try:
        supabase.table(DB_TABLE).delete().neq("id", 0).execute()
        return True
    except Exception as e:
        st.error(f"⚠️ ลบข้อมูลไม่สำเร็จ: {e}")
        return False


def db_delete_one(record_id):
    """ลบ prediction รายตัวตาม id"""
    if not supabase:
        return False
    try:
        supabase.table(DB_TABLE).delete().eq("id", record_id).execute()
        return True
    except Exception as e:
        st.error(f"⚠️ ลบ record ไม่สำเร็จ: {e}")
        return False


def is_settled(p):
    """เช็คว่า prediction settle แล้วไหม — เข้มงวด: ต้องมี actual_result เป็นค่า valid จริง
    (รองรับ None, NaN, empty string ทั้งหมดถือว่ายังไม่ settle)
    สำคัญ: หลัง DataFrame.to_dict('records') ค่า NULL จะเป็น NaN ไม่ใช่ None"""
    val = p.get('actual_result')
    if val is None:
        return False
    try:
        if pd.isna(val):
            return False
    except (TypeError, ValueError):
        pass
    # ต้องเป็น string ที่มีค่าจริง (home_win/draw/away_win) เท่านั้น
    if not isinstance(val, str) or not val.strip():
        return False
    return val in ('home_win', 'draw', 'away_win')


def compute_best_side(p):
    """คำนวณ Best Bet สดจาก gate scanner data (win_rate + gates_passed ของ 4 ฝั่ง)
    แทนการพึ่ง recommended_side ใน DB ที่อาจผิดจากโค้ดเวอร์ชันเก่า (เช่น FLIP bug)
    คืน side name ('AH Home'/'AH Away'/'OU Over'/'OU Under') หรือ None ถ้าไม่มีฝั่งผ่าน"""
    def _nz(v, d=0):
        if v is None: return d
        try:
            if pd.isna(v): return d
        except (TypeError, ValueError): pass
        return v
    sides = [
        ('AH Home', _nz(p.get('ah_home_win_rate'))*100, int(_nz(p.get('ah_home_gates_passed')))),
        ('AH Away', _nz(p.get('ah_away_win_rate'))*100, int(_nz(p.get('ah_away_gates_passed')))),
        ('OU Over', _nz(p.get('ou_over_win_rate'))*100, int(_nz(p.get('ou_over_gates_passed')))),
        ('OU Under', _nz(p.get('ou_under_win_rate'))*100, int(_nz(p.get('ou_under_gates_passed')))),
    ]
    qualified = sorted([s for s in sides if s[2] >= 4 and s[1] >= 55],
                       key=lambda x: x[1], reverse=True)
    return qualified[0][0] if qualified else None


# ════════════════════════════════════════════════════════════════════════
# 🧪 EDGE SIGNALS — อัปเดตจากการวิเคราะห์ 150 เคส (settled)
# ────────────────────────────────────────────────────────────────────────
# บทเรียนสำคัญ: สัญญาณเดี่ยวที่เคยดูดีตอน 94 เคส อ่อนลงเมื่อข้อมูลโต
#   • ah_overround เดี่ยว: 61%→57% (p 0.008→0.17) อ่อนลงชัด
#   • away_wr_5g เดี่ยว: ยัง 58% (p=0.036) แต่ไม่ผ่าน Bonferroni + split-half ผันผวน
# ⭐ การค้นพบใหม่ที่แข็งแกร่งสุด — COMBO 2 เงื่อนไข:
#   "OU overround สูง (>104.8%) + ทีมเยือนฟอร์มแย่ (≤40%)" → เล่นตาม Stat
#   WR 71% (n=42, ROI +32%) · split-half นิ่ง (74%/70%) · เทียบไม่เข้า combo แค่ 40%
#   ⚠️ p=0.004 เกือบผ่าน Bonferroni(0.0025), 5-fold ±17% → ยังต้องเฝ้าดู
# หลักการ: แสดงเป็นสัญญาณให้คนตัดสินใจ ไม่บังคับเป็น Gate จนกว่าจะ 30+ บิล/กลุ่ม
# ════════════════════════════════════════════════════════════════════════
OVERROUND_EDGE_THRESHOLD = 104.7    # ah_overround (สัญญาณเดี่ยว — อ่อนลงแล้ว)
OU_OVERROUND_EDGE_THRESHOLD = 104.8 # ou_overround (ใช้ใน combo ที่แข็งกว่า)
AWAY_FORM_EDGE_THRESHOLD = 0.40     # away_wr_5g ต่ำกว่าหรือเท่านี้ = ฟอร์มแย่

# ════════════════════════════════════════════════════════════════════════
# 🏠 AH HOME CONFIDENCE SCORE — จากวิเคราะห์ 150 เคส
# ────────────────────────────────────────────────────────────────────────
# ค้นพบ: home advantage ในบอล niche แรง (AH Home เสมอ = 59%)
# ยิ่งเข้าหลายเงื่อนไข WR ยิ่งสูงแบบ monotonic:
#   0 สัญญาณ→45% · 1→56% · 2→57% · 3→64% · 4→62%
# AH Home + ค่าน้ำ O/U สูง เดี่ยว: WR 65% (n=72, 5-fold ±6% นิ่งสุด, p=0.006)
# เล่น AH Home เมื่อ ≥3 สัญญาณ: WR 63% (n=65, p=0.023)
# 4 สัญญาณ: ค่าน้ำ O/U สูง, stat เชียร์ home, home ฟอร์มดี, home λ สูง
# ════════════════════════════════════════════════════════════════════════
def ah_home_confidence(p):
    """นับสัญญาณสนับสนุน AH Home (0-4) — ยิ่งสูงยิ่งน่าเล่น AH Home
    คืน (score, list ของสัญญาณที่เข้า)"""
    def _nz(v, d=0):
        if v is None: return d
        try:
            if pd.isna(v): return d
        except (TypeError, ValueError): pass
        return v
    hits = []
    if _nz(p.get('ou_overround')) > OU_OVERROUND_EDGE_THRESHOLD:
        hits.append('ค่าน้ำ O/U สูง')
    if _nz(p.get('divergence_wl')) > 0:
        hits.append('Stat เชียร์เจ้าบ้าน')
    if _nz(p.get('home_wr_5g')) >= 0.40:
        hits.append('เจ้าบ้านฟอร์มดี')
    if _nz(p.get('stat_lambda_home')) >= 1.5:
        hits.append('เจ้าบ้านคาดยิงสูง')
    return len(hits), hits


def compute_edge_signals(p):
    """คืน list ของสัญญาณเสริม — แต่ละตัวเป็น dict
    {label, status: 'strong'/'positive'/'neutral'/'caution', detail}"""
    def _nz(v, d=None):
        if v is None: return d
        try:
            if pd.isna(v): return d
        except (TypeError, ValueError): pass
        return v
    signals = []

    ou_or = _nz(p.get('ou_overround'))
    ah_or = _nz(p.get('ah_overround'))
    away_wr = _nz(p.get('away_wr_5g'))

    # 🏠 AH HOME CONFIDENCE — นับสัญญาณสนับสนุนเจ้าบ้าน (home advantage niche)
    ah_score, ah_hits = ah_home_confidence(p)
    if ah_score >= 3:
        signals.append({
            'label': f'🏠 AH HOME มั่นใจสูง ({ah_score}/4 สัญญาณ)',
            'status': 'strong',
            'detail': f'≥3 สัญญาณหนุนเจ้าบ้าน (อดีต WR 63-64%) → เล่น AH Home น่าสนใจ'
        })
    elif ah_score == 2:
        signals.append({
            'label': f'🏠 AH Home ปานกลาง ({ah_score}/4)',
            'status': 'positive',
            'detail': 'สัญญาณหนุนเจ้าบ้านปานกลาง (อดีต WR ~57%)'
        })

    # ⭐ COMBO SIGNAL (แข็งแกร่งสุด) — OU overround สูง + ทีมเยือนฟอร์มแย่
    if ou_or is not None and away_wr is not None:
        if ou_or > OU_OVERROUND_EDGE_THRESHOLD and away_wr <= AWAY_FORM_EDGE_THRESHOLD:
            signals.append({
                'label': '⭐ AH COMBO: ค่าน้ำ O/U สูง + เยือนฟอร์มแย่',
                'status': 'strong',
                'detail': f'อดีต WR 71% (เทียบไม่เข้า combo 40%) → เล่น AH ตาม Stat น่าสนใจ'
            })

    # ⭐ OU OVER COMBO — OU overround สูง + ทั้งคู่เสียประตูเยอะ → เล่น Over
    home_ga = _nz(p.get('home_ga'))
    away_ga = _nz(p.get('away_ga'))
    if ou_or is not None and home_ga is not None and away_ga is not None:
        avg_conceded = (home_ga + away_ga) / 10  # เฉลี่ยเสีย/นัด รวมสองทีม
        if ou_or > OU_OVERROUND_EDGE_THRESHOLD and avg_conceded > 1.3:
            signals.append({
                'label': '⭐ OU COMBO: ค่าน้ำ O/U สูง + ทั้งคู่เสียเยอะ',
                'status': 'strong',
                'detail': f'อดีต Over WR 65% (เทียบ Over ทั่วไป 52%) → เล่น สูง (Over) น่าสนใจ'
            })

    # สัญญาณเดี่ยว (อ่อนลงแล้ว — แสดงเป็นข้อมูลประกอบ)
    if ah_or is not None:
        if ah_or > OVERROUND_EDGE_THRESHOLD:
            signals.append({
                'label': f'ค่าน้ำ AH สูง ({ah_or:.1f}%)',
                'status': 'neutral',
                'detail': 'เคยเป็นสัญญาณบวก แต่อ่อนลงเมื่อข้อมูลมากขึ้น (เฝ้าดู)'
            })
        else:
            signals.append({
                'label': f'ค่าน้ำ AH ต่ำ ({ah_or:.1f}%)',
                'status': 'caution',
                'detail': 'ตลาด efficient → ระวัง'
            })

    if away_wr is not None:
        if away_wr <= AWAY_FORM_EDGE_THRESHOLD:
            signals.append({
                'label': f'ทีมเยือนฟอร์มแย่ ({away_wr*100:.0f}%)',
                'status': 'positive',
                'detail': 'เจ้าบ้านได้เปรียบ — แข็งขึ้นเมื่อรวมกับค่าน้ำ O/U สูง'
            })
        else:
            signals.append({
                'label': f'ทีมเยือนฟอร์มดี ({away_wr*100:.0f}%)',
                'status': 'neutral',
                'detail': 'คู่สูสี → ระวัง'
            })
    return signals

# ──────────────────────────────────────────────────────────────────────
# SESSION STATE INIT
# ──────────────────────────────────────────────────────────────────────
def init_session_state():
    defaults = {
        'bankroll': 30000.0,
        'bet_phase': 1,              # 1 = Fixed 2% calibration, 2 = Dynamic
        'h1x2_val': 1.0, 'd1x2_val': 1.0, 'a1x2_val': 1.0,
        'hdp_line_val': 0.0, 'hdp_h_w_val': 0.0, 'hdp_a_w_val': 0.0,
        'ou_line_val': 2.5, 'ou_over_w_val': 0.0, 'ou_under_w_val': 0.0,
        'live_hdp': 0.0, 'live_hdp_abs': 0.0, 'live_ou': 2.50,
        'lh_s_input': 0, 'la_s_input': 0, 'current_min': 45,
        'rc_h_chk': False, 'rc_a_chk': False,
        'stats_home_w': 0, 'stats_home_d': 0, 'stats_home_l': 0,
        'stats_home_gf': 0, 'stats_home_ga': 0, 'stats_home_rank': "-",
        'stats_away_w': 0, 'stats_away_d': 0, 'stats_away_l': 0,
        'stats_away_gf': 0, 'stats_away_ga': 0, 'stats_away_rank': "-",
        'stats_temp': 25,
        '_hdp_line_str': "0", '_ou_line_str': "2.5",
        'gate5_mode': "skip",
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

init_session_state()


def clear_prematch_data():
    for k, v in {
        'h1x2_val': 1.0, 'd1x2_val': 1.0, 'a1x2_val': 1.0,
        'hdp_line_val': 0.0, 'hdp_h_w_val': 0.0, 'hdp_a_w_val': 0.0,
        'ou_line_val': 2.5, 'ou_over_w_val': 0.0, 'ou_under_w_val': 0.0,
    }.items():
        st.session_state[k] = v


def parse_line(s):
    s = str(s).replace(' ', '').replace('+', '')
    neg = '-' in s
    s = s.replace('-', '')
    try:
        if '/' in s:
            a, b = s.split('/')
            val = (float(a) + float(b)) / 2
        else:
            val = float(s)
        return -val if neg else val
    except (ValueError, ZeroDivisionError):
        return 0.0


def parse_match_text(text):
    """
    Parse ข้อความราคาบอลรูปแบบไทย -> dict ของค่าที่ extract ได้
    รูปแบบที่รองรับ:
      [ทีมเหย้า] VS [ทีมเยือน]
      เหย้า X.XX   <- 1X2 home (occurrence ที่ 1)
      เสมอ X.XX
      เยือน X.XX   <- 1X2 away (occurrence ที่ 1)
      เหย้า X.XX   <- AH home odds (occurrence ที่ 2)
      AH [line]    <- เช่น "-0.5/1" หรือ "0.5"
      เยือน X.XX   <- AH away odds (occurrence ที่ 2)
      สูง X.XX     <- OU over odds
      สูง/ต่ำ X.X  <- OU line
      ต่ำ X.XX     <- OU under odds
    คืนค่า dict — key ที่ parse ไม่ได้จะไม่ปรากฏใน dict (เหลือค่าเดิมในฟอร์ม)
    """
    result = {}
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]

    for line in lines:
        if re.search(r'\bVS\b', line, re.IGNORECASE):
            parts = re.split(r'\s+VS\s+', line, flags=re.IGNORECASE)
            if len(parts) == 2:
                result['home_team'] = parts[0].strip()
                result['away_team'] = parts[1].strip()
            break

    def extract_value(line, keyword):
        # ใช้ regex ที่จับเฉพาะเลขทศนิยมรูปแบบถูกต้อง (มีจุดได้ไม่เกิน 1 จุด)
        m = re.match(rf'^{re.escape(keyword)}\s+(\d+(?:\.\d+)?)\s*$', line)
        if not m:
            return None
        try:
            return float(m.group(1))
        except (ValueError, TypeError):
            return None

    home_count = 0
    away_count = 0

    for line in lines:
        ah_match = re.match(r'^AH\s+(.+)$', line, re.IGNORECASE)
        if ah_match:
            result['ah_line_raw'] = ah_match.group(1).strip()
            continue

        ou_line_match = re.match(r'^สูง\s*/\s*ต่ำ\s+([\d./]+)\s*$', line)
        if ou_line_match:
            # รองรับเส้นควบ เช่น "2.5/3" → 2.75 (ใช้ parse_line เหมือน AH)
            result['ou_line_raw'] = parse_line(ou_line_match.group(1))
            continue

        v = extract_value(line, 'เหย้า')
        if v is not None:
            home_count += 1
            if home_count == 1:
                result['h1x2'] = v
            elif home_count == 2:
                result['ah_home_odds'] = v
            continue

        v = extract_value(line, 'เสมอ')
        if v is not None:
            result['d1x2'] = v
            continue

        v = extract_value(line, 'เยือน')
        if v is not None:
            away_count += 1
            if away_count == 1:
                result['a1x2'] = v
            elif away_count == 2:
                result['ah_away_odds'] = v
            continue

        v = extract_value(line, 'สูง')
        if v is not None:
            result['ou_over_odds'] = v
            continue

        v = extract_value(line, 'ต่ำ')
        if v is not None:
            result['ou_under_odds'] = v
            continue

    return result


def settle_ah_ou(side, ah_line, ou_line, home_goals, away_goals):
    """
    คำนวณผล Asian Handicap / Over-Under ที่ถูกต้องตามแต้มต่อ
    คืน (win_fraction, loss_fraction) — รองรับ quarter-ball, push, half-win/loss
    convention: ah_line +1 = เจ้าบ้านต่อ 1 (home ให้แต้ม), -1 = เจ้าบ้านรอง
      AH Home: adj = (home-away) - ah_line
      AH Away: adj = (away-home) + ah_line
      OU Over: adj = total - ou_line ; OU Under: adj = ou_line - total
      adj>=0.5 ชนะเต็ม | 0.25 ชนะครึ่ง | 0 คืนทุน | -0.25 แพ้ครึ่ง | <=-0.5 แพ้เต็ม
    """
    import pandas as _pd
    hg = home_goals if (home_goals is not None and not _pd.isna(home_goals)) else 0
    ag = away_goals if (away_goals is not None and not _pd.isna(away_goals)) else 0
    if side in ('AH Home', 'AH Away'):
        if ah_line is None or _pd.isna(ah_line):
            return (0.0, 0.0)
        adj = ((hg - ag) - ah_line) if side == 'AH Home' else ((ag - hg) + ah_line)
    elif side in ('OU Over', 'OU Under'):
        if ou_line is None or _pd.isna(ou_line):
            return (0.0, 0.0)
        total = hg + ag
        adj = (total - ou_line) if side == 'OU Over' else (ou_line - total)
    else:
        return (0.0, 0.0)
    adj = round(adj * 4) / 4
    if adj >= 0.5:   return (1.0, 0.0)
    if adj == 0.25:  return (0.5, 0.0)
    if adj == 0:     return (0.0, 0.0)
    if adj == -0.25: return (0.0, 0.5)
    return (0.0, 1.0)


def fix(o):
    """แปลง malay-style odds (0.xx) เป็น decimal odds (1.xx)"""
    try:
        o = float(o)
    except (ValueError, TypeError):
        return 1.0
    return o + 1.0 if 0 < o < 1.1 else o


# ════════════════════════════════════════════════════════════════════════
# 🧮 MATH CORE — Shin Devig
# ════════════════════════════════════════════════════════════════════════
def shin_devig(oh, od, oa):
    """Shin's method — ลบ favorite-longshot bias ออกจากราคา 1X2"""
    try:
        pi = [1/oh, 1/od, 1/oa]
    except ZeroDivisionError:
        return 1/3, 1/3, 1/3
    sp = sum(pi)
    if sp <= 1.0:
        return pi[0]/sp, pi[1]/sp, pi[2]/sp
    lo, hi = 0.0, 1.0
    z = 0.0
    for _ in range(100):
        z = (lo + hi) / 2
        try:
            p = [(math.sqrt(z**2 + 4*(1-z)*pi_i) - z) / (2*(1-z)) for pi_i in pi]
            if sum(p) > 1: lo = z
            else: hi = z
        except (ValueError, ZeroDivisionError):
            break
    p = [(math.sqrt(z**2 + 4*(1-z)*pi_i) - z) / (2*(1-z)) for pi_i in pi]
    sp = sum(p)
    return p[0]/sp, p[1]/sp, p[2]/sp


def devig_2way(o1, o2):
    """Simple inverse devig สำหรับตลาด 2 ทาง (AH, OU)"""
    i1, i2 = 1/o1, 1/o2
    s = i1 + i2
    return i1/s, i2/s


# ════════════════════════════════════════════════════════════════════════
# 🧮 MATH CORE — Dixon-Coles Poisson Matrix
# ════════════════════════════════════════════════════════════════════════
def _poisson_pmf(k, lam):
    if lam <= 0: return 0.0 if k > 0 else 1.0
    return (lam**k * math.exp(-lam)) / math.factorial(k)


def calc_dixon_coles_matrix(ph, pd, pa, ou, oow, uuw,
                             ch=0, ca=0, ml=90,
                             rch=False, rca=False,
                             lh_override=None, la_override=None):
    """
    คำนวณ Poisson scoring matrix จากราคาตลาด (devigged)
    Returns: (hw2, hw1, dr, aw1, aw2, pou, margin_dist)
      hw2/hw1/dr/aw1/aw2 = 5-bucket margin probabilities (home perspective)
      pou = dict {total_goals: prob}
      margin_dist = 7-bucket {h3,h2,h1,d,a1,a2,a3} (home perspective)
    """
    ow = oow + 1 if oow < 1.1 else oow
    uw = uuw + 1 if uuw < 1.1 else uuw
    op = 1/ow; up = 1/uw
    top = op / (op + up)

    bet = ou + 0.05 + ((top - 0.5) * 2.5)
    et  = max(0.5, bet + (0.25 - pd) * 4.0)
    sup = (ph - pa) * (et ** 0.80)

    lh = max(0.15, (et + sup) / 2) * (ml / 90) ** 0.75
    la = max(0.15, (et - sup) / 2) * (ml / 90) ** 0.75

    if rch:
        lh *= 0.50; la *= 1.30
    if rca:
        la *= 0.50; lh *= 1.30

    # Auto-Fit λ override (reverse-engineered จากตลาด)
    if lh_override is not None and la_override is not None:
        lh = lh_override * (ml / 90) ** 0.75
        la = la_override * (ml / 90) ** 0.75
        if rch:
            lh *= 0.50; la *= 1.30
        if rca:
            la *= 0.50; lh *= 1.30

    dyn_rho = max(-0.25, min(0.0, -0.15 + (et - 2.5) * 0.05))

    mx = [[0.0] * 10 for _ in range(10)]
    for i in range(10):
        for j in range(10):
            bp = _poisson_pmf(i, lh) * _poisson_pmf(j, la)
            if   i == 0 and j == 0: tau = 1 - (lh * la * dyn_rho)
            elif i == 0 and j == 1: tau = 1 + (lh * dyn_rho)
            elif i == 1 and j == 0: tau = 1 + (la * dyn_rho)
            elif i == 1 and j == 1: tau = 1 - dyn_rho
            else: tau = 1.0
            mx[i][j] = max(0, bp * tau)
    tp = sum(sum(r) for r in mx)
    if tp <= 0: tp = 1e-9

    h2 = h1 = dr = a1 = a2 = 0.0
    pou = {}
    margin_dist = {'h3': 0.0, 'h2': 0.0, 'h1': 0.0, 'd': 0.0,
                    'a1': 0.0, 'a2': 0.0, 'a3': 0.0}
    for i in range(10):
        for j in range(10):
            p  = mx[i][j] / tp
            fh = i + ch; fa = j + ca; d = fh - fa
            if   d >= 2:  h2 += p
            elif d == 1:  h1 += p
            elif d == 0:  dr += p
            elif d == -1: a1 += p
            elif d <= -2: a2 += p
            tg = fh + fa
            pou[tg] = pou.get(tg, 0) + p
            if   d >= 3:  margin_dist['h3'] += p
            elif d == 2:  margin_dist['h2'] += p
            elif d == 1:  margin_dist['h1'] += p
            elif d == 0:  margin_dist['d']  += p
            elif d == -1: margin_dist['a1'] += p
            elif d == -2: margin_dist['a2'] += p
            else:         margin_dist['a3'] += p
    return (h2, h1, dr, a1, a2, pou, margin_dist, lh, la)


# ════════════════════════════════════════════════════════════════════════
# 🧮 MATH CORE — Reverse-Engineer λ from Market (Auto-Fit, pure Python)
# ════════════════════════════════════════════════════════════════════════
def _build_probs_from_lambda(lh, la, ou_line, rho=-0.10):
    if lh < 0.1 or la < 0.1: return 0, 0, 0, 0, 0
    mx = [[0.0]*10 for _ in range(10)]
    for i in range(10):
        for j in range(10):
            bp = _poisson_pmf(i, lh) * _poisson_pmf(j, la)
            if i==0 and j==0:   tau = 1 - (lh*la*rho)
            elif i==0 and j==1: tau = 1 + (lh*rho)
            elif i==1 and j==0: tau = 1 + (la*rho)
            elif i==1 and j==1: tau = 1 - rho
            else: tau = 1.0
            mx[i][j] = max(0, bp*tau)
    tp = sum(sum(r) for r in mx)
    if tp <= 0: return 0, 0, 0, 0, 0
    p_h = p_d = p_a = 0.0
    pou = {}
    for i in range(10):
        for j in range(10):
            p = mx[i][j] / tp
            d = i - j
            if d > 0:    p_h += p
            elif d == 0: p_d += p
            else:        p_a += p
            tg = i + j
            pou[tg] = pou.get(tg, 0) + p
    fl = int(math.floor(ou_line)); rm = ou_line - fl
    if rm == 0.25:
        p_over = sum(p for k,p in pou.items() if k > fl) + pou.get(fl,0)*0.5
        p_under = 1 - p_over
    elif rm == 0.5:
        p_over = sum(p for k,p in pou.items() if k > fl)
        p_under = 1 - p_over
    elif rm == 0.75:
        p_over = sum(p for k,p in pou.items() if k > fl+1) + pou.get(fl+1,0)*0.5
        p_under = 1 - p_over
    else:
        p_over = sum(p for k,p in pou.items() if k > fl)
        p_under = sum(p for k,p in pou.items() if k < fl)
    return p_h, p_d, p_a, p_over, p_under


def reverse_engineer_lambda(p_h_mkt, p_d_mkt, p_a_mkt, p_over_mkt, p_under_mkt, ou_line):
    """Nelder-Mead simplex (pure Python) — fit λ ให้ตรงกับตลาดทั้ง 1X2+OU"""
    def loss(params):
        lh, la = params
        if lh < 0.1 or la < 0.1 or lh > 8.0 or la > 8.0: return 1e6
        p_h, p_d, p_a, p_o, p_u = _build_probs_from_lambda(lh, la, ou_line)
        return (p_h-p_h_mkt)**2 + (p_d-p_d_mkt)**2 + (p_a-p_a_mkt)**2 + \
               (p_o-p_over_mkt)**2 + (p_u-p_under_mkt)**2

    initial_et = ou_line + 0.30
    initial_sup = (p_h_mkt - p_a_mkt) * (initial_et ** 0.80)
    lh0 = max(0.3, (initial_et + initial_sup) / 2)
    la0 = max(0.3, (initial_et - initial_sup) / 2)
    simplex = [[lh0, la0], [lh0+0.1, la0], [lh0, la0+0.1]]
    values = [loss(p) for p in simplex]

    for _ in range(150):
        order = sorted(range(3), key=lambda i: values[i])
        simplex = [simplex[i] for i in order]
        values  = [values[i] for i in order]
        if values[0] < 1e-6: break
        centroid = [(simplex[0][0]+simplex[1][0])/2, (simplex[0][1]+simplex[1][1])/2]
        reflected = [2*centroid[0]-simplex[2][0], 2*centroid[1]-simplex[2][1]]
        f_r = loss(reflected)
        if values[0] <= f_r < values[1]:
            simplex[2] = reflected; values[2] = f_r
        elif f_r < values[0]:
            expanded = [centroid[0]+2*(reflected[0]-centroid[0]), centroid[1]+2*(reflected[1]-centroid[1])]
            f_e = loss(expanded)
            if f_e < f_r: simplex[2]=expanded; values[2]=f_e
            else: simplex[2]=reflected; values[2]=f_r
        else:
            contracted = [centroid[0]+0.5*(simplex[2][0]-centroid[0]), centroid[1]+0.5*(simplex[2][1]-centroid[1])]
            f_c = loss(contracted)
            if f_c < values[2]: simplex[2]=contracted; values[2]=f_c
            else:
                simplex[1] = [simplex[0][0]+0.5*(simplex[1][0]-simplex[0][0]), simplex[0][1]+0.5*(simplex[1][1]-simplex[0][1])]
                simplex[2] = [simplex[0][0]+0.5*(simplex[2][0]-simplex[0][0]), simplex[0][1]+0.5*(simplex[2][1]-simplex[0][1])]
                values[1] = loss(simplex[1]); values[2] = loss(simplex[2])

    final_loss = values[0]
    converged = final_loss < 0.01
    return simplex[0][0], simplex[0][1], final_loss, converged


# ════════════════════════════════════════════════════════════════════════
# 🎯 WIN PROBABILITY CORE — P(cover) แทน EV (Primary Signal v4.0)
# ════════════════════════════════════════════════════════════════════════
def p_cover_ah_side(ah_line_signed, margin_dist, side):
    """
    คำนวณ P(cover) แบบไม่กำกวม — ใช้ signed ah_line ตาม convention ของระบบ
    Convention: ah_line_signed > 0 → เจ้าบ้านต่อ (Home=Fav, Away=Dog)
                ah_line_signed < 0 → ทีมเยือนต่อ (Home=Dog, Away=Fav)
                ah_line_signed = 0 → pk (ไม่มี fav/dog)

    side: 'home' หรือ 'away' — ฝั่งที่ต้องการคำนวณ P(cover)

    Returns: (p_win, p_half_win, p_push, p_half_loss, p_loss)

    หลักการ: คำนวณจาก home-margin perspective เสมอเป็นฐาน (gt-based),
    แล้ว derive ผลของแต่ละ side ตาม sign ของเส้นและ side ที่ขอ
    """
    h = abs(ah_line_signed)
    home_is_fav = ah_line_signed > 0  # บวก = เจ้าบ้านต่อ = Home คือ Fav

    # คำนวณ "Home perspective cover" เสมอก่อน:
    #   ถ้า Home เป็น Fav → ใช้สูตร Fav ตรงๆ (gt-based กับ +h)
    #   ถ้า Home เป็น Dog → Home "cover" หมายถึงไม่แพ้เกิน h ลูก
    home_cover_result = _fav_cover_from_home_margin(h, margin_dist) if home_is_fav \
                         else _dog_cover_from_home_margin(h, margin_dist)

    if side == 'home':
        return home_cover_result
    else:
        # Away = mirror ของ Home ที่เส้นเดียวกัน
        w, hw_, p, hl, l = home_cover_result
        return l, hl, p, hw_, w


def _fav_cover_from_home_margin(h, md):
    """Home เป็น Fav (ah_line > 0) — ใช้ gt(home_margin) เทียบ h"""
    fl = int(math.floor(h)); rm = round(h - fl, 2)

    def gt(threshold):
        if   threshold <= -2: return md['h3']+md['h2']+md['h1']+md['d']+md['a1']+md['a2']+md['a3']
        elif threshold == -1: return md['h3']+md['h2']+md['h1']+md['d']+md['a1']+md['a2']
        elif threshold == 0:  return md['h1'] + md['h2'] + md['h3']
        elif threshold == 1:  return md['h2'] + md['h3']
        elif threshold == 2:  return md['h3']
        return 0.0

    def eq(value):
        if   value == 0: return md['d']
        elif value == 1: return md['h1']
        elif value == 2: return md['h2']
        elif value == -1: return md['a1']
        elif value == -2: return md['a2']
        return 0.0

    if rm == 0.0:
        win = gt(fl); push = eq(fl); loss = 1 - win - push
        return win, 0.0, push, 0.0, loss
    elif rm == 0.5:
        win = gt(fl); loss = 1 - win
        return win, 0.0, 0.0, 0.0, loss
    elif rm == 0.25:
        # h=fl.25 = avg(เส้น fl [push ที่ margin=fl], เส้น fl+0.5 [ไม่มี push])
        # margin > fl: ชนะทั้ง 2 component → WIN เต็ม
        # margin == fl: component-fl=push, component-(fl+0.5)=loss → HALF LOSS
        # margin < fl: แพ้ทั้งคู่ → LOSS เต็ม
        win = gt(fl)
        half_loss = eq(fl)
        loss = 1 - win - half_loss
        return win, 0.0, 0.0, half_loss, loss
    elif rm == 0.75:
        # h=fl.75 = avg(เส้น fl+0.5 [ไม่มี push], เส้น fl+1 [push ที่ margin=fl+1])
        # margin > fl+1: ชนะทั้งคู่ → WIN เต็ม
        # margin == fl+1: component-(fl+0.5)=win, component-(fl+1)=push → HALF WIN
        # margin <= fl: แพ้ทั้งคู่ → LOSS เต็ม
        win = gt(fl+1)
        half_win = eq(fl+1)
        loss = 1 - win - half_win
        return win, half_win, 0.0, 0.0, loss
    win = gt(fl); loss = 1 - win
    return win, 0.0, 0.0, 0.0, loss


def _dog_cover_from_home_margin(h, md):
    """Home เป็น Dog (ah_line < 0, Away ต่อ) — Home cover = mirror ของ Away-as-Fav ที่เส้นเดียวกัน"""
    aw_, ahw, ap, ahl, al = _fav_cover_from_home_margin(h, _flip_margin_dist(md))
    # ผลที่ได้คือจากมุม "Away เป็น Fav" (เพราะ flip แล้ว) → home_dog = away_fav mirror กลับมาเป็น home view
    # _fav_cover_from_home_margin(h, flipped) คืนค่า cover ของฝั่งที่ "ใหญ่กว่า" ในมุมที่ flip แล้ว = Away Fav cover
    # ดังนั้น Home(Dog) cover = mirror ของผลลัพธ์นี้
    return al, ahl, ap, ahw, aw_


def _flip_margin_dist(md):
    """สลับมุมมอง home<->away ของ margin_dist (h3<->a3, h2<->a2, h1<->a1, d เท่าเดิม)"""
    return {
        'h3': md['a3'], 'h2': md['a2'], 'h1': md['a1'],
        'd':  md['d'],
        'a1': md['h1'], 'a2': md['h2'], 'a3': md['h3'],
    }


def p_cover_ah(hdp, margin_dist, fav):
    """
    [LEGACY — ใช้เพื่อ backward compat กับ unit tests]
    คำนวณ P(cover) โดยตีความว่า hdp คือเส้นของฝั่งที่ขอ (fav=True หมายถึง
    ฝั่งที่ขอเป็น Fav ไม่ว่าจะเป็น Home หรือ Away — แบบเดียวกับ ev_ah() เดิม)
    Returns: (p_win, p_half_win, p_push, p_half_loss, p_loss)
    """
    return _fav_cover_from_home_margin(abs(hdp), margin_dist) if fav \
           else _dog_cover_from_home_margin(abs(hdp), margin_dist)


def p_cover_ou(ou_line, pou, over):
    """
    คำนวณ P(cover) ของ OU — Over หรือ Under
    Returns: (p_win, p_half_win, p_push, p_half_loss, p_loss)
    """
    fl = int(math.floor(ou_line)); rm = round(ou_line - fl, 2)

    def p_total_gt(t):
        return sum(p for k, p in pou.items() if k > t)
    def p_total_eq(t):
        return pou.get(t, 0.0)

    if over:
        if rm == 0.0:
            p_win = p_total_gt(fl); p_push = p_total_eq(fl)
            return p_win, 0.0, p_push, 0.0, 1 - p_win - p_push
        elif rm == 0.5:
            p_win = p_total_gt(fl)
            return p_win, 0.0, 0.0, 0.0, 1 - p_win
        elif rm == 0.25:
            # avg(เส้น fl [push@fl], เส้น fl+0.5 [ไม่มี push])
            # total > fl: win ทั้งคู่ | total == fl: push+loss = HALF LOSS | total < fl: loss ทั้งคู่
            p_win = p_total_gt(fl)
            p_half_loss = p_total_eq(fl)
            p_loss = 1 - p_win - p_half_loss
            return p_win, 0.0, 0.0, p_half_loss, p_loss
        elif rm == 0.75:
            # avg(เส้น fl+0.5 [ไม่มี push], เส้น fl+1 [push@fl+1])
            # total > fl+1: win ทั้งคู่ | total == fl+1: win+push = HALF WIN | total <= fl: loss ทั้งคู่
            p_win = p_total_gt(fl+1)
            p_half_win = p_total_eq(fl+1)
            p_loss = 1 - p_win - p_half_win
            return p_win, p_half_win, 0.0, 0.0, p_loss
    else:
        if rm == 0.0:
            p_loss = p_total_gt(fl); p_push = p_total_eq(fl)
            return 1 - p_loss - p_push, 0.0, p_push, 0.0, p_loss
        elif rm == 0.5:
            p_loss = p_total_gt(fl)
            return 1 - p_loss, 0.0, 0.0, 0.0, p_loss
        elif rm == 0.25:
            # Under ที่ total==fl: push(เส้น fl)+win(เส้น fl+0.5, total<fl+0.5) = HALF WIN
            p_loss = p_total_gt(fl)
            p_half_win = p_total_eq(fl)
            p_win = 1 - p_loss - p_half_win
            return p_win, p_half_win, 0.0, 0.0, p_loss
        elif rm == 0.75:
            # Under ที่ total==fl+1: loss(เส้น fl+0.5)+push(เส้น fl+1) = HALF LOSS
            p_loss = p_total_gt(fl+1)
            p_half_loss = p_total_eq(fl+1)
            p_win = 1 - p_loss - p_half_loss
            return p_win, 0.0, 0.0, p_half_loss, p_loss
    return 0.0, 0.0, 0.0, 0.0, 1.0


def effective_win_rate(p_win, p_half_win, p_push, p_half_loss, p_loss):
    """
    แปลงผลลัพธ์ 5 สถานะ → 'effective win rate' เดียว สำหรับ Gate 2
    นับ half-win เป็น 0.5 ชนะ, push ไม่นับ (ถอดออกจากฐาน), half-loss เป็น 0.5 แพ้
    """
    base = p_win + p_half_win + p_half_loss + p_loss  # exclude push
    if base <= 0: return 0.0
    effective_wins = p_win + p_half_win * 0.5
    return effective_wins / base  # normalize ไม่นับ push


# ════════════════════════════════════════════════════════════════════════
# 🚦 GATE SYSTEM — แทน threshold EV เดิม
# ════════════════════════════════════════════════════════════════════════
GATE2_MIN_WINRATE = 0.55   # Win Rate ขั้นต่ำ
ODDS_MIN = 1.72
ODDS_MAX = 2.20
GATE4_MAX_DIVERGENCE = 0.15  # Math vs Market สูงสุดที่ยอมรับได้

def overround(*odds):
    return sum(1/o for o in odds) * 100


def check_gate1_market_quality(ah_overround, ou_overround):
    """Gate 1: ตลาดต้องไม่บางเกินไป"""
    avg_or = (ah_overround + ou_overround) / 2
    passed = avg_or <= 106.0
    if avg_or <= 104.0:
        tier = "🟢 Liquid"
    elif avg_or <= 106.0:
        tier = "🟡 Normal"
    else:
        tier = "🟠 Thin/Niche"
    return passed, tier, avg_or


def check_gate2_win_probability(win_rate):
    """Gate 2: ต้องมี Win Rate ≥ 55%"""
    passed = win_rate >= GATE2_MIN_WINRATE
    return passed, win_rate


def check_gate3_odds_range(odds):
    """Gate 3: Odds ต้องอยู่ในช่วงที่กำหนด"""
    passed = ODDS_MIN <= odds <= ODDS_MAX
    return passed, odds


def check_gate4_math_market_agreement(p_cover_math, p_cover_market):
    """Gate 4: Math กับ Market ต้องไม่ขัดแย้งกันเกินไป"""
    divergence = abs(p_cover_math - p_cover_market)
    passed = divergence <= GATE4_MAX_DIVERGENCE
    return passed, divergence


def run_all_gates(win_rate, odds, ah_overround, ou_overround,
                   p_cover_math, p_cover_market):
    """
    รัน gate ทั้ง 4 (บังคับ) แล้วคืนผลรวม
    Returns: dict พร้อม per-gate result + overall pass/fail
    """
    g1_pass, g1_tier, g1_val = check_gate1_market_quality(ah_overround, ou_overround)
    g2_pass, g2_val = check_gate2_win_probability(win_rate)
    g3_pass, g3_val = check_gate3_odds_range(odds)
    g4_pass, g4_val = check_gate4_math_market_agreement(p_cover_math, p_cover_market)

    all_pass = g1_pass and g2_pass and g3_pass and g4_pass

    return {
        'gate1': {'pass': g1_pass, 'label': 'Market Quality', 'value': g1_val, 'detail': g1_tier},
        'gate2': {'pass': g2_pass, 'label': 'Win Probability', 'value': g2_val, 'detail': f"{g2_val*100:.1f}% (need ≥{GATE2_MIN_WINRATE*100:.0f}%)"},
        'gate3': {'pass': g3_pass, 'label': 'Odds Range', 'value': g3_val, 'detail': f"{g3_val:.2f} (need {ODDS_MIN}-{ODDS_MAX})"},
        'gate4': {'pass': g4_pass, 'label': 'Math-Market Agreement', 'value': g4_val, 'detail': f"Δ{g4_val*100:.1f}% (max {GATE4_MAX_DIVERGENCE*100:.0f}%)"},
        'all_pass': all_pass,
        'gates_passed': sum([g1_pass, g2_pass, g3_pass, g4_pass]),
    }


def get_bet_tier(win_rate):
    """กำหนด tier ตาม win_rate สำหรับ Phase 2 (Dynamic sizing)"""
    if win_rate >= 0.62:
        return "Strong", 0.05
    elif win_rate >= 0.58:
        return "Medium", 0.03
    else:
        return "Weak", 0.02


def calc_bet_size(bankroll, win_rate, phase=1):
    """
    คำนวณขนาดเงินเดิมพัน
    Phase 1: Fixed 2% เสมอ (calibration — ไม้ที่ 1-50)
    Phase 2: Dynamic ตาม tier (หลัง 50 ไม้ ถ้า WR≥53%)
    """
    if phase == 1:
        return bankroll * 0.02, "Fixed", 0.02
    else:
        tier, pct = get_bet_tier(win_rate)
        return bankroll * pct, tier, pct


# ════════════════════════════════════════════════════════════════════════
# 🧪 GATE 5 — STAT-DIVERGENCE FILTER (หัวใจของ v5.0)
# ════════════════════════════════════════════════════════════════════════
# จากหลักฐาน 12 เคส (เก็บนอกระบบ เป็น reference ไม่ใช่ seed data):
#   - High divergence (>=40% ใน Win/Lose) -> Market มักถูกกว่า (2/2 เคส)
#     ตรงข้ามสัญชาตญาณ: divergence ใหญ่ = stat กำลังโดน small-sample noise
#     หลอก ไม่ใช่ตลาดพลาด
#   - Low-liquidity market (women's league, lower-tier, cup ไม่มี ranking)
#     -> Stat total goals อาจมี edge (2/2 เคสแต่ sample เล็กมาก)
# Gate 5 จึงเป็น "ตัวเตือน" ไม่ใช่ "ตัวบล็อก" -- ไม่เปลี่ยน Win Rate/EV จาก
# Math Engine แต่ให้ confidence adjustment + warning ที่ผู้ใช้ตัดสินใจเอง
# ════════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════════
# 📊 หลักฐานเชิงประจักษ์ จากข้อมูลจริง 60 เคส — คำนวณด้วยสูตร AH ที่ถูกต้อง
# (แก้ไขจากเวอร์ชันก่อนที่ใช้ผล 1X2 ตัดสิน AH ผิด)
# ────────────────────────────────────────────────────────────────────────
# เล่น AH ตามฝั่งที่ stat เชียร์ (odds 1.90):
#   Low (<15%)     : WR 47% | ROI -8.9% (n=31) — stat ไม่มี edge ชัด
#   Moderate(15-40%): WR 21% | ROI -47.6% (n=25) → stat แย่มากในโซนนี้!
#                     loss=14 push=4 win=4 half_loss=3 → ตลาดถูกชัดเจน
#   Extreme (≥40%) : WR 100% | ROI +56% (n=4 เท่านั้น — น้อยเกินเชื่อ)
# กลยุทธ์ (สูตรถูก):
#   A ตาม Stat ทุกเคส : ROI -20.7%  ❌
#   B ข้าม Moderate   : ROI -1.4%   (35 บิล) ← ปลอดภัย เกือบเสมอตัว
#   C พลิก Moderate   : ROI +15.7%  (60 บิล) ← สูงสุด แต่ยังเสี่ยง overfit
#   D Low only        : ROI -8.9%
# สรุป: Moderate zone คือจุดที่ stat พลาดหนักสุด (ยืนยันชัดขึ้นหลังแก้สูตร)
# ════════════════════════════════════════════════════════════════════════
EXTREME_DIVERGENCE_THRESHOLD = 0.40
MODERATE_DIVERGENCE_THRESHOLD = 0.15

# Bet size multiplier ตามหลักฐาน (ใช้ลด exposure เมื่อ stat อยู่ในโซนเสี่ยง)
MULT_MODERATE_AGAINST = 0.5   # stat สวนตลาด 15-40% → ลดครึ่ง (เดิมคิดตลาดถูก แต่ล่าสุด 48% เกือบ 50/50)
MULT_EXTREME_AGAINST = 0.7    # stat สวนตลาด ≥40% → ลดเล็กน้อย (9 เคสล่าสุดเล่นตาม stat 62% แต่ยังเล็ก)
MULT_LOW_DIVERGENCE = 1.0     # <15% → stat เชื่อถือได้ ไม่ลด

# ────────────────────────────────────────────────────────────────────────
# Backtest บนข้อมูลจริง 60 เคส (AH, odds 1.90) — ผลแต่ละกลยุทธ์:
#   A ตาม Stat ทุกเคส (เดิม)    : ROI -9.0%  (56 บิล)
#   B ข้าม Moderate zone        : ROI +5.0%  (34 บิล) ← DEFAULT ปลอดภัยสุด
#   C Moderate พลิกตามตลาด      : ROI +11.3% (56 บิล) ← สูงสุด แต่ p=0.13 เสี่ยง overfit
#   D เล่นเฉพาะ Low divergence  : ROI +4.7%  (30 บิล)
# เลือก B เป็น default เพราะ "ไม่ทำอันตราย" ถ้าสัญญาณเป็น noise;
# C เปิดเป็น advanced option พร้อมคำเตือน
# ────────────────────────────────────────────────────────────────────────
GATE5_MODE_REDUCE = "reduce"   # ลด bet (multiplier) — conservative
GATE5_MODE_SKIP = "skip"       # ข้าม moderate-against — DEFAULT
GATE5_MODE_FLIP = "flip"       # พลิกตามตลาด — advanced/aggressive


def classify_league_tier(league_name, has_ranking, home_team="", away_team=""):
    """
    จำแนกตลาดเป็น tier ตามสัญญาณที่หาได้จากชื่อลีก + ชื่อทีม + การมี ranking
    Returns: 'women' | 'cup_no_rank' | 'major' | 'niche'
    หมายเหตุ: ชื่อลีกอย่างเดียวอาจไม่พอ (เช่น "Nadeshiko League" ไม่มีคำว่า
    "women" ตรงๆ) จึงเช็คชื่อทีมประกอบด้วย เพราะทีมหญิงมักมีคำว่า "Women"/"Ladies"
    ต่อท้ายชื่อทีมแม้ลีกจะไม่มีคำนั้น
    """
    combined = f"{league_name or ''} {home_team or ''} {away_team or ''}".lower()
    women_keywords = ['women', 'ladies', 'หญิง', 'nadeshiko', 'feminin', 'femenino',
                      "women's", 'wsl', 'frauen']
    if any(kw in combined for kw in women_keywords):
        return 'women'
    name_lower = (league_name or "").lower()
    major_keywords = ['world cup', 'champions league', 'premier league', 'la liga',
                      'serie a', 'bundesliga', 'fifa', 'euro ', 'uefa']
    if any(kw in name_lower for kw in major_keywords):
        return 'major'
    if not has_ranking:
        return 'cup_no_rank'
    return 'niche'


def stat_p_home_from_inputs(home_w, home_d, home_l, home_gf, home_ga,
                             away_w, away_d, away_l, away_gf, away_ga):
    """คำนวณ Stat-based P(Home win) จาก 5 นัดหลังสุด"""
    home_gpg  = home_gf / 5; away_gpg  = away_gf / 5
    home_gapg = home_ga / 5; away_gapg = away_ga / 5
    home_form_score = home_w * 3 + home_d
    away_form_score = away_w * 3 + away_d
    denom = home_form_score + away_form_score
    stat_p_home_raw = home_form_score / denom if denom > 0 else 0.5
    home_gd = home_gpg - home_gapg
    away_gd = away_gpg - away_gapg
    gd_factor = (home_gd - away_gd) * 0.05
    stat_p_home = max(0.10, min(0.85, stat_p_home_raw + gd_factor))
    stat_lh = (home_gpg + away_gapg) / 2
    stat_la = (away_gpg + home_gapg) / 2
    stat_total = stat_lh + stat_la
    return stat_p_home, stat_total, stat_lh, stat_la


def evaluate_gate5(league_name, home_rank, away_rank, temp,
                    home_w, home_d, home_l, home_gf, home_ga,
                    away_w, away_d, away_l, away_gf, away_ga,
                    market_p_home, ou_line, home_team="", away_team=""):
    """ประเมิน Gate 5 ทั้งหมด -- คืนค่า dict พร้อม warnings/signals"""
    has_ranking = (home_rank != "-" and away_rank != "-")
    league_tier = classify_league_tier(league_name, has_ranking, home_team, away_team)

    stat_p_home, stat_total, stat_lh, stat_la = stat_p_home_from_inputs(
        home_w, home_d, home_l, home_gf, home_ga,
        away_w, away_d, away_l, away_gf, away_ga
    )

    divergence_wl = stat_p_home - market_p_home
    home_wr_5g = home_w / 5
    away_wr_5g = away_w / 5
    extreme_wr = (home_wr_5g in (0.0, 1.0)) or (away_wr_5g in (0.0, 1.0))

    signals = []
    abs_div = abs(divergence_wl)
    if abs_div >= EXTREME_DIVERGENCE_THRESHOLD:
        favored_side = "Home" if divergence_wl > 0 else "Away"
        signals.append({
            'type': 'warning', 'level': 'high',
            'title': f"EXTREME DIVERGENCE (D{divergence_wl*100:+.0f}%)",
            'detail': (f"Stat บอก {favored_side} ได้เปรียบกว่าตลาดมาก (≥40%) — เคสแบบนี้พบน้อย "
                      f"(9 เคสในข้อมูลล่าสุด, เล่นตาม Stat ชนะ ~62% แต่ sample ยังเล็กเกินสรุป) "
                      f"ความต่างที่สูงผิดปกติอาจมาจาก small-sample noise ใน 5 นัด "
                      f"แนะนำลดขนาดเดิมพันและตรวจ stat input ซ้ำว่าผิดปกติไหม")
        })
    elif abs_div >= MODERATE_DIVERGENCE_THRESHOLD:
        favored_side = "Home" if divergence_wl > 0 else "Away"
        signals.append({
            'type': 'warning', 'level': 'medium',
            'title': f"Moderate Divergence (D{divergence_wl*100:+.0f}%)",
            'detail': (f"Stat เชียร์ {favored_side} ต่างจากตลาด 15-40% — จากข้อมูลล่าสุด 59 เคส "
                      f"โซนนี้เล่นตาม Stat ใน AH ได้ WR ~48% (เกือบ 50/50, ไม่มี edge ชัด) "
                      f"สัญญาณ 'ตลาดถูกกว่า' ที่เคยเห็นตอน sample เล็กได้จางหายไปแล้ว "
                      f"แนะนำใช้สัญญาณอื่น (COMBO/AH Home confidence) ประกอบการตัดสินใจแทน")
        })
    else:
        signals.append({
            'type': 'success', 'level': 'low',
            'title': f"Low Divergence (D{divergence_wl*100:+.0f}%)",
            'detail': "Stat กับ Market ใกล้เคียงกัน -- ไม่มีสัญญาณขัดแย้งที่ต้องระวังเป็นพิเศษ"
        })

    divergence_goals = stat_total - ou_line
    if league_tier in ('women', 'cup_no_rank') and divergence_goals > 0.3:
        signals.append({
            'type': 'opportunity', 'level': 'medium',
            'title': f"Low-Liquidity Goals Signal ({league_tier})",
            'detail': (f"ตลาดนี้เป็น {league_tier} (liquidity ต่ำ) และ Stat total goals "
                      f"({stat_total:.2f}) สูงกว่า Market line ({ou_line}) อยู่ {divergence_goals:+.2f} "
                      f"-- จากหลักฐานเบื้องต้น ตลาดประเภทนี้อาจ undervalue goals "
                      f"(sample เล็กมาก ใช้เป็นข้อมูลประกอบเท่านั้น)")
        })

    if extreme_wr:
        which = []
        if home_wr_5g in (0.0, 1.0): which.append(f"Home WR={home_wr_5g*100:.0f}%")
        if away_wr_5g in (0.0, 1.0): which.append(f"Away WR={away_wr_5g*100:.0f}%")
        signals.append({
            'type': 'neutral', 'level': 'info',
            'title': f"Extreme WR Detected ({', '.join(which)})",
            'detail': ("จากหลักฐานที่เก็บมา Extreme WR (0%/100% ใน 5 นัด) "
                      "ไม่ใช่ตัวบ่งชี้ที่เชื่อถือได้ ว่า Stat จะถูกหรือผิด (ผลออกมาแบบผสมกัน) "
                      "-- เป็นแค่ข้อสังเกต ไม่ใช่ signal")
        })

    return {
        'league_tier': league_tier,
        'stat_p_home': stat_p_home,
        'stat_total': stat_total,
        'stat_lh': stat_lh, 'stat_la': stat_la,
        'divergence_wl': divergence_wl,
        'divergence_goals': divergence_goals,
        'home_wr_5g': home_wr_5g, 'away_wr_5g': away_wr_5g,
        'extreme_wr_flag': extreme_wr,
        'ranking_agrees': has_ranking,
        'signals': signals,
    }


def gate5_confidence_adjustment(gate5_result, recommended_side_is_home):
    """
    แปลง Gate 5 signals เป็นคำแนะนำปรับ confidence ตามหลักฐานจริง 60 เคส
    Returns: (adjustment_label, adjustment_color, suggested_bet_multiplier)
    """
    abs_div = abs(gate5_result['divergence_wl'])
    stat_favors_home = gate5_result['divergence_wl'] > 0
    # Best Bet ตรงกับฝั่งที่ Stat เชียร์ไหม? (ถ้าตรง = กำลังเล่นตาม stat = เสี่ยงตามหลักฐาน)
    aligns_with_stat = (stat_favors_home == recommended_side_is_home)
    has_opportunity = any(s['type'] == 'opportunity' for s in gate5_result['signals'])

    if abs_div >= EXTREME_DIVERGENCE_THRESHOLD:
        if aligns_with_stat:
            return ("⚠️ ลด Bet เล็กน้อย — Diverge สูง (≥40%) ข้อมูลล่าสุด 9 เคสเล่นตาม Stat 62% (ยังเล็ก)",
                    "#ff8c00", MULT_EXTREME_AGAINST)
        return ("ℹ️ Extreme Divergence แต่ Best Bet ฝั่งตรงข้าม Stat — สอดคล้องตลาด",
                "#4a7a60", 1.0)
    elif abs_div >= MODERATE_DIVERGENCE_THRESHOLD:
        if aligns_with_stat:
            return ("⚠️ ลด Bet ครึ่งหนึ่ง — Best Bet ตามฝั่ง Stat ในโซน 15-40% (ตลาดถูก ~64%)",
                    "#ff8c00", MULT_MODERATE_AGAINST)
        return ("✅ Best Bet สอดคล้องกับตลาด (Stat เชียร์ฝั่งตรงข้าม) — โซนนี้ตลาดแม่น",
                "#00ff88", 1.0)
    else:
        # Low divergence — stat เชื่อถือได้ (WR~57% ใน AH)
        if has_opportunity:
            return ("💡 Low Divergence + Low-Liquidity Goals Signal", "#00b4ff", MULT_LOW_DIVERGENCE)
        return ("✅ Low Divergence — Stat สอดคล้องตลาด เชื่อถือได้", "#00ff88", MULT_LOW_DIVERGENCE)


# ════════════════════════════════════════════════════════════════════════
# 🎨 CSS THEME
# ════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Exo+2:wght@400;600;700;800&family=Rajdhani:wght@400;500;600;700&family=Share+Tech+Mono&display=swap');

.stApp { background: #060c10; }
* { font-family: 'Rajdhani', sans-serif; }

.gem-panel {
    background: #0d1e2e;
    border: 1px solid rgba(0,255,136,0.15);
    border-radius: 8px;
    padding: 14px 16px;
    margin-bottom: 10px;
}
.gem-label {
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.72rem;
    color: #00ff88;
    letter-spacing: 0.1em;
    border-left: 3px solid #00ff88;
    padding-left: 8px;
    margin-bottom: 10px;
}
.gem-divider {
    border-top: 1px solid rgba(0,255,136,0.1);
    margin: 14px 0;
}
.gate-pass {
    background: rgba(0,255,136,0.08);
    border-left: 3px solid #00ff88;
    border-radius: 0 4px 4px 0;
    padding: 10px 14px;
    margin-bottom: 6px;
}
.gate-fail {
    background: rgba(255,59,92,0.08);
    border-left: 3px solid #ff3b5c;
    border-radius: 0 4px 4px 0;
    padding: 10px 14px;
    margin-bottom: 6px;
}
.signal-card {
    border-radius: 0 4px 4px 0;
    padding: 10px 14px;
    margin-bottom: 6px;
}
.signal-valid {
    background: rgba(0,255,136,0.10);
    border: 2px solid #00ff88;
    border-radius: 8px;
    padding: 16px 20px;
    margin: 12px 0;
}
.signal-invalid {
    background: rgba(255,59,92,0.08);
    border: 2px solid #ff3b5c;
    border-radius: 8px;
    padding: 16px 20px;
    margin: 12px 0;
}
h1, h2, h3 { font-family: 'Exo 2', sans-serif !important; color: #e8f5ee !important; }
[data-testid="stSidebar"] { background: #050a0d; border-right: 1px solid rgba(0,255,136,0.1); }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# 🧭 SIDEBAR
# ════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        '<div style="text-align:center;padding:10px 0 16px 0;">'
        '<div style="font-family:\'Exo 2\';font-weight:800;font-size:1.3rem;color:#00ff88;">'
        '🎯 GEM 5.0</div>'
        '<div style="font-family:\'Share Tech Mono\';font-size:0.65rem;color:#4a7a60;'
        'letter-spacing:0.1em;">STAT-VS-MARKET EDITION</div></div>',
        unsafe_allow_html=True
    )
    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)

    st.markdown('<div class="gem-label">◈ BANKROLL MANAGEMENT</div>', unsafe_allow_html=True)
    bankroll = st.number_input("Bankroll (฿)", min_value=1000.0, step=1000.0,
                                key='bankroll', format="%.0f")
    bet_phase = st.radio(
        "Betting Phase",
        options=[1, 2],
        format_func=lambda x: "Phase 1 — Fixed 2% (Calibration)" if x == 1
                               else "Phase 2 — Dynamic 2/3/5%",
        key='bet_phase',
    )
    if bet_phase == 1:
        st.caption(f"💰 ทุกบิลลง **{bankroll*0.02:,.0f} ฿** (2%)")
    else:
        st.caption(f"💰 Weak 2%={bankroll*0.02:,.0f}฿ · Medium 3%={bankroll*0.03:,.0f}฿ · "
                   f"Strong 5%={bankroll*0.05:,.0f}฿")

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="gem-label">◈ GATE 5 STRATEGY</div>', unsafe_allow_html=True)
    st.caption("จากข้อมูลจริง 60 เคส: เมื่อ Stat สวนตลาด 15-40% ตลาดมักถูกกว่า")
    gate5_mode = st.radio(
        "โหมด Gate 5 (Stat-Divergence)",
        options=[GATE5_MODE_SKIP, GATE5_MODE_REDUCE, GATE5_MODE_FLIP],
        format_func=lambda x: {
            GATE5_MODE_SKIP: "🛡️ SKIP — ข้ามเคส Moderate-against (ปลอดภัยสุด, แนะนำ)",
            GATE5_MODE_REDUCE: "⚖️ REDUCE — ลด bet โซนเสี่ยง (กลาง)",
            GATE5_MODE_FLIP: "⚡ FLIP — พลิกตามตลาด (รุก — สัญญาณจางแล้ว ไม่แนะนำ)",
        }[x],
        key='gate5_mode',
    )
    if gate5_mode == GATE5_MODE_FLIP:
        st.warning("⚡ โหมด FLIP: เคยให้ ROI ดีตอน sample เล็ก แต่ข้อมูลล่าสุด 59 เคส "
                  "โซน Moderate กลับมาเกือบ 50/50 (เล่นตาม Stat 48%) — สัญญาณ 'ตลาดถูกกว่า' "
                  "จางหายแล้ว ไม่แนะนำ FLIP อีกต่อไป ใช้ SKIP จะปลอดภัยกว่า")

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="gem-label">◈ GATE THRESHOLDS (Fixed)</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-family:\'Share Tech Mono\';font-size:0.7rem;color:#c8e6d4;line-height:1.8;">'
        f'Gate 1 — Market Quality: ≤106% OR<br>'
        f'Gate 2 — Win Probability: ≥{GATE2_MIN_WINRATE*100:.0f}%<br>'
        f'Gate 3 — Odds Range: {ODDS_MIN}–{ODDS_MAX}<br>'
        f'Gate 4 — Math-Market Agree: ≤{GATE4_MAX_DIVERGENCE*100:.0f}% Δ<br>'
        f'Gate 5 — Stat-Divergence: {gate5_mode.upper()} mode</div>',
        unsafe_allow_html=True
    )

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    auto_fit_lambda = st.checkbox("🎯 Auto-Fit λ to Market", value=True)
    show_value_scanner = st.checkbox("💎 Value Scanner Panel", value=False)

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    st.caption(
        "ℹ️ v5.0: Gate 5 ใหม่ใช้หลักฐานจาก 12 เคส reference (เก็บนอกระบบ) "
        "— extreme divergence (≥40%) เตือนให้เชื่อ Market, low-liquidity market "
        "(women's/cup) อาจมี Stat edge ใน Total Goals. Gate 5 ไม่บล็อกบิล "
        "แต่ทุก prediction ถูกบันทึกเพื่อ backtest ในอนาคต"
    )

# ════════════════════════════════════════════════════════════════════════
# 🏠 HEADER + TABS
# ════════════════════════════════════════════════════════════════════════
st.markdown(
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;">'
    '<span style="font-family:\'Exo 2\';font-weight:800;font-size:1.6rem;color:#e8f5ee;">'
    '🎯 GEM 5.0 — Stat-vs-Market</span></div>'
    '<div style="font-family:\'Rajdhani\';font-size:0.85rem;color:#4a7a60;margin-bottom:16px;">'
    'Win Rate First · 5-Gate Filter · Every Prediction Logged for Backtest</div>',
    unsafe_allow_html=True
)

tab_pre, tab_scan, tab_log, tab_backtest, tab_dash = st.tabs(
    ["📋 PRE-MATCH", "🎯 COMBO SCAN", "📝 PREDICTIONS LOG", "🧪 BACKTEST LAB", "📊 DASHBOARD"]
)

# ════════════════════════════════════════════════════════════════════════
# 📋 TAB 1: PRE-MATCH
# ════════════════════════════════════════════════════════════════════════
with tab_pre:
    # ══════════════════════════════════════════════════════════════════
    # 📋 TEXT PARSER — วางข้อความราคา แล้ว auto-fill ทุกช่อง
    # ══════════════════════════════════════════════════════════════════
    # ── Pending parse: เช็คก่อนสร้าง widget ใดๆ (เหตุผลเดียวกับ pending clear) ──
    if st.session_state.get('_pending_parse_data') is not None:
        parsed = st.session_state['_pending_parse_data']
        filled = []
        if 'home_team' in parsed:
            st.session_state['_parsed_home_team'] = parsed['home_team']; filled.append('ทีมเหย้า')
        if 'away_team' in parsed:
            st.session_state['_parsed_away_team'] = parsed['away_team']; filled.append('ทีมเยือน')
        if 'h1x2' in parsed:
            st.session_state['h1x2_val'] = parsed['h1x2']; filled.append('1X2 Home')
        if 'd1x2' in parsed:
            st.session_state['d1x2_val'] = parsed['d1x2']; filled.append('1X2 Draw')
        if 'a1x2' in parsed:
            st.session_state['a1x2_val'] = parsed['a1x2']; filled.append('1X2 Away')
        if 'ah_line_raw' in parsed:
            st.session_state['_hdp_line_str'] = parsed['ah_line_raw']; filled.append('AH Line')
        if 'ah_home_odds' in parsed:
            st.session_state['hdp_h_w_val'] = parsed['ah_home_odds']; filled.append('AH Home Odds')
        if 'ah_away_odds' in parsed:
            st.session_state['hdp_a_w_val'] = parsed['ah_away_odds']; filled.append('AH Away Odds')
        if 'ou_line_raw' in parsed:
            st.session_state['_ou_line_str'] = str(parsed['ou_line_raw']); filled.append('OU Line')
        if 'ou_over_odds' in parsed:
            st.session_state['ou_over_w_val'] = parsed['ou_over_odds']; filled.append('OU Over')
        if 'ou_under_odds' in parsed:
            st.session_state['ou_under_w_val'] = parsed['ou_under_odds']; filled.append('OU Under')
        st.session_state['_pending_parse_data'] = None
        st.session_state['_parse_filled_fields'] = filled

    # ── Pending clear: เช็คก่อนสร้าง widget ใดๆ เพื่อหลีกเลี่ยง
    # StreamlitAPIException (ห้าม set session_state ของ widget ที่ถูกสร้างไปแล้วในรอบนี้) ──
    if st.session_state.get('_pending_clear', False):
        for k in ['h1x2_val', 'd1x2_val', 'a1x2_val', 'hdp_h_w_val', 'hdp_a_w_val',
                 'ou_over_w_val', 'ou_under_w_val']:
            st.session_state[k] = 0.0
        st.session_state['_hdp_line_str'] = "0"
        st.session_state['_ou_line_str'] = "2.5"
        st.session_state['raw_paste_text'] = ""
        st.session_state.pop('_parsed_home_team', None)
        st.session_state.pop('_parsed_away_team', None)
        for k in ['stats_home_w', 'stats_home_d', 'stats_home_l', 'stats_home_gf', 'stats_home_ga',
                 'stats_away_w', 'stats_away_d', 'stats_away_l', 'stats_away_gf', 'stats_away_ga']:
            st.session_state[k] = 0
        st.session_state['stats_home_rank'] = "-"
        st.session_state['stats_away_rank'] = "-"
        st.session_state['stats_temp'] = 25
        st.session_state['_pending_clear'] = False

    with st.expander("📋 TEXT PARSER — วางข้อความราคาเพื่อ Auto-Fill", expanded=False):
        if st.session_state.get('_parse_filled_fields'):
            filled = st.session_state.pop('_parse_filled_fields')
            if filled:
                st.success(f"✅ Auto-fill สำเร็จ {len(filled)} ช่อง: {', '.join(filled)}")
            else:
                st.warning("⚠️ ไม่พบข้อมูลที่ parse ได้ — ตรวจรูปแบบข้อความอีกครั้ง")

        st.caption(
            "ⓘ รูปแบบ: [ทีมเหย้า] VS [ทีมเยือน] ตามด้วย เหย้า/เสมอ/เยือน (1X2), "
            "เหย้า/AH [line]/เยือน (Asian Handicap), สูง/สูง-ต่ำ [line]/ต่ำ (Over-Under)"
        )
        raw_text = st.text_area(
            "วางข้อความที่นี่",
            height=180,
            placeholder=("คาซัวรินา เอฟซี VS ดาร์วิน ฮาร์ทส์\n"
                        "เหย้า 3.48\nเสมอ 4.43\nเยือน 1.64\n"
                        "เหย้า 0.99\nAH -0.5/1\nเยือน 0.85\n"
                        "สูง 0.94\nสูง/ต่ำ 4.5\nต่ำ 0.88"),
            key="raw_paste_text"
        )
        pc1, pc2 = st.columns(2)
        with pc1:
            if st.button("⚡ Parse & Auto-Fill", use_container_width=True, type="primary"):
                if raw_text.strip():
                    st.session_state['_pending_parse_data'] = parse_match_text(raw_text)
                    st.rerun()
                else:
                    st.warning("⚠️ กรุณาวางข้อความก่อน")
        with pc2:
            if st.button("🗑️ ล้างข้อมูลทั้งหมด", use_container_width=True):
                st.session_state['_pending_clear'] = True
                st.rerun()

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)

    st.markdown('<div class="gem-label">◈ MATCH INFO</div>', unsafe_allow_html=True)
    mc_name1, mc_name2 = st.columns(2)
    home_team = mc_name1.text_input("ทีมเหย้า (Home)", placeholder="เช่น Liverpool",
                                     value=st.session_state.get('_parsed_home_team', ''))
    away_team = mc_name2.text_input("ทีมเยือน (Away)", placeholder="เช่น Man City",
                                     value=st.session_state.get('_parsed_away_team', ''))
    league_name = st.text_input("ลีก / รายการแข่งขัน", placeholder="เช่น Premier League, FIFA World Cup")

    st.markdown('<div class="gem-label" style="margin-top:10px;">◈ MATCH ODDS</div>', unsafe_allow_html=True)
    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        st.markdown('<div class="gem-panel"><div class="gem-label">1X2</div>', unsafe_allow_html=True)
        h1x2 = st.number_input("HOME", format="%.2f", key="h1x2_val")
        d1x2 = st.number_input("DRAW", format="%.2f", key="d1x2_val")
        a1x2 = st.number_input("AWAY", format="%.2f", key="a1x2_val")
        st.markdown('</div>', unsafe_allow_html=True)
    with mc2:
        st.markdown('<div class="gem-panel"><div class="gem-label">ASIAN HANDICAP</div>', unsafe_allow_html=True)
        hdp_line_str = st.text_input("LINE (+ เจ้าบ้านต่อ / - ทีมเยือนต่อ)",
                                      key="_hdp_line_str")
        hdp_h_w = st.number_input("HOME ODDS", format="%.2f", key="hdp_h_w_val")
        hdp_a_w = st.number_input("AWAY ODDS", format="%.2f", key="hdp_a_w_val")
        st.markdown('</div>', unsafe_allow_html=True)
    with mc3:
        st.markdown('<div class="gem-panel"><div class="gem-label">TOTAL GOALS (O/U)</div>', unsafe_allow_html=True)
        ou_line_str = st.text_input("LINE", key="_ou_line_str")
        ou_over_w  = st.number_input("OVER",  format="%.2f", key="ou_over_w_val")
        ou_under_w = st.number_input("UNDER", format="%.2f", key="ou_under_w_val")
        st.markdown('</div>', unsafe_allow_html=True)

    hdp_line = parse_line(hdp_line_str)
    ou_line  = abs(parse_line(ou_line_str))

    # ── Stats Input — บังคับกรอกใน v5.0 เพื่อเก็บข้อมูล backtest ──
    st.markdown('<div class="gem-label" style="margin-top:10px;color:#9b59b6;border-color:#9b59b6;">'
               '◈ 📋 STAT INPUT (บังคับกรอก — ใช้สำหรับ Gate 5 + Backtest)</div>',
               unsafe_allow_html=True)
    st.caption("ⓘ v5.0 บังคับกรอกสถิติทุกครั้งเพื่อให้ทุก prediction ถูกบันทึกสำหรับ backtest ในอนาคต")

    sc1, sc2 = st.columns(2)
    with sc1:
        st.markdown('<div style="color:#00ff88;font-family:\'Share Tech Mono\';font-size:0.78rem;">🏠 HOME (5 นัดล่าสุด)</div>',
                   unsafe_allow_html=True)
        home_w = st.number_input("Wins(5)", 0, 5, key="stats_home_w")
        home_d = st.number_input("Draws(5)", 0, 5, key="stats_home_d")
        home_l = st.number_input("Losses(5)", 0, 5, key="stats_home_l")
        home_gf = st.number_input("Goals For(5g)", 0, key="stats_home_gf")
        home_ga = st.number_input("Goals Against(5g)", 0, key="stats_home_ga")
        home_rank = st.text_input("Rank ('-' if cup)", key="stats_home_rank")
    with sc2:
        st.markdown('<div style="color:#ff8c00;font-family:\'Share Tech Mono\';font-size:0.78rem;">✈️ AWAY (5 นัดล่าสุด)</div>',
                   unsafe_allow_html=True)
        away_w = st.number_input("Wins(5) ", 0, 5, key="stats_away_w")
        away_d = st.number_input("Draws(5) ", 0, 5, key="stats_away_d")
        away_l = st.number_input("Losses(5) ", 0, 5, key="stats_away_l")
        away_gf = st.number_input("Goals For(5g) ", 0, key="stats_away_gf")
        away_ga = st.number_input("Goals Against(5g) ", 0, key="stats_away_ga")
        away_rank = st.text_input("Rank ('-' if cup) ", key="stats_away_rank")
    temp = st.number_input("🌡️ Stadium Temp (°C)", -20, 50, key="stats_temp")

    home_total = home_w + home_d + home_l
    away_total = away_w + away_d + away_l
    stats_complete = (home_total == 5 and away_total == 5)
    if not stats_complete:
        if home_total != 5:
            st.warning(f"⚠️ Home W+D+L = {home_total} ต้องครบ 5 นัด")
        if away_total != 5:
            st.warning(f"⚠️ Away W+D+L = {away_total} ต้องครบ 5 นัด")

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    # ══════════════════════════════════════════════════════════════════
    # ANALYSIS — รันเมื่อมีราคา + stat ครบ
    # ══════════════════════════════════════════════════════════════════
    valid_odds = h1x2 > 1.0 and d1x2 > 1.0 and a1x2 > 1.0 and \
                 hdp_h_w > 0 and hdp_a_w > 0 and ou_over_w > 0 and ou_under_w > 0
    valid_input = valid_odds and stats_complete

    if not valid_odds:
        st.info("👆 กรอกราคาให้ครบทุกช่อง (1X2 + AH + OU) เพื่อเริ่มวิเคราะห์")
    elif not stats_complete:
        st.info("👆 กรอกสถิติ 5 นัดล่าสุดให้ครบทั้ง Home และ Away (v5.0 บังคับกรอกเพื่อเก็บข้อมูล backtest)")
    else:
        ph, pd_, pa = shin_devig(h1x2, d1x2, a1x2)
        hwo, awo = fix(hdp_h_w), fix(hdp_a_w)
        owo, uwo = fix(ou_over_w), fix(ou_under_w)

        po_mkt, pu_mkt = devig_2way(owo, uwo)
        lh_fit = la_fit = None
        fit_loss = None
        fit_converged = False
        if auto_fit_lambda:
            lh_fit, la_fit, fit_loss, fit_converged = reverse_engineer_lambda(
                ph, pd_, pa, po_mkt, pu_mkt, ou_line
            )

        hw2, hw1, dr, aw1, aw2, pou, md, lh, la = calc_dixon_coles_matrix(
            ph, pd_, pa, ou_line, owo, uwo,
            lh_override=lh_fit, la_override=la_fit
        )

        ah_or = overround(hwo, awo)
        ou_or = overround(owo, uwo)

        # ── Probability Engine Display ──
        st.markdown('<div class="gem-label">◈ PROBABILITY ENGINE</div>', unsafe_allow_html=True)
        p1, p2, p3 = st.columns(3)
        p1.metric("HOME WIN", f"{ph*100:.1f}%")
        p2.metric("DRAW", f"{pd_*100:.1f}%")
        p3.metric("AWAY WIN", f"{pa*100:.1f}%")

        if auto_fit_lambda:
            fit_color = "#00ff88" if fit_converged else "#ff8c00"
            fit_status = "✅ CONVERGED" if fit_converged else "⚠️ DIVERGED"
            st.markdown(
                f'<div style="background:#0d1e2e;border-left:3px solid {fit_color};'
                f'padding:8px 12px;margin-top:6px;border-radius:0 4px 4px 0;">'
                f'<span style="font-family:\'Share Tech Mono\';font-size:0.7rem;color:{fit_color};">'
                f'🎯 AUTO-FIT λ — {fit_status}</span><br>'
                f'<span style="font-family:\'Share Tech Mono\';font-size:0.72rem;color:#c8e6d4;">'
                f'λ_home={lh:.3f} · λ_away={la:.3f} · loss={fit_loss:.5f}</span></div>',
                unsafe_allow_html=True
            )

        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)

        # ── Market Quality ──
        st.markdown('<div class="gem-label">◈ MARKET QUALITY</div>', unsafe_allow_html=True)
        mq1, mq2 = st.columns(2)
        mq1.metric("AH Overround", f"{ah_or:.2f}%")
        mq2.metric("OU Overround", f"{ou_or:.2f}%")

        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)

        # ══════════════════════════════════════════════════════════════
        # 🧪 GATE 5 — STAT-DIVERGENCE EVALUATION (ใหม่ทั้งหมดใน v5.0)
        # ══════════════════════════════════════════════════════════════
        gate5_result = evaluate_gate5(
            league_name=league_name, home_rank=home_rank, away_rank=away_rank, temp=temp,
            home_w=home_w, home_d=home_d, home_l=home_l, home_gf=home_gf, home_ga=home_ga,
            away_w=away_w, away_d=away_d, away_l=away_l, away_gf=away_gf, away_ga=away_ga,
            market_p_home=ph, ou_line=ou_line,
            home_team=home_team, away_team=away_team
        )

        tier_colors = {'women': '#9b59b6', 'major': '#00b4ff', 'niche': '#4a7a60', 'cup_no_rank': '#ff8c00'}
        tier_color = tier_colors.get(gate5_result['league_tier'], '#4a7a60')
        st.markdown(
            f'<div class="gem-label" style="color:{tier_color};border-color:{tier_color};">'
            f'◈ 🧪 GATE 5 — STAT-DIVERGENCE FILTER '
            f'[{gate5_result["league_tier"].upper()}]</div>',
            unsafe_allow_html=True
        )
        g5c1, g5c2 = st.columns(2)
        g5c1.metric("Stat P(Home)", f"{gate5_result['stat_p_home']*100:.0f}%",
                    f"Δ{gate5_result['divergence_wl']*100:+.0f}% vs Market")
        g5c2.metric("Stat Total Goals", f"{gate5_result['stat_total']:.2f}",
                    f"Δ{gate5_result['divergence_goals']:+.2f} vs Line")

        sig_colors = {'warning': '#ff3b5c', 'info': '#ffd600', 'success': '#00ff88',
                     'opportunity': '#00b4ff', 'neutral': '#4a7a60'}
        for sig in gate5_result['signals']:
            c = sig_colors.get(sig['type'], '#4a7a60')
            st.markdown(
                f'<div class="signal-card" style="background:rgba(255,255,255,0.03);'
                f'border-left:3px solid {c};">'
                f'<span style="font-family:\'Share Tech Mono\';font-size:0.75rem;color:{c};">'
                f'{sig["title"]}</span><br>'
                f'<span style="font-family:\'Rajdhani\';font-size:0.8rem;color:#c8e6d4;">'
                f'{sig["detail"]}</span></div>',
                unsafe_allow_html=True
            )

        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)

        # ══════════════════════════════════════════════════════════════
        # 🚦 4-SIDE GATE SCANNER (Gate 1-4, เหมือน v4.0)
        # ══════════════════════════════════════════════════════════════
        st.markdown('<div class="gem-label" style="margin-top:6px;">◈ 4-SIDE GATE SCANNER</div>',
                    unsafe_allow_html=True)

        home_cover = p_cover_ah_side(hdp_line, md, 'home')
        away_cover = p_cover_ah_side(hdp_line, md, 'away')
        over_cover = p_cover_ou(ou_line, pou, True)
        under_cover = p_cover_ou(ou_line, pou, False)

        p_market_home, p_market_away = devig_2way(hwo, awo)
        p_market_over, p_market_under = devig_2way(owo, uwo)

        sides_data = [
            {"name": "AH Home", "thai": "เจ้าบ้าน", "cover": home_cover, "odds": hwo,
             "p_market": p_market_home, "is_home": True,
             "line_display": f"{'-' if hdp_line>0 else '+'}{abs(hdp_line)}" if hdp_line != 0 else "0"},
            {"name": "AH Away", "thai": "ทีมเยือน", "cover": away_cover, "odds": awo,
             "p_market": p_market_away, "is_home": False,
             "line_display": f"{'-' if hdp_line<0 else '+'}{abs(hdp_line)}" if hdp_line != 0 else "0"},
            {"name": "OU Over", "thai": "สูง", "cover": over_cover, "odds": owo,
             "p_market": p_market_over, "is_home": None, "line_display": f"{ou_line}"},
            {"name": "OU Under", "thai": "ต่ำ", "cover": under_cover, "odds": uwo,
             "p_market": p_market_under, "is_home": None, "line_display": f"{ou_line}"},
        ]

        for s in sides_data:
            pw, phw, pp, phl, pl = s['cover']
            s['win_rate'] = effective_win_rate(pw, phw, pp, phl, pl)
            s['p_cover_math'] = pw + phw * 0.5
            s['gates'] = run_all_gates(
                s['win_rate'], s['odds'], ah_or, ou_or,
                s['p_cover_math'], s['p_market']
            )

        scan_rows = []
        for s in sides_data:
            scan_rows.append({
                "ฝั่ง": f"{s['name']} ({s['line_display']})",
                "Target": s['thai'],
                "Win Rate": f"{s['win_rate']*100:.1f}%",
                "Odds": f"{s['odds']:.2f}",
                "Gates": f"{s['gates']['gates_passed']}/4",
                "ผ่าน": "✅" if s['gates']['all_pass'] else "❌",
            })
        st.dataframe(pd.DataFrame(scan_rows), use_container_width=True, hide_index=True)

        valid_sides = [s for s in sides_data if s['gates']['all_pass']]
        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)

        best = None
        bet_size = 0
        bet_size_adjusted = 0
        mode_action_msg = None
        if valid_sides:
            best = max(valid_sides, key=lambda s: s['win_rate'])

            # ── Gate 5 mode logic (จากหลักฐาน 60 เคส) ──
            abs_div_g5 = abs(gate5_result['divergence_wl'])
            stat_favors_home_g5 = gate5_result['divergence_wl'] > 0
            best_aligns_stat = (stat_favors_home_g5 == best['is_home'])
            in_moderate = MODERATE_DIVERGENCE_THRESHOLD <= abs_div_g5 < EXTREME_DIVERGENCE_THRESHOLD
            in_extreme = abs_div_g5 >= EXTREME_DIVERGENCE_THRESHOLD
            risky_zone = (in_moderate or in_extreme) and best_aligns_stat

            gate5_mode_active = st.session_state.get('gate5_mode', 'skip')
            mode_action_msg = None

            # SKIP mode: ถ้า best bet ตามฝั่ง stat ในโซนเสี่ยง → ไม่แนะนำ
            if gate5_mode_active == GATE5_MODE_SKIP and risky_zone:
                zone_name = "Moderate (15-40%)" if in_moderate else "Extreme (≥40%)"
                st.markdown(
                    f'<div class="signal-invalid">'
                    f'<div style="font-family:\'Exo 2\';font-weight:800;font-size:1.1rem;color:#ff8c00;">'
                    f'🛡️ GATE 5 SKIP — ข้ามคู่นี้</div>'
                    f'<div style="font-family:\'Rajdhani\';font-size:0.88rem;color:#c8e6d4;margin-top:8px;">'
                    f'Best Bet ({best["name"]}) ตรงกับฝั่งที่ Stat เชียร์ในโซน {zone_name} '
                    f'— จากข้อมูลจริง ตลาดมักถูกกว่า Stat ในโซนนี้ (~64%) '
                    f'โหมด SKIP จึงข้ามเพื่อเลี่ยงความเสี่ยง<br>'
                    f'(เปลี่ยนโหมดที่ Sidebar ได้ถ้าต้องการเล่น)</div>'
                    f'</div>', unsafe_allow_html=True
                )
                best = None  # ยกเลิก best bet
            # FLIP mode: พลิกไปฝั่งตรงข้าม (ตามตลาด) ในโซน moderate
            # ⚠️ ต้องพลิกไปฝั่งที่ผ่าน Gate 1-4 ครบเท่านั้น ไม่งั้น skip
            elif gate5_mode_active == GATE5_MODE_FLIP and in_moderate and best_aligns_stat:
                flipped = [s for s in sides_data
                          if s['is_home'] != best['is_home']
                          and s['name'].split()[0] == best['name'].split()[0]
                          and s['gates']['all_pass']]  # ← ฝั่งตรงข้ามต้องผ่าน gate ครบด้วย
                if flipped:
                    mode_action_msg = (f"⚡ FLIP: พลิกจาก {best['name']} → {flipped[0]['name']} "
                                      f"(เชื่อตลาดแทน Stat ในโซน Moderate)")
                    best = flipped[0]
                else:
                    # ฝั่งตรงข้ามไม่ผ่าน gate → ไม่เล่น (ดีกว่าเล่นฝั่งอ่อน)
                    st.markdown(
                        f'<div class="signal-invalid">'
                        f'<div style="font-family:\'Exo 2\';font-weight:800;font-size:1.1rem;color:#ff8c00;">'
                        f'🛡️ GATE 5 FLIP — ข้ามคู่นี้</div>'
                        f'<div style="font-family:\'Rajdhani\';font-size:0.88rem;color:#c8e6d4;margin-top:8px;">'
                        f'ควรพลิกจาก {best["name"]} ไปเล่นตามตลาด แต่ฝั่งตรงข้ามไม่ผ่าน Gate 1-4 ครบ '
                        f'— จึงข้ามเพื่อเลี่ยงการเล่นฝั่งที่อ่อนแอ</div>'
                        f'</div>', unsafe_allow_html=True
                    )
                    best = None

        if best is not None:
            conf_label, conf_color, conf_mult = gate5_confidence_adjustment(
                gate5_result, recommended_side_is_home=best['is_home']
            )
            # REDUCE mode ใช้ multiplier เต็มที่; SKIP/FLIP ใช้ 1.0 (จัดการไปแล้วข้างบน)
            if st.session_state.get('gate5_mode') != GATE5_MODE_REDUCE:
                conf_mult = 1.0
                conf_label = conf_label.replace("ลด Bet ครึ่งหนึ่ง — ", "").replace("ลด Bet แรง — ", "")

            bet_size, tier_label, tier_pct = calc_bet_size(bankroll, best['win_rate'], bet_phase)
            bet_size_adjusted = bet_size * conf_mult

            if locals().get('mode_action_msg'):
                st.info(mode_action_msg)

            st.markdown(
                f'<div class="signal-valid">'
                f'<div style="font-family:\'Exo 2\';font-weight:800;font-size:1.1rem;color:#00ff88;">'
                f'🟢 SIGNAL VALID — {best["name"]} ({best["thai"]}) {best["line_display"]}</div>'
                f'<div style="font-family:\'Rajdhani\';font-size:0.95rem;color:#c8e6d4;margin-top:8px;">'
                f'Win Rate: <strong>{best["win_rate"]*100:.1f}%</strong> · '
                f'Odds: <strong>{best["odds"]:.2f}</strong> · '
                f'Gates: <strong>{best["gates"]["gates_passed"]}/4</strong></div>'
                f'<div style="font-family:\'Share Tech Mono\';font-size:1.3rem;color:#00ff88;margin-top:10px;">'
                f'💰 แนะนำลง: {bet_size_adjusted:,.0f} ฿ ({tier_label}, {tier_pct*100:.0f}%'
                f'{f" × Gate5 {conf_mult}" if conf_mult != 1.0 else ""})</div>'
                f'<div style="font-family:\'Rajdhani\';font-size:0.78rem;color:{conf_color};margin-top:6px;">'
                f'{conf_label}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        elif not valid_sides:
            closest = max(sides_data, key=lambda s: s['gates']['gates_passed'])
            failed_gates = [g['label'] for k, g in closest['gates'].items()
                           if k in ('gate1', 'gate2', 'gate3', 'gate4') and not g['pass']]
            st.markdown(
                f'<div class="signal-invalid">'
                f'<div style="font-family:\'Exo 2\';font-weight:800;font-size:1.1rem;color:#ff3b5c;">'
                f'🔴 NO SIGNAL — Skip คู่นี้</div>'
                f'<div style="font-family:\'Rajdhani\';font-size:0.88rem;color:#c8e6d4;margin-top:8px;">'
                f'ไม่มีฝั่งไหนผ่านทั้ง 4 gates บังคับ — '
                f'ใกล้สุดคือ <strong>{closest["name"]}</strong> ({closest["gates"]["gates_passed"]}/4)</div>'
                f'<div style="font-family:\'Share Tech Mono\';font-size:0.78rem;color:#ff8c00;margin-top:6px;">'
                f'ตกที่: {", ".join(failed_gates)}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        # ถ้า valid_sides มีแต่ best=None แปลว่าถูก Gate 5 SKIP (แสดง message ไปแล้วข้างบน)

        # ══════════════════════════════════════════════════════════════
        # 💾 SAVE PREDICTION — บันทึกทุกครั้งลง Supabase (ไม่ว่าจะมี signal หรือไม่)
        # ══════════════════════════════════════════════════════════════
        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)

        if st.button("💾 บันทึก Prediction นี้ (สำหรับ Backtest)", use_container_width=True):
            side_win_rates = {s['name']: s['win_rate'] for s in sides_data}
            side_gates = {s['name']: s['gates']['gates_passed'] for s in sides_data}

            pred_record = {
                'match_name': f"{home_team or 'Home'} vs {away_team or 'Away'}",
                'league': league_name,
                'league_tier': gate5_result['league_tier'],

                # 1X2 probabilities
                'market_p_home': ph, 'market_p_draw': pd_, 'market_p_away': pa,
                'stat_p_home': gate5_result['stat_p_home'],
                'divergence_wl': gate5_result['divergence_wl'],

                # Goals
                'market_total': ou_line, 'stat_total': gate5_result['stat_total'],
                'divergence_goals': gate5_result['divergence_goals'],
                'stat_lambda_home': gate5_result['stat_lh'],
                'stat_lambda_away': gate5_result['stat_la'],

                # Math engine internals — เก็บไว้ reproduce/debug ย้อนหลัง
                'math_lambda_home': lh, 'math_lambda_away': la,
                'auto_fit_used': auto_fit_lambda,
                'auto_fit_converged': fit_converged if auto_fit_lambda else None,
                'auto_fit_loss': fit_loss if auto_fit_lambda else None,

                # Raw 5-game stats (ดิบ — reproduce สูตรใหม่ได้ถ้าปรับทีหลัง)
                'home_w': home_w, 'home_d': home_d, 'home_l': home_l,
                'home_gf': home_gf, 'home_ga': home_ga,
                'away_w': away_w, 'away_d': away_d, 'away_l': away_l,
                'away_gf': away_gf, 'away_ga': away_ga,
                'home_rank': home_rank, 'away_rank': away_rank,
                'stadium_temp': temp,
                'home_wr_5g': gate5_result['home_wr_5g'], 'away_wr_5g': gate5_result['away_wr_5g'],
                'extreme_wr_flag': gate5_result['extreme_wr_flag'],
                'ranking_agrees': gate5_result['ranking_agrees'],

                # Odds ดิบทั้งหมด
                'ah_line': hdp_line, 'ah_home_odds': hwo, 'ah_away_odds': awo,
                'ou_line': ou_line, 'ou_over_odds': owo, 'ou_under_odds': uwo,
                'h1x2_odds': h1x2, 'd1x2_odds': d1x2, 'a1x2_odds': a1x2,
                'ah_overround': ah_or, 'ou_overround': ou_or,

                # ทุก 4 ฝั่ง — ไม่ใช่แค่ฝั่งที่แนะนำ เพื่อ backtest ทางเลือกอื่นย้อนหลัง
                'ah_home_win_rate': side_win_rates.get('AH Home'),
                'ah_home_gates_passed': side_gates.get('AH Home'),
                'ah_away_win_rate': side_win_rates.get('AH Away'),
                'ah_away_gates_passed': side_gates.get('AH Away'),
                'ou_over_win_rate': side_win_rates.get('OU Over'),
                'ou_over_gates_passed': side_gates.get('OU Over'),
                'ou_under_win_rate': side_win_rates.get('OU Under'),
                'ou_under_gates_passed': side_gates.get('OU Under'),

                # Gate 5 signals เก็บเป็น JSON (โครงสร้างยืดหยุ่น ปรับได้ในอนาคตไม่ต้อง migrate schema)
                'gate5_signals': json.dumps(gate5_result['signals'], ensure_ascii=False),

                # สรุป
                'gates_passed': max(s['gates']['gates_passed'] for s in sides_data),
                'all_gates_pass': len(valid_sides) > 0,
                'recommended_side': best['name'] if best else None,
                'recommended_bet_size': bet_size_adjusted if best else 0,
                'bet_phase': bet_phase,
                'bankroll_at_time': bankroll,
            }
            new_id, was_updated = db_save_or_update_prediction(pred_record)
            if new_id is not None:
                if was_updated:
                    st.success(f"♻️ พบคู่นี้อยู่แล้ว (ยังไม่กรอกผล) — เซฟทับข้อมูลเดิมแล้ว (id={new_id}) "
                              f"· ดูที่ tab 📝 PREDICTIONS LOG")
                else:
                    st.success(f"✅ บันทึก Prediction ใหม่ลงฐานข้อมูลแล้ว (id={new_id}) — "
                              f"ดูที่ tab 📝 PREDICTIONS LOG เพื่อกรอกผลภายหลัง")
                st.cache_data.clear()


# ════════════════════════════════════════════════════════════════════════
# 📝 TAB 2: PREDICTIONS LOG — กรอกผลย้อนหลัง + คำนวณ wl/goals winner อัตโนมัติ
# ════════════════════════════════════════════════════════════════════════
def compute_wl_winner(market_p_home, stat_p_home, actual_result):
    """
    เปรียบเทียบว่า Market หรือ Stat 'ใกล้เคียง' ผลจริงมากกว่า
    actual_result: 'home_win' | 'draw' | 'away_win'
    หลักการ: แปลงผลจริงเป็น P(home)=1/0.5/0 แล้วดูว่าใครห่างน้อยกว่า
    """
    if actual_result == 'home_win':
        target = 1.0
    elif actual_result == 'away_win':
        target = 0.0
    else:
        target = 0.5

    market_dist = abs(market_p_home - target)
    stat_dist = abs(stat_p_home - target)

    if abs(market_dist - stat_dist) < 0.03:  # ใกล้กันมาก = neutral
        return 'neutral'
    return 'market' if market_dist < stat_dist else 'stat'


def compute_goals_winner(market_total, stat_total, actual_total_goals):
    """เปรียบเทียบว่า Market หรือ Stat total goals ใกล้ผลจริงมากกว่า"""
    market_dist = abs(market_total - actual_total_goals)
    stat_dist = abs(stat_total - actual_total_goals)
    if abs(market_dist - stat_dist) < 0.2:
        return 'neutral'
    return 'market' if market_dist < stat_dist else 'stat'


with tab_scan:
    st.markdown('<div class="gem-label">◈ 🎯 COMBO SCAN — คู่ที่เข้าสัญญาณเด่น</div>',
               unsafe_allow_html=True)
    st.caption("สแกน predictions ที่ยังไม่จบ (pending) หาคู่ที่เข้า ⭐ COMBO signal — เพื่อหาบิลน่าเล่นเร็วๆ")

    scan_df = db_load_predictions()
    scan_log = scan_df.to_dict('records') if not scan_df.empty else []
    scan_pending = [p for p in scan_log if not is_settled(p)]

    def nz_global(v, d=0):
        if v is None: return d
        try:
            if pd.isna(v): return d
        except (TypeError, ValueError): pass
        return v

    # คัดเฉพาะคู่ที่มี strong combo signal
    combo_hits = []
    for p in scan_pending:
        sigs = compute_edge_signals(p)
        strong = [s for s in sigs if s['status'] == 'strong']
        if strong:
            # ตรวจ Double Opportunity: เข้าทั้ง AH (Home conf หรือ AH combo) + OU Over combo
            has_ah = any(('AH HOME' in s['label'] or 'AH COMBO' in s['label']) for s in strong)
            has_ou = any('OU COMBO' in s['label'] for s in strong)
            is_double = has_ah and has_ou
            combo_hits.append((p, strong, compute_best_side(p), is_double))

    # เรียง Double Opportunity ขึ้นบนสุด
    combo_hits.sort(key=lambda x: not x[3])
    n_double = sum(1 for h in combo_hits if h[3])

    if not scan_pending:
        st.info("ยังไม่มีคู่ที่รอผล (pending) — วิเคราะห์คู่ใหม่ที่ tab 📋 PRE-MATCH ก่อน")
    elif not combo_hits:
        st.markdown(
            f'<div style="background:#0d1e2e;border-left:3px solid #7a9a88;padding:14px 18px;'
            f'border-radius:0 8px 8px 0;">'
            f'<div style="font-family:\'Rajdhani\';font-size:0.9rem;color:#c8e6d4;">'
            f'มี {len(scan_pending)} คู่รอผล แต่ยังไม่มีคู่ไหนเข้า ⭐ COMBO signal</div>'
            f'<div style="font-family:\'Rajdhani\';font-size:0.76rem;color:#7a9a88;margin-top:6px;">'
            f'COMBO ต้องมี: ค่าน้ำ O/U สูง (>104.8%) + (เยือนฟอร์มแย่ หรือ ทั้งคู่เสียเยอะ)</div></div>',
            unsafe_allow_html=True
        )
    else:
        # สรุปบนสุด — 2 การ์ด: รวม + double opportunity
        dbl_card = (
            f'<div style="flex:1;background:linear-gradient(135deg,#2a1010,#0d1e2e);border:1px solid #ff6b9d55;'
            f'border-top:3px solid #ff6b9d;border-radius:10px;padding:14px 18px;">'
            f'<div style="font-family:\'Share Tech Mono\';font-size:2rem;color:#ff6b9d;">{n_double}</div>'
            f'<div style="font-family:\'Rajdhani\';font-size:0.74rem;color:#c8e6d4;">'
            f'⭐⭐ DOUBLE (เล่นได้ทั้ง AH + Over)</div></div>'
        ) if n_double > 0 else ''
        st.markdown(
            f'<div style="display:flex;gap:10px;margin-bottom:14px;">'
            f'<div style="flex:1;background:linear-gradient(135deg,#2a2410,#0d1e2e);border:1px solid #ffd70055;'
            f'border-top:3px solid #ffd700;border-radius:10px;padding:14px 18px;">'
            f'<div style="font-family:\'Share Tech Mono\';font-size:2rem;color:#ffd700;">{len(combo_hits)}</div>'
            f'<div style="font-family:\'Rajdhani\';font-size:0.74rem;color:#c8e6d4;">'
            f'คู่ที่เข้า ⭐ COMBO (จาก {len(scan_pending)} คู่รอผล)</div></div>'
            f'{dbl_card}</div>',
            unsafe_allow_html=True
        )

        # การ์ดแต่ละคู่
        for p, strong_sigs, best, is_double in combo_hits:
            match = p.get('match_name', '-')
            league = p.get('league', '-')
            tier = p.get('league_tier', '-')

            # สรุปคำแนะนำจาก combo
            recs = []
            for s in strong_sigs:
                if 'AH HOME' in s['label']:
                    recs.append(('AH Home (เจ้าบ้าน)', 'AH Home', '63-65%'))
                elif 'AH COMBO' in s['label']:
                    bs = best or ('AH Home' if (p.get('divergence_wl') or 0) > 0 else 'AH Away')
                    recs.append(('AH ตาม Stat', bs, '71%'))
                elif 'OU COMBO' in s['label']:
                    recs.append(('Total Goals', 'OU Over (สูง)', '65%'))

            rec_html = ""
            for rtype, rside, rwr in recs:
                rec_html += (
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'background:#0a1520;border-radius:6px;padding:8px 12px;margin:4px 0;">'
                    f'<span style="font-family:\'Rajdhani\';font-size:0.82rem;color:#ffd700;font-weight:600;">'
                    f'💡 {rtype}: <span style="color:#00ff88;">{rside}</span></span>'
                    f'<span style="font-family:\'Share Tech Mono\';font-size:0.76rem;color:#7a9a88;">'
                    f'อดีต WR {rwr}</span></div>'
                )

            # ค่าประกอบ
            ou_or = nz_global(p.get('ou_overround'))
            away_wr = nz_global(p.get('away_wr_5g'))
            ah_or = nz_global(p.get('ah_overround'))

            sig_labels = " · ".join(s['label'].replace('⭐ ', '') for s in strong_sigs)

            # การ์ด double opportunity = สีชมพู-ทอง + badge
            if is_double:
                card_border = "#ff6b9d"
                card_bg = "linear-gradient(135deg,#2a1010,#1a1505)"
                title_color = "#ff6b9d"
                badge = ('<span style="background:#ff6b9d;color:#0a0a0a;font-family:\'Share Tech Mono\';'
                        'font-size:0.62rem;font-weight:800;padding:2px 8px;border-radius:10px;'
                        'margin-left:8px;">⭐⭐ DOUBLE</span>')
            else:
                card_border = "#ffd700"
                card_bg = "linear-gradient(135deg,#1a1505,#0d1e2e)"
                title_color = "#ffd700"
                badge = ""

            st.markdown(
                f'<div style="background:{card_bg};'
                f'border:1px solid {card_border}44;border-left:4px solid {card_border};border-radius:10px;'
                f'padding:14px 18px;margin-bottom:12px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:start;">'
                f'<div style="font-family:\'Exo 2\';font-weight:800;font-size:1.05rem;color:{title_color};">'
                f'⭐ {match}{badge}</div></div>'
                f'<div style="font-family:\'Rajdhani\';font-size:0.74rem;color:#7a9a88;margin-bottom:8px;">'
                f'🏆 {league} [{tier}]</div>'
                f'{rec_html}'
                f'<div style="font-family:\'Share Tech Mono\';font-size:0.7rem;color:#5a7a68;'
                f'margin-top:8px;border-top:1px solid #2a3a2a;padding-top:6px;">'
                f'สัญญาณ: {sig_labels}<br>'
                f'ค่าน้ำ O/U {ou_or:.1f}% · เยือนฟอร์ม {away_wr*100:.0f}% · ค่าน้ำ AH {ah_or:.1f}%</div>'
                f'</div>',
                unsafe_allow_html=True
            )

        st.markdown(
            '<div style="background:#1e1505;border-left:3px solid #ff8c00;padding:10px 14px;'
            'border-radius:0 6px 6px 0;margin-top:8px;">'
            '<span style="font-family:\'Rajdhani\';font-size:0.74rem;color:#c8e6d4;">'
            '⚠️ COMBO signals ยังเป็นสัญญาณทดลอง (split-half นิ่งแต่ยังไม่ผ่าน Bonferroni เต็ม) '
            'ใช้ประกอบการตัดสินใจ ไม่ใช่รับประกัน — เก็บข้อมูลเพิ่มเพื่อยืนยัน</span></div>',
            unsafe_allow_html=True
        )


with tab_log:
    st.markdown('<div class="gem-label">◈ PREDICTIONS LOG</div>', unsafe_allow_html=True)

    log_df = db_load_predictions()

    if log_df.empty:
        st.info("ยังไม่มี prediction ที่บันทึกไว้ — ไปที่ PRE-MATCH tab เพื่อวิเคราะห์และบันทึกคู่แรก")
    else:
        # ใช้เกณฑ์เดียวกับ is_settled (actual_result ต้องเป็น home_win/draw/away_win)
        # เพื่อให้ PENDING/SETTLED ตรงกันทุก tab
        valid_results = ['home_win', 'draw', 'away_win']
        _ar = log_df['actual_result']
        settled_mask = _ar.isin(valid_results)
        pending_df = log_df[~settled_mask]
        settled_df_raw = log_df[settled_mask]

        def nz(val, default=0):
            """แปลง None/NaN เป็นค่า default อย่างปลอดภัย (NaN or 0 ใน Python คืน NaN ไม่ใช่ 0)"""
            if val is None:
                return default
            try:
                if pd.isna(val):
                    return default
            except (TypeError, ValueError):
                pass
            return val

        def render_prediction_card(p, mode='pending'):
            """render card แต่ละใบ"""
            rec_id = p['id']
            created = pd.to_datetime(p['created_at']).strftime("%d/%m %H:%M") if pd.notna(p.get('created_at')) else "-"
            match_name = p.get('match_name', '-')
            tier = p.get('league_tier', '-')

            # ── คำนวณ Best Bet สดจาก gate scanner (แทน recommended_side ใน DB
            #    ที่อาจผิดจากโค้ดเวอร์ชันเก่า เช่น FLIP bug) ──
            def _nz_local(v, d=0):
                if v is None: return d
                try:
                    if pd.isna(v): return d
                except (TypeError, ValueError): pass
                return v
            _sides_calc = [
                ('AH Home', _nz_local(p.get('ah_home_win_rate'))*100, int(_nz_local(p.get('ah_home_gates_passed')))),
                ('AH Away', _nz_local(p.get('ah_away_win_rate'))*100, int(_nz_local(p.get('ah_away_gates_passed')))),
                ('OU Over', _nz_local(p.get('ou_over_win_rate'))*100, int(_nz_local(p.get('ou_over_gates_passed')))),
                ('OU Under', _nz_local(p.get('ou_under_win_rate'))*100, int(_nz_local(p.get('ou_under_gates_passed')))),
            ]
            _qualified = sorted([s for s in _sides_calc if s[2] >= 4 and s[1] >= 55],
                               key=lambda x: x[1], reverse=True)
            computed_best_side = _qualified[0][0] if _qualified else None

            # ใช้ best ที่คำนวณสดเป็นหลัก; ถ้าไม่มี qualified → No Signal
            # (recommended_side ใน DB เก็บไว้เทียบ แต่ไม่ใช้ตัดสิน)
            raw_side = p.get('recommended_side')
            db_side = raw_side if (isinstance(raw_side, str) and raw_side) else None
            side = computed_best_side if computed_best_side else 'No Signal'
            # แจ้งเตือนถ้า DB เก็บฝั่งต่างจากที่คำนวณสด (ข้อมูลเก่าจาก bug)
            side_mismatch = (db_side is not None and computed_best_side is not None
                            and db_side != computed_best_side)
            signal = computed_best_side is not None
            div = p.get('divergence_wl', 0)
            div = div if pd.notna(div) else 0

            # Header color
            if mode == 'settled':
                res = p.get('actual_result', '') or ''
                score = p.get('actual_score', '-')
                wf, lf = settle_ah_ou(side, p.get('ah_line'), p.get('ou_line'),
                                      p.get('actual_home_goals'), p.get('actual_away_goals'))
                if wf > lf:
                    header_color, status_icon = "#00ff88", ("✅" if wf == 1.0 else "🟢½")
                elif lf > wf:
                    header_color, status_icon = "#ff3b5c", ("❌" if lf == 1.0 else "🔴½")
                else:
                    header_color, status_icon = "#4a7a60", "➖"  # push
                header_right = f"{status_icon} {score}"
            else:
                header_color = "#00ff88" if signal else "#ffd600"
                header_right = "🟢 SIGNAL" if signal else "⏳ PENDING"

            tier_colors = {'women': '#9b59b6', 'major': '#00b4ff', 'niche': '#4a7a60', 'cup_no_rank': '#ff8c00'}
            tier_color = tier_colors.get(tier, '#4a7a60')
            div_color = "#ff3b5c" if abs(div) >= 0.40 else ("#ffd600" if abs(div) >= 0.15 else "#4a7a60")

            label = f"{created} | {match_name}"
            with st.expander(label, expanded=False):
                # ── ส่วนบน: overview ──
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'border-left:3px solid {header_color};padding:8px 12px;background:#0d1e2e;'
                    f'border-radius:0 6px 6px 0;margin-bottom:10px;">'
                    f'<div>'
                    f'<div style="font-family:\'Exo 2\';font-weight:700;font-size:1rem;color:#e8f5ee;">'
                    f'{match_name}</div>'
                    f'<div style="font-size:0.75rem;color:{tier_color};">'
                    f'🏆 {p.get("league","") or "-"} [{tier}]</div>'
                    f'</div>'
                    f'<div style="text-align:right;">'
                    f'<div style="font-family:\'Share Tech Mono\';font-size:0.85rem;color:{header_color};">'
                    f'{header_right}</div>'
                    f'<div style="font-size:0.7rem;color:#4a7a60;">{created}</div>'
                    f'</div></div>',
                    unsafe_allow_html=True
                )

                # ── 🎯 RECOMMENDATION PANEL — ฝั่งที่แนะนำ + เงินลง + ผลแพ้ชนะ ──
                rec_side = side if side != 'No Signal' else None
                bet_amt = nz(p.get('recommended_bet_size'))
                div_label_full = ("🚨 EXTREME" if abs(div) >= 0.40
                                  else ("⚠️ MODERATE" if abs(div) >= 0.15 else "✅ LOW"))
                stat_favors = "Home" if div > 0 else "Away"

                if rec_side:
                    odds_map_card = {
                        'AH Home': p.get('ah_home_odds'), 'AH Away': p.get('ah_away_odds'),
                        'OU Over': p.get('ou_over_odds'), 'OU Under': p.get('ou_under_odds'),
                    }
                    rec_odds = nz(odds_map_card.get(rec_side))
                    rec_line = ""
                    if rec_side in ('AH Home', 'AH Away'):
                        rec_line = f"(line {nz(p.get('ah_line')):+.2f})"
                    elif rec_side in ('OU Over', 'OU Under'):
                        rec_line = f"(line {nz(p.get('ou_line')):.2f})"
                    rec_html = (
                        f'<div style="font-family:\'Exo 2\';font-weight:700;font-size:0.95rem;color:#00ff88;">'
                        f'💰 แนะนำลง: {rec_side} {rec_line}</div>'
                        f'<div style="font-size:0.8rem;color:#c8e6d4;margin-top:3px;">'
                        f'เงินเดิมพัน: <b>฿{bet_amt:,.0f}</b> @ odds {rec_odds:.2f}</div>'
                    )
                else:
                    rec_html = (
                        f'<div style="font-family:\'Exo 2\';font-weight:700;font-size:0.95rem;color:#ff8c00;">'
                        f'🔴 NO SIGNAL — ไม่แนะนำลงบิลนี้</div>'
                    )

                # ผลแพ้ชนะ (ถ้า settled) — คำนวณสดจากฝั่งที่ถูกต้อง
                result_html = ""
                if mode == 'settled':
                    if rec_side:
                        wf_c, lf_c = settle_ah_ou(rec_side, p.get('ah_line'), p.get('ou_line'),
                                                  p.get('actual_home_goals'), p.get('actual_away_goals'))
                        # คำนวณ PnL สดจากฝั่งที่ถูก (ไม่ใช้ pnl ใน DB ที่อาจผิด)
                        _odds_for_pnl = nz({
                            'AH Home': p.get('ah_home_odds'), 'AH Away': p.get('ah_away_odds'),
                            'OU Over': p.get('ou_over_odds'), 'OU Under': p.get('ou_under_odds'),
                        }.get(rec_side))
                        _bet = nz(p.get('recommended_bet_size'))
                        pnl_card = _bet * wf_c * (_odds_for_pnl - 1) - _bet * lf_c
                        if wf_c > lf_c:
                            outcome_txt = "✅ ชนะเต็ม" if wf_c == 1.0 else "🟢 ชนะครึ่ง"
                            oc_color = "#00ff88"
                        elif lf_c > wf_c:
                            outcome_txt = "❌ แพ้เต็ม" if lf_c == 1.0 else "🔴 แพ้ครึ่ง"
                            oc_color = "#ff3b5c"
                        else:
                            outcome_txt = "➖ คืนทุน (Push)"
                            oc_color = "#4a7a60"
                        pnl_txt = f"฿{pnl_card:+,.0f}"
                    else:
                        outcome_txt = "— (ไม่ได้ลงบิล)"
                        oc_color = "#4a7a60"
                        pnl_txt = "-"
                    result_html = (
                        f'<div style="border-top:1px solid #1a3a2a;margin-top:6px;padding-top:6px;">'
                        f'<span style="font-family:\'Share Tech Mono\';font-size:0.82rem;color:{oc_color};">'
                        f'ผลบิล: {outcome_txt}</span> '
                        f'<span style="font-family:\'Share Tech Mono\';font-size:0.82rem;color:{oc_color};'
                        f'float:right;">PnL: <b>{pnl_txt}</b></span></div>'
                    )

                # แถบเตือนถ้าข้อมูลใน DB เก็บฝั่งผิด (จาก bug เก่า)
                mismatch_html = ""
                if side_mismatch:
                    mismatch_html = (
                        f'<div style="background:#2a1a0d;border-radius:5px;padding:6px 10px;margin-top:6px;">'
                        f'<span style="font-family:\'Rajdhani\';font-size:0.72rem;color:#ff8c00;">'
                        f'⚠️ ข้อมูลเก่าใน DB เคยบันทึกเป็น <b>{db_side}</b> (จาก bug) '
                        f'— การ์ดนี้แสดงฝั่งที่ถูกต้อง <b>{computed_best_side}</b> และคำนวณผล/PnL ใหม่แล้ว</span></div>'
                    )

                st.markdown(
                    f'<div style="background:#060c10;border:1px solid #1a3a2a;border-radius:8px;'
                    f'padding:10px 14px;margin-bottom:10px;">'
                    f'{rec_html}'
                    f'<div style="border-top:1px solid #1a3a2a;margin-top:6px;padding-top:6px;'
                    f'font-family:\'Share Tech Mono\';font-size:0.75rem;color:{div_color};">'
                    f'STAT-DIVERGENCE: {div_label_full} · Δ{div*100:+.0f}% '
                    f'<span style="color:#4a7a60;">(Stat เชียร์ {stat_favors} '
                    f'มากกว่าตลาด)</span></div>'
                    f'{result_html}'
                    f'{mismatch_html}'
                    f'</div>',
                    unsafe_allow_html=True
                )

                # ── แถวที่ 1: Probabilities ──
                ca, cb, cc_col = st.columns(3)
                ca.metric("Market P(Home)", f"{nz(p.get('market_p_home'))*100:.0f}%")
                cb.metric("Stat P(Home)", f"{nz(p.get('stat_p_home'))*100:.0f}%",
                         delta=f"{div*100:+.0f}%",
                         delta_color="off")
                cc_col.metric("Market P(Away)", f"{nz(p.get('market_p_away'))*100:.0f}%")

                st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)

                # ── แถวที่ 2: Gate Scanner (4 ฝั่ง) ──
                st.markdown('<div class="gem-label" style="font-size:0.65rem;">◈ GATE SCANNER</div>',
                           unsafe_allow_html=True)
                sides_info = [
                    ("AH Home", p.get('ah_home_win_rate'), p.get('ah_home_gates_passed'), p.get('ah_home_odds')),
                    ("AH Away", p.get('ah_away_win_rate'), p.get('ah_away_gates_passed'), p.get('ah_away_odds')),
                    ("OU Over", p.get('ou_over_win_rate'), p.get('ou_over_gates_passed'), p.get('ou_over_odds')),
                    ("OU Under", p.get('ou_under_win_rate'), p.get('ou_under_gates_passed'), p.get('ou_under_odds')),
                ]
                g1, g2, g3, g4 = st.columns(4)
                for col, (sname, wr, gp, odds) in zip([g1, g2, g3, g4], sides_info):
                    wr_val = nz(wr) * 100
                    gp_val = int(nz(gp))
                    odds_val = nz(odds)
                    is_rec = sname == side
                    c = "#00ff88" if (gp_val >= 4 and wr_val >= 55) else "#4a7a60"
                    rec_tag = " ⭐" if is_rec else ""
                    col.markdown(
                        f'<div style="border:1px solid {c};border-radius:6px;padding:6px 8px;'
                        f'background:#060c10;text-align:center;">'
                        f'<div style="font-family:\'Share Tech Mono\';font-size:0.65rem;color:{c};">'
                        f'{sname}{rec_tag}</div>'
                        f'<div style="font-size:1rem;font-weight:700;color:{c};">{wr_val:.0f}%</div>'
                        f'<div style="font-size:0.6rem;color:#4a7a60;">{gp_val}/4 gates</div>'
                        f'<div style="font-size:0.65rem;color:#c8e6d4;">@ {odds_val:.2f}</div>'
                        f'</div>', unsafe_allow_html=True
                    )

                st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)

                # ── 🏆 BEST BET RANKING — จัดอันดับ 4 ฝั่ง + ฟันธงฝั่งที่ดีที่สุด ──
                st.markdown('<div class="gem-label" style="font-size:0.65rem;">🏆 ข้อสรุป: ฝั่งไหนน่าลงที่สุด</div>',
                           unsafe_allow_html=True)
                # ให้คะแนนแต่ละฝั่ง = (gates_passed * 100) + win_rate% เพื่อจัดอันดับ
                ranked = []
                for sname, wr, gp, odds in sides_info:
                    wr_v = nz(wr) * 100
                    gp_v = int(nz(gp))
                    od_v = nz(odds)
                    pass_all = gp_v >= 4
                    in_odds = 1.72 <= od_v <= 2.20
                    score = gp_v * 1000 + wr_v
                    ranked.append({
                        'side': sname, 'wr': wr_v, 'gp': gp_v, 'odds': od_v,
                        'pass_all': pass_all, 'in_odds': in_odds, 'score': score
                    })
                ranked.sort(key=lambda x: x['score'], reverse=True)

                # ฝั่งที่ผ่านครบ 4 gates (ลงได้จริง)
                qualified = [r for r in ranked if r['pass_all'] and r['wr'] >= 55]
                thai_name = {'AH Home': 'ต่อ/รอง เจ้าบ้าน (AH Home)',
                            'AH Away': 'ต่อ/รอง ทีมเยือน (AH Away)',
                            'OU Over': 'สูง (Over)', 'OU Under': 'ต่ำ (Under)'}

                if qualified:
                    best = qualified[0]
                    # เช็ค Gate 5 mode กับ divergence
                    g5_note = ""
                    is_home_side = 'Home' in best['side']
                    stat_home = div > 0
                    aligns = (stat_home == is_home_side) if best['side'] in ('AH Home','AH Away') else None
                    if abs(div) >= 0.15 and abs(div) < 0.40 and aligns:
                        g5_note = ("<br><span style='color:#ff8c00;'>⚠️ Gate 5: ฝั่งนี้ตรงกับ Stat "
                                  "ในโซน Moderate ที่ตลาดมักถูกกว่า — พิจารณาลดเงินหรือข้าม</span>")
                    elif abs(div) >= 0.40 and aligns:
                        g5_note = ("<br><span style='color:#ff3b5c;'>🚨 Gate 5: Divergence สูงมาก "
                                  "(ข้อมูลน้อย) — ระวัง</span>")

                    verdict_html = (
                        f'<div style="background:linear-gradient(135deg,#0a2a18,#0d1e2e);'
                        f'border:1px solid #00ff8855;border-left:4px solid #00ff88;border-radius:8px;'
                        f'padding:12px 16px;margin-bottom:8px;">'
                        f'<div style="font-family:\'Exo 2\';font-weight:800;font-size:1.05rem;color:#00ff88;">'
                        f'✅ ลงฝั่งนี้: {thai_name.get(best["side"], best["side"])}</div>'
                        f'<div style="font-family:\'Share Tech Mono\';font-size:0.8rem;color:#c8e6d4;margin-top:4px;">'
                        f'Win Rate {best["wr"]:.0f}% · ผ่าน {best["gp"]}/4 gates · @ {best["odds"]:.2f}'
                        f'{g5_note}</div></div>'
                    )
                    if len(qualified) > 1:
                        alts = " · ".join(f"{r['side']} ({r['wr']:.0f}%)" for r in qualified[1:])
                        verdict_html += (
                            f'<div style="font-family:\'Rajdhani\';font-size:0.72rem;color:#7a9a88;'
                            f'margin-bottom:8px;">ทางเลือกรอง: {alts}</div>'
                        )
                else:
                    # ไม่มีฝั่งไหนผ่านครบ — แสดงฝั่งที่ใกล้สุด
                    top = ranked[0]
                    verdict_html = (
                        f'<div style="background:#1e0d0d;border:1px solid #ff3b5c55;'
                        f'border-left:4px solid #ff3b5c;border-radius:8px;padding:12px 16px;margin-bottom:8px;">'
                        f'<div style="font-family:\'Exo 2\';font-weight:800;font-size:1.05rem;color:#ff3b5c;">'
                        f'🔴 ไม่แนะนำลงคู่นี้ (No Signal)</div>'
                        f'<div style="font-family:\'Share Tech Mono\';font-size:0.78rem;color:#c8e6d4;margin-top:4px;">'
                        f'ไม่มีฝั่งไหนผ่านครบ 4 gates + WR≥55%<br>'
                        f'ใกล้สุด: {top["side"]} ({top["wr"]:.0f}%, {top["gp"]}/4 gates)</div></div>'
                    )
                st.markdown(verdict_html, unsafe_allow_html=True)

                # ── 🧪 สัญญาณเสริม (ทดลอง) — แสดงข้อมูล ไม่บังคับ ──
                edge_signals = compute_edge_signals(p)
                if edge_signals:
                    sig_color = {'strong': '#ffd700', 'positive': '#00ff88', 'neutral': '#7a9a88', 'caution': '#ff8c00'}
                    sig_icon = {'strong': '⭐', 'positive': '🟢', 'neutral': '⚪', 'caution': '🟠'}
                    pos_count = sum(1 for s in edge_signals if s['status'] in ('strong', 'positive'))
                    has_combo = any(s['status'] == 'strong' for s in edge_signals)
                    edge_html = (
                        f'<div style="background:#0a1520;border:1px dashed #2a4a5a;border-radius:8px;'
                        f'padding:10px 14px;margin-bottom:8px;">'
                        f'<div style="font-family:\'Share Tech Mono\';font-size:0.7rem;color:#5a8a9a;'
                        f'margin-bottom:6px;">🧪 สัญญาณเสริม (ทดลอง · ยังไม่ใช้ตัดสินใจอัตโนมัติ) '
                        f'· บวก {pos_count}/{len(edge_signals)}</div>'
                    )
                    for s in edge_signals:
                        c = sig_color[s['status']]
                        edge_html += (
                            f'<div style="display:flex;align-items:center;gap:8px;margin:3px 0;">'
                            f'<span>{sig_icon[s["status"]]}</span>'
                            f'<span style="font-family:\'Rajdhani\';font-size:0.78rem;color:{c};'
                            f'font-weight:600;min-width:160px;">{s["label"]}</span>'
                            f'<span style="font-family:\'Rajdhani\';font-size:0.7rem;color:#5a7a68;">'
                            f'{s["detail"]}</span></div>'
                        )
                    edge_html += '</div>'
                    st.markdown(edge_html, unsafe_allow_html=True)

                st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
                # ── 📊 ราคาตลาด: ASIAN HANDICAP + TOTAL GOALS (O/U) ──
                ah_line_v = nz(p.get('ah_line'))
                ah_h_odds = nz(p.get('ah_home_odds'))
                ah_a_odds = nz(p.get('ah_away_odds'))
                ou_line_v = nz(p.get('ou_line'))
                ou_o_odds = nz(p.get('ou_over_odds'))
                ou_u_odds = nz(p.get('ou_under_odds'))
                # แสดง line ในรูปแบบที่อ่านง่าย (+ เจ้าบ้านต่อ / - เจ้าบ้านรอง)
                if ah_line_v > 0:
                    ah_line_txt = f"เจ้าบ้านต่อ {abs(ah_line_v):g}"
                elif ah_line_v < 0:
                    ah_line_txt = f"เจ้าบ้านรอง {abs(ah_line_v):g}"
                else:
                    ah_line_txt = "เสมอ (0)"
                rec = side  # ฝั่งที่แนะนำ เพื่อ highlight
                ah_h_hl = "#00ff88" if rec == 'AH Home' else "#c8e6d4"
                ah_a_hl = "#00ff88" if rec == 'AH Away' else "#c8e6d4"
                ou_o_hl = "#00ff88" if rec == 'OU Over' else "#c8e6d4"
                ou_u_hl = "#00ff88" if rec == 'OU Under' else "#c8e6d4"

                st.markdown(
                    f'<div style="display:flex;gap:10px;flex-wrap:wrap;">'
                    # ASIAN HANDICAP card
                    f'<div style="flex:1;min-width:160px;background:#0d1e2e;border-radius:8px;'
                    f'padding:10px 14px;border-top:2px solid #00b4ff;">'
                    f'<div style="font-family:\'Share Tech Mono\';font-size:0.7rem;color:#00b4ff;'
                    f'letter-spacing:1px;margin-bottom:6px;">⚖️ ASIAN HANDICAP</div>'
                    f'<div style="font-family:\'Rajdhani\';font-size:0.74rem;color:#7a9a88;margin-bottom:6px;">'
                    f'{ah_line_txt}</div>'
                    f'<div style="display:flex;justify-content:space-between;font-family:\'Share Tech Mono\';'
                    f'font-size:0.82rem;">'
                    f'<span style="color:{ah_h_hl};">เจ้าบ้าน {ah_h_odds:.2f}{" ⭐" if rec=="AH Home" else ""}</span>'
                    f'<span style="color:{ah_a_hl};">เยือน {ah_a_odds:.2f}{" ⭐" if rec=="AH Away" else ""}</span>'
                    f'</div></div>'
                    # TOTAL GOALS card
                    f'<div style="flex:1;min-width:160px;background:#0d1e2e;border-radius:8px;'
                    f'padding:10px 14px;border-top:2px solid #ff8c00;">'
                    f'<div style="font-family:\'Share Tech Mono\';font-size:0.7rem;color:#ff8c00;'
                    f'letter-spacing:1px;margin-bottom:6px;">🥅 TOTAL GOALS (O/U)</div>'
                    f'<div style="font-family:\'Rajdhani\';font-size:0.74rem;color:#7a9a88;margin-bottom:6px;">'
                    f'เส้น {ou_line_v:g}</div>'
                    f'<div style="display:flex;justify-content:space-between;font-family:\'Share Tech Mono\';'
                    f'font-size:0.82rem;">'
                    f'<span style="color:{ou_o_hl};">สูง {ou_o_odds:.2f}{" ⭐" if rec=="OU Over" else ""}</span>'
                    f'<span style="color:{ou_u_hl};">ต่ำ {ou_u_odds:.2f}{" ⭐" if rec=="OU Under" else ""}</span>'
                    f'</div></div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

                st.markdown('<div style="height:10px;"></div>', unsafe_allow_html=True)

                tg1, tg2 = st.columns(2)
                tg1.metric("Market Total Goals Line", f"{nz(p.get('market_total')):.2f}")
                tg2.metric("Stat Total Goals", f"{nz(p.get('stat_total')):.2f}",
                          delta=f"{nz(p.get('divergence_goals')):+.2f}")

                if pd.notna(p.get('home_w')):
                    st.markdown('<div class="gem-label" style="font-size:0.65rem;">◈ STATS (5 นัดล่าสุด)</div>',
                               unsafe_allow_html=True)
                    s1, s2 = st.columns(2)
                    with s1:
                        hw = int(nz(p.get('home_w'))); hd = int(nz(p.get('home_d')))
                        hl = int(nz(p.get('home_l')))
                        hgf = nz(p.get('home_gf')); hga = nz(p.get('home_ga'))
                        st.markdown(
                            f'<div style="background:#0d1e2e;border-left:3px solid #00ff88;'
                            f'padding:8px 10px;border-radius:0 4px 4px 0;">'
                            f'<div style="font-size:0.7rem;color:#00ff88;">🏠 HOME</div>'
                            f'<div style="font-size:0.78rem;color:#c8e6d4;">'
                            f'WR: <b>{hw/5*100:.0f}%</b> ({hw}W/{hd}D/{hl}L)<br>'
                            f'Goals: {hgf/5:.1f} scored / {hga/5:.1f} conceded<br>'
                            f'Rank: #{p.get("home_rank") or "-"}</div></div>',
                            unsafe_allow_html=True
                        )
                    with s2:
                        aw = int(nz(p.get('away_w'))); ad = int(nz(p.get('away_d')))
                        al = int(nz(p.get('away_l')))
                        agf = nz(p.get('away_gf')); aga = nz(p.get('away_ga'))
                        st.markdown(
                            f'<div style="background:#0d1e2e;border-left:3px solid #ff8c00;'
                            f'padding:8px 10px;border-radius:0 4px 4px 0;">'
                            f'<div style="font-size:0.7rem;color:#ff8c00;">✈️ AWAY</div>'
                            f'<div style="font-size:0.78rem;color:#c8e6d4;">'
                            f'WR: <b>{aw/5*100:.0f}%</b> ({aw}W/{ad}D/{al}L)<br>'
                            f'Goals: {agf/5:.1f} scored / {aga/5:.1f} conceded<br>'
                            f'Rank: #{p.get("away_rank") or "-"}</div></div>',
                            unsafe_allow_html=True
                        )

                # ── Math internals (collapsible) ──
                if pd.notna(p.get('math_lambda_home')):
                    with st.expander("🔬 Math Engine Details", expanded=False):
                        lh_v = nz(p.get('math_lambda_home'))
                        la_v = nz(p.get('math_lambda_away'))
                        conv = p.get('auto_fit_converged')
                        loss = p.get('auto_fit_loss')
                        loss_str = f"{loss:.5f}" if pd.notna(loss) else "N/A"
                        slh = nz(p.get("stat_lambda_home"))
                        sla = nz(p.get("stat_lambda_away"))
                        st.markdown(
                            f'<div style="font-family:\'Share Tech Mono\';font-size:0.72rem;color:#c8e6d4;'
                            f'background:#0d1e2e;padding:8px 10px;border-radius:4px;">'
                            f'λ_home={lh_v:.3f} · λ_away={la_v:.3f}<br>'
                            f'Auto-Fit: {"✅ CONVERGED" if conv else "⚠️ DIVERGED"} '
                            f'(loss={loss_str})<br>'
                            f'Stat λ_h={slh:.2f} · '
                            f'Stat λ_a={sla:.2f}</div>',
                            unsafe_allow_html=True
                        )

                # ── Settle section (pending only) ──
                if mode == 'pending':
                    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
                    st.markdown('<div style="font-family:\'Share Tech Mono\';font-size:0.7rem;color:#ffd600;">'
                               '📝 กรอกผลการแข่งขัน</div>', unsafe_allow_html=True)
                    rc1, rc2, rc3 = st.columns([2, 2, 3])
                    home_goals = rc1.number_input("ประตู Home", 0, 20, key=f"hg_{rec_id}")
                    away_goals = rc2.number_input("ประตู Away", 0, 20, key=f"ag_{rec_id}")
                    with rc3:
                        st.write("")
                        st.write("")
                        if st.button("✅ บันทึกผล", key=f"settle_{rec_id}", use_container_width=True):
                            if home_goals > away_goals: actual_result = 'home_win'
                            elif away_goals > home_goals: actual_result = 'away_win'
                            else: actual_result = 'draw'
                            actual_total = home_goals + away_goals
                            wl_w = compute_wl_winner(p['market_p_home'], p['stat_p_home'], actual_result)
                            goals_w = compute_goals_winner(p['market_total'], p['stat_total'], actual_total)
                            ok = db_update_result(rec_id, {
                                'actual_result': actual_result,
                                'actual_score': f"{home_goals}-{away_goals}",
                                'actual_home_goals': home_goals,
                                'actual_away_goals': away_goals,
                                'actual_total_goals': actual_total,
                                'wl_winner': wl_w, 'goals_winner': goals_w,
                            })
                            if ok:
                                st.cache_data.clear()
                                st.rerun()

                # ── Stat-vs-Market analysis (settled only) ──
                if mode == 'settled':
                    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
                    st.markdown('<div class="gem-label" style="font-size:0.65rem;">'
                               '◈ STAT vs MARKET — ใครทำนายแม่นกว่า</div>',
                               unsafe_allow_html=True)
                    r1, r2, r3, r4 = st.columns(4)
                    r1.metric("สกอร์จริง", p.get('actual_score', '-'))
                    wl_w = p.get('wl_winner', '-')
                    gl_w = p.get('goals_winner', '-')
                    r2.metric("W/L ทายแม่น", "Market" if wl_w=='market' else ("Stat" if wl_w=='stat' else "เสมอ"),
                             help="ใครทำนายผลแพ้ชนะ (1X2) ใกล้ความจริงกว่า")
                    r3.metric("Goals ทายแม่น", "Market" if gl_w=='market' else ("Stat" if gl_w=='stat' else "เสมอ"),
                             help="ใครทำนายจำนวนประตูรวมใกล้กว่า")
                    pnl = p.get('pnl')
                    r4.metric("PnL บิลนี้", f"฿{pnl:+,.0f}" if pd.notna(pnl) else "-")

                    # ── 🔍 ตรวจสอบผลทุกฝั่ง — เช็คว่าโปรแกรมคำนวณถูกไหม ──
                    st.markdown('<div class="gem-label" style="font-size:0.65rem;margin-top:8px;">'
                               '🔍 ผลจริงทุกฝั่ง (ตรวจสอบการคำนวณ)</div>',
                               unsafe_allow_html=True)
                    hg_v = p.get('actual_home_goals')
                    ag_v = p.get('actual_away_goals')
                    if pd.notna(hg_v) and pd.notna(ag_v):
                        all_sides = [
                            ('AH Home', 'ต่อ/รอง เจ้าบ้าน', p.get('ah_home_odds')),
                            ('AH Away', 'ต่อ/รอง ทีมเยือน', p.get('ah_away_odds')),
                            ('OU Over', 'สูง (Over)', p.get('ou_over_odds')),
                            ('OU Under', 'ต่ำ (Under)', p.get('ou_under_odds')),
                        ]
                        verify_html = '<div style="display:flex;flex-direction:column;gap:5px;">'
                        for side_key, side_th, side_odds in all_sides:
                            wf_v, lf_v = settle_ah_ou(side_key, p.get('ah_line'), p.get('ou_line'), hg_v, ag_v)
                            if wf_v == 1.0:
                                res_txt, res_color = "✅ ชนะเต็ม", "#00ff88"
                            elif wf_v == 0.5:
                                res_txt, res_color = "🟢 ชนะครึ่ง", "#7dd87d"
                            elif wf_v == lf_v:
                                res_txt, res_color = "➖ คืนทุน", "#7a9a88"
                            elif lf_v == 0.5:
                                res_txt, res_color = "🔴 แพ้ครึ่ง", "#d87d7d"
                            else:
                                res_txt, res_color = "❌ แพ้เต็ม", "#ff3b5c"
                            # ไฮไลต์ฝั่งที่ระบบแนะนำ
                            is_rec = (side_key == side)
                            border = "2px solid #00ff88" if is_rec else "1px solid #1a2e3e"
                            star = " ⭐" if is_rec else ""
                            verify_html += (
                                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                                f'background:#0d1e2e;border:{border};border-radius:6px;padding:6px 12px;">'
                                f'<span style="font-family:\'Share Tech Mono\';font-size:0.78rem;color:#c8e6d4;">'
                                f'{side_key} <span style="color:#5a7a68;">· {side_th}</span>{star}</span>'
                                f'<span style="font-family:\'Rajdhani\';font-size:0.8rem;color:{res_color};'
                                f'font-weight:600;">{res_txt}</span></div>'
                            )
                        verify_html += '</div>'
                        st.markdown(verify_html, unsafe_allow_html=True)
                        st.caption("⭐ = ฝั่งที่ระบบแนะนำ · ใช้ตรวจว่า PnL ด้านบนตรงกับผลฝั่งที่แนะนำไหม")

                    # ── ปุ่มยกเลิกผล (un-settle) — กลับไปเป็น pending เพื่อแก้ผลที่กรอกพลาด ──
                    unsettle_key = f"unsettle_{rec_id}"
                    confirm_unsettle = f"confirm_unsettle_{rec_id}"
                    if not st.session_state.get(confirm_unsettle):
                        if st.button("↩️ ยกเลิกผล (กลับเป็น Pending)", key=unsettle_key,
                                    use_container_width=True):
                            st.session_state[confirm_unsettle] = True
                            st.rerun()
                    else:
                        st.warning("⚠️ ยกเลิกผลคู่นี้ กลับไปสถานะรอกรอกผล?")
                        uc1, uc2 = st.columns(2)
                        if uc1.button("✅ ยืนยัน", key=f"{unsettle_key}_yes",
                                     use_container_width=True, type="primary"):
                            ok = db_update_result(rec_id, {
                                'actual_result': None, 'actual_score': None,
                                'actual_home_goals': None, 'actual_away_goals': None,
                                'actual_total_goals': None, 'wl_winner': None,
                                'goals_winner': None, 'pnl': None, 'bet_outcome': None,
                            })
                            if ok:
                                st.session_state[confirm_unsettle] = False
                                st.cache_data.clear()
                                st.rerun()
                        if uc2.button("❌ ไม่ยกเลิก", key=f"{unsettle_key}_no",
                                     use_container_width=True):
                            st.session_state[confirm_unsettle] = False
                            st.rerun()

                # ── ปุ่มลบ log รายตัว (ทุก card) ──
                st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
                del_key = f"del_{rec_id}"
                confirm_key = f"confirm_del_{rec_id}"
                if not st.session_state.get(confirm_key):
                    if st.button("🗑️ ยกเลิก/ลบ Log นี้", key=del_key, use_container_width=True):
                        st.session_state[confirm_key] = True
                        st.rerun()
                else:
                    st.warning("⚠️ ยืนยันลบ log นี้ถาวร?")
                    dc1, dc2 = st.columns(2)
                    if dc1.button("✅ ลบเลย", key=f"{del_key}_yes", use_container_width=True, type="primary"):
                        if db_delete_one(rec_id):
                            st.session_state[confirm_key] = False
                            st.cache_data.clear()
                            st.rerun()
                    if dc2.button("❌ ไม่ลบ", key=f"{del_key}_no", use_container_width=True):
                        st.session_state[confirm_key] = False
                        st.rerun()

        # ── PENDING SECTION ──
        st.markdown(
            f'<div style="font-family:\'Share Tech Mono\';font-size:0.78rem;color:#ffd600;'
            f'border-left:3px solid #ffd600;padding:6px 10px;margin-bottom:8px;">'
            f'⏳ PENDING — รอกรอกผล ({len(pending_df)} คู่)</div>',
            unsafe_allow_html=True
        )
        if len(pending_df) == 0:
            st.caption("ไม่มี prediction ที่รอผล")
        else:
            for _, p in pending_df.iterrows():
                render_prediction_card(p.to_dict(), mode='pending')

        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)

        # ── SETTLED SECTION ──
        st.markdown(
            f'<div style="font-family:\'Share Tech Mono\';font-size:0.78rem;color:#00ff88;'
            f'border-left:3px solid #00ff88;padding:6px 10px;margin-bottom:8px;">'
            f'✅ SETTLED — มีผลแล้ว ({len(settled_df_raw)} คู่)</div>',
            unsafe_allow_html=True
        )
        if len(settled_df_raw) == 0:
            st.caption("ยังไม่มี prediction ที่ settle แล้ว")
        else:
            for _, p in settled_df_raw.iterrows():
                render_prediction_card(p.to_dict(), mode='settled')

        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
        if st.button("🗑️ ล้าง Predictions Log ทั้งหมด (ลบจากฐานข้อมูลถาวร!)"):
            st.session_state['_confirm_delete_all'] = True
        if st.session_state.get('_confirm_delete_all'):
            st.warning("⚠️ การลบนี้จะลบข้อมูลทั้งหมดในฐานข้อมูลถาวร ไม่สามารถกู้คืนได้")
            cc1, cc2 = st.columns(2)
            if cc1.button("✅ ยืนยันลบทั้งหมด", type="primary"):
                if db_delete_all():
                    st.session_state['_confirm_delete_all'] = False
                    st.cache_data.clear()
                    st.rerun()
            if cc2.button("❌ ยกเลิก"):
                st.session_state['_confirm_delete_all'] = False
                st.rerun()


# ════════════════════════════════════════════════════════════════════════
# 🧪 TAB 3: BACKTEST LAB — Hypothesis Tester (แทน Optimizer เดิม)
# ════════════════════════════════════════════════════════════════════════
def calc_ci_95(p_hat, n):
    """95% confidence interval ของสัดส่วน (Wilson-ish normal approx)"""
    if n == 0:
        return 0, 0
    se = math.sqrt(max(p_hat * (1 - p_hat), 0.0001) / n)
    return max(0, p_hat - 1.96 * se), min(1, p_hat + 1.96 * se)


with tab_backtest:
    st.markdown('<div class="gem-label">◈ 🧪 HYPOTHESIS LAB</div>', unsafe_allow_html=True)
    st.caption("ทดสอบสมมุติฐาน Stat-vs-Market จากข้อมูลจริงใน Supabase (settle แล้ว)")

    log_df_bt = db_load_predictions()
    log = log_df_bt.to_dict('records') if not log_df_bt.empty else []
    settled = [p for p in log if is_settled(p)]

    if len(settled) < 3:
        st.markdown(
            f'<div style="background:#0d1e2e;border-left:3px solid #ffd600;padding:16px 20px;'
            f'border-radius:0 8px 8px 0;">'
            f'<div style="font-family:\'Exo 2\';font-size:1rem;color:#ffd600;font-weight:700;">'
            f'⏳ ข้อมูลยังไม่พอ</div>'
            f'<div style="font-family:\'Rajdhani\';font-size:0.85rem;color:#c8e6d4;margin-top:6px;">'
            f'มี {len(settled)} เคสที่ settle แล้ว — ต้องการอย่างน้อย 15-20 เคสเพื่อเริ่มมีความหมายทางสถิติ'
            f'</div></div>',
            unsafe_allow_html=True
        )
    else:
        for p in settled:
            p['_abs_div'] = abs(p.get('divergence_wl') or 0)

        # ── helper ──
        def _ci95(k, n):
            if n == 0: return (0, 0)
            ph = k/n; se = (max(ph*(1-ph), 1e-9)/n)**0.5
            return (max(0, ph-1.96*se), min(1, ph+1.96*se))

        def _settle(side, ah, ou, hg, ag):
            hg = hg if pd.notna(hg) else 0; ag = ag if pd.notna(ag) else 0
            if side in ('AH Home','AH Away'):
                if pd.isna(ah): return (0.0,0.0)
                adj = ((hg-ag)-ah) if side=='AH Home' else ((ag-hg)+ah)
            elif side in ('OU Over','OU Under'):
                if pd.isna(ou): return (0.0,0.0)
                t=hg+ag; adj=(t-ou) if side=='OU Over' else (ou-t)
            else: return (0.0,0.0)
            adj = round(adj*4)/4
            if adj>=0.5: return (1.0,0.0)
            if adj==0.25: return (0.5,0.0)
            if adj==0: return (0.0,0.0)
            if adj==-0.25: return (0.0,0.5)
            return (0.0,1.0)

        n_settled = len(settled)
        n_pending = len([p for p in log if not is_settled(p)])

        # ═══════════ OVERVIEW STRIP ═══════════
        st.markdown(
            f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px;">'
            f'<div style="flex:1;min-width:100px;background:#0d1e2e;border-radius:8px;padding:12px 14px;text-align:center;">'
            f'<div style="font-family:\'Share Tech Mono\';font-size:1.6rem;color:#00ff88;">{n_settled}</div>'
            f'<div style="font-family:\'Rajdhani\';font-size:0.7rem;color:#7a9a88;">SETTLED</div></div>'
            f'<div style="flex:1;min-width:100px;background:#0d1e2e;border-radius:8px;padding:12px 14px;text-align:center;">'
            f'<div style="font-family:\'Share Tech Mono\';font-size:1.6rem;color:#ffd600;">{n_pending}</div>'
            f'<div style="font-family:\'Rajdhani\';font-size:0.7rem;color:#7a9a88;">PENDING</div></div>'
            f'<div style="flex:1;min-width:100px;background:#0d1e2e;border-radius:8px;padding:12px 14px;text-align:center;">'
            f'<div style="font-family:\'Share Tech Mono\';font-size:1.6rem;color:#00b4ff;">{n_settled+n_pending}</div>'
            f'<div style="font-family:\'Rajdhani\';font-size:0.7rem;color:#7a9a88;">TOTAL</div></div>'
            f'</div>',
            unsafe_allow_html=True
        )

        # ═══════════ SECTION 1: DIVERGENCE BUCKETS ═══════════
        st.markdown('<div class="gem-label">◈ STAT-DIVERGENCE — ใครทำนายแม่นกว่า</div>',
                   unsafe_allow_html=True)
        st.caption("เมื่อ Stat ต่างจากตลาดมากขึ้น ใครทำนายผลแพ้ชนะแม่นกว่ากัน")

        buckets = [(0, 0.15, "LOW", "<15%", "#4a7a60"),
                   (0.15, 0.40, "MODERATE", "15-40%", "#ff8c00"),
                   (0.40, 1.01, "EXTREME", "≥40%", "#ff3b5c")]

        for lo, hi, name, rng, color in buckets:
            sub = [p for p in settled if lo <= p['_abs_div'] < hi]
            n = len(sub)
            mkt = sum(1 for p in sub if p.get('wl_winner')=='market')
            stat = sum(1 for p in sub if p.get('wl_winner')=='stat')
            neu = sum(1 for p in sub if p.get('wl_winner')=='neutral')
            dec = mkt + stat
            if n == 0:
                continue
            mkt_pct = mkt/dec*100 if dec>0 else 0
            stat_pct = stat/dec*100 if dec>0 else 0
            # bar แสดงสัดส่วน market vs stat
            winner_txt = ""
            if dec > 0:
                lo_c, hi_c = _ci95(max(mkt,stat), dec)
                w_name = "Market" if mkt>=stat else "Stat"
                sig = "✅ ชัดเจน" if (lo_c > 0.5) else "⚠️ ยังไม่ชัด"
                winner_txt = f"{w_name} แม่นกว่า {max(mkt_pct,stat_pct):.0f}% · {sig}"

            # AH bet จริง (เล่นตามฝั่ง stat) ในแต่ละ bucket — ต่างจาก wl_winner
            ah_w = ah_l = 0
            for p in sub:
                div = p.get('divergence_wl') or 0
                bet_side = 'AH Home' if div > 0 else 'AH Away'
                wf, lf = settle_ah_ou(bet_side, p.get('ah_line'), p.get('ou_line'),
                                      p.get('actual_home_goals'), p.get('actual_away_goals'))
                if wf > lf: ah_w += 1
                elif lf > wf: ah_l += 1
            ah_dec = ah_w + ah_l
            ah_wr = ah_w / ah_dec * 100 if ah_dec > 0 else 0
            ah_txt = f"เล่น AH ตาม Stat: {ah_wr:.0f}% (W{ah_w}-L{ah_l})" if ah_dec > 0 else ""

            st.markdown(
                f'<div style="background:#0d1e2e;border-radius:10px;padding:14px 16px;margin-bottom:10px;'
                f'border-left:3px solid {color};">'
                f'<div style="display:flex;justify-content:space-between;margin-bottom:8px;">'
                f'<span style="font-family:\'Exo 2\';font-weight:700;color:{color};font-size:0.9rem;">'
                f'{name} <span style="color:#5a7a68;font-size:0.75rem;">({rng})</span></span>'
                f'<span style="font-family:\'Share Tech Mono\';font-size:0.78rem;color:#7a9a88;">n={n}</span>'
                f'</div>'
                # สัดส่วน bar
                f'<div style="display:flex;height:26px;border-radius:5px;overflow:hidden;background:#060c10;">'
                f'<div style="width:{mkt_pct}%;background:linear-gradient(90deg,#0088cc,#00b4ff);'
                f'display:flex;align-items:center;justify-content:center;font-family:\'Share Tech Mono\';'
                f'font-size:0.72rem;color:#fff;">{f"Mkt {mkt}" if mkt_pct>15 else ""}</div>'
                f'<div style="width:{stat_pct}%;background:linear-gradient(90deg,#7d3c98,#9b59b6);'
                f'display:flex;align-items:center;justify-content:center;font-family:\'Share Tech Mono\';'
                f'font-size:0.72rem;color:#fff;">{f"Stat {stat}" if stat_pct>15 else ""}</div>'
                f'</div>'
                f'<div style="font-family:\'Rajdhani\';font-size:0.74rem;color:#c8e6d4;margin-top:6px;">'
                f'<span style="color:#9b8bb5;">[Calibration]</span> {winner_txt} · เสมอ {neu}</div>'
                f'<div style="font-family:\'Rajdhani\';font-size:0.74rem;color:#7dd87d;margin-top:2px;">'
                f'<span style="color:#5a9a6a;">[เดิมพันจริง]</span> {ah_txt}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

        # ═══════════ SECTION 2: STRATEGY COMPARISON ═══════════
        st.markdown('<div class="gem-label" style="margin-top:18px;">◈ เทียบกลยุทธ์ Gate 5 (AH จริง)</div>',
                   unsafe_allow_html=True)
        st.caption("จำลองเล่น AH ตามแต่ละกลยุทธ์ บนข้อมูลจริง (odds 1.90, flat 100/บิล)")

        pool = [p for p in settled if pd.notna(p.get('ah_line'))]
        odds_a = 1.90

        def run_strat(mode):
            pnl=inv=0.0; bets=w=l=0
            for p in pool:
                div = p.get('divergence_wl') or 0; ad = abs(div); sh = div>0
                if mode=='skip' and 0.15<=ad<0.40: continue
                if mode=='low' and ad>=0.15: continue
                side_home = (not sh) if (mode=='flip' and 0.15<=ad<0.40) else sh
                side = 'AH Home' if side_home else 'AH Away'
                wf,lf = _settle(side, p.get('ah_line'), p.get('ou_line'),
                               p.get('actual_home_goals'), p.get('actual_away_goals'))
                inv+=100; bets+=1; pnl += 100*wf*(odds_a-1) - 100*lf
                if wf>lf: w+=1
                elif lf>wf: l+=1
            roi = pnl/inv*100 if inv>0 else 0
            return bets, pnl, roi, w, l

        strats = [
            ('follow', 'A · ตาม Stat ทุกเคส', '#7a9a88'),
            ('skip', 'B · ข้าม Moderate (SKIP) ⭐', '#00ff88'),
            ('flip', 'C · พลิกตามตลาด (FLIP)', '#00b4ff'),
            ('low', 'D · เล่นเฉพาะ Low', '#9b59b6'),
        ]
        # หา max abs ROI เพื่อ scale bar
        results = {code: run_strat(code) for code,_,_ in strats}
        max_roi = max(abs(r[2]) for r in results.values()) or 1

        for code, label, color in strats:
            bets, pnl, roi, w, l = results[code]
            bar_w = abs(roi)/max_roi*50  # ครึ่งความกว้าง (center=50%)
            roi_color = "#00ff88" if roi>=0 else "#ff3b5c"
            # bar จาก center
            if roi >= 0:
                bar_html = (f'<div style="position:absolute;left:50%;width:{bar_w}%;height:100%;'
                           f'background:linear-gradient(90deg,{roi_color}66,{roi_color});border-radius:0 4px 4px 0;"></div>')
            else:
                bar_html = (f'<div style="position:absolute;right:50%;width:{bar_w}%;height:100%;'
                           f'background:linear-gradient(90deg,{roi_color},{roi_color}66);border-radius:4px 0 0 4px;"></div>')
            st.markdown(
                f'<div style="background:#0d1e2e;border-radius:8px;padding:10px 14px;margin-bottom:8px;'
                f'border-left:3px solid {color};">'
                f'<div style="display:flex;justify-content:space-between;margin-bottom:6px;">'
                f'<span style="font-family:\'Rajdhani\';font-size:0.85rem;color:#c8e6d4;font-weight:600;">{label}</span>'
                f'<span style="font-family:\'Share Tech Mono\';font-size:0.9rem;color:{roi_color};font-weight:700;">'
                f'ROI {roi:+.1f}%</span></div>'
                f'<div style="position:relative;height:14px;background:#060c10;border-radius:4px;overflow:hidden;">'
                f'<div style="position:absolute;left:50%;width:1px;height:100%;background:#3a5a48;"></div>'
                f'{bar_html}</div>'
                f'<div style="font-family:\'Rajdhani\';font-size:0.7rem;color:#7a9a88;margin-top:4px;">'
                f'{bets} บิล · ชนะ {w} แพ้ {l} · PnL ฿{pnl:+,.0f}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

        st.markdown(
            '<div style="background:#0d1e2e;border-left:3px solid #00ff88;padding:10px 14px;'
            'border-radius:0 6px 6px 0;margin-top:6px;">'
            '<span style="font-family:\'Rajdhani\';font-size:0.78rem;color:#c8e6d4;">'
            '💡 SKIP (⭐ default) เลือกเป็นค่าเริ่มต้นเพราะปลอดภัยสุด — ข้ามเคสที่ Stat สวนตลาด '
            'ในโซน Moderate ที่พิสูจน์แล้วว่า Stat มักพลาด</span></div>',
            unsafe_allow_html=True
        )

        # ═══════════ SECTION 3: GOALS BY TIER ═══════════
        st.markdown('<div class="gem-label" style="margin-top:18px;">◈ Total Goals — Stat มี edge ในลีกไหน</div>',
                   unsafe_allow_html=True)
        tier_colors = {'women':'#9b59b6','major':'#00b4ff','niche':'#4a7a60','cup_no_rank':'#ff8c00'}
        any_tier = False
        for tier in ['women','cup_no_rank','niche','major']:
            sub = [p for p in settled if p.get('league_tier')==tier and p.get('goals_winner')]
            n=len(sub)
            if n==0: continue
            any_tier=True
            stat=sum(1 for p in sub if p.get('goals_winner')=='stat')
            mkt=sum(1 for p in sub if p.get('goals_winner')=='market')
            dec=stat+mkt
            stat_pct = stat/dec*100 if dec>0 else 0
            tc = tier_colors.get(tier,'#4a7a60')
            edge = "Stat มี edge" if stat_pct>55 else ("ตลาดดีกว่า" if stat_pct<45 else "เสมอตัว")
            st.markdown(
                f'<div style="background:#0d1e2e;border-radius:8px;padding:10px 14px;margin-bottom:8px;'
                f'border-left:3px solid {tc};">'
                f'<div style="display:flex;justify-content:space-between;">'
                f'<span style="font-family:\'Share Tech Mono\';font-size:0.82rem;color:{tc};">{tier}</span>'
                f'<span style="font-family:\'Rajdhani\';font-size:0.75rem;color:#c8e6d4;">'
                f'Stat {stat_pct:.0f}% · {edge}</span></div>'
                f'<div style="font-family:\'Rajdhani\';font-size:0.7rem;color:#7a9a88;margin-top:3px;">'
                f'n={n} · Stat ชนะ {stat} / Market ชนะ {mkt}</div></div>',
                unsafe_allow_html=True
            )
        if not any_tier:
            st.caption("ยังไม่มีข้อมูล goals_winner เพียงพอ")

        # ═══════════ SECTION 4: EDGE SIGNAL TRACKING (ทดลอง) ═══════════
        st.markdown('<div class="gem-label" style="margin-top:18px;">🧪 ติดตามสัญญาณเสริม (ทดลอง)</div>',
                   unsafe_allow_html=True)
        st.caption("ดูว่าสัญญาณที่ 'ดูมีแนวโน้ม' ยัง hold ไหมเมื่อข้อมูลมากขึ้น — ยังไม่ใช้ตัดสินใจอัตโนมัติ")

        # คำนวณ WR ของบิล (เล่นตามฝั่ง stat) แยกตามว่ามีสัญญาณบวกไหม
        def _ah_outcome(p):
            div = p.get('divergence_wl') or 0
            side = 'AH Home' if div > 0 else 'AH Away'
            wf, lf = settle_ah_ou(side, p.get('ah_line'), p.get('ou_line'),
                                  p.get('actual_home_goals'), p.get('actual_away_goals'))
            if wf > lf: return 1
            if lf > wf: return 0
            return None

        def _over_outcome(p):
            wf, lf = settle_ah_ou('OU Over', p.get('ah_line'), p.get('ou_line'),
                                  p.get('actual_home_goals'), p.get('actual_away_goals'))
            if wf > lf: return 1
            if lf > wf: return 0
            return None

        def _home_outcome(p):
            wf, lf = settle_ah_ou('AH Home', p.get('ah_line'), p.get('ou_line'),
                                  p.get('actual_home_goals'), p.get('actual_away_goals'))
            if wf > lf: return 1
            if lf > wf: return 0
            return None

        def _safe_num(v):
            if v is None: return None
            try:
                return None if pd.isna(v) else float(v)
            except (TypeError, ValueError): return None

        # (label, condition, outcome_fn) — แต่ละ edge เล่นทิศทางต่างกัน
        edge_defs = [
            ('🏠 AH HOME ≥3 สัญญาณ → Home', lambda p: ah_home_confidence(p)[0] >= 3, _home_outcome),
            ('⭐ AH COMBO: O/U สูง + เยือนแย่', lambda p: (
                _safe_num(p.get('ou_overround')) is not None
                and _safe_num(p.get('ou_overround')) > OU_OVERROUND_EDGE_THRESHOLD
                and _safe_num(p.get('away_wr_5g')) is not None
                and _safe_num(p.get('away_wr_5g')) <= AWAY_FORM_EDGE_THRESHOLD), _ah_outcome),
            ('⭐ OU COMBO: O/U สูง + เสียเยอะ → Over', lambda p: (
                _safe_num(p.get('ou_overround')) is not None
                and _safe_num(p.get('ou_overround')) > OU_OVERROUND_EDGE_THRESHOLD
                and _safe_num(p.get('home_ga')) is not None
                and _safe_num(p.get('away_ga')) is not None
                and (_safe_num(p.get('home_ga')) + _safe_num(p.get('away_ga')))/10 > 1.3), _over_outcome),
            ('ค่าน้ำ AH สูง (>104.7%) [เดี่ยว]', lambda p: (
                _safe_num(p.get('ah_overround')) is not None
                and _safe_num(p.get('ah_overround')) > OVERROUND_EDGE_THRESHOLD), _ah_outcome),
            ('ทีมเยือนฟอร์มแย่ (≤40%) [เดี่ยว]', lambda p: (
                _safe_num(p.get('away_wr_5g')) is not None
                and _safe_num(p.get('away_wr_5g')) <= AWAY_FORM_EDGE_THRESHOLD), _ah_outcome),
        ]
        for label, cond, outcome_fn in edge_defs:
            with_sig = []
            without_sig = []
            for p in settled:
                if pd.isna(p.get('ah_line')): continue
                oc = outcome_fn(p)
                if oc is None: continue
                if cond(p):
                    with_sig.append(oc)
                else:
                    without_sig.append(oc)
            n_with = len(with_sig)
            n_without = len(without_sig)
            wr_with = sum(with_sig)/n_with*100 if n_with > 0 else 0
            wr_without = sum(without_sig)/n_without*100 if n_without > 0 else 0
            diff = wr_with - wr_without
            # bar เทียบ
            diff_color = "#00ff88" if diff > 5 else ("#ff8c00" if diff < -5 else "#7a9a88")
            stable_note = ""
            if n_with >= 30:
                stable_note = "✅ ข้อมูลพอเริ่มเชื่อได้"
            elif n_with >= 15:
                stable_note = "⚠️ ข้อมูลปานกลาง"
            else:
                stable_note = "🔸 ข้อมูลยังน้อย"
            st.markdown(
                f'<div style="background:#0d1e2e;border-radius:8px;padding:12px 16px;margin-bottom:8px;'
                f'border-left:3px solid {diff_color};">'
                f'<div style="display:flex;justify-content:space-between;margin-bottom:6px;">'
                f'<span style="font-family:\'Rajdhani\';font-size:0.85rem;color:#c8e6d4;font-weight:600;">'
                f'{label}</span>'
                f'<span style="font-family:\'Share Tech Mono\';font-size:0.85rem;color:{diff_color};">'
                f'{diff:+.0f}%</span></div>'
                f'<div style="display:flex;gap:14px;font-family:\'Rajdhani\';font-size:0.74rem;color:#7a9a88;">'
                f'<span>มีสัญญาณ: <b style="color:#00ff88;">{wr_with:.0f}%</b> (n={n_with})</span>'
                f'<span>ไม่มี: <b style="color:#ff8c00;">{wr_without:.0f}%</b> (n={n_without})</span>'
                f'<span>· {stable_note}</span></div></div>',
                unsafe_allow_html=True
            )
        st.markdown(
            '<div style="background:#1e1505;border-left:3px solid #ff8c00;padding:8px 12px;'
            'border-radius:0 6px 6px 0;margin-top:4px;">'
            '<span style="font-family:\'Rajdhani\';font-size:0.72rem;color:#c8e6d4;">'
            '⚠️ สัญญาณเหล่านี้ยังไม่ผ่าน robustness test (split-half ไม่นิ่ง) '
            'รอข้อมูล 30+ บิลต่อกลุ่มก่อนพิจารณาใช้จริง</span></div>',
            unsafe_allow_html=True
        )

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-family:\'Rajdhani\';font-size:0.72rem;color:#4a7a60;">'
        'ⓘ อ่านจาก Supabase (ถาวร) — อัปเดตอัตโนมัติเมื่อมีเคส settle เพิ่ม</div>',
        unsafe_allow_html=True
    )


with tab_dash:
    st.markdown('<div class="gem-label">◈ BETTING PERFORMANCE</div>', unsafe_allow_html=True)
    st.caption("ⓘ เฉพาะ predictions ที่ผ่าน Gate 1-4 (มี recommended_side) และ settle แล้ว")

    log_df_dash = db_load_predictions()
    log = log_df_dash.to_dict('records') if not log_df_dash.empty else []
    def _truthy(v):
        """True เฉพาะค่าจริง — กัน NaN ที่ bool(NaN)=True"""
        if v is None: return False
        try:
            if pd.isna(v): return False
        except (TypeError, ValueError):
            pass
        return bool(v)
    bet_candidates = [p for p in log if compute_best_side(p) is not None]
    def _has_goals(p):
        hg = p.get('actual_home_goals'); ag = p.get('actual_away_goals')
        if hg is None or ag is None: return False
        try:
            return not (pd.isna(hg) or pd.isna(ag))
        except (TypeError, ValueError):
            return True
    bet_settled = [p for p in bet_candidates if is_settled(p) and _has_goals(p)]

    # ── ล้าง pnl/bet_outcome ค้างของเคสที่ยังไม่ settle สมบูรณ์ (แก้ phantom PnL เก่าใน DB) ──
    for p in bet_candidates:
        if not (is_settled(p) and _has_goals(p)):
            if p.get('pnl') is not None and not (isinstance(p.get('pnl'), float) and pd.isna(p.get('pnl'))):
                db_update_result(p['id'], {'pnl': None, 'bet_outcome': None})

    if len(bet_settled) == 0:
        st.info("ยังไม่มีบิลที่ผ่าน Gate ครบและ settle แล้ว — เริ่มที่ PRE-MATCH tab")
    else:
        def calc_bet_pnl(p):
            """คำนวณ PnL ที่ถูกต้อง — ใช้ Best Bet ที่คำนวณสด (ไม่ใช่ recommended_side ใน DB ที่อาจผิด)"""
            side = compute_best_side(p)
            if not isinstance(side, str):
                return 0.0, None
            hg = p.get('actual_home_goals')
            ag = p.get('actual_away_goals')
            if hg is None or ag is None or pd.isna(hg) or pd.isna(ag):
                return None, None
            odds_map = {
                'AH Home': p.get('ah_home_odds'), 'AH Away': p.get('ah_away_odds'),
                'OU Over': p.get('ou_over_odds'), 'OU Under': p.get('ou_under_odds'),
            }
            odds = odds_map.get(side) or 0
            bet = p.get('recommended_bet_size', 0) or 0
            win_frac, loss_frac = settle_ah_ou(side, p.get('ah_line'), p.get('ou_line'), hg, ag)
            pnl_val = bet * win_frac * (odds - 1) - bet * loss_frac
            if win_frac > loss_frac:
                outcome = 'win' if win_frac == 1.0 else 'half_win'
            elif loss_frac > win_frac:
                outcome = 'loss' if loss_frac == 1.0 else 'half_loss'
            else:
                outcome = 'push'
            return pnl_val, outcome

        for p in bet_settled:
            pnl_val, outcome = calc_bet_pnl(p)
            p['_pnl'] = pnl_val
            # บันทึก/อัปเดต pnl กลับเข้า DB เสมอ (เพราะสูตรเก่าผิด ต้อง recompute ทับ)
            db_update_result(p['id'], {'pnl': pnl_val, 'bet_outcome': outcome})

        total_bets = len(bet_settled)
        total_pnl = sum(p['_pnl'] for p in bet_settled)
        total_invested = sum(p.get('recommended_bet_size', 0) or 0 for p in bet_settled)
        wins = sum(1 for p in bet_settled if p['_pnl'] > 0)
        losses = sum(1 for p in bet_settled if p['_pnl'] < 0)
        pushes = sum(1 for p in bet_settled if p['_pnl'] == 0)
        decisive = wins + losses
        wr = (wins / decisive * 100) if decisive > 0 else 0
        roi = (total_pnl / total_invested * 100) if total_invested > 0 else 0

        # ── HERO STAT CARDS (HTML) ──
        pnl_color = "#00ff88" if total_pnl >= 0 else "#ff3b5c"
        roi_color = "#00ff88" if roi >= 0 else "#ff3b5c"
        wr_color = "#00ff88" if wr >= 53 else ("#ffd600" if wr >= 48 else "#ff3b5c")

        def stat_card(label, value, sub, accent):
            return (
                f'<div style="flex:1;min-width:140px;background:linear-gradient(135deg,#0d1e2e 0%,#0a1722 100%);'
                f'border:1px solid {accent}44;border-top:3px solid {accent};border-radius:10px;'
                f'padding:16px 18px;box-shadow:0 4px 14px rgba(0,0,0,0.3);">'
                f'<div style="font-family:\'Rajdhani\';font-size:0.72rem;color:#7a9a88;'
                f'text-transform:uppercase;letter-spacing:1px;">{label}</div>'
                f'<div style="font-family:\'Share Tech Mono\';font-size:1.9rem;font-weight:700;'
                f'color:{accent};line-height:1.3;margin:4px 0;">{value}</div>'
                f'<div style="font-family:\'Rajdhani\';font-size:0.74rem;color:#5a7a68;">{sub}</div>'
                f'</div>'
            )

        st.markdown(
            '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px;">'
            + stat_card("Total PnL", f"฿{total_pnl:+,.0f}",
                       f"จาก {total_bets} บิล · ลงทุน ฿{total_invested:,.0f}", pnl_color)
            + stat_card("ROI", f"{roi:+.1f}%",
                       "ผลตอบแทนต่อเงินลงทุน", roi_color)
            + stat_card("Win Rate", f"{wr:.0f}%",
                       f"ชนะ {wins} · แพ้ {losses} · เสมอ {pushes}", wr_color)
            + '</div>', unsafe_allow_html=True
        )

        # ── PHASE 1 CALIBRATION (progress bar HTML) ──
        progress_pct = min(total_bets / 50 * 100, 100)
        if total_bets >= 50:
            phase_msg = (f"✅ ครบ 50 บิล! Win Rate {wr:.0f}% — "
                        + ("พร้อมเข้า Phase 2 (Dynamic sizing)" if wr >= 53
                           else "WR ต่ำกว่า 53% ควรอยู่ Phase 1 ต่อ"))
            phase_color = "#00ff88" if wr >= 53 else "#ffd600"
        else:
            phase_msg = f"เก็บข้อมูล Phase 1 — อีก {50-total_bets} บิลก่อนประเมิน Phase 2"
            phase_color = "#00b4ff"
        st.markdown(
            f'<div style="background:#0d1e2e;border-radius:10px;padding:14px 18px;margin:10px 0;'
            f'border:1px solid {phase_color}33;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
            f'<span style="font-family:\'Rajdhani\';font-size:0.8rem;color:#c8e6d4;font-weight:600;">'
            f'📊 PHASE 1 CALIBRATION</span>'
            f'<span style="font-family:\'Share Tech Mono\';font-size:0.78rem;color:{phase_color};">'
            f'{total_bets}/50</span></div>'
            f'<div style="background:#060c10;border-radius:6px;height:10px;overflow:hidden;">'
            f'<div style="width:{progress_pct}%;height:100%;background:linear-gradient(90deg,{phase_color}88,{phase_color});'
            f'border-radius:6px;"></div></div>'
            f'<div style="font-family:\'Rajdhani\';font-size:0.74rem;color:#7a9a88;margin-top:8px;">'
            f'{phase_msg}</div></div>',
            unsafe_allow_html=True
        )

        # ── EQUITY CURVE ──
        st.markdown('<div class="gem-label">◈ EQUITY CURVE</div>', unsafe_allow_html=True)
        cum_pnl = []
        running = 0
        for p in bet_settled:
            running += p['_pnl']
            cum_pnl.append(running)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            y=cum_pnl, mode='lines+markers',
            line=dict(color='#00ff88', width=2.5, shape='spline'),
            marker=dict(size=6, color='#00ff88', line=dict(width=1, color='#0d1e2e')),
            fill='tozeroy', fillcolor='rgba(0,255,136,0.08)'
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="#4a7a60", line_width=1)
        fig.update_layout(
            template='plotly_dark', height=280,
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(13,30,46,0.5)',
            margin=dict(l=20, r=20, t=10, b=20),
            yaxis_title="Cumulative PnL (฿)", xaxis_title="ลำดับบิล",
            font=dict(family="Rajdhani")
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── BY SIDE (HTML bars) ──
        st.markdown('<div class="gem-label">◈ ผลตามประเภทเดิมพัน</div>', unsafe_allow_html=True)
        side_groups = {}
        for p in bet_settled:
            side_groups.setdefault(compute_best_side(p) or '-', []).append(p)
        side_html = '<div style="display:flex;flex-direction:column;gap:8px;">'
        for side, plist in sorted(side_groups.items()):
            n = len(plist)
            pnl = sum(p['_pnl'] for p in plist)
            inv = sum(p.get('recommended_bet_size', 0) or 0 for p in plist)
            w = sum(1 for p in plist if p['_pnl'] > 0)
            wrp = w/n*100 if n>0 else 0
            roip = pnl/inv*100 if inv>0 else 0
            bar_color = "#00ff88" if pnl >= 0 else "#ff3b5c"
            side_html += (
                f'<div style="background:#0d1e2e;border-radius:8px;padding:10px 14px;'
                f'border-left:3px solid {bar_color};">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<span style="font-family:\'Share Tech Mono\';font-size:0.85rem;color:#c8e6d4;">{side}</span>'
                f'<span style="font-family:\'Share Tech Mono\';font-size:0.95rem;color:{bar_color};font-weight:700;">'
                f'฿{pnl:+,.0f}</span></div>'
                f'<div style="font-family:\'Rajdhani\';font-size:0.72rem;color:#7a9a88;margin-top:2px;">'
                f'{n} บิล · WR {wrp:.0f}% · ROI {roip:+.1f}%</div></div>'
            )
        side_html += '</div>'
        st.markdown(side_html, unsafe_allow_html=True)

        # ── BY TIER (HTML bars) ──
        st.markdown('<div class="gem-label" style="margin-top:14px;">◈ ผลตามระดับลีก</div>',
                   unsafe_allow_html=True)
        tier_groups = {}
        for p in bet_settled:
            tier_groups.setdefault(p.get('league_tier', 'unknown'), []).append(p)
        tier_colors = {'women':'#9b59b6','major':'#00b4ff','niche':'#4a7a60','cup_no_rank':'#ff8c00'}
        tier_html = '<div style="display:flex;flex-direction:column;gap:8px;">'
        for tier, plist in sorted(tier_groups.items()):
            n = len(plist)
            pnl = sum(p['_pnl'] for p in plist)
            inv = sum(p.get('recommended_bet_size', 0) or 0 for p in plist)
            w = sum(1 for p in plist if p['_pnl'] > 0)
            tc = tier_colors.get(tier, '#4a7a60')
            pnl_c = "#00ff88" if pnl >= 0 else "#ff3b5c"
            tier_html += (
                f'<div style="background:#0d1e2e;border-radius:8px;padding:10px 14px;'
                f'border-left:3px solid {tc};">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<span style="font-family:\'Share Tech Mono\';font-size:0.82rem;color:{tc};">{tier}</span>'
                f'<span style="font-family:\'Share Tech Mono\';font-size:0.9rem;color:{pnl_c};font-weight:700;">'
                f'฿{pnl:+,.0f}</span></div>'
                f'<div style="font-family:\'Rajdhani\';font-size:0.72rem;color:#7a9a88;margin-top:2px;">'
                f'{n} บิล · ชนะ {w}/{n} · ROI {pnl/inv*100 if inv>0 else 0:+.1f}%</div></div>'
            )
        tier_html += '</div>'
        st.markdown(tier_html, unsafe_allow_html=True)

        # Full log (เก็บเป็น expander แบบ minimal)
        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
        with st.expander("📋 ดู Bet Log ทั้งหมด"):
            for p in bet_settled:
                t = pd.to_datetime(p.get('created_at','')).strftime("%d/%m %H:%M") if p.get('created_at') else '-'
                pc = "#00ff88" if p.get('_pnl',0) >= 0 else "#ff3b5c"
                # สร้างสกอร์จาก goals โดยตรง (กัน actual_score ที่อาจเป็น nan)
                hg = p.get('actual_home_goals'); ag = p.get('actual_away_goals')
                if pd.notna(hg) and pd.notna(ag):
                    score_str = f"{int(hg)}-{int(ag)}"
                else:
                    score_str = "-"
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;padding:6px 10px;'
                    f'border-bottom:1px solid #1a2e3e;font-family:\'Rajdhani\';font-size:0.8rem;">'
                    f'<span style="color:#c8e6d4;">{t} · {p.get("match_name","-")[:28]} '
                    f'<span style="color:#5a7a68;">({compute_best_side(p) or "-"} · {score_str})</span></span>'
                    f'<span style="color:{pc};font-family:\'Share Tech Mono\';">฿{p.get("_pnl",0):+,.0f}</span></div>',
                    unsafe_allow_html=True
                )

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    st.caption("ℹ️ ข้อมูลทั้งหมดเก็บถาวรใน Supabase — เปิดแอพใหม่ข้อมูลยังอยู่ครบ")
