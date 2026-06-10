# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""Human-in-the-loop Mobile Suica login for the web application."""

import base64
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

from src.api.utils import now_ymd_hms
from src.api.receipt.new_receipt_registration.newReceiptRegistration import NewReceiptRegistration
from src.common.auth_context import reset_current_user_id, set_current_user_id
from src.common.base.base_batch import BaseBatch


SUICA_LOGIN_URL = "https://www.mobilesuica.com/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"


class AutoCsvInput_Suica(BaseBatch):
    def __init__(self, db_path=None):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path or None)
        self._validate_headers_functions = {}
        self._validate_body_functions = {}
        self.ensure_schema()

    def validate_headers(self, request_dict):
        return super().validate_headers(request_dict)

    def validate_body(self, request_dict):
        return super().validate_body(request_dict)

    def main(self, request_dict):
        user_id = self.require_user_id(request_dict)
        body = request_dict.get("body") or {}
        config = self.get_config(user_id)
        if not config:
            raise RuntimeError("Suicaの自動連携設定が見つかりません。")
        if not int(self.value(config, "ENABLED", "enabled") or 0):
            return {"statusCode": 400, "body": {"ok": False, "errorMessage": "Suica自動連携が無効です。"}}

        if body.get("action") == "submit":
            return {"statusCode": 200, "body": self.submit_login(config, user_id, body)}
        return {"statusCode": 200, "body": self.start_login(config, user_id)}

    def start_login(self, config, user_id):
        session = self.new_session()
        response = session.get(SUICA_LOGIN_URL, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        form = soup.find("form", id="form1")
        image = form.find("img", src=lambda value: value and "WebCaptchaImage" in value) if form else None
        if not form or not image:
            raise RuntimeError("Mobile Suicaのログインフォームを取得できませんでした。")

        captcha_response = session.get(urljoin(response.url, image.get("src")), timeout=30)
        captcha_response.raise_for_status()
        fields = {
            element.get("name"): element.get("value") or ""
            for element in form.find_all("input")
            if element.get("name") and element.get("type") == "hidden"
        }
        challenge_id = uuid.uuid4().hex
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        self.save_challenge(
            config,
            user_id,
            challenge_id,
            expires_at.isoformat(),
            urljoin(response.url, form.get("action")),
            self.serialize_cookies(session.cookies),
            fields,
        )
        return {
            "ok": True,
            "status": "CAPTCHA_REQUIRED",
            "challengeId": challenge_id,
            "captchaImage": "data:" + (captcha_response.headers.get("Content-Type") or "image/gif")
            + ";base64," + base64.b64encode(captcha_response.content).decode("ascii"),
            "expiresInSeconds": 600,
            "message": "画像に表示された文字を入力してください。",
        }

    def submit_login(self, config, user_id, body):
        challenge_id = str(body.get("challengeId") or "")
        captcha = str(body.get("captcha") or "").strip()
        if not challenge_id or not captcha:
            return {"ok": False, "status": "CAPTCHA_REQUIRED", "message": "画像認証の文字を入力してください。"}
        if challenge_id != str(self.value(config, "SUICA_CHALLENGE_ID", "suica_challenge_id") or ""):
            return {"ok": False, "status": "CHALLENGE_EXPIRED", "message": "画像認証を再取得してください。"}

        expires_at = self.value(config, "SUICA_CHALLENGE_EXPIRES_AT", "suica_challenge_expires_at")
        if not expires_at or datetime.fromisoformat(str(expires_at)) < datetime.now(timezone.utc):
            return {"ok": False, "status": "CHALLENGE_EXPIRED", "message": "画像認証の有効期限が切れました。再取得してください。"}

        session = self.new_session()
        self.restore_cookies(
            session,
            json.loads(self.value(config, "SUICA_COOKIE_JSON", "suica_cookie_json") or "[]"),
        )
        payload = json.loads(self.value(config, "SUICA_FORM_JSON", "suica_form_json") or "{}")
        payload.update({
            "MailAddress": self.value(config, "LOGIN_ID_1", "login_id_1") or "",
            "Password": self.value(config, "LOGIN_PW_1", "login_pw_1") or "",
            "WebCaptcha1__editor": captcha,
            "WebCaptcha1__editor_clientState": self.captcha_editor_state(captcha),
            "WebCaptcha1_clientState": '[[[[null]],[],[]],[{},[]],null]',
            "LOGIN": "ログイン",
        })
        action_url = self.value(config, "SUICA_FORM_ACTION", "suica_form_action")
        # Mobile Suica is an ASP.NET page encoded as Shift_JIS. Sending the
        # Japanese LOGIN button value as UTF-8 makes the server treat the POST
        # as a page refresh instead of a login event.
        encoded_payload = urlencode(payload, encoding="shift_jis", errors="strict").encode("ascii")
        response = session.post(
            action_url,
            data=encoded_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=Shift_JIS"},
            timeout=30,
            allow_redirects=True,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        if not self.is_login_success(soup):
            self.update_status(config, user_id, "LOGIN_FAILED")
            return {
                "ok": False,
                "status": "LOGIN_FAILED",
                "message": self.login_error_message(soup),
            }

        self.save_authenticated_session(config, user_id, self.serialize_cookies(session.cookies))
        try:
            history_url = self.extract_history_url(soup, response.url)
            if not history_url:
                raise RuntimeError("利用履歴ページのリンクが見つかりませんでした。")
            history_response = session.post(history_url, data={}, timeout=30, allow_redirects=True)
            history_response = self.follow_auto_submit_forms(session, history_response)
            history_soup = BeautifulSoup(history_response.content, "html.parser")
            rows = self.parse_history(history_soup)
            inserted_count = self.save_history_rows(rows, user_id)
            registered_count = self.register_pending_expenses(user_id)
        except Exception as error:
            self.logger.warning("Suica利用履歴の取得に失敗しました: %s", error)
            return {
                "ok": True,
                "status": "AUTHENTICATED",
                "message": "Mobile Suicaへのログインに成功しましたが、利用履歴を取得できませんでした。",
                "fetchedCount": 0,
                "insertedCount": 0,
                "duplicateCount": 0,
            }

        return {
            "ok": True,
            "status": "COMPLETED",
            "message": "Mobile Suicaへのログインと利用履歴の取得が完了しました。",
            "fetchedCount": len(rows),
            "insertedCount": inserted_count,
            "duplicateCount": len(rows) - inserted_count,
            "registeredCount": registered_count,
        }

    @staticmethod
    def is_login_success(soup):
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        return bool(
            "会員メニュー" in title
            or soup.find("form", {"name": "Suica"})
            or soup.find(id="btn_sfHistory")
        )

    @staticmethod
    def login_error_message(soup):
        for selector in ("#msg", ".error", ".errorMessage", ".validation-summary-errors"):
            element = soup.select_one(selector)
            if element:
                message = element.get_text(" ", strip=True)
                if message:
                    return message
        if soup.find("input", {"name": "WebCaptcha1__editor"}):
            return "ログイン処理が受け付けられず、ログイン画面が再表示されました。画像認証を再取得してください。"
        return "ログインに失敗しました。画像認証、会員ID、パスワードを確認してください。"

    @staticmethod
    def extract_history_url(soup, base_url):
        link = soup.select_one("#btn_sfHistory a[href]")
        href = link.get("href", "") if link else ""
        match = re.search(r"StartApplication\(['\"]([^'\"]+)['\"]\)", href)
        if match:
            return urljoin(base_url, match.group(1))
        if href and not href.lower().startswith("javascript:"):
            return urljoin(base_url, href)
        return ""

    def follow_auto_submit_forms(self, session, response, max_steps=5):
        for step in range(max_steps):
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            form = soup.find("form")
            self.logger.info(
                "Suica履歴遷移 step=%s url=%s title=%s form_method=%s form_action=%s fields=%s "
                "body_onload=%s scripts=%s meta=%s",
                step,
                response.url,
                title,
                form.get("method") if form else "",
                form.get("action") if form else "",
                [
                    element.get("name")
                    for element in form.find_all("input")
                    if element.get("name")
                ] if form else [],
                (soup.body or {}).get("onload", "") if soup.body else "",
                [script.get("src") or script.get_text(" ", strip=True)[:300] for script in soup.find_all("script")],
                [(meta.get("http-equiv"), meta.get("content")) for meta in soup.find_all("meta")],
            )
            if "SF（電子マネー）利用履歴" in title or soup.select_one("td.historyTable"):
                return response
            if not form:
                return response
            script_text = " ".join(script.get_text(" ", strip=True) for script in soup.find_all("script"))
            body_onload = (soup.body or {}).get("onload", "") if soup.body else ""
            is_transfer_page = "SuicaChangeTransfer.aspx" in response.url
            if (
                not is_transfer_page
                and "submit()" not in script_text
                and "submit(" not in script_text
                and "submit" not in body_onload.lower()
            ):
                return response
            payload = {
                element.get("name"): element.get("value") or ""
                for element in form.find_all("input")
                if element.get("name") and element.get("type", "text").lower() not in ("button", "submit", "image")
            }
            action_value = form.get("action") or ""
            if not action_value:
                html = response.content.decode(response.encoding or "shift_jis", errors="replace")
                start_application_match = re.search(
                    r"StartApplication\(['\"]([^'\"]+)['\"]\)",
                    html,
                    re.IGNORECASE,
                )
                if start_application_match:
                    action_value = start_application_match.group(1)
                action_match = re.search(
                    r"(?:document\.)?forms(?:\[[^\]]+\])?\.action\s*=\s*['\"]([^'\"]+)['\"]",
                    html,
                    re.IGNORECASE,
                )
                if not action_value and not action_match:
                    action_match = re.search(
                        r"<form[^>]+action\s*=\s*['\"]([^'\"]+)['\"]",
                        html,
                        re.IGNORECASE,
                    )
                if not action_value:
                    action_value = action_match.group(1) if action_match else ""
            if not action_value:
                self.logger.warning("Suica履歴遷移先をページ内スクリプトから取得できませんでした。")
                return response
            action = urljoin(response.url, action_value)
            method = (form.get("method") or "get").lower()
            response = (
                session.post(action, data=payload, timeout=30, allow_redirects=True)
                if method == "post"
                else session.get(action, params=payload, timeout=30, allow_redirects=True)
            )
        return response

    @staticmethod
    def parse_history(soup):
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        table = soup.select_one("td.historyTable table")
        if "SF（電子マネー）利用履歴" not in title and not table:
            raise RuntimeError("Mobile Suicaの利用履歴ページを確認できませんでした。")
        if not table:
            return []

        selected_month = soup.select_one('select[name="specifyYearMonth"] option[selected]')
        year_month = selected_month.get("value", "") if selected_month else ""
        current_year = int(year_month[:4]) if re.match(r"^\d{4}/\d{2}$", year_month) else datetime.now().year
        current_month = int(year_month[5:7]) if re.match(r"^\d{4}/\d{2}$", year_month) else datetime.now().month
        rows = []
        for tr in table.find_all("tr")[1:]:
            cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"], recursive=False)]
            if len(cells) < 8 or not re.match(r"^\d{2}/\d{2}$", cells[1]):
                continue
            month, day = (int(value) for value in cells[1].split("/"))
            year = current_year - 1 if month > current_month else current_year
            amount_text = cells[7].replace("\\", "").replace("￥", "").replace(",", "").strip()
            balance_text = cells[6].replace("\\", "").replace("￥", "").replace(",", "").strip()
            rows.append({
                "date": f"{year:04d}-{month:02d}-{day:02d}",
                "entryType": cells[2],
                "entryPlace": cells[3],
                "exitType": cells[4],
                "exitPlace": cells[5],
                "balance": int(balance_text) if re.match(r"^-?\d+$", balance_text) else None,
                "amount": int(amount_text) if re.match(r"^[+-]?\d+$", amount_text) else None,
            })
        return rows

    def save_history_rows(self, rows, user_id):
        inserted_count = 0
        ymd, hms = now_ymd_hms()
        for row in rows:
            content = json.dumps(row, ensure_ascii=False, sort_keys=True)
            source_key = hashlib.sha256(content.encode("utf-8")).hexdigest()
            existing = self.database.select(
                """
                SELECT id FROM auto_csv_input_cont
                WHERE CRE_USER_ID = %(USER_ID)s AND CONNECTION_TYPE = 'SUICA'
                  AND SOURCE_KEY = %(SOURCE_KEY)s AND DEL_FLAG = 0
                LIMIT 1
                """,
                {"USER_ID": user_id, "SOURCE_KEY": source_key},
            )
            if existing:
                continue
            self.database.insert(
                """
                INSERT INTO auto_csv_input_cont (
                    CRE_PROG, UPD_PROG, INV_REG_NUM, RET_CONT, RET_DT, RET_TM,
                    AUTO_INPUT_STATUS, CONNECTION_TYPE, SOURCE_KEY,
                    CRE_DT, CRE_TM, UPD_DT, UPD_TM, CRE_USER_ID, UPD_USER_ID, DEL_FLAG
                ) VALUES (
                    'AutoCsvInput_Suica', 'AutoCsvInput_Suica', 'SUICA',
                    %(RET_CONT)s, %(RET_DT)s, '', 'FETCHED', 'SUICA', %(SOURCE_KEY)s,
                    %(CRE_DT)s, %(CRE_TM)s, %(CRE_DT)s, %(CRE_TM)s, %(USER_ID)s, %(USER_ID)s, 0
                )
                """,
                {
                    "RET_CONT": content,
                    "RET_DT": row["date"].replace("-", ""),
                    "SOURCE_KEY": source_key,
                    "CRE_DT": ymd,
                    "CRE_TM": hms,
                    "USER_ID": user_id,
                },
            )
            inserted_count += 1
        return inserted_count

    def register_pending_expenses(self, user_id):
        rows = self.database.select(
            """
            SELECT id, RET_CONT
            FROM auto_csv_input_cont
            WHERE CRE_USER_ID = %(USER_ID)s
              AND CONNECTION_TYPE = 'SUICA'
              AND AUTO_INPUT_STATUS = 'FETCHED'
              AND DEL_FLAG = 0
            ORDER BY id
            """,
            {"USER_ID": user_id},
        )
        registered_count = 0
        grouped = {}
        for staging_row in rows:
            history = json.loads(self.value(staging_row, "RET_CONT", "ret_cont") or "{}")
            amount = history.get("amount")
            if amount is None or amount >= 0:
                self.update_auto_input_status(staging_row, user_id, "SKIPPED")
                continue
            if str(history.get("entryType") or "") == "物販":
                group_key = (history["date"], "VENDING", self.value(staging_row, "id", "ID"))
            else:
                group_key = (history["date"], "TRANSPORT", "")
            grouped.setdefault(group_key, []).append((staging_row, history))

        registration_api = NewReceiptRegistration()
        for (receipt_date, group_type, _), group_rows in grouped.items():
            details = [self.history_to_detail(history) for _, history in group_rows]
            receipt_info = {
                "invoiceRegistrationNumber": "SUICA",
                "supplierName": "Mobile Suica 交通" if group_type == "TRANSPORT" else "Mobile Suica 自動販売機",
                "receiptDate": receipt_date,
                "receiptTime": "00:00",
                "taxFlag": 0,
                "receiptDetailCount": len(details),
                "receiptDetails": details,
                "totalPrice": sum(detail["totalPrice"] for detail in details),
                "supplierImage": None,
            }
            appended = group_type == "TRANSPORT" and self.append_to_existing_transport_receipt(
                registration_api,
                receipt_info,
                user_id,
            )
            if not appended:
                auth_token = set_current_user_id(user_id)
                try:
                    result = registration_api.call(
                        headers={"x-kakeibo-user-id": user_id, "Content-Type": "application/json"},
                        body={"receiptInfo": receipt_info},
                    )
                finally:
                    reset_current_user_id(auth_token)
                if int(result.get("statusCode", 500)) >= 400:
                    raise RuntimeError(f"Suicaの出費登録に失敗しました: {result}")
            for staging_row, _ in group_rows:
                self.update_auto_input_status(staging_row, user_id, "3")
                registered_count += 1
        return registered_count

    @staticmethod
    def append_to_existing_transport_receipt(registration_api, receipt_info, user_id):
        receipt_date = str(receipt_info["receiptDate"]).replace("-", "")
        rows = registration_api.database.select(
            """
            SELECT RET_ID
            FROM receipt_info
            WHERE CRE_USER_ID = %(USER_ID)s
              AND INV_REG_NUM = 'SUICA'
              AND SUP_NAME = 'Mobile Suica 交通'
              AND RET_DT = %(RET_DT)s
              AND DEL_FLAG = 0
            ORDER BY CRE_DT, CRE_TM, RET_ID
            LIMIT 1
            FOR UPDATE
            """,
            {"USER_ID": user_id, "RET_DT": receipt_date},
        )
        if not rows:
            return False

        receipt_id = AutoCsvInput_Suica.value(rows[0], "RET_ID", "ret_id")
        details = receipt_info["receiptDetails"]
        registration_api.insert_receipt_details(
            receipt_id=receipt_id,
            receipt_details=details,
            tax_flag=receipt_info.get("taxFlag"),
            user_id=user_id,
        )
        ymd, hms = now_ymd_hms()
        registration_api.database.update(
            """
            UPDATE receipt_info
            SET RET_DET_CNT = COALESCE(RET_DET_CNT, 0) + %(DETAIL_COUNT)s,
                TOA_PRICE = COALESCE(TOA_PRICE, 0) + %(TOTAL_PRICE)s,
                UPD_PROG = 'AutoCsvInput_Suica',
                UPD_DT = %(UPD_DT)s,
                UPD_TM = %(UPD_TM)s,
                UPD_USER_ID = %(USER_ID)s
            WHERE RET_ID = %(RET_ID)s
              AND CRE_USER_ID = %(USER_ID)s
              AND DEL_FLAG = 0
            """,
            {
                "DETAIL_COUNT": len(details),
                "TOTAL_PRICE": receipt_info["totalPrice"],
                "UPD_DT": ymd,
                "UPD_TM": hms,
                "RET_ID": receipt_id,
                "USER_ID": user_id,
            },
        )
        registration_api.database.commit()
        return True

    @staticmethod
    def history_to_detail(history):
        entry_type = str(history.get("entryType") or "")
        entry_place = AutoCsvInput_Suica.normalize_suica_place(history.get("entryPlace"))
        exit_place = AutoCsvInput_Suica.normalize_suica_place(history.get("exitPlace"))
        is_transport = entry_type not in ("物販", "現金")
        if is_transport:
            category1, category2 = "交通", "電車・バス"
            route = " → ".join(place for place in (entry_place, exit_place) if place)
            item_name = f"Suica {entry_type} {route}".strip()
        elif entry_type == "物販":
            category1, category2 = "食費", "飲料"
            item_name = "Suica 自動販売機"
        else:
            category1, category2 = "その他", "未分類"
            item_name = f"Suica {entry_type} {entry_place}".strip()
        amount = abs(int(history["amount"]))
        return {
            "itemName": item_name,
            "category1": category1,
            "category2": category2,
            "taxRate": 0.10,
            "quantity": 1,
            "unit": "件",
            "unitPrice": amount,
            "totalPrice": amount,
        }

    @staticmethod
    def normalize_suica_place(value):
        place = str(value or "").strip()
        prefixes = {
            "小": "小田急",
            "小田": "小田急",
            "地": "地下鉄",
            "メトロ": "東京メトロ",
            "営団": "東京メトロ",
            "京王": "京王",
            "京成": "京成",
            "都": "都営",
            "都営": "都営",
            "臨": "りんかい線",
            "臨海": "りんかい線",
            "東急": "東急",
            "西武": "西武",
            "東武": "東武",
            "相鉄": "相鉄",
            "横浜": "横浜市営地下鉄",
        }
        match = re.match(r"^([^\s\u3000]+)[\s\u3000]+(.+)$", place)
        if match and match.group(1) in prefixes:
            return f"{prefixes[match.group(1)]} {match.group(2).strip()}"
        # Some Mobile Suica rows omit the separator for known prefixes.
        for prefix, label in (
            ("小", "小田急"),
            ("地", "地下鉄"),
            ("臨", "りんかい線"),
            ("都", "都営"),
            ("京王", "京王"),
            ("京成", "京成"),
        ):
            if place.startswith(prefix) and len(place) > len(prefix):
                return f"{label} {place[len(prefix):].strip()}"
        return place.replace("\u3000", " ").strip()

    def update_auto_input_status(self, staging_row, user_id, status):
        ymd, hms = now_ymd_hms()
        self.database.update(
            """
            UPDATE auto_csv_input_cont
            SET AUTO_INPUT_STATUS = %(STATUS)s,
                UPD_PROG = 'AutoCsvInput_Suica',
                UPD_DT = %(UPD_DT)s,
                UPD_TM = %(UPD_TM)s,
                UPD_USER_ID = %(USER_ID)s
            WHERE id = %(id)s AND CRE_USER_ID = %(USER_ID)s AND DEL_FLAG = 0
            """,
            {
                "STATUS": status,
                "UPD_DT": ymd,
                "UPD_TM": hms,
                "USER_ID": user_id,
                "id": self.value(staging_row, "id", "ID"),
            },
        )

    def new_session(self):
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ja-JP,ja;q=0.9"})
        return session

    @staticmethod
    def serialize_cookies(cookie_jar):
        return [
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "secure": cookie.secure,
                "expires": cookie.expires,
                "rest": dict(cookie._rest),
            }
            for cookie in cookie_jar
        ]

    @staticmethod
    def restore_cookies(session, cookies):
        # Backward compatibility for challenges created before full CookieJar
        # serialization was introduced.
        if isinstance(cookies, dict):
            session.cookies.update(cookies)
            return
        for cookie in cookies:
            session.cookies.set(
                cookie["name"],
                cookie.get("value", ""),
                domain=cookie.get("domain") or None,
                path=cookie.get("path") or "/",
                secure=bool(cookie.get("secure")),
                expires=cookie.get("expires"),
                rest=cookie.get("rest") or {},
            )

    @staticmethod
    def captcha_editor_state(captcha):
        editor_value = "01" + captcha
        return (
            f"|0|{editor_value}||"
            f'[[[[]],[],[]],[{{}},[]],"{editor_value}"]'
        )

    def ensure_schema(self):
        for statement in (
            "ALTER TABLE auto_csv_input_info ADD COLUMN IF NOT EXISTS SUICA_CHALLENGE_ID TEXT",
            "ALTER TABLE auto_csv_input_info ADD COLUMN IF NOT EXISTS SUICA_CHALLENGE_EXPIRES_AT TEXT",
            "ALTER TABLE auto_csv_input_info ADD COLUMN IF NOT EXISTS SUICA_COOKIE_JSON TEXT",
            "ALTER TABLE auto_csv_input_info ADD COLUMN IF NOT EXISTS SUICA_FORM_JSON TEXT",
            "ALTER TABLE auto_csv_input_info ADD COLUMN IF NOT EXISTS SUICA_FORM_ACTION TEXT",
        ):
            self.database.execute(statement)

    def save_challenge(self, config, user_id, challenge_id, expires_at, action_url, cookies, fields):
        self.database.update(
            """
            UPDATE auto_csv_input_info SET
                SUICA_CHALLENGE_ID = %(CHALLENGE_ID)s,
                SUICA_CHALLENGE_EXPIRES_AT = %(EXPIRES_AT)s,
                SUICA_COOKIE_JSON = %(COOKIE_JSON)s,
                SUICA_FORM_JSON = %(FORM_JSON)s,
                SUICA_FORM_ACTION = %(FORM_ACTION)s,
                LAST_LOGIN_STATUS = 'CAPTCHA_REQUIRED'
            WHERE id = %(id)s AND CRE_USER_ID = %(USER_ID)s AND DEL_FLAG = 0
            """,
            {
                "CHALLENGE_ID": challenge_id,
                "EXPIRES_AT": expires_at,
                "COOKIE_JSON": json.dumps(cookies),
                "FORM_JSON": json.dumps(fields),
                "FORM_ACTION": action_url,
                "id": self.value(config, "id", "ID"),
                "USER_ID": user_id,
            },
        )

    def save_authenticated_session(self, config, user_id, cookies):
        ymd, hms = now_ymd_hms()
        self.database.update(
            """
            UPDATE auto_csv_input_info SET
                SUICA_COOKIE_JSON = %(COOKIE_JSON)s,
                SUICA_CHALLENGE_ID = NULL,
                SUICA_CHALLENGE_EXPIRES_AT = NULL,
                SUICA_FORM_JSON = NULL,
                SUICA_FORM_ACTION = NULL,
                LAST_LOGIN_STATUS = 'AUTHENTICATED',
                LAST_LOGIN_DT = %(DT)s,
                LAST_LOGIN_TM = %(TM)s
            WHERE id = %(id)s AND CRE_USER_ID = %(USER_ID)s AND DEL_FLAG = 0
            """,
            {
                "COOKIE_JSON": json.dumps(cookies),
                "DT": ymd,
                "TM": hms,
                "id": self.value(config, "id", "ID"),
                "USER_ID": user_id,
            },
        )

    def update_status(self, config, user_id, status):
        self.database.update(
            "UPDATE auto_csv_input_info SET LAST_LOGIN_STATUS = %(STATUS)s WHERE id = %(id)s AND CRE_USER_ID = %(USER_ID)s",
            {"STATUS": status, "id": self.value(config, "id", "ID"), "USER_ID": user_id},
        )

    def get_config(self, user_id):
        """
        コンフィグから連携情報を取得する。
        args:
        
        """
        rows = self.database.select(
            """
            SELECT * FROM auto_csv_input_info
            WHERE CRE_USER_ID = %(USER_ID)s AND DEL_FLAG = 0
              AND (CONNECTION_TYPE = 'SUICA' OR UPPER(SUP_NAME) = 'SUICA')
            ORDER BY id DESC LIMIT 1
            """,
            {"USER_ID": user_id},
        )
        return rows[0] if rows else {}

    @staticmethod
    def value(row, *keys):
        lower = {str(key).lower(): value for key, value in (row or {}).items()}
        for key in keys:
            if key in (row or {}):
                return row.get(key)
            if str(key).lower() in lower:
                return lower[str(key).lower()]
        return None
