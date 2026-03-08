-- Finance Coach Initial Schema
-- Deployed to Supabase PostgreSQL
-- Run via: supabase db push

-- ── users ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    plaid_access_tokens JSONB DEFAULT '[]'::jsonb,  -- [{access_token, institution_id, institution_name}]
    monthly_income NUMERIC,
    glasses_device_fingerprint TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── budget_categories ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS budget_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,              -- 'Dining', 'Coffee', 'Groceries', etc.
    monthly_limit NUMERIC NOT NULL,
    alert_at_percent INTEGER DEFAULT 80,  -- Alert when 80% used
    plaid_categories TEXT[],         -- Plaid category names to match
    icon TEXT,                       -- Emoji for TTS context
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, name)
);

-- ── transactions (synced from Plaid) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,             -- Plaid transaction_id
    user_id UUID REFERENCES users(id),
    account_id TEXT NOT NULL,
    amount NUMERIC NOT NULL,         -- Positive = expense, negative = income
    merchant_name TEXT,
    merchant_category TEXT,          -- Normalized category
    plaid_categories TEXT[],         -- Raw Plaid category hierarchy
    budget_category_id UUID REFERENCES budget_categories(id),
    location_lat NUMERIC,
    location_lon NUMERIC,
    location_address TEXT,
    date DATE NOT NULL,
    pending BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions(user_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(budget_category_id);

-- ── budget_snapshots (daily rollup) ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS budget_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    category_id UUID REFERENCES budget_categories(id),
    snapshot_date DATE NOT NULL,
    spent_this_month NUMERIC DEFAULT 0,
    remaining NUMERIC,
    transaction_count INTEGER DEFAULT 0,
    UNIQUE (user_id, category_id, snapshot_date)
);

-- ── geofences (location triggers) ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS geofences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    name TEXT NOT NULL,
    lat NUMERIC NOT NULL,
    lon NUMERIC NOT NULL,
    radius_meters INTEGER DEFAULT 100,
    merchant_category TEXT,
    trigger_type TEXT DEFAULT 'enter',  -- 'enter' | 'exit'
    tts_template TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_geofences_user ON geofences(user_id);

-- ── glasses_sessions ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS glasses_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    device_fingerprint TEXT NOT NULL,
    session_token TEXT NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    location_tracking_enabled BOOLEAN DEFAULT FALSE,
    last_location_lat NUMERIC,
    last_location_lon NUMERIC
);

-- ── coaching_sessions ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS coaching_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    session_type TEXT NOT NULL,   -- 'morning_briefing' | 'weekly_review' | 'voice_query' | 'location_trigger'
    initiated_at TIMESTAMPTZ DEFAULT NOW(),
    transcript JSONB DEFAULT '[]'::jsonb,  -- [{role, content, timestamp}]
    tts_audio_urls TEXT[],
    insights JSONB DEFAULT '[]'::jsonb     -- Extracted insights for vault injection
);

-- ── Seed default budget categories ────────────────────────────────────────────
-- (Users will customize these; these are sensible defaults)
-- Note: Requires a user_id — populate via application after user creation
