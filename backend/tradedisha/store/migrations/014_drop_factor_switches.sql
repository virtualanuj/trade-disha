-- Milestone E16: factor switches moved into the versioned config (`factors`), every
-- factor starting on; the separate store of Milestone E15 is dropped.
DELETE FROM app_state WHERE key = 'factors_off';
