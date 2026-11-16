-- Milestone E6: bullion (MCX GOLD/SILVER) ticks, kept apart from `ticks` so evening MCX
-- trading never stretches an NSE replay. Same columns as `ticks`, plus the feed's day
-- candle, which MCX futures carry and the BULLION tab shows.
CREATE TABLE bullion_ticks (
    key        TEXT    NOT NULL,
    ts         INTEGER NOT NULL,
    ltp        REAL    NOT NULL,
    volume     INTEGER,
    oi         INTEGER,
    bid        REAL,
    ask        REAL,
    iv         REAL,
    delta      REAL,
    close_prev REAL,
    bid_qty    INTEGER,
    ask_qty    INTEGER,
    bid_qty5   INTEGER,
    ask_qty5   INTEGER,
    tbq        INTEGER,
    tsq        INTEGER,
    atp        REAL,
    ltq        INTEGER,
    day_open   REAL,
    day_high   REAL,
    day_low    REAL
);
CREATE INDEX ix_bullion_ticks_key_ts ON bullion_ticks (key, ts);
CREATE INDEX ix_bullion_ticks_ts ON bullion_ticks (ts);
