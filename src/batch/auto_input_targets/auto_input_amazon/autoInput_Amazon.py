# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""Amazon注文履歴を取得し、家計簿レシートへ自動登録する。"""

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from src.api.receipt.ai_receipt.receiptAnalyzer import (
    GeminiReceiptAnalyzer,
    build_category_pair_mapping_prompt,
    clean_category_label,
)
from src.api.receipt.new_receipt_registration.newReceiptRegistration import NewReceiptRegistration
from src.api.receipt.taxPrice import normalize_tax_rate
from src.api.utils import now_ymd_hms
from src.common.auth_context import reset_current_user_id, set_current_user_id
from src.common.base.base_auto_input import BaseAutoInput


AMAZON_HOME_URL = "https://www.amazon.co.jp/"
AMAZON_ORDER_HISTORY_URL = "https://www.amazon.co.jp/your-orders/orders?orderFilter=months-3"
AMAZON_LOOKBACK_DAYS = 92
AMAZON_MAX_ORDER_PAGES = 10
AMAZON_SUPPLIER_NAME = "アマゾンジャパン合同会社"
AMAZON_INVOICE_NUMBER = "T3040001028447"
AUTO_INPUT_STATUS_FETCHED = "FETCHED"
AUTO_INPUT_STATUS_REGISTERED = "3"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)


