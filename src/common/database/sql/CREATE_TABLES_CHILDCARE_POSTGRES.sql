-- SPDX-License-Identifier: MIT
CREATE SCHEMA IF NOT EXISTS childcare;
CREATE TABLE IF NOT EXISTS childcare.family_space (
    family_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS childcare.family_member (
    family_id TEXT NOT NULL REFERENCES childcare.family_space(family_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner', 'member')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (family_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_childcare_member_user ON childcare.family_member(user_id);
CREATE TABLE IF NOT EXISTS childcare.family_invite (
    invite_id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL REFERENCES childcare.family_space(family_id) ON DELETE CASCADE,
    code_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS childcare.baby_profile (
    baby_id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL REFERENCES childcare.family_space(family_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    birth_date DATE NOT NULL,
    notes TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_childcare_baby_family ON childcare.baby_profile(family_id);
CREATE TABLE IF NOT EXISTS childcare.baby_event (
    event_id TEXT PRIMARY KEY,
    baby_id TEXT NOT NULL REFERENCES childcare.baby_profile(baby_id) ON DELETE CASCADE,
    family_id TEXT NOT NULL REFERENCES childcare.family_space(family_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('feed', 'diaper', 'temperature', 'sleep', 'growth', 'note')),
    happened_at TIMESTAMPTZ NOT NULL,
    data_json TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_childcare_event_day ON childcare.baby_event(baby_id, happened_at DESC);
