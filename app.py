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
        m = re.match(rf'^{re.escape(keyword)}\s+([\d.]+)\s*$', line)
        return float(m.group(1)) if m else None

    home_count = 0
    away_count = 0

    for line in lines:
        ah_match = re.match(r'^AH\s+(.+)$', line, re.IGNORECASE)
        if ah_match:
            result['ah_line_raw'] = ah_match.group(1).strip()
            continue

        ou_line_match = re.match(r'^สูง\s*/\s*ต่ำ\s+([\d.]+)\s*$', line)
        if ou_line_match:
            result['ou_line_raw'] = float(ou_line_match.group(1))
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
MULT_MODERATE_AGAINST = 0.5   # stat สวนตลาด 15-40% → ลดครึ่ง (ตลาดถูก ~64%)
MULT_EXTREME_AGAINST = 0.4    # stat สวนตลาด ≥40% → ลดแรง (ข้อมูลน้อย เสี่ยงสูง)
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
            'detail': (f"Stat บอก {favored_side} ได้เปรียบกว่าตลาดมาก (≥40%) — เคสแบบนี้พบน้อยมาก "
                      f"(4 เคสในข้อมูล, ผล 50/50 ยังสรุปไม่ได้) ความต่างที่สูงผิดปกติขนาดนี้ "
                      f"มักมาจาก small-sample noise ใน 5 นัด แนะนำลดขนาดเดิมพันลงแรง "
                      f"และตรวจ stat input ซ้ำว่าผิดปกติไหม")
        })
    elif abs_div >= MODERATE_DIVERGENCE_THRESHOLD:
        favored_side = "Home" if divergence_wl > 0 else "Away"
        signals.append({
            'type': 'warning', 'level': 'medium',
            'title': f"Moderate Divergence (D{divergence_wl*100:+.0f}%)",
            'detail': (f"Stat เชียร์ {favored_side} ต่างจากตลาด 15-40% — จากข้อมูลจริง 60 เคส "
                      f"โซนนี้ Stat มักพลาด (เล่นตาม Stat ใน AH ได้ WR ~36% / เล่นตามตลาด ~64%) "
                      f"แนะนำลดขนาดเดิมพันลงครึ่งหนึ่งถ้า Best Bet ตรงกับฝั่งที่ Stat เชียร์ "
                      f"(แนวโน้มชัด แต่ sample ยังไม่ถึงนัยสำคัญทางสถิติ p=0.13)")
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
            return ("🚨 ลด Bet แรง — Best Bet ตามฝั่ง Stat ที่ Diverge สูงมาก (≥40%, ข้อมูลน้อย)",
                    "#ff3b5c", MULT_EXTREME_AGAINST)
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
            GATE5_MODE_SKIP: "🛡️ SKIP — ข้ามเคส Moderate-against (ปลอดภัยสุด, ROI +5%)",
            GATE5_MODE_REDUCE: "⚖️ REDUCE — ลด bet โซนเสี่ยง (กลาง, ROI +4.7%)",
            GATE5_MODE_FLIP: "⚡ FLIP — พลิกตามตลาด (รุก, ROI +11% แต่เสี่ยง overfit p=0.13)",
        }[x],
        key='gate5_mode',
    )
    if gate5_mode == GATE5_MODE_FLIP:
        st.warning("⚡ โหมด FLIP: ระบบจะแนะนำให้เล่นตรงข้าม Stat ในโซน Moderate "
                  "(เชื่อตลาด) — ผลตอบแทนสูงสุดใน backtest แต่ยังไม่ผ่านนัยสำคัญทางสถิติ "
                  "(p=0.13, n=20) ใช้ด้วยความระมัดระวัง")

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

