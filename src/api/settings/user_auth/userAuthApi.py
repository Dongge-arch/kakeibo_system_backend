# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from src.api.utils import json_response, now_ymd_hms
from src.common.auth_token import issue_token, verify_token
from src.common.base import BaseRestApi


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
RESET_TOKEN_MINUTES = 30


class UserAuthApi(BaseRestApi):
    """アカウント登録、ログイン、パスワード再設定を扱うAPI。"""

    _account_columns_ready = False

    def __init__(self, db_path=None):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)
        self.ensure_account_columns()

    def validate_body(self, request_dict):
        return super().validate_body(request_dict)

    def main(self, request_dict):
        body = request_dict.get("body") or {}
        action = body.get("action")

        if action == "register":
            return self.register(body)
        if action == "login":
            return self.login(body)
        if action == "logout":
            return self.logout(body)
        if action == "me":
            return self.me(body)
        if action == "request_password_reset":
            return self.request_password_reset(body)
        if action == "reset_password":
            return self.reset_password(body)

        return json_response(400, {"errorMessage": "不明なアカウント操作です。"})

    def register(self, body):
        username = self.normalize_email(body.get("email") or body.get("username"))
        password = str(body.get("password") or "")
        nickname = self.clean(body.get("nickname")) or username.split("@", 1)[0]

        if not self.is_valid_email(username):
            return json_response(400, {"errorMessage": "有効なメールアドレスを入力してください。"})
        if len(password) < 8:
            return json_response(400, {"errorMessage": "パスワードは8文字以上で入力してください。"})

        exists = self.database.select(
            """
            SELECT USER_ID FROM user_info
            WHERE USER_NAME = :USER_NAME
              AND DEL_FLAG = 0
            LIMIT 1
            """,
            {"USER_NAME": username},
        )
        if exists:
            return json_response(409, {"errorMessage": "このメールアドレスはすでに登録されています。"})

        user_id = uuid.uuid4().hex
        ymd, hms = now_ymd_hms()
        self.database.insert(
            """
            INSERT INTO user_info (
              CRE_PROG, UPD_PROG, USER_ID, USER_NAME, NICKNAME,
              USER_PASSWORD, PASSWORD_HASH, PASSWORD_SALT,
              CRE_DT, CRE_TM, UPD_DT, UPD_TM,
              CRE_USER_ID, UPD_USER_ID, DEL_FLAG
            ) VALUES (
              :CRE_PROG, :UPD_PROG, :USER_ID, :USER_NAME, :NICKNAME,
              :USER_PASSWORD, :PASSWORD_HASH, :PASSWORD_SALT,
              :CRE_DT, :CRE_TM, :UPD_DT, :UPD_TM,
              :CRE_USER_ID, :UPD_USER_ID, 0
            )
            """,
            {
                "CRE_PROG": "user_register",
                "UPD_PROG": "user_register",
                "USER_ID": user_id,
                "USER_NAME": username,
                "NICKNAME": nickname,
                "USER_PASSWORD": password,
                "PASSWORD_HASH": password,
                "PASSWORD_SALT": "",
                "CRE_DT": ymd,
                "CRE_TM": hms,
                "UPD_DT": ymd,
                "UPD_TM": hms,
                "CRE_USER_ID": user_id,
                "UPD_USER_ID": user_id,
            },
        )
        return self.issue_session(user_id, username, nickname)

    def login(self, body):
        username = self.normalize_email(body.get("email") or body.get("username"))
        password = str(body.get("password") or "")
        if not self.is_valid_email(username):
            return json_response(400, {"errorMessage": "有効なメールアドレスを入力してください。"})
        if not password:
            return json_response(400, {"errorMessage": "パスワードを入力してください。"})

        rows = self.database.select(
            """
            SELECT USER_ID, USER_NAME, NICKNAME, USER_PASSWORD, PASSWORD_HASH, PASSWORD_SALT
            FROM user_info
            WHERE USER_NAME = :USER_NAME
              AND DEL_FLAG = 0
            LIMIT 1
            """,
            {"USER_NAME": username},
        )
        if not rows or not self.password_matches(password, rows[0]):
            return json_response(401, {"errorMessage": "メールアドレスまたはパスワードが正しくありません。"})

        row = rows[0]
        return self.issue_session(
            self.row_value(row, "USER_ID"),
            self.row_value(row, "USER_NAME"),
            self.row_value(row, "NICKNAME"),
        )

    def logout(self, _body):
        return json_response(200, {"ok": True})

    def me(self, body):
        user = verify_token(body.get("token") or "")
        if not user:
            return json_response(200, None)
        return self.issue_session(
            user.get("userId"),
            user.get("email") or user.get("username"),
            user.get("nickname"),
        )

    def request_password_reset(self, body):
        username = self.normalize_email(body.get("email") or body.get("username"))
        if not self.is_valid_email(username):
            return json_response(400, {"errorMessage": "有効なメールアドレスを入力してください。"})

        rows = self.database.select(
            """
            SELECT USER_ID
            FROM user_info
            WHERE USER_NAME = :USER_NAME
              AND DEL_FLAG = 0
            LIMIT 1
            """,
            {"USER_NAME": username},
        )

        generic_body = {
            "ok": True,
            "message": "アカウントが存在する場合はリセットコードを発行しました。",
        }
        if not rows:
            return json_response(200, generic_body)

        reset_token = secrets.token_urlsafe(24)
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_MINUTES)).isoformat()
        ymd, hms = now_ymd_hms()
        self.database.update(
            """
            UPDATE user_info
            SET UPD_PROG = :UPD_PROG,
                RESET_TOKEN_HASH = :RESET_TOKEN_HASH,
                RESET_TOKEN_SALT = :RESET_TOKEN_SALT,
                RESET_TOKEN_EXPIRES_AT = :RESET_TOKEN_EXPIRES_AT,
                RESET_TOKEN_USED = 0,
                UPD_DT = :UPD_DT,
                UPD_TM = :UPD_TM
            WHERE USER_ID = :USER_ID
              AND DEL_FLAG = 0
            """,
            {
                "UPD_PROG": "password_reset_request",
                "RESET_TOKEN_HASH": reset_token,
                "RESET_TOKEN_SALT": "",
                "RESET_TOKEN_EXPIRES_AT": expires_at,
                "UPD_DT": ymd,
                "UPD_TM": hms,
                "USER_ID": self.row_value(rows[0], "USER_ID"),
            },
        )
        return json_response(200, {**generic_body, "resetToken": reset_token, "expiresInMinutes": RESET_TOKEN_MINUTES})

    def reset_password(self, body):
        username = self.normalize_email(body.get("email") or body.get("username"))
        reset_token = self.clean(body.get("resetToken") or body.get("token"))
        new_password = str(body.get("newPassword") or body.get("password") or "")

        if not self.is_valid_email(username):
            return json_response(400, {"errorMessage": "有効なメールアドレスを入力してください。"})
        if not reset_token:
            return json_response(400, {"errorMessage": "リセットコードを入力してください。"})
        if len(new_password) < 8:
            return json_response(400, {"errorMessage": "新しいパスワードは8文字以上で入力してください。"})

        rows = self.database.select(
            """
            SELECT USER_ID, RESET_TOKEN_HASH, RESET_TOKEN_SALT, RESET_TOKEN_EXPIRES_AT, RESET_TOKEN_USED
            FROM user_info
            WHERE USER_NAME = :USER_NAME
              AND DEL_FLAG = 0
            LIMIT 1
            """,
            {"USER_NAME": username},
        )
        if not rows or not self.reset_token_matches(reset_token, rows[0]):
            return json_response(400, {"errorMessage": "リセットコードが正しくありません。"})

        row = rows[0]
        if self.is_reset_token_expired(self.row_value(row, "RESET_TOKEN_EXPIRES_AT")):
            return json_response(400, {"errorMessage": "リセットコードの有効期限が切れています。"})

        ymd, hms = now_ymd_hms()
        self.database.update(
            """
            UPDATE user_info
            SET UPD_PROG = :UPD_PROG,
                USER_PASSWORD = :USER_PASSWORD,
                PASSWORD_HASH = :PASSWORD_HASH,
                PASSWORD_SALT = :PASSWORD_SALT,
                RESET_TOKEN_HASH = NULL,
                RESET_TOKEN_SALT = NULL,
                RESET_TOKEN_EXPIRES_AT = NULL,
                RESET_TOKEN_USED = 1,
                UPD_DT = :UPD_DT,
                UPD_TM = :UPD_TM
            WHERE USER_ID = :USER_ID
              AND DEL_FLAG = 0
            """,
            {
                "UPD_PROG": "password_reset_confirm",
                "USER_PASSWORD": new_password,
                "PASSWORD_HASH": new_password,
                "PASSWORD_SALT": "",
                "UPD_DT": ymd,
                "UPD_TM": hms,
                "USER_ID": self.row_value(row, "USER_ID"),
            },
        )
        return json_response(200, {"ok": True, "message": "パスワードを更新しました。"})

    def issue_session(self, user_id, username, nickname):
        session = {
            "userId": user_id,
            "username": username,
            "email": username,
            "nickname": nickname or username,
        }
        session["token"] = issue_token(session)
        return json_response(200, session)

    def password_matches(self, password, row):
        plain_password = self.row_value(row, "USER_PASSWORD") or ""
        if plain_password and hmac.compare_digest(str(password), str(plain_password)):
            return True

        legacy_value = self.row_value(row, "PASSWORD_HASH") or ""
        legacy_salt = self.row_value(row, "PASSWORD_SALT") or ""
        if legacy_value and hmac.compare_digest(str(password), str(legacy_value)):
            return True
        if legacy_value and legacy_salt:
            expected = hashlib.pbkdf2_hmac(
                "sha256",
                str(password).encode("utf-8"),
                str(legacy_salt).encode("utf-8"),
                120000,
            ).hex()
            return hmac.compare_digest(expected, str(legacy_value))
        return False

    def reset_token_matches(self, reset_token, row):
        token_used = str(self.row_value(row, "RESET_TOKEN_USED") or "0") in ("1", "true", "True")
        if token_used:
            return False
        stored = self.row_value(row, "RESET_TOKEN_HASH") or ""
        salt = self.row_value(row, "RESET_TOKEN_SALT") or ""
        if stored and hmac.compare_digest(str(reset_token), str(stored)):
            return True
        if stored and salt:
            expected = hashlib.pbkdf2_hmac(
                "sha256",
                str(reset_token).encode("utf-8"),
                str(salt).encode("utf-8"),
                120000,
            ).hex()
            return hmac.compare_digest(expected, str(stored))
        return False

    def ensure_account_columns(self):
        if not self.database or self.__class__._account_columns_ready:
            return

        columns = {
            "USER_PASSWORD": "USER_PASSWORD TEXT",
            "RESET_TOKEN_HASH": "RESET_TOKEN_HASH TEXT",
            "RESET_TOKEN_SALT": "RESET_TOKEN_SALT TEXT",
            "RESET_TOKEN_EXPIRES_AT": "RESET_TOKEN_EXPIRES_AT TEXT",
            "RESET_TOKEN_USED": "RESET_TOKEN_USED INTEGER DEFAULT 0",
        }
        for ddl in columns.values():
            self.database.execute(f"ALTER TABLE user_info ADD COLUMN IF NOT EXISTS {ddl}")
        self.__class__._account_columns_ready = True

    def row_value(self, row, name, default=None):
        if not row:
            return default
        if name in row:
            return row.get(name)
        lowered = name.lower()
        for key, value in row.items():
            if str(key).lower() == lowered:
                return value
        return default

    def is_reset_token_expired(self, expires_at):
        try:
            expires = datetime.fromisoformat(str(expires_at))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) > expires
        except Exception:
            return True

    def clean(self, value):
        return str(value or "").strip()

    def normalize_email(self, value):
        return self.clean(value).lower()

    def is_valid_email(self, value):
        return bool(EMAIL_PATTERN.match(value or ""))
