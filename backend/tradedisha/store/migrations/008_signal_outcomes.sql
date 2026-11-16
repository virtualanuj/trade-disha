-- What the option did after each signal fired, traded or not: the yardstick for tuning.
CREATE TABLE IF NOT EXISTS signal_outcomes (
    signal_id      TEXT    PRIMARY KEY,
    end_ts         INTEGER NOT NULL,   -- horizon end, or square-off if sooner
    result         TEXT    NOT NULL,   -- open | target | stop | neither
    result_ts      INTEGER,
    best_price     REAL    NOT NULL,
    best_ts        INTEGER NOT NULL,
    worst_price    REAL    NOT NULL,
    worst_ts       INTEGER NOT NULL,
    px_1m          REAL,
    px_5m          REAL,
    px_15m         REAL,
    spot_at_fire   REAL,
    spot_pre_move  REAL,               -- spot move over the 10 minutes before firing, signed
    spot_best_move REAL,               -- best spot move after firing, in the signal direction
    final          INTEGER NOT NULL DEFAULT 0
);

-- The quote at the moment of firing: what a buyer would really have paid.
ALTER TABLE signals ADD COLUMN entry_ask REAL;
ALTER TABLE signals ADD COLUMN spread_pct REAL;
