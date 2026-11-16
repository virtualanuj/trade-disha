-- Order-flow fields from the Upstox full feed, recorded so the trigger can be studied
-- and replayed. NULL on every day recorded before this migration.
ALTER TABLE ticks ADD COLUMN bid_qty INTEGER;   -- quantity at the best bid
ALTER TABLE ticks ADD COLUMN ask_qty INTEGER;   -- quantity at the best ask
ALTER TABLE ticks ADD COLUMN bid_qty5 INTEGER;  -- quantity over the five bid levels
ALTER TABLE ticks ADD COLUMN ask_qty5 INTEGER;  -- quantity over the five ask levels
ALTER TABLE ticks ADD COLUMN tbq INTEGER;       -- total buy quantity pending
ALTER TABLE ticks ADD COLUMN tsq INTEGER;       -- total sell quantity pending
ALTER TABLE ticks ADD COLUMN atp REAL;          -- exchange average traded price
ALTER TABLE ticks ADD COLUMN ltq INTEGER;       -- last traded quantity
