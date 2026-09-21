# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from src.common.api_utils import now_ymd_hms
from src.common.functions.response import response
from src.common.auth_token import issue_token, verify_token
from src.common.base import BaseRestApi


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
RESET_TOKEN_MINUTES = 30


class UserAuthBase(BaseRestApi):
    """アカウント登録、認証、プロフィール更新の共通処理。"""

    _account_columns_ready = False

    def __init__(self, db_path=None):
        """
        クラスを初期化する。

        Args:
            db_path (Any): 旧呼び出し互換のためのDB指定。

        Returns:
            None: 戻り値なし。
        """
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)
        self.ensure_account_columns()

    def validate_body(self, request_dict):
        """
        リクエスト本文を検証する。

        Args:
            request_dict (Any): API呼び出し時のリクエスト情報。

        Returns:
            Any: 処理結果。
        """
        return super().validate_body(request_dict)

    def register(self, body):
        """
        registerの処理を実行する。

        Args:
            body (Any): リクエスト本文。

        Returns:
            Any: 処理結果。
        """
        username = self.normalize_email(body.get("email") or body.get("username"))
        password = str(body.get("password") or "")
        nickname = self.clean(body.get("nickname")) or username.split("@", 1)[0]

        if not self.is_valid_email(username):
            return response(400, {"errorMessage": "有効なメールアドレスを入力してください。"})
        if len(password) < 8:
            return response(400, {"errorMessage": "パスワードは8文字以上で入力してください。"})

        exists = self.database.select(
            self.database.read_sql("SELECT_USER_INFO", location=__file__),
            {"USER_NAME": username},
        )
        if exists:
            return response(409, {"errorMessage": "このメールアドレスはすでに登録されています。"})

        user_id = uuid.uuid4().hex
        ymd, hms = now_ymd_hms()
        self.database.insert(
            self.database.read_sql("INSERT_USER_INFO", location=__file__),
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
        """
        loginの処理を実行する。

        Args:
            body (Any): リクエスト本文。

        Returns:
            Any: 処理結果。
        """
        username = self.normalize_email(body.get("email") or body.get("username"))
        password = str(body.get("password") or "")
        if not self.is_valid_email(username):
            return response(400, {"errorMessage": "有効なメールアドレスを入力してください。"})
        if not password:
            return response(400, {"errorMessage": "パスワードを入力してください。"})

        rows = self.database.select(
            self.database.read_sql("SELECT_USER_INFO_02", location=__file__),
            {"USER_NAME": username},
        )
        if not rows or not self.password_matches(password, rows[0]):
            return response(401, {"errorMessage": "メールアドレスまたはパスワードが正しくありません。"})

        row = rows[0]
        return self.issue_session(
            self.row_value(row, "USER_ID"),
            self.row_value(row, "USER_NAME"),
            self.row_value(row, "NICKNAME"),
            self.row_value(row, "AVATAR_IMAGE"),
        )

    def logout(self, _body):
        """
        logoutの処理を実行する。

        Args:
            _body (Any): _bodyの値。

        Returns:
            Any: 処理結果。
        """
        return response(200, {"ok": True})

    def me(self, body):
        """
        meの処理を実行する。

        Args:
            body (Any): リクエスト本文。

        Returns:
            Any: 処理結果。
        """
        user = verify_token(body.get("token") or "")
        if not user:
            return response(200, None)
        rows = self.database.select(
            self.database.read_sql("SELECT_USER_INFO_03", location=__file__),
            {"USER_ID": user.get("userId")},
        )
        if rows:
            row = rows[0]
            return self.issue_session(
                self.row_value(row, "USER_ID"),
                self.row_value(row, "USER_NAME"),
                self.row_value(row, "NICKNAME"),
                self.row_value(row, "AVATAR_IMAGE"),
            )
        return self.issue_session(
            user.get("userId"),
            user.get("email") or user.get("username"),
            user.get("nickname"),
            user.get("avatarImage"),
        )

    def update_profile(self, body):
        """
        update_profileの処理を実行する。

        Args:
            body (Any): リクエスト本文。

        Returns:
            Any: 処理結果。
        """
        user = verify_token(body.get("token") or "")
        user_id = user.get("userId")
        if not user_id:
            return response(401, {"errorMessage": "ログインが必要です。"})

        nickname = self.clean(body.get("nickname"))
        avatar_image = body.get("avatarImage")
        if not nickname:
            return response(400, {"errorMessage": "表示名を入力してください。"})
        if avatar_image is not None and len(str(avatar_image)) > 700000:
            return response(400, {"errorMessage": "アイコン画像が大きすぎます。"})

        ymd, hms = now_ymd_hms()
        self.database.update(
            self.database.read_sql("UPDATE_USER_INFO", location=__file__),
            {
                "UPD_PROG": "profile_update",
                "NICKNAME": nickname,
                "AVATAR_IMAGE": avatar_image or "",
                "UPD_DT": ymd,
                "UPD_TM": hms,
                "USER_ID": user_id,
            },
        )
        rows = self.database.select(
            self.database.read_sql("SELECT_USER_INFO_04", location=__file__),
            {"USER_ID": user_id},
        )
        if not rows:
            return response(404, {"errorMessage": "アカウントが見つかりません。"})
        row = rows[0]
        return self.issue_session(
            self.row_value(row, "USER_ID"),
            self.row_value(row, "USER_NAME"),
            self.row_value(row, "NICKNAME"),
            self.row_value(row, "AVATAR_IMAGE"),
        )

    def request_password_reset(self, body):
        """
        request_password_resetの処理を実行する。

        Args:
            body (Any): リクエスト本文。

        Returns:
            Any: 処理結果。
        """
        username = self.normalize_email(body.get("email") or body.get("username"))
        if not self.is_valid_email(username):
            return response(400, {"errorMessage": "有効なメールアドレスを入力してください。"})

        rows = self.database.select(
            self.database.read_sql("SELECT_USER_INFO_05", location=__file__),
            {"USER_NAME": username},
        )

        generic_body = {
            "ok": True,
            "message": "アカウントが存在する場合はリセットコードを発行しました。",
        }
        if not rows:
            return response(200, generic_body)

        reset_token = secrets.token_urlsafe(24)
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_MINUTES)).isoformat()
        ymd, hms = now_ymd_hms()
        self.database.update(
            self.database.read_sql("UPDATE_USER_INFO_02", location=__file__),
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
        return response(200, {**generic_body, "resetToken": reset_token, "expiresInMinutes": RESET_TOKEN_MINUTES})

    def reset_password(self, body):
        """
        reset_passwordの処理を実行する。

        Args:
            body (Any): リクエスト本文。

        Returns:
            Any: 処理結果。
        """
        username = self.normalize_email(body.get("email") or body.get("username"))
        reset_token = self.clean(body.get("resetToken") or body.get("token"))
        new_password = str(body.get("newPassword") or body.get("password") or "")

        if not self.is_valid_email(username):
            return response(400, {"errorMessage": "有効なメールアドレスを入力してください。"})
        if not reset_token:
            return response(400, {"errorMessage": "リセットコードを入力してください。"})
        if len(new_password) < 8:
            return response(400, {"errorMessage": "新しいパスワードは8文字以上で入力してください。"})

        rows = self.database.select(
            self.database.read_sql("SELECT_USER_INFO_06", location=__file__),
            {"USER_NAME": username},
        )
        if not rows or not self.reset_token_matches(reset_token, rows[0]):
            return response(400, {"errorMessage": "リセットコードが正しくありません。"})

        row = rows[0]
        if self.is_reset_token_expired(self.row_value(row, "RESET_TOKEN_EXPIRES_AT")):
            return response(400, {"errorMessage": "リセットコードの有効期限が切れています。"})

        ymd, hms = now_ymd_hms()
        self.database.update(
            self.database.read_sql("UPDATE_USER_INFO_03", location=__file__),
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
        return response(200, {"ok": True, "message": "パスワードを更新しました。"})

    def issue_session(self, user_id, username, nickname, avatar_image=""):
        """
        issue_sessionの処理を実行する。

        Args:
            user_id (Any): ユーザーID。
            username (Any): usernameの値。
            nickname (Any): nicknameの値。
            avatar_image (Any): avatar_imageの値。

        Returns:
            Any: 処理結果。
        """
        session = {
            "userId": user_id,
            "username": username,
            "email": username,
            "nickname": nickname or username,
            "avatarImage": avatar_image or "",
        }
        session["token"] = issue_token(session)
        return response(200, session)

    def password_matches(self, password, row):
        """
        password_matchesの処理を実行する。

        Args:
            password (Any): passwordの値。
            row (Any): rowの値。

        Returns:
            Any: 処理結果。
        """
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
        """
        reset_token_matchesの処理を実行する。

        Args:
            reset_token (Any): reset_tokenの値。
            row (Any): rowの値。

        Returns:
            Any: 処理結果。
        """
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
        """
        ensure_account_columnsの処理を実行する。

        Args:
            None: 引数なし。

        Returns:
            Any: 処理結果。
        """
        if not self.database or UserAuthBase._account_columns_ready:
            return
        for column in (
            "USER_PASSWORD", "RESET_TOKEN_HASH", "RESET_TOKEN_SALT",
            "RESET_TOKEN_EXPIRES_AT", "RESET_TOKEN_USED", "AVATAR_IMAGE",
        ):
            self.database.execute(self.database.read_sql(f"ALTER_USER_INFO_{column}", location=__file__))
        UserAuthBase._account_columns_ready = True

    def row_value(self, row, name, default=None):
        """
        row_valueの処理を実行する。

        Args:
            row (Any): rowの値。
            name (Any): nameの値。
            default (Any): defaultの値。

        Returns:
            Any: 処理結果。
        """
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
        """
        is_reset_token_expiredの処理を実行する。

        Args:
            expires_at (Any): expires_atの値。

        Returns:
            Any: 処理結果。
        """
        try:
            expires = datetime.fromisoformat(str(expires_at))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) > expires
        except Exception:
            return True

    def clean(self, value):
        """
        cleanの処理を実行する。

        Args:
            value (Any): valueの値。

        Returns:
            Any: 処理結果。
        """
        return str(value or "").strip()

    def normalize_email(self, value):
        """
        normalize_emailの処理を実行する。

        Args:
            value (Any): valueの値。

        Returns:
            Any: 処理結果。
        """
        return self.clean(value).lower()

    def is_valid_email(self, value):
        """
        is_valid_emailの処理を実行する。

        Args:
            value (Any): valueの値。

        Returns:
            Any: 処理結果。
        """
        return bool(EMAIL_PATTERN.match(value or ""))
