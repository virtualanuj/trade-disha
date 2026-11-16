-- Milestone E8: buyer- and seller-initiated volume per 1-minute candle, signed from the
-- ticks (quote rule, then tick rule). NULL where there is no side information: an index
-- has no volume, and backfilled minutes come from the candle API without trades.
ALTER TABLE candles_1m ADD COLUMN bv INTEGER;
ALTER TABLE candles_1m ADD COLUMN sv INTEGER;
