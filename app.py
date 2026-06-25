#!/usr/bin/env python3
"""
GEM 5.0 — สคริปต์วิเคราะห์ predictions CSV แบบครบวงจร
ใช้: python3 analyze_predictions.py <path_to_csv>
ออกแบบให้รันซ้ำได้ทุกครั้งที่มีข้อมูลใหม่ เพื่อติดตามว่าสมมุติฐานยัง hold ไหม
"""
import sys
import pandas as pd
import numpy as np

try:
    from scipy import stats as sst
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


# ── helper: AH/OU settlement ที่ถูกต้องตามแต้มต่อ ──
def settle_ah_ou(side, ah_line, ou_line, hg, ag):
    """คืน (win_fraction, loss_fraction) รองรับ quarter-ball/push/half"""
    hg = hg if pd.notna(hg) else 0
    ag = ag if pd.notna(ag) else 0
    if side in ('AH Home', 'AH Away'):
        if pd.isna(ah_line):
            return (0.0, 0.0)
        adj = ((hg - ag) - ah_line) if side == 'AH Home' else ((ag - hg) + ah_line)
    elif side in ('OU Over', 'OU Under'):
        if pd.isna(ou_line):
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


def ci95(k, n):
    if n == 0:
        return (0, 0)
    p = k / n
    se = np.sqrt(max(p * (1 - p), 1e-9) / n)
    return (max(0, p - 1.96 * se), min(1, p + 1.96 * se))


def binom_p(k, n, p0=0.5):
    """p-value ทดสอบ H1: rate > p0 (คืน None ถ้าไม่มี scipy)"""
    if not HAS_SCIPY or n == 0:
        return None
    return sst.binomtest(k, n, p0, alternative='greater').pvalue


def sig_tag(pval):
    if pval is None:
        return "(ติดตั้ง scipy เพื่อดู p-value)"
    if pval < 0.01:
        return f"p={pval:.4f} ✅✅ มีนัยสำคัญสูง"
    if pval < 0.05:
        return f"p={pval:.4f} ✅ มีนัยสำคัญ"
    if pval < 0.10:
        return f"p={pval:.3f} ⚠️ แนวโน้ม (ยังไม่ชัด)"
    return f"p={pval:.3f} ❌ ยังไม่มีนัยสำคัญ"


