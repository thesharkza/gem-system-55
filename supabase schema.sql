-- ════════════════════════════════════════════════════════════════════════
-- GEM 5.0 — Supabase Schema
-- รัน SQL นี้ใน Supabase SQL Editor (project เดิม, table ใหม่ไม่ชนกับ v3.x)
-- ════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS gem5_predictions (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    -- Match info
    match_name      TEXT NOT NULL,
    league          TEXT,
    league_tier     TEXT,  -- 'major' | 'niche' | 'women' | 'cup_no_rank'

    -- Market vs Stat probabilities (1X2)
    market_p_home   NUMERIC,
    market_p_draw   NUMERIC,
    market_p_away   NUMERIC,
    stat_p_home     NUMERIC,
    divergence_wl   NUMERIC,

    -- Total goals
    market_total      NUMERIC,
    stat_total        NUMERIC,
    divergence_goals  NUMERIC,
    stat_lambda_home  NUMERIC,  -- stat-based λ_home (จาก 5 นัดหลังสุด)
    stat_lambda_away  NUMERIC,  -- stat-based λ_away

    -- Math Engine internals — เก็บไว้เพื่อ reproduce/debug สูตรย้อนหลัง
    math_lambda_home   NUMERIC,  -- λ_home จาก Dixon-Coles (หลัง Auto-Fit ถ้าเปิดใช้)
    math_lambda_away   NUMERIC,
    auto_fit_used       BOOLEAN,
    auto_fit_converged  BOOLEAN,
    auto_fit_loss        NUMERIC,

    -- Raw 5-game stats (เก็บดิบไว้ reproduce การคำนวณใหม่ได้ถ้าปรับสูตรทีหลัง)
    home_w INTEGER, home_d INTEGER, home_l INTEGER, home_gf INTEGER, home_ga INTEGER,
    away_w INTEGER, away_d INTEGER, away_l INTEGER, away_gf INTEGER, away_ga INTEGER,
    home_rank      TEXT,
    away_rank      TEXT,
    stadium_temp   NUMERIC,
    home_wr_5g        NUMERIC,
    away_wr_5g        NUMERIC,
    extreme_wr_flag   BOOLEAN,
    ranking_agrees    BOOLEAN,

    -- Odds (ราคาตลาดดิบทั้งหมด)
    ah_line           NUMERIC,
    ah_home_odds      NUMERIC,
    ah_away_odds      NUMERIC,
    ou_line           NUMERIC,
    ou_over_odds      NUMERIC,
    ou_under_odds     NUMERIC,
    h1x2_odds         NUMERIC,
    d1x2_odds         NUMERIC,
    a1x2_odds         NUMERIC,
    ah_overround      NUMERIC,
    ou_overround      NUMERIC,

    -- ทุก 4 ฝั่ง (ไม่ใช่แค่ฝั่งที่แนะนำ) — เพื่อ backtest ทางเลือกอื่นย้อนหลัง
    ah_home_win_rate    NUMERIC,
    ah_home_gates_passed INTEGER,
    ah_away_win_rate    NUMERIC,
    ah_away_gates_passed INTEGER,
    ou_over_win_rate    NUMERIC,
    ou_over_gates_passed INTEGER,
    ou_under_win_rate   NUMERIC,
    ou_under_gates_passed INTEGER,

    -- Gate 5 signals (เก็บเป็น JSON เพื่อ flexibility — โครงสร้างอาจเปลี่ยนได้ในอนาคต)
    gate5_signals     JSONB,

    -- Gate results สรุป
    gates_passed         INTEGER,
    all_gates_pass        BOOLEAN,
    recommended_side      TEXT,
    recommended_bet_size  NUMERIC,
    bet_phase             INTEGER,
    bankroll_at_time       NUMERIC,

    -- Results (กรอกทีหลัง)
    actual_result       TEXT,    -- 'home_win' | 'draw' | 'away_win'
    actual_score         TEXT,
    actual_home_goals    INTEGER,
    actual_away_goals    INTEGER,
    actual_total_goals   INTEGER,
    wl_winner            TEXT,   -- 'market' | 'stat' | 'neutral'
    goals_winner         TEXT,   -- 'market' | 'stat' | 'neutral'
    bet_outcome           TEXT,  -- 'win' | 'loss' | 'push' | NULL
    pnl                    NUMERIC,

    -- Free-text สำหรับบันทึกข้อสังเกตเพิ่มเติมตอน settle (เช่น มีใบแดง, สภาพอากาศพิเศษ)
    notes                  TEXT
);

-- ════════════════════════════════════════════════════════════════════════
-- MIGRATION (ใช้เฉพาะถ้าเคยรัน schema เวอร์ชันเก่าไปแล้ว — ข้ามได้ถ้าเพิ่งสร้างใหม่)
-- รันบล็อกนี้เพื่อเพิ่มคอลัมน์ใหม่เข้า table เดิมโดยไม่ลบข้อมูล
-- ════════════════════════════════════════════════════════════════════════
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS stat_lambda_home NUMERIC;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS stat_lambda_away NUMERIC;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS math_lambda_home NUMERIC;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS math_lambda_away NUMERIC;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS auto_fit_used BOOLEAN;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS auto_fit_converged BOOLEAN;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS auto_fit_loss NUMERIC;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS home_w INTEGER;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS home_d INTEGER;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS home_l INTEGER;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS home_gf INTEGER;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS home_ga INTEGER;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS away_w INTEGER;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS away_d INTEGER;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS away_l INTEGER;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS away_gf INTEGER;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS away_ga INTEGER;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS home_rank TEXT;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS away_rank TEXT;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS stadium_temp NUMERIC;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS h1x2_odds NUMERIC;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS d1x2_odds NUMERIC;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS a1x2_odds NUMERIC;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS ah_overround NUMERIC;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS ou_overround NUMERIC;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS ah_home_win_rate NUMERIC;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS ah_home_gates_passed INTEGER;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS ah_away_win_rate NUMERIC;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS ah_away_gates_passed INTEGER;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS ou_over_win_rate NUMERIC;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS ou_over_gates_passed INTEGER;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS ou_under_win_rate NUMERIC;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS ou_under_gates_passed INTEGER;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS gate5_signals JSONB;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS bankroll_at_time NUMERIC;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS actual_home_goals INTEGER;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS actual_away_goals INTEGER;
ALTER TABLE gem5_predictions ADD COLUMN IF NOT EXISTS notes TEXT;

-- Index สำหรับ query บ่อยๆ (pending vs settled, backtest by tier/divergence)
CREATE INDEX IF NOT EXISTS idx_gem5_settled ON gem5_predictions ((actual_result IS NOT NULL));
CREATE INDEX IF NOT EXISTS idx_gem5_tier ON gem5_predictions (league_tier);
CREATE INDEX IF NOT EXISTS idx_gem5_created ON gem5_predictions (created_at DESC);

-- RLS (Row Level Security) — เปิดแบบ public read/write เพราะใช้คนเดียว
-- ถ้าต้องการความปลอดภัยสูงกว่านี้ ปรับ policy ตามความเหมาะสม
ALTER TABLE gem5_predictions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all access for anon" ON gem5_predictions
    FOR ALL
    USING (true)
    WITH CHECK (true);
