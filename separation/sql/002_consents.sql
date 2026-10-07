USE music_analyzer;

CREATE TABLE IF NOT EXISTS user_consents (
    user_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    consent_type VARCHAR(16) CHARACTER SET ascii NOT NULL,
    policy_version VARCHAR(32) CHARACTER SET ascii NOT NULL,
    accepted_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (user_id, consent_type, policy_version),
    CONSTRAINT fk_consents_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;
