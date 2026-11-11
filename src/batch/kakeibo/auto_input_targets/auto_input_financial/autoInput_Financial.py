# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""外部決済サイトへログインし、履歴HTMLから出費源または購入小票を取り込む。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
import uuid

from bs4 import BeautifulSoup
import requests

from src.api.kakeibo.expense_source.expenseSourceBase import ExpenseSourceBase
from src.api.kakeibo.receipt.new_receipt_registration.newReceiptRegistration import NewReceiptRegistration
from src.common.api_utils import now_ymd_hms
from src.common.auth_context import reset_current_user_id, set_current_user_id
from src.common.base.base_auto_input import BaseAutoInput
from src.common.functions.response import response


class NetworkRestrictionError(RuntimeError):
    """AWS側IP制限、bot対策、JavaScript必須画面をServerへ引き継ぐための例外。"""


@dataclass(frozen=True)
class FinancialService:
    connection_type: str
    display_name: str
    login_url: str
    history_url: str
    source_kind: str
    marketplace_receipt: bool = False


FINANCIAL_SERVICES = {
    "MERCARI_MARKET": FinancialService(
        "MERCARI_MARKET", "メルカリ購入", "https://jp.mercari.com/login",
        "https://jp.mercari.com/mypage/purchases", "MARKETPLACE", True,
    ),
    "MERCARD": FinancialService(
        "MERCARD", "メルカード", "https://jp.mercari.com/login",
        "https://jp.mercari.com/mypage/merpay/credit", "CREDIT_CARD",
    ),
    "PAYPAY": FinancialService(
        "PAYPAY", "PayPay", "https://www.paypay.ne.jp/portal/",
        "https://www.paypay.ne.jp/portal/history", "QR_PAYMENT",
    ),
    "MUFG_BANK": FinancialService(
        "MUFG_BANK", "三菱UFJ銀行口座", "https://direct.bk.mufg.jp/",
        "https://direct.bk.mufg.jp/", "BANK_ACCOUNT",
    ),
    "MDC": FinancialService(
        "MDC", "My Digital Connect", "https://www2.mufgcard.com/",
        "https://www2.mufgcard.com/", "CREDIT_CARD",
    ),
}


