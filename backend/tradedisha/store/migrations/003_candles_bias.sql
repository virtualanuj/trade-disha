CREATE TABLE IF NOT EXISTS candles_1m (
    key       TEXT    NOT NULL,
    minute_ts INTEGER NOT NULL,
    o         REAL    NOT NULL,
    h         REAL    NOT NULL,
    l         REAL    NOT NULL,
    c         REAL    NOT NULL,
    v         INTEGER NOT NULL,
    synthetic INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (key, minute_ts)
);

CREATE TABLE IF NOT EXISTS bias_minutes (
    idx            TEXT    NOT NULL,
    minute_ts      INTEGER NOT NULL,
    bias           REAL    NOT NULL,
    label          TEXT    NOT NULL,
    strength       INTEGER NOT NULL,
    breakdown_json TEXT    NOT NULL,
    PRIMARY KEY (idx, minute_ts)
);
