-- Milestone E20: paper trades opened by hand (enhancement 23, spec §10.1). Such a trade
-- stores 'manual' as its signal_id, so paper_trades needs no new column for it. Every set
-- of levels a trade has had is kept: the ones it opened with, then each edit.
CREATE TABLE IF NOT EXISTS paper_trade_levels (
    id       INTEGER PRIMARY KEY,
    trade_id TEXT    NOT NULL,
    ts       INTEGER NOT NULL,  -- market time
    target   REAL    NOT NULL,
    stop     REAL    NOT NULL,
    ltp      REAL    NOT NULL,  -- the price when they were set
    source   TEXT    NOT NULL   -- entry, edit
);
CREATE INDEX IF NOT EXISTS ix_paper_trade_levels_trade ON paper_trade_levels (trade_id);

-- Target or stop changed after the trade opened.
ALTER TABLE paper_trades ADD COLUMN levels_edited INTEGER NOT NULL DEFAULT 0;