class AutoInput_Financial(BaseAutoInput):
    """設定された金融・決済サービスを共通フローで取り込む。"""

    def __init__(self, connection_type, db_path=None):
        self.service = FINANCIAL_SERVICES[str(connection_type or "").upper()]
        super().__init__(class_name=f"AutoInput_{self.service.connection_type}", db_path=db_path or None)
        self._validate_headers_functions = {}
        self._validate_body_functions = {}

    def main(self, request_dict):
        user_id = self.require_user_id(request_dict)
        body = request_dict.get("body") or {}
        config = self.get_config(user_id)
        try:
            if body.get("action") == "submit":
                result = self.submit_challenge(config, user_id, body)
            else:
                result = self.start(config, user_id)
            return response(200, result)
        except NetworkRestrictionError as exc:
            # 2026-11-11 Codex: BaseLambdaで例外が500へ変換される前に、Server引継ぎ可能な状態として返す。
            return response(200, {
                "ok": False,
                "status": "SERVER_REQUIRED",
                "message": "AWSから接続できないため、Serverで処理を継続します。",
                "reason": str(exc)[:1000],
            })

    def start(self, config, user_id):
        """ログイン後の履歴ページを取得し、OTPがあれば入力待ちで返す。"""
        account_id = str(self.value(config, "LOGIN_ID_1", "login_id_1") or "").strip()
        password = str(self.value(config, "LOGIN_PW_1", "login_pw_1") or "")
        if not account_id or not password:
            return {"ok": False, "status": "CONFIG_REQUIRED", "message": "先にログイン情報を保存してください。"}
        session = self.new_session()
        response = self.safe_get(session, self.login_url(config))
        response = self.submit_login_form(session, response, account_id, password)
        challenge = self.find_challenge_form(response)
        if challenge:
            return self.save_challenge(config, user_id, session, challenge)
        if self.looks_like_login(response):
            return {"ok": False, "status": "LOGIN_FAILED", "message": "ログイン情報または追加認証を確認してください。"}
        history_response = self.safe_get(session, self.history_url(config))
        return self.complete_import(history_response.text, user_id)

    def submit_challenge(self, config, user_id, body):
        """保存済みセッションへ確認コードを送信して履歴取得を再開する。"""
        challenge_id = str(body.get("challengeId") or "")
        verification_code = str(body.get("verificationCode") or body.get("captcha") or "").strip()
        if challenge_id != str(self.value(config, "SUICA_CHALLENGE_ID", "suica_challenge_id") or ""):
            return {"ok": False, "status": "CHALLENGE_EXPIRED", "message": "確認コードを再取得してください。"}
        expires_at = self.value(config, "SUICA_CHALLENGE_EXPIRES_AT", "suica_challenge_expires_at")
        if not expires_at or datetime.fromisoformat(str(expires_at)) < datetime.now(timezone.utc):
            return {"ok": False, "status": "CHALLENGE_EXPIRED", "message": "確認コードの有効期限が切れました。"}
        if not verification_code:
            return {"ok": False, "status": "OTP_REQUIRED", "message": "確認コードを入力してください。"}

        session = self.new_session()
        self.restore_cookies(session, json.loads(self.value(config, "SUICA_COOKIE_JSON", "suica_cookie_json") or "[]"))
        form_info = json.loads(self.value(config, "SUICA_FORM_JSON", "suica_form_json") or "{}")
        payload = form_info.get("fields") or {}
        payload[form_info.get("codeField") or "verificationCode"] = verification_code
        response = session.post(
            self.value(config, "SUICA_FORM_ACTION", "suica_form_action") or form_info.get("action"),
            data=payload,
            timeout=30,
            allow_redirects=True,
        )
        self.raise_for_access(response)
        next_challenge = self.find_challenge_form(response)
        if next_challenge:
            return self.save_challenge(config, user_id, session, next_challenge)
        history_response = self.safe_get(session, self.history_url(config))
        return self.complete_import(history_response.text, user_id)

    def complete_import(self, html, user_id):
        """履歴HTMLを解析し、購入小票または出費源として保存する。"""
        rows = self.parse_history_html(html)
        if not rows:
            if self.javascript_only_html(html):
                raise NetworkRestrictionError(f"{self.service.display_name}はブラウザ実行が必要です。")
            return {"ok": True, "status": "COMPLETED", "message": "新しい履歴はありません。", "fetchedCount": 0,
                    "registeredCount": 0, "duplicateCount": 0, "failedCount": 0}

        if self.service.marketplace_receipt:
            registered, duplicate, failed = self.register_marketplace_receipts(rows, user_id)
            return {"ok": True, "status": "COMPLETED", "message": f"メルカリ購入小票を{registered}件登録しました。",
                    "fetchedCount": len(rows), "registeredCount": registered,
                    "duplicateCount": duplicate, "failedCount": failed}

        expense_service = ExpenseSourceBase()
        inserted = 0
        for row in rows:
            expense_service.upsert_source(user_id, {
                "sourceType": self.service.connection_type,
                "externalId": row["externalId"],
                "transactionDate": row["transactionDate"],
                "transactionTime": row.get("transactionTime"),
                "merchantName": row["merchantName"],
                "amount": row["amount"],
                "currency": "JPY",
                "direction": row.get("direction") or "DEBIT",
                "sourceKind": self.service.source_kind,
                "accountLabel": self.service.display_name,
                "rawData": row,
            })
            inserted += 1
        expense_service.database.commit()
        return {"ok": True, "status": "COMPLETED", "message": f"{self.service.display_name}の出費源を{inserted}件取り込みました。",
                "fetchedCount": len(rows), "insertedCount": inserted,
                "registeredCount": inserted, "duplicateCount": 0, "failedCount": 0}

    def parse_history_html(self, html):
        """表・一覧要素から日付、店舗、通貨記号右側の金額を抽出する。"""
        soup = BeautifulSoup(html or "", "html.parser")
        candidates = list(soup.select("tr"))
        if not candidates:
            candidates = list(soup.select("article, li, [data-transaction], [data-order]"))
        rows = []
        seen = set()
        for element in candidates:
            text = " ".join(element.stripped_strings)
            date = self.parse_date(text)
            amount = self.parse_currency_amount(text)
            if not date or amount is None:
                continue
            merchant = self.parse_merchant(text, date, amount)
            if not merchant:
                continue
            transaction_time = self.parse_time(text)
            external_id = self.external_id(element, text, date, merchant, amount)
            if external_id in seen:
                continue
            seen.add(external_id)
            rows.append({
                "externalId": external_id,
                "transactionDate": date,
                "transactionTime": transaction_time,
                "merchantName": merchant,
                "amount": amount,
                "direction": "CREDIT" if any(word in text for word in ("返金", "入金", "取消")) else "DEBIT",
                "rawText": text[:2000],
            })
        return rows

    def register_marketplace_receipts(self, rows, user_id):
        """メルカリ購入履歴を一購入一明細の小票として登録する。"""
        registration = NewReceiptRegistration()
        registered = duplicate = failed = 0
        for row in rows:
            receipt_info = {
                "userId": user_id,
                "invoiceRegistrationNumber": "MERCARI",
                "supplierName": "メルカリ",
                "storeName": row["merchantName"],
                "receiptNo": row["externalId"][:24],
                "receiptDate": row["transactionDate"],
                "receiptTime": row.get("transactionTime") or "00:00",
                "taxFlag": 1,
                "receiptDetailCount": 1,
                "receiptDetails": [{
                    "itemName": row["merchantName"] or "メルカリ購入",
                    "category1": "その他",
                    "category2": "未分類",
                    "taxRate": 0.10,
                    "quantity": 1,
                    "unit": "個",
                    "unitPrice": abs(row["amount"]),
                    "discount": 0,
                    "totalPrice": abs(row["amount"]),
                }],
                "totalPrice": abs(row["amount"]),
                "supplierImage": "",
            }
            token = set_current_user_id(user_id)
            try:
                result = registration.call(headers={"x-kakeibo-user-id": user_id}, body={"receiptInfo": receipt_info})
            finally:
                reset_current_user_id(token)
            status = int(result.get("statusCode", 500))
            if status == 409:
                duplicate += 1
            elif status >= 400:
                failed += 1
            else:
                registered += 1
        return registered, duplicate, failed

    def submit_login_form(self, session, response, account_id, password, stage=0):
        soup = BeautifulSoup(response.content, "html.parser")
        form = soup.find("form")
        if not form:
            if self.javascript_only_html(response.text):
                raise NetworkRestrictionError(f"{self.service.display_name}ログインはServerブラウザが必要です。")
            return response
        payload = {field.get("name"): field.get("value") or "" for field in form.select("input[type=hidden][name]")}
        account_field = self.find_input_name(form, ("email", "mail", "login", "user", "account", "id"), ("text", "email", "tel"))
        password_field = self.find_input_name(form, ("pass", "password", "pwd"), ("password",))
        if not account_field and not password_field:
            raise NetworkRestrictionError(f"{self.service.display_name}ログインフォームをAWSで解析できません。")
        if account_field:
            payload[account_field] = account_id
        if password_field:
            payload[password_field] = password
        result = session.post(urljoin(response.url, form.get("action") or response.url), data=payload, timeout=30, allow_redirects=True)
        self.raise_for_access(result)
        if account_field and not password_field and stage == 0:
            # 2026-11-11 Codex: メールアドレス送信後にパスワード画面へ進む二段階ログインへ対応する。
            return self.submit_login_form(session, result, account_id, password, stage=1)
        return result

    def find_challenge_form(self, response):
        soup = BeautifulSoup(response.content, "html.parser")
        for form in soup.find_all("form"):
            code_field = self.find_input_name(form, ("otp", "code", "verify", "verification", "onetime", "token"), ("text", "tel", "number"))
            if not code_field:
                continue
            fields = {field.get("name"): field.get("value") or "" for field in form.select("input[type=hidden][name]")}
            return {"action": urljoin(response.url, form.get("action") or response.url), "codeField": code_field, "fields": fields}
        return None

    def save_challenge(self, config, user_id, session, challenge):
        challenge_id = uuid.uuid4().hex
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        ymd, hms = now_ymd_hms()
        self.database.update(
            """UPDATE AUTO_INPUT_INFO SET SUICA_CHALLENGE_ID=%(challenge_id)s,
                   SUICA_CHALLENGE_EXPIRES_AT=%(expires_at)s, SUICA_COOKIE_JSON=%(cookies)s,
                   SUICA_FORM_JSON=%(form_json)s, SUICA_FORM_ACTION=%(action)s,
                   UPD_PROG='AutoInput_Financial', UPD_DT=%(ymd)s, UPD_TM=%(hms)s, UPD_USER_ID=%(user_id)s
               WHERE ID=%(id)s AND CRE_USER_ID=%(user_id)s AND DEL_FLAG=0""",
            {"challenge_id": challenge_id, "expires_at": expires_at.isoformat(),
             "cookies": json.dumps(self.serialize_cookies(session.cookies), ensure_ascii=False),
             "form_json": json.dumps(challenge, ensure_ascii=False), "action": challenge["action"],
             "ymd": ymd, "hms": hms, "user_id": user_id, "id": self.value(config, "ID", "id")},
        )
        self.database.commit()
        return {"ok": True, "status": "OTP_REQUIRED", "challengeId": challenge_id,
                "verificationLabel": f"{self.service.display_name}確認コード", "expiresInSeconds": 600,
                "message": "確認コードを入力してください。"}

    def get_config(self, user_id):
        rows = self.database.select(
            """SELECT * FROM AUTO_INPUT_INFO WHERE CRE_USER_ID=%(user_id)s
               AND CONNECTION_TYPE=%(connection_type)s AND DEL_FLAG=0 ORDER BY ID DESC LIMIT 1""",
            {"user_id": user_id, "connection_type": self.service.connection_type},
        )
        return rows[0] if rows else {}

    def login_url(self, config):
        return self.value(config, "PAGE_URL_2", "page_url_2") or self.service.login_url

    def history_url(self, config):
        return self.value(config, "PAGE_URL_1", "page_url_1") or self.service.history_url

    def safe_get(self, session, url):
        try:
            response = session.get(url, timeout=30, allow_redirects=True)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as exc:
            raise NetworkRestrictionError(str(exc)) from exc
        self.raise_for_access(response)
        return response

    @staticmethod
    def new_session():
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 AppleWebKit/537.36 Chrome/126 Safari/537.36", "Accept-Language": "ja-JP,ja;q=0.9"})
        return session

    @staticmethod
    def raise_for_access(response):
        text = str(response.text or "").lower()
        if response.status_code in {403, 407, 429, 451, 503} or any(word in text for word in (
            "access denied", "unusual traffic", "robot check", "cloudflare", "captcha challenge",
        )):
            raise NetworkRestrictionError(f"HTTP {response.status_code}")
        response.raise_for_status()

    @staticmethod
    def javascript_only_html(html):
        text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True).lower()
        return len(text) < 80 or any(word in text for word in ("javascriptを有効", "enable javascript", "読み込み中"))

    @staticmethod
    def looks_like_login(response):
        soup = BeautifulSoup(response.content, "html.parser")
        return bool(soup.select_one("input[type=password]"))

    @staticmethod
    def find_input_name(form, keywords, types):
        for field in form.find_all("input"):
            field_type = str(field.get("type") or "text").lower()
            name = str(field.get("name") or "")
            field_id = str(field.get("id") or "")
            if field_type in types and any(keyword in f"{name} {field_id}".lower() for keyword in keywords):
                return name
        return ""

    @staticmethod
    def parse_currency_amount(text):
        # 2026-11-11 Codex: 通貨記号がある場合は必ず記号右側の最初の数値を価格として採用する。
        match = re.search(r"[¥￥]\s*(-?[0-9][0-9,]*(?:\.[0-9]{1,2})?)", str(text or ""))
        if not match:
            match = re.search(r"(-?[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*円", str(text or ""))
        if not match:
            return None
        value = float(match.group(1).replace(",", ""))
        return int(value) if value.is_integer() else value

    @staticmethod
    def parse_date(text):
        match = re.search(r"(20\d{2})[年/\-.](\d{1,2})[月/\-.](\d{1,2})日?", str(text or ""))
        if not match:
            return ""
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    @staticmethod
    def parse_time(text):
        match = re.search(r"(?:^|\s)(\d{1,2}):(\d{2})(?::(\d{2}))?", str(text or ""))
        return f"{int(match.group(1)):02d}:{match.group(2)}:{match.group(3) or '00'}" if match else ""

    @staticmethod
    def parse_merchant(text, date, amount):
        value = re.sub(r"20\d{2}[年/\-.]\d{1,2}[月/\-.]\d{1,2}日?", " ", str(text or ""))
        value = re.sub(r"[¥￥]\s*-?[0-9][0-9,]*(?:\.[0-9]{1,2})?|\-?[0-9][0-9,]*(?:\.[0-9]{1,2})?\s*円", " ", value)
        value = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", value)
        value = re.sub(r"\s+", " ", value).strip(" -|:")
        return value[:255]

    @staticmethod
    def external_id(element, text, date, merchant, amount):
        for key in ("data-transaction-id", "data-order-id", "data-id", "id"):
            if element.get(key):
                return str(element.get(key))
        raw = f"{date}|{merchant}|{amount}|{text}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def serialize_cookies(cookie_jar):
        return [{"name": cookie.name, "value": cookie.value, "domain": cookie.domain, "path": cookie.path} for cookie in cookie_jar]

    @staticmethod
    def restore_cookies(session, cookies):
        for cookie in cookies:
            session.cookies.set(cookie.get("name"), cookie.get("value"), domain=cookie.get("domain"), path=cookie.get("path") or "/")

    @staticmethod
    def value(row, *keys):
        for key in keys:
            if row and key in row:
                return row.get(key)
        return None


class AutoInput_MercariMarket(AutoInput_Financial):
    """メルカリ購入履歴の定期実行入口。"""

    def __init__(self, db_path=None):
        super().__init__("MERCARI_MARKET", db_path=db_path)


class AutoInput_Mercard(AutoInput_Financial):
    """メルカード利用明細の定期実行入口。"""

    def __init__(self, db_path=None):
        super().__init__("MERCARD", db_path=db_path)


class AutoInput_PayPay(AutoInput_Financial):
    """PayPay取引履歴の定期実行入口。"""

    def __init__(self, db_path=None):
        super().__init__("PAYPAY", db_path=db_path)


class AutoInput_MufgBank(AutoInput_Financial):
    """三菱UFJ銀行明細の定期実行入口。"""

    def __init__(self, db_path=None):
        super().__init__("MUFG_BANK", db_path=db_path)


class AutoInput_Mdc(AutoInput_Financial):
    """My Digital Connect明細の定期実行入口。"""

    def __init__(self, db_path=None):
        super().__init__("MDC", db_path=db_path)