def section(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def main(csv_path):
    df = pd.read_csv(csv_path)
    print(f"\n📂 โหลด: {csv_path}")
    print(f"   ทั้งหมด {len(df)} แถว, {len(df.columns)} คอลัมน์")

    settled = df[df['actual_result'].notna()].copy()
    pending = df[df['actual_result'].isna()]
    print(f"   Settled: {len(settled)} | Pending: {len(pending)}")

    if len(settled) == 0:
        print("\n⚠️ ยังไม่มีเคส settled — หยุดวิเคราะห์")
        return

    settled['abs_div'] = settled['divergence_wl'].abs()

    # ════════════════════════════════════════════════════════════════
    section("1️⃣  STAT-DIVERGENCE BUCKETS — wl_winner (calibration)")
    print("   วัด: ตัวเลขความน่าจะเป็นของใครใกล้ผลจริงกว่า (ไม่ใช่ผล AH bet)")
    buckets = [(0, 0.15, "Low (<15%)"), (0.15, 0.40, "Moderate (15-40%)"),
               (0.40, 1.01, "Extreme (≥40%)")]
    for lo, hi, label in buckets:
        sub = settled[(settled['abs_div'] >= lo) & (settled['abs_div'] < hi)]
        n = len(sub)
        if n == 0:
            print(f"\n   {label}: n=0")
            continue
        mkt = (sub['wl_winner'] == 'market').sum()
        stat = (sub['wl_winner'] == 'stat').sum()
        neu = (sub['wl_winner'] == 'neutral').sum()
        dec = mkt + stat
        print(f"\n   {label}: n={n} (Market {mkt} / Stat {stat} / Neutral {neu})")
        if dec > 0:
            mr = mkt / dec
            lo_c, hi_c = ci95(mkt, dec)
            winner = "Market" if mr >= 0.5 else "Stat"
            k = mkt if mr >= 0.5 else stat
            print(f"      ชี้ขาด {dec}: {winner} ถูก {max(mr, 1-mr)*100:.0f}% "
                  f"[CI {lo_c*100:.0f}-{hi_c*100:.0f}%] {sig_tag(binom_p(k, dec))}")

    # ════════════════════════════════════════════════════════════════
    section("2️⃣  AH BET จริง — เล่นตามฝั่งที่ Stat เชียร์ (ใช้เดิมพันได้)")
    print("   วัด: ถ้าเล่น AH ตามฝั่ง stat ในแต่ละ bucket ได้ WR/ROI เท่าไร")
    odds = 1.90
    for lo, hi, label in buckets:
        sub = settled[(settled['abs_div'] >= lo) & (settled['abs_div'] < hi)]
        n = len(sub)
        if n == 0:
            continue
        wins = losses = 0.0
        pnl = inv = 0.0
        for _, r in sub.iterrows():
            side = 'AH Home' if r['divergence_wl'] > 0 else 'AH Away'
            wf, lf = settle_ah_ou(side, r.get('ah_line'), r.get('ou_line'),
                                  r.get('actual_home_goals'), r.get('actual_away_goals'))
            inv += 100
            pnl += 100 * wf * (odds - 1) - 100 * lf
            wins += wf
            losses += lf
        dec = wins + losses
        roi = pnl / inv * 100 if inv > 0 else 0
        wr = wins / dec * 100 if dec > 0 else 0
        print(f"\n   {label}: n={n}")
        print(f"      เล่นตาม Stat: WR={wr:.0f}% | PnL={pnl:+.0f} | ROI={roi:+.1f}%")

    # ════════════════════════════════════════════════════════════════
    section("3️⃣  เทียบกลยุทธ์ Gate 5 (AH, สูตรถูกต้อง)")
    pool = [r for _, r in settled.iterrows() if pd.notna(r.get('ah_line'))]

    def run(mode):
        pnl = inv = 0.0
        bets = wins = losses = 0
        for r in pool:
            div = r['divergence_wl'] if pd.notna(r['divergence_wl']) else 0
            ad = abs(div)
            stat_home = div > 0
            if mode == 'skip_mod' and 0.15 <= ad < 0.40:
                continue
            if mode == 'low_only' and ad >= 0.15:
                continue
            if mode == 'flip_mod' and 0.15 <= ad < 0.40:
                side_home = not stat_home
            else:
                side_home = stat_home
            side = 'AH Home' if side_home else 'AH Away'
            wf, lf = settle_ah_ou(side, r.get('ah_line'), r.get('ou_line'),
                                  r.get('actual_home_goals'), r.get('actual_away_goals'))
            inv += 100
            bets += 1
            pnl += 100 * wf * (odds - 1) - 100 * lf
            if wf > lf:
                wins += 1
            elif lf > wf:
                losses += 1
        roi = pnl / inv * 100 if inv > 0 else 0
        return bets, pnl, roi, wins, losses

    for code, name in [('follow', 'A: ตาม Stat ทุกเคส'),
                       ('skip_mod', 'B: ข้าม Moderate (SKIP)'),
                       ('flip_mod', 'C: พลิก Moderate (FLIP)'),
                       ('low_only', 'D: เล่นเฉพาะ Low')]:
        b, pnl, roi, w, l = run(code)
        print(f"   {name:28} {b:3} บิล | W{w}-L{l} | PnL {pnl:+6.0f} | ROI {roi:+.1f}%")

    # ════════════════════════════════════════════════════════════════
    section("4️⃣  TOTAL GOALS by TIER — Stat มี edge ไหม")
    for tier in ['women', 'cup_no_rank', 'niche', 'major']:
        sub = settled[(settled['league_tier'] == tier) & settled['goals_winner'].notna()]
        n = len(sub)
        if n == 0:
            print(f"   {tier}: n=0")
            continue
        stat = (sub['goals_winner'] == 'stat').sum()
        mkt = (sub['goals_winner'] == 'market').sum()
        dec = stat + mkt
        if dec > 0:
            lo_c, hi_c = ci95(stat, dec)
            print(f"   {tier}: n={n} | Stat {stat}/{dec}={stat/dec*100:.0f}% "
                  f"[CI {lo_c*100:.0f}-{hi_c*100:.0f}%] {sig_tag(binom_p(stat, dec))}")

    # ════════════════════════════════════════════════════════════════
    section("5️⃣  GATE SYSTEM — บิลที่ผ่าน Gate 1-4 จริง")
    passed = settled[(settled['all_gates_pass'] == True) &
                     settled['recommended_side'].notna()].copy()
    print(f"   ผ่าน Gate + settled: {len(passed)} บิล")
    if len(passed) > 0:
        pnl = inv = 0.0
        w = l = push = 0
        for _, r in passed.iterrows():
            side = r['recommended_side']
            odds_map = {'AH Home': r.get('ah_home_odds'), 'AH Away': r.get('ah_away_odds'),
                        'OU Over': r.get('ou_over_odds'), 'OU Under': r.get('ou_under_odds')}
            o = odds_map.get(side) or 0
            bet = r.get('recommended_bet_size') or 0
            wf, lf = settle_ah_ou(side, r.get('ah_line'), r.get('ou_line'),
                                  r.get('actual_home_goals'), r.get('actual_away_goals'))
            pnl += bet * wf * (o - 1) - bet * lf
            inv += bet
            if wf > lf: w += 1
            elif lf > wf: l += 1
            else: push += 1
        dec = w + l
        wr = w / dec * 100 if dec > 0 else 0
        roi = pnl / inv * 100 if inv > 0 else 0
        lo_c, hi_c = ci95(w, dec) if dec > 0 else (0, 0)
        print(f"   ผล: W{w}-L{l}-Push{push} | WR={wr:.0f}% [CI {lo_c*100:.0f}-{hi_c*100:.0f}%]")
        print(f"   PnL รวม: {pnl:+,.0f} | ROI: {roi:+.1f}%")
        print(f"   {sig_tag(binom_p(w, dec)) if dec > 0 else ''}")
        if len(passed) < 30:
            print(f"   ⚠️ sample {len(passed)} บิล ยังน้อยเกินสรุป (ต้องการ 30+)")

    # ════════════════════════════════════════════════════════════════
    section("6️⃣  KELLY CRITERION — % เดิมพันที่เหมาะสม (ถ้า WR เชื่อถือได้)")
    print("   อ้างอิง odds 1.90 (b=0.90):")
    for wr in [0.50, 0.52, 0.55, 0.58, 0.60, 0.65]:
        b = 0.90
        f = (b * wr - (1 - wr)) / b
        status = "❌ ไม่ควรเล่น" if f <= 0 else f"half-Kelly={f*50:.1f}%"
        print(f"      WR {wr*100:.0f}%: Kelly={f*100:+.1f}% | {status}")
    print("   → ต้องมี WR ที่เชื่อถือได้ (30+ บิล) ก่อนใช้ Kelly ปรับ %")

    # ════════════════════════════════════════════════════════════════
    section("7️⃣  DATA QUALITY")
    if 'ah_overround' in settled.columns:
        over_fail = (settled['ah_overround'] > 106).sum()
        print(f"   AH overround เฉลี่ย: {settled['ah_overround'].mean():.1f}%")
        print(f"   เกิน 106% (Gate 1 fail): {over_fail}/{len(settled)} "
              f"= {over_fail/len(settled)*100:.0f}%")
    if 'league_tier' in settled.columns:
        print(f"   Tier distribution: {dict(settled['league_tier'].value_counts())}")

    print("\n" + "=" * 72)
    print("✅ วิเคราะห์เสร็จ — เทียบกับรอบก่อนเพื่อดูว่าสมมุติฐานยัง hold ไหม")
    print("=" * 72)


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else '/mnt/user-data/uploads/gem5_predictions_rows.csv'
    main(path)
