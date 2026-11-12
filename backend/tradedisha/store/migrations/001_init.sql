CREATE TABLE IF NOT EXISTS app_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY,
    token       TEXT NOT NULL,
    obtained_at INTEGER NOT NULL,
    expires_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS instruments (
    instrument_key  TEXT NOT NULL,
    trading_symbol  TEXT NOT NULL,
    exchange        TEXT NOT NULL,
    segment         TEXT NOT NULL,
    name            TEXT NOT NULL,
    instrument_type TEXT NOT NULL,
    expiry          TEXT,
    strike          REAL,
    lot_size        INTEGER NOT NULL,
    tick_size       REAL NOT NULL,
    loaded_on       TEXT NOT NULL,
    PRIMARY KEY (instrument_key, loaded_on)
);

CREATE TABLE IF NOT EXISTS ticks (
    key    TEXT    NOT NULL,
    ts     INTEGER NOT NULL,
    ltp    REAL    NOT NULL,
    volume INTEGER,
    oi     INTEGER,
    bid    REAL,
    ask    REAL,
    iv     REAL,
    delta  REAL
);
CREATE INDEX IF NOT EXISTS ix_ticks_key_ts ON ticks (key, ts);
CREATE INDEX IF NOT EXISTS ix_ticks_ts ON ticks (ts);

CREATE TABLE IF NOT EXISTS feed_events (
    ts     INTEGER NOT NULL,
    kind   TEXT    NOT NULL,
    detail TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS latency_samples (
    ts  INTEGER NOT NULL,
    hop TEXT    NOT NULL,
    p50 REAL    NOT NULL,
    p95 REAL    NOT NULL,
    p99 REAL    NOT NULL,
    n   INTEGER NOT NULL
);
