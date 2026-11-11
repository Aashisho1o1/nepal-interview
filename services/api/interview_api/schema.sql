-- Schema. Applied on every API start; every statement is idempotent, and the
-- migrations block at the end upgrades databases created by earlier versions.
-- Money and usage: integers in minor units / seconds; provider quantities NUMERIC.

CREATE TABLE IF NOT EXISTS users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email         TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student','counselor','admin')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auth_sessions (
  token_hash  TEXT PRIMARY KEY,            -- sha256 of the cookie value; raw token never stored
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at  TIMESTAMPTZ NOT NULL,
  revoked_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS student_profiles (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  display_name  TEXT NOT NULL,
  country_track TEXT NOT NULL,
  is_synthetic  BOOLEAN NOT NULL DEFAULT false,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Proposed facts with their source; students confirm or correct each one.
CREATE TABLE IF NOT EXISTS extracted_facts (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id          UUID NOT NULL REFERENCES student_profiles(id) ON DELETE CASCADE,
  ref                 TEXT NOT NULL,
  field_name          TEXT NOT NULL,
  value_json          JSONB NOT NULL,
  source_label        TEXT NOT NULL,
  source_snippet      TEXT NOT NULL,
  confirmation_status TEXT NOT NULL DEFAULT 'proposed'
                        CHECK (confirmation_status IN ('proposed','confirmed','corrected','rejected')),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (student_id, ref)
);

CREATE TABLE IF NOT EXISTS profile_snapshots (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id           UUID NOT NULL REFERENCES student_profiles(id) ON DELETE CASCADE,
  version              INT NOT NULL,
  confirmed_facts_json JSONB NOT NULL,
  funding_json         JSONB NOT NULL,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (student_id, version)
);

CREATE TABLE IF NOT EXISTS entitlements (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id       UUID NOT NULL REFERENCES student_profiles(id) ON DELETE CASCADE,
  bucket           TEXT NOT NULL CHECK (bucket IN ('premium_seconds','basic_seconds')),
  package_version  TEXT NOT NULL,
  granted_seconds  INT NOT NULL CHECK (granted_seconds >= 0),
  consumed_seconds INT NOT NULL DEFAULT 0 CHECK (consumed_seconds >= 0),
  expires_at       TIMESTAMPTZ NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (consumed_seconds <= granted_seconds)
);

CREATE TABLE IF NOT EXISTS interview_sessions (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id        UUID NOT NULL REFERENCES student_profiles(id) ON DELETE CASCADE,
  snapshot_id       UUID NOT NULL REFERENCES profile_snapshots(id),
  idempotency_key   TEXT NOT NULL,
  track             TEXT NOT NULL,
  format_id         TEXT NOT NULL,
  mode              TEXT NOT NULL CHECK (mode IN ('avatar','voice')),  -- tier: video | voice
  provider_id       TEXT NOT NULL,          -- which interviewer delivered it (config/providers.json)
  providers         JSONB NOT NULL,         -- provider details stored for reporting
  policy_version    TEXT NOT NULL,
  status            TEXT NOT NULL CHECK (status IN ('created','active','completed','failed')),
  practice_seconds  INT NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  hard_deadline_at  TIMESTAMPTZ NOT NULL,   -- nothing may run after this
  media_ready_at    TIMESTAMPTZ,            -- student-facing clock starts here
  practice_ends_at  TIMESTAMPTZ,
  last_heartbeat_at TIMESTAMPTZ,            -- browser heartbeats keep the session live
  ended_at          TIMESTAMPTZ,
  vendor_closed_at  TIMESTAMPTZ,            -- vendor session confirmed stopped
  end_reason        TEXT,
  charged_premium_seconds INT,
  charged_basic_seconds   INT,
  waived_seconds          INT,
  -- The vendor's id for the session and the launch payload, so an idempotent retry
  -- never creates a second vendor conversation.
  vendor_ref        TEXT,
  launch_json       JSONB,
  launch_claimed_at TIMESTAMPTZ,
  UNIQUE (student_id, idempotency_key)
);
-- At most one live session per student, enforced by the database, so a refresh or a
-- second tab cannot start parallel paid provider sessions.
CREATE UNIQUE INDEX IF NOT EXISTS one_live_session_per_student
  ON interview_sessions (student_id) WHERE status IN ('created','active');

CREATE TABLE IF NOT EXISTS usage_reservations (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entitlement_id   UUID NOT NULL REFERENCES entitlements(id),
  session_id       UUID NOT NULL UNIQUE REFERENCES interview_sessions(id),
  reserved_seconds INT NOT NULL CHECK (reserved_seconds > 0),
  state            TEXT NOT NULL CHECK (state IN ('active','settled')),
  settled_seconds  INT,
  expires_at       TIMESTAMPTZ NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  settled_at       TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS session_events (
  id         BIGSERIAL PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL,
  payload    JSONB NOT NULL DEFAULT '{}'::jsonb,
  source     TEXT NOT NULL,
  at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS interview_turns (
  session_id UUID NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
  turn_id    TEXT NOT NULL,
  sequence   INT NOT NULL,
  speaker    TEXT NOT NULL CHECK (speaker IN ('student','interviewer')),
  text       TEXT NOT NULL,
  start_ms   INT NOT NULL,
  end_ms     INT NOT NULL,
  canceled   BOOLEAN NOT NULL DEFAULT false,
  metrics    JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (session_id, turn_id)
);

CREATE TABLE IF NOT EXISTS usage_ledger (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id        UUID NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
  provider_event_id TEXT NOT NULL,
  provider          TEXT NOT NULL,
  meter             TEXT NOT NULL,
  quantity          NUMERIC(20,6) NOT NULL,
  unit              TEXT NOT NULL,
  cost_usd_micros   BIGINT,               -- NULL = unpriced meter
  price_version     TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (session_id, provider_event_id)  -- idempotent writes
);

CREATE TABLE IF NOT EXISTS feedback_reports (
  session_id      UUID PRIMARY KEY REFERENCES interview_sessions(id) ON DELETE CASCADE,
  status          TEXT NOT NULL CHECK (status IN ('pending','ready','failed')),
  grader          TEXT,
  schema_version  TEXT,
  rubric_version  TEXT,
  attempts        INT NOT NULL DEFAULT 0,
  validated_json  JSONB,
  last_error      TEXT,
  review_status   TEXT NOT NULL DEFAULT 'not_reviewed',
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_events (
  id            BIGSERIAL PRIMARY KEY,
  actor_id      TEXT NOT NULL,
  action        TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id   TEXT NOT NULL,
  detail        JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS sessions_vendor_ref
  ON interview_sessions (provider_id, vendor_ref) WHERE vendor_ref IS NOT NULL;

-- Student ratings after each mock: the same questions for every provider, so
-- providers can be compared on experience, not just on our own metrics.
CREATE TABLE IF NOT EXISTS session_ratings (
  session_id      UUID PRIMARY KEY REFERENCES interview_sessions(id) ON DELETE CASCADE,
  realism         SMALLINT NOT NULL CHECK (realism BETWEEN 1 AND 5),
  reply_speed     TEXT NOT NULL CHECK (reply_speed IN ('instant','slight_pause','noticeably_slow','frustrating')),
  audio_video_ok  BOOLEAN NOT NULL,
  would_use_again BOOLEAN NOT NULL,
  comment         TEXT CHECK (length(comment) <= 1000),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A shared promo code (one code for many students). Only its SHA-256 is stored.
CREATE TABLE IF NOT EXISTS promo_codes (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code_hash       TEXT NOT NULL UNIQUE,
  label           TEXT NOT NULL,
  premium_seconds INT NOT NULL CHECK (premium_seconds >= 0),
  basic_seconds   INT NOT NULL CHECK (basic_seconds >= 0),
  valid_days      INT NOT NULL CHECK (valid_days > 0),   -- how long the granted time lasts
  max_uses        INT CHECK (max_uses > 0),              -- NULL = no cap
  uses            INT NOT NULL DEFAULT 0,
  expires_at      TIMESTAMPTZ,                           -- NULL = never
  active          BOOLEAN NOT NULL DEFAULT true,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS promo_redemptions (
  code_id     UUID NOT NULL REFERENCES promo_codes(id),
  student_id  UUID NOT NULL REFERENCES student_profiles(id) ON DELETE CASCADE,
  redeemed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (code_id, student_id)                      -- once per student
);

-- ---------------------------------------------------------------- migrations
-- Databases created before 2026-11-02 (own LiveKit pipeline). Safe to re-run.
ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS provider_id TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE interview_sessions ALTER COLUMN provider_id DROP DEFAULT;
ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS vendor_ref TEXT;
ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS launch_json JSONB;
ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS launch_claimed_at TIMESTAMPTZ;
ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS vendor_closed_at TIMESTAMPTZ;
ALTER TABLE interview_sessions DROP COLUMN IF EXISTS display;
ALTER TABLE interview_sessions DROP COLUMN IF EXISTS room_name;
ALTER TABLE interview_sessions DROP COLUMN IF EXISTS fallback_at;
ALTER TABLE interview_sessions DROP COLUMN IF EXISTS room_closed_at;
-- Free daily grants and promo grants are keyed by package_version: at most one each.
CREATE UNIQUE INDEX IF NOT EXISTS entitlements_once
  ON entitlements (student_id, bucket, package_version);

-- Lookups that otherwise scan the whole table: active reservations per entitlement
-- (every balance and every start), a session's events, expired sign-ins, and ended
-- sessions the reconciler still has to close at the vendor.
CREATE INDEX IF NOT EXISTS reservations_active
  ON usage_reservations (entitlement_id) WHERE state = 'active';
CREATE INDEX IF NOT EXISTS session_events_session ON session_events (session_id);
CREATE INDEX IF NOT EXISTS auth_sessions_expiry ON auth_sessions (expires_at);
CREATE INDEX IF NOT EXISTS sessions_unclosed
  ON interview_sessions (ended_at)
  WHERE vendor_closed_at IS NULL AND status IN ('completed','failed');
