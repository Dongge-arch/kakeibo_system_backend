# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""Gmailから当日分の電子レシートを取得し、家計簿へ登録する。"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
import html as html_module
import re
from zoneinfo import ZoneInfo

import requests

from src.common.base.base_auto_input import BaseAutoInput
from src.common.const.datetime import TIME_ZONE_JST
from src.common.functions.response import response


GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
RECEIPT_WORDS = ("領収", "レシート", "ご注文", "注文確認", "購入", "お支払い", "決済")


class GmailReceiptImporter(BaseAutoInput):
    """OAuth済みGmailの当日メールを電子レシートとして取り込む。"""

    def __init__(self, db_path=None):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path or None)

    def main(self, request_dict):
        user_id = self.require_user_id(request_dict)
        token = self.get_token(user_id)
        if not token or not self.value(token, "REFRESH_TOKEN", "refresh_token"):
            return response(200, {
                "ok": False,
                "status": "OAUTH_REQUIRED",
                "message": "先にGoogleアカウントを連携してください。",
            })
        access_token = self.refresh_access_token(token, user_id)
        messages = self.list_today_messages(access_token)
        registered = duplicate = skipped = failed = 0
        for item in messages:
            message = self.get_message(access_token, item["id"])
            receipt = self.parse_message(message)
            if not receipt:
                skipped += 1
                continue
            result = self.register_receipt(self.receipt_info(receipt, item["id"], user_id), user_id)
            status_code = int(result.get("statusCode", 500))
            if status_code == 409:
                duplicate += 1
            elif status_code >= 400:
                failed += 1
            else:
                registered += 1
        return response(200, {
            "ok": True,
            "status": "COMPLETED",
            "message": f"当日メールから電子レシートを{registered}件登録しました。",
            "fetchedCount": len(messages),
            "registeredCount": registered,
            "duplicateCount": duplicate,
            "skippedCount": skipped,
            "failedCount": failed,
        })

    def get_token(self, user_id):
        rows = self.database.select(
            """SELECT * FROM GMAIL_OAUTH_TOKEN
               WHERE CRE_USER_ID=%(user_id)s AND DEL_FLAG=0 ORDER BY ID DESC LIMIT 1""",
            {"user_id": user_id},
        )
        return rows[0] if rows else {}

    def refresh_access_token(self, token, user_id):
        """保存済みrefresh tokenから短期access tokenを発行する。"""
        import os

        client_id = str(os.environ.get("GMAIL_OAUTH_CLIENT_ID") or "")
        client_secret = str(os.environ.get("GMAIL_OAUTH_CLIENT_SECRET") or "")
        if not client_id or not client_secret:
            raise RuntimeError("Gmail OAuth環境変数が設定されていません。")
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": self.value(token, "REFRESH_TOKEN", "refresh_token"),
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        expires_at = datetime.now(ZoneInfo("UTC")) + timedelta(seconds=int(data.get("expires_in") or 3600))
        self.database.update(
            """UPDATE GMAIL_OAUTH_TOKEN SET ACCESS_TOKEN=%(access_token)s,
                   TOKEN_EXPIRES_AT=%(expires_at)s, UPD_PROG='GmailReceiptImporter',
                   UPD_USER_ID=%(user_id)s WHERE CRE_USER_ID=%(user_id)s AND DEL_FLAG=0""",
            {"access_token": data["access_token"], "expires_at": expires_at.isoformat(), "user_id": user_id},
        )
        self.database.commit()
        return data["access_token"]

    def list_today_messages(self, access_token):
        """日本時間の当日範囲と電子レシート関連語でメールを絞り込む。"""
        today = datetime.now(ZoneInfo(TIME_ZONE_JST)).date()
        tomorrow = today + timedelta(days=1)
        query = (
            f"after:{today:%Y/%m/%d} before:{tomorrow:%Y/%m/%d} "
            "(領収書 OR レシート OR 注文 OR 購入 OR お支払い OR 決済)"
        )
        response = requests.get(
            f"{GMAIL_API}/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"q": query, "maxResults": 100},
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("messages") or []

    @staticmethod
    def get_message(access_token, message_id):
        response = requests.get(
            f"{GMAIL_API}/messages/{message_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"format": "full"},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    @classmethod
    def parse_message(cls, message):
        """件名、送信元、本文から高信頼の店舗・日付・合計金額を抽出する。"""
        payload = message.get("payload") or {}
        headers = {str(row.get("name") or "").lower(): str(row.get("value") or "") for row in payload.get("headers") or []}
        subject = headers.get("subject", "")
        if not any(word in subject for word in RECEIPT_WORDS):
            return None
        body = cls.message_text(payload)
        text = re.sub(r"\s+", " ", html_module.unescape(body)).strip()
        amount = cls.currency_amount(text)
        if amount is None:
            return None
        internal_date = int(message.get("internalDate") or 0)
        receipt_dt = datetime.fromtimestamp(internal_date / 1000, ZoneInfo(TIME_ZONE_JST)) if internal_date else datetime.now(ZoneInfo(TIME_ZONE_JST))
        sender = headers.get("from", "")
        merchant = re.sub(r"\s*<[^>]+>\s*", "", sender).strip(' "') or subject
        item_name = re.sub(r"^(?:Re:|Fwd:)\s*", "", subject, flags=re.IGNORECASE).strip()
        return {
            "merchant": merchant[:255],
            "itemName": item_name[:255] or "電子レシート",
            "amount": amount,
            "date": receipt_dt.strftime("%Y-%m-%d"),
            "time": receipt_dt.strftime("%H:%M:%S"),
        }

    @classmethod
    def message_text(cls, payload):
        values = []
        body_data = (payload.get("body") or {}).get("data")
        if body_data:
            values.append(cls.decode_base64url(body_data))
        for part in payload.get("parts") or []:
            mime = str(part.get("mimeType") or "")
            if mime.startswith("multipart/"):
                values.append(cls.message_text(part))
                continue
            data = (part.get("body") or {}).get("data")
            if data and mime in {"text/plain", "text/html"}:
                values.append(cls.decode_base64url(data))
        return " ".join(values)

    @staticmethod
    def decode_base64url(value):
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(f"{value}{padding}").decode("utf-8", errors="replace")

    @staticmethod
    def currency_amount(text):
        # 2026-11-11 Codex: 通貨記号の左側にある商品番号・数量を誤って価格にしない。
        matches = re.findall(r"[¥￥]\s*(-?[0-9][0-9,]*(?:\.[0-9]{1,2})?)", str(text or ""))
        if not matches:
            matches = re.findall(r"(?:合計|請求|支払)[^0-9-]{0,12}(-?[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*円", str(text or ""))
        if not matches:
            return None
        value = float(matches[-1].replace(",", ""))
        return int(value) if value.is_integer() else value

    @staticmethod
    def receipt_info(receipt, message_id, user_id):
        amount = abs(receipt["amount"])
        return {
            "userId": user_id,
            "invoiceRegistrationNumber": "GMAIL",
            "supplierName": receipt["merchant"],
            "storeName": receipt["merchant"],
            "receiptNo": str(message_id)[:24],
            "receiptDate": receipt["date"],
            "receiptTime": receipt["time"],
            "taxFlag": 1,
            "receiptDetailCount": 1,
            "receiptDetails": [{
                "itemName": receipt["itemName"],
                "category1": "その他",
                "category2": "未分類",
                "taxRate": 0.10,
                "quantity": 1,
                "unit": "件",
                "unitPrice": amount,
                "discount": 0,
                "totalPrice": amount,
            }],
            "totalPrice": amount,
            "supplierImage": "",
        }
