-- Milestone E17: the paper bank (spec §10.5). One account; its cash moves are a ledger:
-- the opening deposit, then a deposit or withdrawal each time the opening balance changes.
CREATE TABLE IF NOT EXISTS bank_ledger (
    id              INTEGER PRIMARY KEY,
    ts              INTEGER NOT NULL,  -- wall clock
    kind            TEXT    NOT NULL,  -- OPEN, DEPOSIT, WITHDRAW
    amount          REAL    NOT NULL,  -- always positive
    opening_balance REAL    NOT NULL,  -- the parameter after this entry
    config_version  INTEGER
);

-- Money a paper trade holds while open, and whether the bank funded it. Trades from before
-- this milestone were not funded and never count.
ALTER TABLE paper_trades ADD COLUMN blocked REAL NOT NULL DEFAULT 0;
ALTER TABLE paper_trades ADD COLUMN banked INTEGER NOT NULL DEFAULT 0;
