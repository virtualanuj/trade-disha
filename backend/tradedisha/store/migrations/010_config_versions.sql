-- Every saved set of tunable parameters, numbered and tagged; the highest version is the
-- one in force. A signal points at the version it fired under.
CREATE TABLE config_versions (
    version       INTEGER PRIMARY KEY,
    tag           TEXT NOT NULL,
    created_ts    INTEGER NOT NULL,
    source        TEXT NOT NULL,  -- seed | edit | revert
    reverted_from INTEGER REFERENCES config_versions(version),
    params_json   TEXT NOT NULL
);

ALTER TABLE signals ADD COLUMN config_version INTEGER REFERENCES config_versions(version);
