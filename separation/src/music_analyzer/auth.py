"""MySQL accounts, opaque sessions, and analysis ownership.

Audio stays on disk. MySQL is authoritative for access; missing ownership denies access.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import re
import secrets
from pathlib import Path
from uuid import uuid4

from .common import project_root
from .legal import ConsentError, require_consents

SESSION_SECONDS = 7 * 24 * 60 * 60
COOKIE_NAME = "music_session"


class AuthError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class DatabaseUnavailable(Exception):
    pass


def load_settings():
    values = {}
    path = project_root() / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    values.update(os.environ)
    return values


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000)
    return f"pbkdf2_sha256$600000${salt}${digest.hex()}"


def password_matches(password, encoded):
    try:
        algorithm, iterations, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or iterations != "600000":
            return False
        actual = password_hash(password, salt).split("$")[-1]
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


class AuthStore:
    def __init__(self, settings=None):
        self.settings = load_settings() if settings is None else settings
        self.secure_cookie = self.settings.get("AUTH_COOKIE_SECURE", "0") == "1"
        self.dummy_hash = password_hash(secrets.token_urlsafe(24))

    def connect(self, with_database=True):
        import pymysql
        try:
            return pymysql.connect(
                host=self.settings.get("MYSQL_HOST", "127.0.0.1"),
                port=int(self.settings.get("MYSQL_PORT", "3306")),
                user=self.settings.get("MYSQL_USER", "root"),
                password=self.settings.get("MYSQL_PASSWORD", ""),
                database=self.settings.get("MYSQL_DATABASE", "music_analyzer") if with_database else None,
                charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=5, read_timeout=10, write_timeout=10,
            )
        except pymysql.MySQLError:
            raise DatabaseUnavailable("MySQL 연결을 확인해 주세요.") from None

    def query(self, sql, args=()):
        import pymysql
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, args)
                result = cursor.fetchall()
            connection.commit()
            return result
        except pymysql.IntegrityError:
            raise
        except pymysql.MySQLError:
            raise DatabaseUnavailable("회원 DB를 사용할 수 없습니다. 연결 및 DDL 적용을 확인해 주세요.") from None
        finally:
            connection.close()

    def transaction(self, statements):
        import pymysql
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                for sql, args in statements:
                    cursor.execute(sql, args)
            connection.commit()
        except pymysql.IntegrityError:
            connection.rollback()
            raise
        except pymysql.MySQLError:
            connection.rollback()
            raise DatabaseUnavailable("회원 DB를 사용할 수 없습니다. 연결 및 DDL 적용을 확인해 주세요.") from None
        finally:
            connection.close()

    def check(self):
        for table in ("users", "sessions", "analysis_owners", "auth_attempts", "user_consents"):
            self.query(f"SELECT 1 FROM {table} LIMIT 1")

    def throttle(self, address):
        # Persistent, shared across server threads and restarts. Do not trust forwarded IP headers.
        bucket = hashlib.sha256(address.encode()).hexdigest()
        self.query("DELETE FROM auth_attempts WHERE expires_at <= UTC_TIMESTAMP()")
        self.query("INSERT INTO auth_attempts (bucket_hash, expires_at) VALUES (%s, DATE_ADD(UTC_TIMESTAMP(), INTERVAL 15 MINUTE)) ON DUPLICATE KEY UPDATE attempts=attempts+1", (bucket,))
        if self.query("SELECT attempts FROM auth_attempts WHERE bucket_hash=%s", (bucket,))[0]["attempts"] > 30:
            raise AuthError("시도가 너무 많습니다. 15분 후 다시 시도해 주세요.", 429)

    def credentials(self, data):
        if not isinstance(data, dict):
            raise AuthError("잘못된 요청입니다.")
        email, password = data.get("email"), data.get("password")
        if not isinstance(email, str) or not isinstance(password, str):
            raise AuthError("이메일과 비밀번호를 입력해 주세요.")
        email = email.strip().lower()
        if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise AuthError("올바른 이메일을 입력해 주세요.")
        if not 10 <= len(password) <= 128:
            raise AuthError("비밀번호는 10~128자로 입력해 주세요.")
        return email, password

    def register(self, data):
        """Email/password account creation. Consent is validated and stored independently of the provider."""
        import pymysql
        email, password = self.credentials(data)
        name = data.get("display_name", "")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise AuthError("닉네임은 1~80자로 입력해 주세요.")
        try:
            consents = require_consents(data.get("consents"))
        except ConsentError as error:
            raise AuthError(str(error)) from None
        user = {"id": uuid4().hex, "email": email, "display_name": name.strip()}
        try:
            self.transaction([("INSERT INTO users (id,email,display_name,password_hash) VALUES (%s,%s,%s,%s)",
                               (user["id"], email, user["display_name"], password_hash(password))),
                              *self.consent_statements(user["id"], consents)])
        except pymysql.IntegrityError:
            raise AuthError("이미 가입된 이메일입니다.", 409) from None
        return user

    @staticmethod
    def consent_statements(user_id, consents):
        return [("INSERT INTO user_consents (user_id,consent_type,policy_version) VALUES (%s,%s,%s)", (user_id, kind, version))
                for kind, version in consents.items()]

    def consents(self, user_id):
        return {row["consent_type"]: row["policy_version"] for row in
                self.query("SELECT consent_type,policy_version FROM user_consents WHERE user_id=%s", (user_id,))}

    def delete_account(self, user_id):
        """Remove sessions, ownership rows, consents and the account itself in one transaction."""
        self.transaction([("DELETE FROM analysis_owners WHERE user_id=%s", (user_id,)),
                          ("DELETE FROM user_consents WHERE user_id=%s", (user_id,)),
                          ("DELETE FROM sessions WHERE user_id=%s", (user_id,)),
                          ("DELETE FROM users WHERE id=%s", (user_id,))])

    def release(self, identifier):
        self.query("DELETE FROM analysis_owners WHERE analysis_id=%s", (identifier,))

    def login(self, data):
        email, password = self.credentials(data)
        rows = self.query("SELECT id,email,display_name,password_hash FROM users WHERE email=%s", (email,))
        valid = password_matches(password, rows[0]["password_hash"] if rows else self.dummy_hash)
        if not rows or not valid:
            raise AuthError("이메일 또는 비밀번호가 일치하지 않습니다.", 401)
        return {key: rows[0][key] for key in ("id", "email", "display_name")}

    def new_session(self, user_id):
        token = secrets.token_urlsafe(32)
        self.query("DELETE FROM sessions WHERE expires_at<=UTC_TIMESTAMP()")
        self.query("INSERT INTO sessions (token_hash,user_id,expires_at) VALUES (%s,%s,DATE_ADD(UTC_TIMESTAMP(), INTERVAL 7 DAY))",
                   (hashlib.sha256(token.encode()).hexdigest(), user_id))
        return token

    def session_user(self, token):
        if not token or len(token) > 128:
            return None
        rows = self.query("SELECT u.id,u.email,u.display_name FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=%s AND s.expires_at>UTC_TIMESTAMP()",
                          (hashlib.sha256(token.encode()).hexdigest(),))
        return rows[0] if rows else None

    def logout(self, token):
        self.query("DELETE FROM sessions WHERE token_hash=%s", (hashlib.sha256(token.encode()).hexdigest(),))

    def owned_ids(self, user_id):
        return {row["analysis_id"] for row in self.query("SELECT analysis_id FROM analysis_owners WHERE user_id=%s", (user_id,))}

    def owns(self, user_id, identifier):
        return bool(self.query("SELECT 1 FROM analysis_owners WHERE user_id=%s AND analysis_id=%s", (user_id, identifier)))

    def assign(self, user_id, identifier):
        self.query("INSERT INTO analysis_owners (analysis_id,user_id) VALUES (%s,%s)", (identifier, user_id))


def main():
    parser = argparse.ArgumentParser(description="Initialize MySQL account tables (non-destructive).")
    parser.add_argument("--init-db", action="store_true", required=True)
    parser.parse_args()
    store = AuthStore()
    if store.settings.get("MYSQL_DATABASE", "music_analyzer") != "music_analyzer":
        parser.error("The supplied DDL targets music_analyzer.")
    connection = store.connect(with_database=False)
    try:
        with connection.cursor() as cursor:
            for script in sorted((project_root() / "separation/sql").glob("*.sql")):
                for statement in script.read_text(encoding="utf-8").split(";"):
                    if statement.strip():
                        cursor.execute(statement)
        connection.commit()
    finally:
        connection.close()
    store.check()
    print("music_analyzer account schema ready.")


if __name__ == "__main__":
    main()