tab_pre, tab_log, tab_backtest, tab_dash = st.tabs(
    ["📋 PRE-MATCH", "📝 PREDICTIONS LOG", "🧪 BACKTEST LAB", "📊 DASHBOARD"]
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
            elif gate5_mode_active == GATE5_MODE_FLIP and in_moderate and best_aligns_stat:
                flipped = [s for s in sides_data
                          if s['is_home'] != best['is_home']
                          and s['name'].split()[0] == best['name'].split()[0]]
                if flipped:
                    mode_action_msg = (f"⚡ FLIP: พลิกจาก {best['name']} → {flipped[0]['name']} "
                                      f"(เชื่อตลาดแทน Stat ในโซน Moderate)")
                    best = flipped[0]

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
            new_id = db_save_prediction(pred_record)
            if new_id is not None:
                st.success(f"✅ บันทึก Prediction ลงฐานข้อมูลแล้ว (id={new_id}) — "
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


with tab_log:
    st.markdown('<div class="gem-label">◈ PREDICTIONS LOG</div>', unsafe_allow_html=True)

    log_df = db_load_predictions()

    if log_df.empty:
        st.info("ยังไม่มี prediction ที่บันทึกไว้ — ไปที่ PRE-MATCH tab เพื่อวิเคราะห์และบันทึกคู่แรก")
    else:
        pending_df = log_df[log_df['actual_result'].isna()]
        settled_df_raw = log_df[log_df['actual_result'].notna()]

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
            raw_side = p.get('recommended_side')
            side = raw_side if (isinstance(raw_side, str) and raw_side) else 'No Signal'
            signal = bool(p.get('all_gates_pass')) and p.get('all_gates_pass') is not None
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

                # ── แถวที่ 1: Probabilities ──
                ca, cb, cc_col = st.columns(3)
                ca.metric("Market P(Home)", f"{nz(p.get('market_p_home'))*100:.0f}%")
                cb.metric("Stat P(Home)", f"{nz(p.get('stat_p_home'))*100:.0f}%",
                         delta=f"{div*100:+.0f}%",
                         delta_color="off")
                cc_col.metric("Market P(Away)", f"{nz(p.get('market_p_away'))*100:.0f}%")

                # ── Gate 5 Divergence badge ──
                div_label = "🚨 EXTREME" if abs(div) >= 0.40 else ("⚠️ MODERATE" if abs(div) >= 0.15 else "✅ LOW")
                st.markdown(
                    f'<div style="border-left:3px solid {div_color};padding:6px 10px;'
                    f'background:#0d1e2e;border-radius:0 4px 4px 0;margin:4px 0;">'
                    f'<span style="font-family:\'Share Tech Mono\';font-size:0.72rem;color:{div_color};">'
                    f'Gate 5 Divergence: {div_label} (Δ{div*100:+.0f}%)</span>'
                    f'</div>', unsafe_allow_html=True
                )

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

                # ── แถวที่ 3: Total Goals + Stats ──
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

                # ── Result summary (settled only) ──
                if mode == 'settled':
                    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
                    res_color = "#00ff88" if header_color == "#00ff88" else "#ff3b5c"
                    r1, r2, r3, r4 = st.columns(4)
                    r1.metric("ผล", p.get('actual_score', '-'))
                    r2.metric("W/L Winner", p.get('wl_winner', '-'))
                    r3.metric("Goals Winner", p.get('goals_winner', '-'))
                    pnl = p.get('pnl')
                    r4.metric("PnL", f"฿{pnl:+,.0f}" if pd.notna(pnl) else "-")

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
    st.caption("ⓘ ทดสอบสมมุติฐานจาก Predictions Log ที่ settle แล้ว — ต้องการอย่างน้อย "
              "10-15 เคส settled ถึงจะเริ่มมีความหมายทางสถิติ")

    log_df_bt = db_load_predictions()
    log = log_df_bt.to_dict('records') if not log_df_bt.empty else []
    settled = [p for p in log if p.get('actual_result') is not None]

    if len(settled) < 3:
        st.warning(f"⚠️ มีแค่ {len(settled)} เคสที่ settle แล้ว — ต้องการอย่างน้อย 3 เคสเพื่อแสดงผลเบื้องต้น "
                  f"(แนะนำ 15-20+ เพื่อความน่าเชื่อถือทางสถิติ)")
    else:
        bt_module = st.radio(
            "เลือก Module",
            ["1️⃣ Gate Sensitivity", "2️⃣ Stat-Divergence Backtest",
             "3️⃣ League Tier Backtest", "4️⃣ Combined Strategy Simulator"],
            horizontal=False
        )

        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)

        # ══════════════════════════════════════════════════════════════
        # MODULE 1: Gate Sensitivity — ลอง threshold ต่างๆ ของ Gate 2
        # ══════════════════════════════════════════════════════════════
        if bt_module.startswith("1"):
            st.markdown('<div class="gem-label">◈ GATE 2 SENSITIVITY (Win Rate Threshold)</div>',
                       unsafe_allow_html=True)
            st.caption("ดูว่าถ้าปรับ threshold ของ Gate 2 (ปัจจุบัน ≥55%) เป็นค่าอื่น "
                      "WR/sample size จะเปลี่ยนยังไง — ใช้ stat_p_home เป็น proxy ของ win rate ที่ทำนาย")

            thresholds = [0.50, 0.53, 0.55, 0.58, 0.60, 0.62, 0.65]
            rows = []
            for thr in thresholds:
                # กรองเคสที่ recommended_side มีและ market สนับสนุน threshold นี้
                matching = [p for p in settled if p.get('recommended_side') is not None]
                # ใช้ wl_winner เป็นตัวบอกว่า "ฝั่งที่ระบบแนะนำ" ถูกหรือไม่
                # (simplification: นับจาก gates_passed >= บางระดับเป็น proxy)
                n = len(matching)
                if n == 0:
                    continue
                correct = sum(1 for p in matching if p['wl_winner'] in ('market', 'both_correct'))
                wr = correct / n if n > 0 else 0
                ci_lo, ci_hi = calc_ci_95(wr, n)
                rows.append({
                    'Threshold': f"{thr*100:.0f}%", 'N': n,
                    'Market-aligned WR': f"{wr*100:.1f}%",
                    '95% CI': f"{ci_lo*100:.0f}-{ci_hi*100:.0f}%"
                })
            if rows:
                st.dataframe(pd.DataFrame(rows).drop_duplicates(), use_container_width=True, hide_index=True)
            st.info("💡 หมายเหตุ: Module นี้ต้องการข้อมูล bet_outcome จริง (ชนะ/แพ้บิล) "
                   "เพื่อความแม่นยำเต็มรูปแบบ — ตอนนี้ใช้ wl_winner เป็น proxy เบื้องต้น")

        # ══════════════════════════════════════════════════════════════
        # MODULE 2: Stat-Divergence Backtest — กลุ่มตาม divergence bucket
        # ══════════════════════════════════════════════════════════════
        elif bt_module.startswith("2"):
            st.markdown('<div class="gem-label">◈ STAT-DIVERGENCE BUCKETS</div>', unsafe_allow_html=True)
            st.caption("ทดสอบสมมุติฐาน: divergence ใหญ่ขึ้น -> ใครชนะบ่อยกว่า (Market vs Stat)?")

            buckets = [(0, 0.15, "Low (0-15%)"), (0.15, 0.40, "Moderate (15-40%)"),
                      (0.40, 1.0, "Extreme (≥40%)")]

            bucket_rows = []
            for lo, hi, label in buckets:
                matching = [p for p in settled if lo <= abs(p.get('divergence_wl', 0)) < hi]
                n = len(matching)
                if n == 0:
                    bucket_rows.append({'Bucket': label, 'N': 0, 'Market Win': '-',
                                       'Stat Win': '-', 'Neutral': '-'})
                    continue
                market_wins = sum(1 for p in matching if p['wl_winner'] == 'market')
                stat_wins = sum(1 for p in matching if p['wl_winner'] == 'stat')
                neutral = n - market_wins - stat_wins
                bucket_rows.append({
                    'Bucket': label, 'N': n,
                    'Market Win': f"{market_wins} ({market_wins/n*100:.0f}%)",
                    'Stat Win': f"{stat_wins} ({stat_wins/n*100:.0f}%)",
                    'Neutral': f"{neutral} ({neutral/n*100:.0f}%)",
                })
            st.dataframe(pd.DataFrame(bucket_rows), use_container_width=True, hide_index=True)

            # Chart
            chart_data = [(r['Bucket'], int(r['Market Win'].split(' ')[0]) if r['N'] != 0 else 0,
                          int(r['Stat Win'].split(' ')[0]) if r['N'] != 0 else 0)
                          for r in bucket_rows]
            if any(m+s > 0 for _, m, s in chart_data):
                fig = go.Figure()
                fig.add_trace(go.Bar(name='Market Wins', x=[c[0] for c in chart_data],
                                     y=[c[1] for c in chart_data], marker_color='#00b4ff'))
                fig.add_trace(go.Bar(name='Stat Wins', x=[c[0] for c in chart_data],
                                     y=[c[2] for c in chart_data], marker_color='#9b59b6'))
                fig.update_layout(barmode='group', template='plotly_dark',
                                  paper_bgcolor='#0d1e2e', plot_bgcolor='#0d1e2e', height=300)
                st.plotly_chart(fig, use_container_width=True)

            st.markdown(
                '<div style="background:#0d1e2e;border-left:3px solid #00ff88;'
                'padding:10px 14px;border-radius:0 4px 4px 0;margin-top:10px;">'
                '<span style="font-family:\'Rajdhani\';font-size:0.82rem;color:#c8e6d4;">'
                '📊 <b>หลักฐานจากข้อมูลจริง 60 เคส (settled):</b><br>'
                '• Low (&lt;15%): เล่นตาม Stat ใน AH ได้ ~57% — Stat เชื่อถือได้<br>'
                '• <b>Moderate (15-40%): Stat มักพลาด — ตลาดถูก ~64%</b> '
                '(เล่นตาม Stat เหลือ 36%) สัญญาณแข็งสุด แม้ p=0.13<br>'
                '• Extreme (≥40%): n=4 น้อยเกินสรุป (เดิมคิดว่าตลาดถูก แต่ข้อมูลใหม่ 50/50)<br>'
                '→ Gate 5 ตอนนี้ปรับ bet/skip ตามโซนเหล่านี้ (เลือกโหมดที่ Sidebar)</span></div>',
                unsafe_allow_html=True
            )

        # ══════════════════════════════════════════════════════════════
        # MODULE 3: League Tier Backtest — แยก major/niche/women/cup
        # ══════════════════════════════════════════════════════════════
        elif bt_module.startswith("3"):
            st.markdown('<div class="gem-label">◈ LEAGUE TIER BACKTEST</div>', unsafe_allow_html=True)
            st.caption("ทดสอบสมมุติฐาน: ตลาด liquidity ต่ำ (women's/cup) Stat มี edge ใน Total Goals ไหม?")

            tiers = ['major', 'niche', 'women', 'cup_no_rank']
            tier_rows = []
            for tier in tiers:
                matching = [p for p in settled if p.get('league_tier') == tier
                           and p.get('goals_winner') is not None]
                n = len(matching)
                if n == 0:
                    tier_rows.append({'Tier': tier, 'N': 0, 'Stat Win (Goals)': '-',
                                     'Market Win (Goals)': '-'})
                    continue
                stat_wins = sum(1 for p in matching if p['goals_winner'] == 'stat')
                market_wins = sum(1 for p in matching if p['goals_winner'] == 'market')
                tier_rows.append({
                    'Tier': tier, 'N': n,
                    'Stat Win (Goals)': f"{stat_wins} ({stat_wins/n*100:.0f}%)",
                    'Market Win (Goals)': f"{market_wins} ({market_wins/n*100:.0f}%)",
                })
            st.dataframe(pd.DataFrame(tier_rows), use_container_width=True, hide_index=True)

            st.markdown(
                '<div style="background:#0d1e2e;border-left:3px solid #9b59b6;'
                'padding:10px 14px;border-radius:0 4px 4px 0;margin-top:10px;">'
                '<span style="font-family:\'Rajdhani\';font-size:0.82rem;color:#c8e6d4;">'
                '📌 Reference (12 เคสนอกระบบ): Women\'s football Stat Win Goals = 2/2 (100%), '
                'Men\'s (mixed niche+major) Stat Win Goals = 0/8 (0%). '
                'Sample เล็กมาก — ต้องการข้อมูลเพิ่มอย่างน้อย 5-8 เคสต่อ tier '
                'ถึงจะเริ่มเชื่อถือได้</span></div>',
                unsafe_allow_html=True
            )

        # ══════════════════════════════════════════════════════════════
        # MODULE 4: Combined Strategy Simulator
        # ══════════════════════════════════════════════════════════════
        else:
            st.markdown('<div class="gem-label">◈ COMBINED STRATEGY SIMULATOR</div>', unsafe_allow_html=True)
            st.caption("เทียบ ROI ของ 4 กลยุทธ์ Gate 5 บนข้อมูลจริง (คำนวณ AH/OU ถูกต้องตามแต้มต่อ)")

            # ใช้ทุกเคสที่ settle (ไม่ใช่แค่ที่ผ่าน gate) เพื่อ sample พอ — เล่นตามฝั่ง stat
            sim_pool = [p for p in settled if pd.notna(p.get('ah_line'))]
            odds_assume = 1.90

            def run_strategy(mode):
                pnl=inv=0; bets=0; wins=losses=0
                for p in sim_pool:
                    div = p.get('divergence_wl', 0) or 0
                    ad = abs(div); stat_home = div>0
                    if mode=='skip_mod' and 0.15<=ad<0.40: continue
                    if mode=='low_only' and ad>=0.15: continue
                    if mode=='flip_mod' and 0.15<=ad<0.40:
                        side_home = not stat_home
                    else:
                        side_home = stat_home
                    side = 'AH Home' if side_home else 'AH Away'
                    wf, lf = settle_ah_ou(side, p.get('ah_line'), p.get('ou_line'),
                                          p.get('actual_home_goals'), p.get('actual_away_goals'))
                    if wf == 0 and lf == 0 and not (pd.notna(p.get('ah_line'))):
                        continue
                    inv+=100; bets+=1
                    pnl += 100*wf*(odds_assume-1) - 100*lf
                    if wf>lf: wins+=1
                    elif lf>wf: losses+=1
                roi = pnl/inv*100 if inv>0 else 0
                return bets, pnl, roi

            strategies = [
                ('follow', 'A: ตาม Stat ทุกเคส'),
                ('skip_mod', 'B: ข้าม Moderate (SKIP)'),
                ('flip_mod', 'C: พลิก Moderate (FLIP)'),
                ('low_only', 'D: เล่นเฉพาะ Low'),
            ]
            rows=[]
            for code,name in strategies:
                b,pnl,roi = run_strategy(code)
                rows.append({'กลยุทธ์': name, 'บิล': b, 'PnL': f"฿{pnl:+,.0f}",
                            'ROI': f"{roi:+.1f}%"})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.caption(f"สมมุติ odds 1.90 ต่อบิล, flat 100/บิล, เล่นตามฝั่งที่ Stat เชียร์ "
                      f"(n={len(sim_pool)} เคสที่มี ah_line)")
            st.info("💡 ผลปัจจุบันชี้ว่า Moderate zone คือจุดที่ Stat พลาดหนักสุด — "
                   "โหมด SKIP/FLIP ช่วยได้ แต่ FLIP ยังเสี่ยง overfit (sample เล็ก)")

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-family:\'Rajdhani\';font-size:0.75rem;color:#4a7a60;">'
        'ⓘ Backtest Lab อ่านข้อมูลจาก Supabase (ถาวร) — ผลอัปเดตอัตโนมัติเมื่อมีเคส settle เพิ่ม</div>',
        unsafe_allow_html=True
    )