class AutoInput_Amazon(BaseAutoInput):
    """Amazon注文履歴のログイン、追加認証、取得、登録を行う。"""

    def __init__(self, db_path=None):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path or None)
        self._validate_headers_functions = {}
        self._validate_body_functions = {}

    def main(self, request_dict):
        """開始または確認コード送信のアクションを振り分ける。"""
        user_id = self.require_user_id(request_dict)
        body = request_dict.get("body") or {}
        config = self.get_config(user_id)
        if not config:
            raise RuntimeError("Amazonログイン設定が見つかりません。")
        if not self.value(config, "LOGIN_ID_1", "login_id_1") or not self.value(config, "LOGIN_PW_1", "login_pw_1"):
            return {"statusCode": 400, "body": {"ok": False, "errorMessage": "先にAmazonログイン情報を保存してください。"}}
        if body.get("action") == "submit":
            return {"statusCode": 200, "body": self.submit_verification_code(config, user_id, body)}
        return {"statusCode": 200, "body": self.start_login(config, user_id)}

    def start_login(self, config, user_id):
        """注文履歴ページへ遷移し、必要に応じてメール・パスワードを送信する。"""
        session = self.new_session()
        response = session.get(AMAZON_ORDER_HISTORY_URL, timeout=30, allow_redirects=True)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        if self.is_orders_page(soup, response.url):
            return self.complete_order_fetch(session, response, user_id)

        response = self.submit_email_if_needed(session, response, config)
        soup = BeautifulSoup(response.content, "html.parser")
        if self.is_orders_page(soup, response.url):
            return self.complete_order_fetch(session, response, user_id)

        response = self.submit_password_if_needed(session, response, config)
        soup = BeautifulSoup(response.content, "html.parser")
        if self.is_orders_page(soup, response.url):
            return self.complete_order_fetch(session, response, user_id)

        verification = self.find_verification_form(soup, response.url)
        if verification:
            challenge_id = uuid.uuid4().hex
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
            self.save_challenge(
                config,
                user_id,
                challenge_id,
                expires_at.isoformat(),
                verification["action"],
                self.serialize_cookies(session.cookies),
                verification,
            )
            return {
                "ok": True,
                "status": "OTP_REQUIRED",
                "challengeId": challenge_id,
                "verificationLabel": "Amazon確認コード",
                "expiresInSeconds": 300,
                "message": "Amazonから届いた確認コードを入力してください。",
            }

        if self.is_automation_challenge_page(soup, response.url):
            self.update_status(config, user_id, "CHALLENGE_REQUIRED")
            self.log_page_shape("amazon_automation_challenge", soup, response.url)
            return {"ok": False, "status": "CHALLENGE_REQUIRED", "message": "Amazon追加確認ページで停止しました。"}

        self.update_status(config, user_id, "LOGIN_FAILED")
        self.log_page_shape("amazon_login_unrecognized", soup, response.url)
        return {"ok": False, "status": "LOGIN_FAILED", "message": self.login_error_message(soup) or "Amazonログイン画面を解析できませんでした。"}

    def submit_verification_code(self, config, user_id, body):
        """保存済みセッションへ確認コードを送信し、注文履歴を取得する。"""
        challenge_id = str(body.get("challengeId") or "")
        code = str(body.get("captcha") or body.get("verificationCode") or "").strip()
        if not challenge_id or not code:
            return {"ok": False, "status": "OTP_REQUIRED", "message": "確認コードを入力してください。"}
        if challenge_id != str(self.value(config, "SUICA_CHALLENGE_ID", "suica_challenge_id") or ""):
            return {"ok": False, "status": "CHALLENGE_EXPIRED", "message": "確認コードを再取得してください。"}

        expires_at = self.value(config, "SUICA_CHALLENGE_EXPIRES_AT", "suica_challenge_expires_at")
        if not expires_at or datetime.fromisoformat(str(expires_at)) < datetime.now(timezone.utc):
            return {"ok": False, "status": "CHALLENGE_EXPIRED", "message": "確認コードの有効期限が切れました。"}

        session = self.new_session()
        self.restore_cookies(session, json.loads(self.value(config, "SUICA_COOKIE_JSON", "suica_cookie_json") or "[]"))
        form_info = json.loads(self.value(config, "SUICA_FORM_JSON", "suica_form_json") or "{}")
        payload = form_info.get("fields") or {}
        payload[form_info.get("codeField") or "otpCode"] = code
        response = session.post(
            self.value(config, "SUICA_FORM_ACTION", "suica_form_action") or form_info.get("action"),
            data=payload,
            timeout=30,
            allow_redirects=True,
        )
        response.raise_for_status()
        response = session.get(AMAZON_ORDER_HISTORY_URL, timeout=30, allow_redirects=True)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        if not self.is_orders_page(soup, response.url):
            if self.is_automation_challenge_page(soup, response.url):
                self.update_status(config, user_id, "CHALLENGE_REQUIRED")
                self.log_page_shape("amazon_otp_automation_challenge", soup, response.url)
                return {"ok": False, "status": "CHALLENGE_REQUIRED", "message": "Amazon追加確認ページで停止しました。"}
            self.update_status(config, user_id, "LOGIN_FAILED")
            self.log_page_shape("amazon_otp_submit_unrecognized", soup, response.url)
            return {"ok": False, "status": "LOGIN_FAILED", "message": self.login_error_message(soup) or "確認コード送信後に注文履歴へ遷移できませんでした。"}
        return self.complete_order_fetch(session, response, user_id)

    def submit_email_if_needed(self, session, response, config):
        """メールアドレス入力画面の場合だけ送信する。"""
        soup = BeautifulSoup(response.content, "html.parser")
        form_info = self.find_form_with_input(soup, response.url, ("email",))
        if not form_info:
            return response
        payload = form_info["fields"]
        payload["email"] = self.value(config, "LOGIN_ID_1", "login_id_1") or ""
        payload.setdefault("continue", "Continue")
        # 2026-07-15 Codex: Armbian batchでもLambda版と同じログイン遷移を使えるよう、フォーム解析結果を再利用する。
        return session.post(form_info["action"], data=payload, timeout=30, allow_redirects=True)

    def submit_password_if_needed(self, session, response, config):
        """パスワード入力画面の場合だけ送信する。"""
        soup = BeautifulSoup(response.content, "html.parser")
        form_info = self.find_form_with_input(soup, response.url, ("password",))
        if not form_info:
            return response
        payload = form_info["fields"]
        payload["password"] = self.value(config, "LOGIN_PW_1", "login_pw_1") or ""
        payload.setdefault("signInSubmit", "Sign in")
        return session.post(form_info["action"], data=payload, timeout=30, allow_redirects=True)

    def complete_order_fetch(self, session, response, user_id):
        """直近3か月の注文を取得・一時保存し、未登録注文を家計簿へ登録する。"""
        self.save_authenticated_session_for_user(user_id, self.serialize_cookies(session.cookies))
        rows = self.fetch_recent_orders(session, response)
        inserted_count = self.save_order_rows(rows, user_id)
        registered_count, failed_count = self.register_pending_orders(user_id)
        return {
            "ok": True,
            "status": "COMPLETED",
            "message": "Amazon注文履歴の取得が完了しました。",
            "fetchedCount": len(rows),
            "insertedCount": inserted_count,
            "duplicateCount": len(rows) - inserted_count,
            "registeredCount": registered_count,
            "failed": failed_count,
        }

    def fetch_recent_orders(self, session, first_response):
        """Amazon注文履歴を直近3か月分、ページ送りしながら取得する。"""
        rows = []
        seen_order_ids = set()
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=AMAZON_LOOKBACK_DAYS)).date()
        response = first_response
        next_url = response.url
        start_index = 0

        for _ in range(AMAZON_MAX_ORDER_PAGES):
            if next_url and next_url != response.url:
                response = session.get(next_url, timeout=30, allow_redirects=True)
                response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            new_count = 0
            for order in self.parse_orders(soup):
                order_id = order.get("orderId")
                order_date = self.parse_order_date_value(order.get("orderDate"))
                if not order_id or order_id in seen_order_ids:
                    continue
                if order_date and order_date < cutoff_date:
                    continue
                seen_order_ids.add(order_id)
                rows.append(order)
                new_count += 1
            next_url = self.find_next_order_page_url(soup, response.url)
            if not next_url and new_count:
                start_index += 10
                # 2026-07-15 Codex: Amazonが明示的な次ページリンクを返さない画面でも、startIndexで3か月分を追加取得する。
                next_url = self.build_order_page_url(response.url, start_index)
            if not next_url:
                break
        return rows

    def parse_orders(self, soup):
        """注文履歴ページから注文番号、日付、合計、商品名を抽出する。"""
        orders = []
        for card in soup.select(".order-card, .js-order-card, .a-box-group"):
            text = card.get_text(" ", strip=True)
            order_id_match = (
                re.search(r"注文番号[:：]?\s*([0-9A-Z-]{8,})", text)
                or re.search(r"Order\s*(?:#|ID)[:：]?\s*([0-9A-Z-]{8,})", text, re.IGNORECASE)
            )
            if not order_id_match:
                continue
            total_match = (
                re.search(r"合計[:：]?\s*[￥¥]?\s*([0-9,]+)", text)
                or re.search(r"Total[:：]?\s*[￥¥]?\s*([0-9,]+)", text, re.IGNORECASE)
            )
            # 2026-07-15 Codex: キャンセル済み・請求なし注文は支出として登録しない。
            if "キャンセル済み" in text or "請求は行われていません" in text:
                continue
            date_match = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", text) or re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
            items = self.parse_order_items(card)
            total_price = int(total_match.group(1).replace(",", "")) if total_match else 0
            if total_price <= 0:
                continue
            orders.append({
                "orderId": order_id_match.group(1),
                "orderDate": f"{int(date_match.group(1)):04d}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}" if date_match else "",
                "totalPrice": total_price,
                "items": items,
                "rawText": text[:2000],
            })
        return orders

    def parse_order_items(self, card):
        """注文カード内の商品リンクから商品名候補を抽出する。"""
        items = []
        seen = set()
        for link in card.select("a[href*='/dp/'], a[href*='/gp/product/']"):
            name = re.sub(r"\s+", " ", link.get_text(" ", strip=True))
            if not name or len(name) < 2 or name in seen:
                continue
            seen.add(name)
            items.append({"itemName": name, "amazonCategoryName": name})
        if not items:
            title = re.sub(r"\s+", " ", card.get_text(" ", strip=True))[:80]
            items.append({"itemName": title or "Amazon注文", "amazonCategoryName": title or "Amazon注文"})
        return items

    def find_next_order_page_url(self, soup, base_url):
        """注文履歴ページの次ページURLを取得する。"""
        for selector in ("li.a-last a", ".a-pagination .a-last a", "a[aria-label*='次']", "a[href*='startIndex=']"):
            link = soup.select_one(selector)
            if link and link.get("href"):
                return urljoin(base_url, link.get("href"))
        return ""

    @staticmethod
    def build_order_page_url(base_url, start_index):
        """startIndex付きの注文履歴URLを作る。"""
        parsed = urlparse(base_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["orderFilter"] = query.get("orderFilter") or "months-3"
        query["startIndex"] = str(start_index)
        return urlunparse(parsed._replace(query=urlencode(query)))

    @staticmethod
    def parse_order_date_value(value):
        if not value:
            return None
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except ValueError:
            return None

    def save_order_rows(self, rows, user_id):
        """未保存のAmazon注文履歴を一時保存する。"""
        inserted_count = 0
        ymd, hms = now_ymd_hms()
        for row in rows:
            content = json.dumps(row, ensure_ascii=False, sort_keys=True)
            source_key = hashlib.sha256((row.get("orderId") or content).encode("utf-8")).hexdigest()
            existing = self.database.select(
                """
                SELECT id FROM kakeibo.auto_input_cont
                WHERE CRE_USER_ID = %(USER_ID)s AND CONNECTION_TYPE = 'AMAZON'
                  AND DEL_FLAG = 0 AND SOURCE_KEY = %(SOURCE_KEY)s
                LIMIT 1
                """,
                {"USER_ID": user_id, "SOURCE_KEY": source_key},
            )
            if existing:
                continue
            self.database.insert(
                """
                INSERT INTO kakeibo.auto_input_cont (
                    CRE_PROG, UPD_PROG, INV_REG_NUM, RET_CONT, RET_DT, RET_TM,
                    AUTO_INPUT_STATUS, CONNECTION_TYPE, SOURCE_KEY,
                    CRE_DT, CRE_TM, UPD_DT, UPD_TM, CRE_USER_ID, UPD_USER_ID, DEL_FLAG
                ) VALUES (
                    'AutoInput_Amazon', 'AutoInput_Amazon', 'AMAZON',
                    %(RET_CONT)s, %(RET_DT)s, '', %(STATUS)s, 'AMAZON', %(SOURCE_KEY)s,
                    %(CRE_DT)s, %(CRE_TM)s, %(CRE_DT)s, %(CRE_TM)s, %(USER_ID)s, %(USER_ID)s, 0
                )
                """,
                {
                    "RET_CONT": content,
                    "RET_DT": (row.get("orderDate") or "").replace("-", ""),
                    "STATUS": AUTO_INPUT_STATUS_FETCHED,
                    "SOURCE_KEY": source_key,
                    "CRE_DT": ymd,
                    "CRE_TM": hms,
                    "USER_ID": user_id,
                },
            )
            inserted_count += 1
        return inserted_count

    def register_pending_orders(self, user_id):
        """FETCHED状態のAmazon注文を家計簿レシートへ登録する。"""
        rows = self.database.select(
            """
            SELECT id, RET_CONT
            FROM kakeibo.auto_input_cont
            WHERE CRE_USER_ID = %(USER_ID)s
              AND CONNECTION_TYPE = 'AMAZON'
              AND AUTO_INPUT_STATUS = %(STATUS)s
              AND DEL_FLAG = 0
            ORDER BY RET_DT DESC, id DESC
            """,
            {"USER_ID": user_id, "STATUS": AUTO_INPUT_STATUS_FETCHED},
        ) or []
        if not rows:
            return 0, 0

        categories = self.load_receipt_categories(user_id)
        analyzer = GeminiReceiptAnalyzer(timeout=40)
        registration_api = NewReceiptRegistration()
        registered_count = 0
        failed_count = 0

        for row in rows:
            try:
                order = json.loads(self.value(row, "RET_CONT", "ret_cont") or "{}")
                receipt_info = self.build_receipt_info_from_order(order, user_id, categories, analyzer)
                auth_token = set_current_user_id(user_id)
                try:
                    result = registration_api.call(
                        headers={"x-kakeibo-user-id": user_id, "Content-Type": "application/json"},
                        body={"receiptInfo": receipt_info},
                    )
                finally:
                    reset_current_user_id(auth_token)
                if int(result.get("statusCode", 500)) == 409:
                    # 2026-07-15 Codex: 既に家計簿へ登録済みのAmazon注文は再試行対象から外し、夜間batchの失敗件数に含めない。
                    self.mark_order_registered(row)
                    continue
                if int(result.get("statusCode", 500)) >= 400:
                    raise RuntimeError(f"Amazon receipt registration failed: {result}")
                self.mark_order_registered(row)
                registered_count += 1
            except Exception as exc:
                failed_count += 1
                self.logger.error("Failed to register Amazon order: %s", exc)
        return registered_count, failed_count

    def build_receipt_info_from_order(self, order, user_id, categories, analyzer):
        """Amazon注文をレシート登録APIの入力形式へ変換する。"""
        details = self.build_amazon_receipt_details(order, categories, analyzer)
        return {
            "userId": user_id,
            "invoiceRegistrationNumber": AMAZON_INVOICE_NUMBER,
            "supplierName": AMAZON_SUPPLIER_NAME,
            "storeName": "Amazon.co.jp",
            "storeCode": "",
            "posNo": "",
            "receiptNo": order.get("orderId") or "",
            "receiptDate": order.get("orderDate") or datetime.now().strftime("%Y-%m-%d"),
            "receiptTime": "00:00",
            "taxFlag": 1,
            "receiptDetailCount": len(details),
            "receiptDetails": details,
            "totalPrice": order.get("totalPrice") or sum(int(item.get("totalPrice") or 0) for item in details),
            "supplierImage": "",
        }

    def build_amazon_receipt_details(self, order, categories, analyzer):
        """Amazon商品名をAIで家計簿カテゴリへ寄せ、明細金額を注文合計から按分する。"""
        items = order.get("items") or [{"itemName": "Amazon注文", "amazonCategoryName": "Amazon注文"}]
        category_map = self.map_amazon_items_with_ai(items, categories, analyzer)
        total_price = int(order.get("totalPrice") or 0)
        prices = self.split_total_price(total_price, len(items))
        details = []
        for index, item in enumerate(items):
            item_name = item.get("itemName") or "Amazon注文"
            mapped = category_map.get(item_name) or self.default_unknown_amazon_category_mapping(categories)
            details.append({
                "itemName": item_name,
                "category1": mapped.get("category1"),
                "category2": mapped.get("category2"),
                "taxRate": mapped.get("taxRate"),
                "quantity": 1.0,
                "unit": "個",
                "unitPrice": prices[index],
                "discount": 0,
                "totalPrice": prices[index],
                "amazonCategoryName": item.get("amazonCategoryName") or item_name,
            })
        return details

    def map_amazon_items_with_ai(self, items, categories, analyzer):
        """Amazonの商品名・カテゴリ候補を現在の家計簿カテゴリへAIで対応付ける。"""
        if not items:
            return {}
        prompt = build_category_pair_mapping_prompt(categories)
        input_text = json.dumps({
            "belcCategories": [
                {"belcCategoryCode": "", "belcCategoryName": item.get("amazonCategoryName") or item.get("itemName") or ""}
                for item in items
            ]
        }, ensure_ascii=False)
        parsed = analyzer.analyze_json_with_prompt(text=input_text, prompt=prompt, label="Amazon商品カテゴリ一覧")
        if int(parsed.get("statusCode", 500)) >= 400:
            self.logger.warning("Amazon AI category mapping failed: %s", parsed)
            return {}
        mappings = ((parsed.get("body") or {}).get("mappings") or [])
        valid_pairs = self.category_pair_map(categories)
        result = {}
        for item, mapping in zip(items, mappings):
            category1 = clean_category_label(mapping.get("category1"))
            category2 = clean_category_label(mapping.get("category2"))
            pair_key = (category1, category2)
            if pair_key not in valid_pairs:
                continue
            result[item.get("itemName") or "Amazon注文"] = {
                "category1": category1,
                "category2": category2,
                "taxRate": normalize_tax_rate(mapping.get("taxRate") or valid_pairs[pair_key].get("taxRate")),
            }
        return result

    @staticmethod
    def split_total_price(total_price, count):
        if count <= 0:
            return []
        base = int(total_price / count) if total_price else 0
        prices = [base for _ in range(count)]
        if prices:
            prices[-1] += total_price - sum(prices)
        return prices

    def default_unknown_amazon_category_mapping(self, categories):
        rows = self.category_rows(categories)
        if not rows:
            return {"category1": "その他", "category2": "未分類", "taxRate": 0.10}
        for row in rows:
            if row.get("category1") == "その他" and row.get("category2") == "未分類":
                return {"category1": row.get("category1"), "category2": row.get("category2"), "taxRate": normalize_tax_rate(row.get("taxRate"))}
        first_row = rows[0]
        return {"category1": first_row.get("category1"), "category2": first_row.get("category2"), "taxRate": normalize_tax_rate(first_row.get("taxRate"))}

    def load_receipt_categories(self, user_id):
        return {
            "category1": self.database.select(
                """
                SELECT DISTINCT CATEGORY1_NAME
                FROM kakeibo.receipt_info_category1
                WHERE DEL_FLAG = 0
                  AND CRE_USER_ID = %(USER_ID)s
                """,
                {"USER_ID": user_id},
            ) or [],
            "category2": self.database.select(
                """
                SELECT CATEGORY1_NAME, CATEGORY2_NAME, TAX_RATE
                FROM kakeibo.receipt_info_category2
                WHERE DEL_FLAG = 0
                  AND CRE_USER_ID = %(USER_ID)s
                """,
                {"USER_ID": user_id},
            ) or [],
        }

    def category_rows(self, categories):
        rows = []
        for item in categories.get("category2") or []:
            if not isinstance(item, dict):
                continue
            category1 = clean_category_label(item.get("CATEGORY1_NAME") or item.get("category1Name") or item.get("category1_name"))
            category2 = clean_category_label(item.get("CATEGORY2_NAME") or item.get("category2Name") or item.get("category2_name"))
            if category1 and category2:
                rows.append({
                    "category1": category1,
                    "category2": category2,
                    "taxRate": item.get("TAX_RATE") if item.get("TAX_RATE") is not None else item.get("taxRate") or item.get("tax_rate"),
                })
        return rows

    def category_pair_map(self, categories):
        return {
            (row.get("category1"), row.get("category2")): row
            for row in self.category_rows(categories)
        }

    def mark_order_registered(self, row):
        ymd, hms = now_ymd_hms()
        self.database.update(
            """
            UPDATE kakeibo.auto_input_cont
            SET AUTO_INPUT_STATUS = %(STATUS)s,
                UPD_PROG = 'AutoInput_Amazon',
                UPD_DT = %(UPD_DT)s,
                UPD_TM = %(UPD_TM)s
            WHERE id = %(id)s
            """,
            {"STATUS": AUTO_INPUT_STATUS_REGISTERED, "UPD_DT": ymd, "UPD_TM": hms, "id": self.value(row, "id", "ID")},
        )

    def find_verification_form(self, soup, base_url):
        """確認コード入力フォームを探す。"""
        candidates = ("otpCode", "code", "cvf-input-code", "verificationCode", "mfaCode")
        for name in candidates:
            form_info = self.find_form_with_input(soup, base_url, (name,))
            if form_info:
                form_info["codeField"] = name
                return form_info
        return None

    def find_form_with_input(self, soup, base_url, input_names):
        """指定nameの入力項目を含むフォーム情報を返す。"""
        for form in soup.find_all("form"):
            names = {element.get("name") for element in form.find_all(["input", "button"]) if element.get("name")}
            if not any(name in names for name in input_names):
                continue
            fields = {}
            for element in form.find_all("input"):
                name = element.get("name")
                if not name or element.get("type", "text").lower() in ("button", "image"):
                    continue
                value = element.get("value") or ""
                if name in fields and fields[name] and not value:
                    continue
                fields[name] = value
            # 2026-07-15 Codex: 同名hidden項目で入力値を潰さないよう、有効値を優先して保持する。
            return {"action": urljoin(base_url, form.get("action") or base_url), "fields": fields}
        return None

    @staticmethod
    def is_orders_page(soup, current_url):
        """注文履歴ページへ到達したかを判定する。"""
        text = soup.get_text(" ", strip=True)
        # 2026-07-15 Codex: Amazonの注文履歴URLは /gp/css/order-history と /your-orders/orders の両方がある。
        is_order_url = "order-history" in current_url or "/your-orders/orders" in current_url
        return is_order_url and ("注文" in text or "order" in text.lower())

    @staticmethod
    def is_automation_challenge_page(soup, current_url):
        """Amazon側の自動アクセス確認ページを判定する。"""
        title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
        text = soup.get_text(" ", strip=True).lower()
        return "/ax/aaut/verify" in current_url or "challenge page" in title or "aamationtoken" in current_url.lower() or ("verify" in title and "challenge" in text)

    @staticmethod
    def login_error_message(soup):
        """Amazonログイン画面のエラーメッセージを抽出する。"""
        for selector in ("#auth-error-message-box", ".a-alert-content", ".a-box-inner"):
            element = soup.select_one(selector)
            if element:
                message = element.get_text(" ", strip=True)
                if message:
                    return message
        return ""

    def log_page_shape(self, label, soup, current_url):
        """解析できないAmazon画面の構造をログへ残す。"""
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        forms = []
        for form in soup.find_all("form")[:5]:
            forms.append({
                "id": form.get("id") or "",
                "name": form.get("name") or "",
                "action": form.get("action") or "",
                "inputs": [
                    {"name": item.get("name") or "", "id": item.get("id") or "", "type": item.get("type") or ""}
                    for item in form.find_all("input")[:20]
                ],
            })
        self.logger.warning("%s url=%s title=%s forms=%s", label, current_url, title, json.dumps(forms, ensure_ascii=False))

    def save_challenge(self, config, user_id, challenge_id, expires_at, action_url, cookies, form_info):
        """確認コード送信用のフォーム・Cookieを一時保存する。"""
        self.database.update(
            """
            UPDATE auto_input_info SET
                SUICA_CHALLENGE_ID = %(CHALLENGE_ID)s,
                SUICA_CHALLENGE_EXPIRES_AT = %(EXPIRES_AT)s,
                SUICA_COOKIE_JSON = %(COOKIE_JSON)s,
                SUICA_FORM_JSON = %(FORM_JSON)s,
                SUICA_FORM_ACTION = %(FORM_ACTION)s,
                LAST_LOGIN_STATUS = 'OTP_REQUIRED'
            WHERE id = %(id)s AND CRE_USER_ID = %(USER_ID)s AND DEL_FLAG = 0
            """,
            {
                "CHALLENGE_ID": challenge_id,
                "EXPIRES_AT": expires_at,
                "COOKIE_JSON": json.dumps(cookies),
                "FORM_JSON": json.dumps(form_info),
                "FORM_ACTION": action_url,
                "id": self.value(config, "id", "ID"),
                "USER_ID": user_id,
            },
        )

    def save_authenticated_session_for_user(self, user_id, cookies):
        """認証成功後のCookieとログイン状態を保存する。"""
        ymd, hms = now_ymd_hms()
        self.database.update(
            """
            UPDATE auto_input_info SET
                SUICA_COOKIE_JSON = %(COOKIE_JSON)s,
                SUICA_CHALLENGE_ID = NULL,
                SUICA_CHALLENGE_EXPIRES_AT = NULL,
                SUICA_FORM_JSON = NULL,
                SUICA_FORM_ACTION = NULL,
                LAST_LOGIN_STATUS = 'AUTHENTICATED',
                LAST_LOGIN_DT = %(DT)s,
                LAST_LOGIN_TM = %(TM)s
            WHERE CRE_USER_ID = %(USER_ID)s AND CONNECTION_TYPE = 'AMAZON' AND DEL_FLAG = 0
            """,
            {"COOKIE_JSON": json.dumps(cookies), "DT": ymd, "TM": hms, "USER_ID": user_id},
        )

    def update_status(self, config, user_id, status):
        """Amazon設定のログイン状態を更新する。"""
        self.database.update(
            "UPDATE auto_input_info SET LAST_LOGIN_STATUS = %(STATUS)s WHERE id = %(id)s AND CRE_USER_ID = %(USER_ID)s",
            {"STATUS": status, "id": self.value(config, "id", "ID"), "USER_ID": user_id},
        )

    def get_config(self, user_id):
        """ユーザーのAmazon連携設定を取得する。"""
        rows = self.database.select(
            """
            SELECT * FROM auto_input_info
            WHERE CRE_USER_ID = %(USER_ID)s AND DEL_FLAG = 0
              AND (CONNECTION_TYPE = 'AMAZON' OR UPPER(SUP_NAME) = 'AMAZON')
            ORDER BY id DESC LIMIT 1
            """,
            {"USER_ID": user_id},
        )
        return rows[0] if rows else {}

    def new_session(self):
        """Amazon接続用HTTPセッションを作成する。"""
        session = super().new_session(USER_AGENT)
        session.headers.update({
            "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.7,en;q=0.6",
            "Referer": AMAZON_HOME_URL,
        })
        return session

    @staticmethod
    def serialize_cookies(cookie_jar):
        """HTTP CookieJarをDB保存可能な配列へ変換する。"""
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
        """保存済みCookieをHTTPセッションへ復元する。"""
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
    def value(row, *keys):
        """辞書から大文字小文字を区別せず候補キーの値を取得する。"""
        lower = {str(key).lower(): value for key, value in (row or {}).items()}
        for key in keys:
            if key in (row or {}):
                return row.get(key)
            if str(key).lower() in lower:
                return lower[str(key).lower()]
        return None
