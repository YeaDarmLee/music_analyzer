CREATE DATABASE IF NOT EXISTS music_analyzer CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE music_analyzer;

CREATE TABLE IF NOT EXISTS users (
    id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
    email VARCHAR(254) NOT NULL,
    display_name VARCHAR(80) NOT NULL,
    password_hash VARCHAR(255) CHARACTER SET ascii NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sessions (
    token_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
    user_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY ix_sessions_expiry (expires_at),
    KEY ix_sessions_user (user_id),
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS analysis_owners (
    analysis_id VARCHAR(48) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
    user_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY ix_analyses_user (user_id, created_at),
    CONSTRAINT fk_analyses_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS auth_attempts (
    bucket_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
    attempts INT UNSIGNED NOT NULL DEFAULT 1,
    expires_at DATETIME NOT NULL,
    KEY ix_attempts_expiry (expires_at)
) ENGINE=InnoDB;
