# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""Gmail読取専用OAuthの開始とコールバックを処理する。"""

from datetime import datetime, timedelta, timezone
import os
import secrets
from urllib.parse import urlencode

import requests

from src.api.kakeibo.expense_source.expenseSourceBase import ExpenseSourceBase
from src.common.api_utils import now_ymd_hms
from src.common.base import BaseRestApi
from src.common.base.base_lambda import BaseLambda
from src.common.functions.response import response


AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class GmailOAuthStart(BaseRestApi):
    """ログイン済み利用者向けにGoogle同意画面URLを発行する。"""

    def __init__(self, db_path=None):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)

    def main(self, request_dict):
        user_id = self.require_user_id(request_dict)
        client_id, _, redirect_uri = oauth_config()
        ExpenseSourceBase().ensure_schema()
        state = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        ymd, hms = now_ymd_hms()
        self.database.execute(
            """INSERT INTO GMAIL_OAUTH_TOKEN (
                   CRE_PROG, UPD_PROG, OAUTH_STATE, OAUTH_STATE_EXPIRES_AT, SCOPES,
                   CRE_DT, CRE_TM, UPD_DT, UPD_TM, CRE_USER_ID, UPD_USER_ID, DEL_FLAG
               ) VALUES (
                   'GmailOAuthStart', 'GmailOAuthStart', %(state)s, %(expires_at)s, %(scopes)s,
                   %(ymd)s, %(hms)s, %(ymd)s, %(hms)s, %(user_id)s, %(user_id)s, 0
               ) ON CONFLICT (CRE_USER_ID) WHERE DEL_FLAG=0 DO UPDATE SET
                   OAUTH_STATE=EXCLUDED.OAUTH_STATE,
                   OAUTH_STATE_EXPIRES_AT=EXCLUDED.OAUTH_STATE_EXPIRES_AT,
                   SCOPES=EXCLUDED.SCOPES,
                   UPD_PROG='GmailOAuthStart', UPD_DT=EXCLUDED.UPD_DT, UPD_TM=EXCLUDED.UPD_TM""",
            {"state": state, "expires_at": expires_at.isoformat(), "scopes": SCOPE,
             "ymd": ymd, "hms": hms, "user_id": user_id},
        )
        query = urlencode({
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        })
        return response(200, {"ok": True, "authorizationUrl": f"{AUTH_URL}?{query}"})


class GmailOAuthCallback(BaseLambda):
    """Googleから返されたcodeをtokenへ交換する公開コールバック。"""

    def __init__(self, db_path=None):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)

    def main(self, request_dict):
        query = request_dict.get("query") or {}
        state = str(query.get("state") or "")
        code = str(query.get("code") or "")
        rows = self.database.select(
            """SELECT * FROM GMAIL_OAUTH_TOKEN WHERE OAUTH_STATE=%(state)s AND DEL_FLAG=0
               ORDER BY ID DESC LIMIT 1""",
            {"state": state},
        )
        token_row = rows[0] if rows else {}
        expires_at = str(value(token_row, "OAUTH_STATE_EXPIRES_AT", "oauth_state_expires_at") or "")
        if not token_row or not code or not expires_at or datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
            return html_response(400, "Gmail連携に失敗しました。連携画面からもう一度お試しください。")
        client_id, client_secret, redirect_uri = oauth_config()
        token_response = requests.post(
            TOKEN_URL,
            data={"client_id": client_id, "client_secret": client_secret, "code": code,
                  "redirect_uri": redirect_uri, "grant_type": "authorization_code"},
            timeout=30,
        )
        token_response.raise_for_status()
        token_data = token_response.json()
        access_token = token_data["access_token"]
        profile = requests.get(PROFILE_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=30)
        profile.raise_for_status()
        user_id = str(value(token_row, "CRE_USER_ID", "cre_user_id"))
        expires = datetime.now(timezone.utc) + timedelta(seconds=int(token_data.get("expires_in") or 3600))
        self.database.update(
            """UPDATE GMAIL_OAUTH_TOKEN SET EMAIL_ADDRESS=%(email)s, ACCESS_TOKEN=%(access_token)s,
                   REFRESH_TOKEN=COALESCE(%(refresh_token)s, REFRESH_TOKEN), TOKEN_EXPIRES_AT=%(expires_at)s,
                   OAUTH_STATE=NULL, OAUTH_STATE_EXPIRES_AT=NULL, UPD_PROG='GmailOAuthCallback',
                   UPD_USER_ID=%(user_id)s WHERE ID=%(id)s AND DEL_FLAG=0""",
            {"email": profile.json().get("emailAddress") or "", "access_token": access_token,
             "refresh_token": token_data.get("refresh_token"), "expires_at": expires.isoformat(),
             "user_id": user_id, "id": value(token_row, "ID", "id")},
        )
        return html_response(200, "Gmail連携が完了しました。この画面を閉じて家計簿へ戻ってください。")


def oauth_config():
    client_id = str(os.environ.get("GMAIL_OAUTH_CLIENT_ID") or "")
    client_secret = str(os.environ.get("GMAIL_OAUTH_CLIENT_SECRET") or "")
    redirect_uri = str(os.environ.get("GMAIL_OAUTH_REDIRECT_URI") or "")
    if not client_id or not client_secret or not redirect_uri:
        raise RuntimeError("Gmail OAuth環境変数が設定されていません。")
    return client_id, client_secret, redirect_uri


def html_response(status_code, message):
    safe_message = str(message).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": f"<!doctype html><html lang='ja'><meta charset='utf-8'><title>Gmail連携</title>"
                f"<body><main><h1>Gmail連携</h1><p>{safe_message}</p></main></body></html>",
    }


def value(row, *keys):
    lower = {str(key).lower(): item for key, item in (row or {}).items()}
    for key in keys:
        if key in (row or {}):
            return row.get(key)
        if str(key).lower() in lower:
            return lower[str(key).lower()]
    return None
