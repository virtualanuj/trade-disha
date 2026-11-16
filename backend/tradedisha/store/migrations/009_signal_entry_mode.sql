-- Which rule fired a signal, and whether it was the live rule or the one run in shadow.
ALTER TABLE signals ADD COLUMN entry_mode TEXT NOT NULL DEFAULT 'minute_close';
ALTER TABLE signals ADD COLUMN shadow INTEGER NOT NULL DEFAULT 0;
ALTER TABLE signals ADD COLUMN flow_score REAL;  -- order-flow score when a trigger signal fired
