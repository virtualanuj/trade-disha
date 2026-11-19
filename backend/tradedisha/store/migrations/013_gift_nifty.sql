-- Milestone E14: GIFT Nifty at the previous NSE close and just before the open, one row per
-- NSE trading day, for NIFTY's opening-gap vote. Kept so a replay reads it without Upstox.
CREATE TABLE gift_nifty (
    day           TEXT    PRIMARY KEY,  -- the NSE trading day, ISO
    ref_ts        INTEGER NOT NULL,     -- minute of GIFT's last close before the previous 15:30
    ref_close     REAL    NOT NULL,
    preopen_ts    INTEGER NOT NULL,     -- minute of its last close before today's open
    preopen_price REAL    NOT NULL,
    fetched_at    INTEGER NOT NULL      -- wall clock, epoch ms
);
