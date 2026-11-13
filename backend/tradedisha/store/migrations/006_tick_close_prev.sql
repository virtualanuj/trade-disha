-- Previous close per instrument, so a replayed day can show change on the day.
-- Written only when it changes for a key, so almost every row leaves it NULL.
ALTER TABLE ticks ADD COLUMN close_prev REAL;
