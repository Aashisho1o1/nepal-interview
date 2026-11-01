-- Milestone one schema. A subset of the handoff's logical model; counselor,
-- organization, order and settlement tables arrive with the pilot milestone.
-- Money and usage: integers in minor units / seconds; provider quantities NUMERIC.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

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
  mode              TEXT NOT NULL CHECK (mode IN ('avatar','voice')),
  display           TEXT NOT NULL CHECK (display IN ('avatar','portrait')),
  providers         JSONB NOT NULL,
  policy_version    TEXT NOT NULL,
  room_name         TEXT NOT NULL UNIQUE,
  status            TEXT NOT NULL CHECK (status IN ('created','active','completed','failed')),
  practice_seconds  INT NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  hard_deadline_at  TIMESTAMPTZ NOT NULL,   -- nothing may run after this
  media_ready_at    TIMESTAMPTZ,            -- student-facing clock starts here
  practice_ends_at  TIMESTAMPTZ,
  fallback_at       TIMESTAMPTZ,            -- avatar -> voice
  last_heartbeat_at TIMESTAMPTZ,
  ended_at          TIMESTAMPTZ,
  room_closed_at    TIMESTAMPTZ,            -- media room confirmed deleted
  end_reason        TEXT,
  charged_premium_seconds INT,
  charged_basic_seconds   INT,
  waived_seconds          INT,
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