# ════════════════════════════════════════════════════════════════════════
# 📊 TAB 4: DASHBOARD — ROI / PnL / Bankroll Tracking
# ════════════════════════════════════════════════════════════════════════
with tab_dash:
    st.markdown('<div class="gem-label">◈ BETTING PERFORMANCE</div>', unsafe_allow_html=True)
    st.caption("ⓘ เฉพาะ predictions ที่ผ่าน Gate 1-4 (มี recommended_side) และ settle แล้ว")

    log_df_dash = db_load_predictions()
    log = log_df_dash.to_dict('records') if not log_df_dash.empty else []
    bet_candidates = [p for p in log if p.get('all_gates_pass') and p.get('recommended_side')]
    bet_settled = [p for p in bet_candidates if p.get('actual_result') is not None]

    if len(bet_settled) == 0:
        st.info("ยังไม่มีบิลที่ผ่าน Gate ครบและ settle แล้ว — เริ่มที่ PRE-MATCH tab")
    else:
        def calc_bet_pnl(p):
            """คำนวณ PnL ที่ถูกต้องตามหลัก Asian Handicap / Over-Under"""
            side = p.get('recommended_side')
            if not isinstance(side, str):
                return 0.0, None
            odds_map = {
                'AH Home': p.get('ah_home_odds'), 'AH Away': p.get('ah_away_odds'),
                'OU Over': p.get('ou_over_odds'), 'OU Under': p.get('ou_under_odds'),
            }
            odds = odds_map.get(side) or 0
            bet = p.get('recommended_bet_size', 0) or 0
            win_frac, loss_frac = settle_ah_ou(
                side, p.get('ah_line'), p.get('ou_line'),
                p.get('actual_home_goals'), p.get('actual_away_goals')
            )
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

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Total Bets", f"{total_bets}", help=f"ชนะ {wins} · แพ้ {losses} · เสมอ(push) {pushes}")
        d2.metric("Win Rate", f"{wr:.1f}%", help="ไม่นับ push ในตัวหาร")
        d3.metric("Total PnL", f"฿{total_pnl:+,.0f}")
        d4.metric("ROI", f"{roi:+.2f}%")

        # Phase 1 calibration
        phase1_bets = [p for p in bet_settled if st.session_state.get('bet_phase', 1) == 1]
        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="gem-label">◈ PHASE 1 CALIBRATION CHECK</div>', unsafe_allow_html=True)
        st.write(f"Settled bets so far: {total_bets}/50")
        if total_bets >= 50:
            if wr >= 53:
                st.success(f"✅ Win Rate {wr:.1f}% ≥ 53% — พร้อมเปลี่ยนเป็น Phase 2 (Dynamic sizing) ได้")
            else:
                st.warning(f"⚠️ Win Rate {wr:.1f}% < 53% — ควรอยู่ Phase 1 ต่อ และทบทวน Gate thresholds")
        else:
            st.info(f"ℹ️ ต้องการอีก {50-total_bets} ไม้ก่อนประเมิน Phase 2")

        # Equity curve
        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="gem-label">◈ EQUITY CURVE</div>', unsafe_allow_html=True)
        cum_pnl = []
        running = 0
        for p in bet_settled:
            running += p['_pnl']
            cum_pnl.append(running)
        fig = go.Figure()
        fig.add_trace(go.Scatter(y=cum_pnl, mode='lines+markers',
                                 line=dict(color='#00ff88', width=2), marker=dict(size=5)))
        fig.update_layout(template='plotly_dark', height=300,
                          paper_bgcolor='#0d1e2e', plot_bgcolor='#0d1e2e',
                          margin=dict(l=20, r=20, t=20, b=20), yaxis_title="Cumulative PnL (฿)")
        st.plotly_chart(fig, use_container_width=True)

        # By side breakdown
        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="gem-label">◈ BY SIDE</div>', unsafe_allow_html=True)
        side_groups = {}
        for p in bet_settled:
            side = p['recommended_side']
            side_groups.setdefault(side, []).append(p)
        side_rows = []
        for side, plist in side_groups.items():
            n = len(plist)
            pnl = sum(p['_pnl'] for p in plist)
            inv = sum(p.get('recommended_bet_size', 0) for p in plist)
            w = sum(1 for p in plist if p['_pnl'] > 0)
            side_rows.append({
                'Side': side, 'Bets': n, 'WR%': f"{w/n*100:.0f}",
                'PnL': f"฿{pnl:+,.0f}", 'ROI%': f"{pnl/inv*100:+.1f}" if inv > 0 else "-"
            })
        st.dataframe(pd.DataFrame(side_rows), use_container_width=True, hide_index=True)

        # By league tier
        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="gem-label">◈ BY LEAGUE TIER</div>', unsafe_allow_html=True)
        tier_groups = {}
        for p in bet_settled:
            tier = p.get('league_tier', 'unknown')
            tier_groups.setdefault(tier, []).append(p)
        tier_rows2 = []
        for tier, plist in tier_groups.items():
            n = len(plist)
            pnl = sum(p['_pnl'] for p in plist)
            inv = sum(p.get('recommended_bet_size', 0) for p in plist)
            tier_rows2.append({
                'Tier': tier, 'Bets': n, 'PnL': f"฿{pnl:+,.0f}",
                'ROI%': f"{pnl/inv*100:+.1f}" if inv > 0 else "-"
            })
        st.dataframe(pd.DataFrame(tier_rows2), use_container_width=True, hide_index=True)

        # Full log
        st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
        with st.expander("📋 Full Bet Log"):
            full_df = pd.DataFrame([{
                'Time': pd.to_datetime(p.get('created_at', '')).strftime("%Y-%m-%d %H:%M") if p.get('created_at') else '-',
                'Match': p.get('match_name', '-'),
                'Side': p.get('recommended_side', '-'),
                'Bet': f"฿{p.get('recommended_bet_size', 0) or 0:,.0f}",
                'Score': p.get('actual_score', '-'),
                'PnL': f"฿{p.get('_pnl', 0):+,.0f}"
            } for p in bet_settled])
            st.dataframe(full_df, use_container_width=True, hide_index=True)

    st.markdown('<div class="gem-divider"></div>', unsafe_allow_html=True)
    st.caption("ℹ️ ข้อมูลทั้งหมดเก็บถาวรใน Supabase — เปิดแอพใหม่ข้อมูลยังอยู่ครบ")
