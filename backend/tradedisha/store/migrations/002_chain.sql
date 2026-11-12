CREATE TABLE IF NOT EXISTS chain_minutes (
    idx            TEXT    NOT NULL,
    minute_ts      INTEGER NOT NULL,
    strike         REAL    NOT NULL,
    ce_ltp         REAL,
    ce_oi          INTEGER,
    ce_oi_chg_open INTEGER,
    ce_iv          REAL,
    ce_buildup     TEXT,
    pe_ltp         REAL,
    pe_oi          INTEGER,
    pe_oi_chg_open INTEGER,
    pe_iv          REAL,
    pe_buildup     TEXT,
    atm            REAL    NOT NULL,
    pcr            REAL,
    max_pain       REAL,
    PRIMARY KEY (idx, minute_ts, strike)
);
