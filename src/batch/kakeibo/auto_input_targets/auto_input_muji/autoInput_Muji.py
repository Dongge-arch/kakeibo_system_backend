# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""無印良品注文履歴を取得し、家計簿レシートへ自動登録する。"""

import hashlib
import json
import os
import re
from datetime import datetime, timedelta

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from src.batch.kakeibo.auto_input_targets.auto_input_common.autoInputShopBase import (
    AutoInputShopBase,
    ReceiptShopConfig,
)
from src.common.exception import Error


MUJI_CONFIG = ReceiptShopConfig(
    connection_type="MUJI",
    display_name="無印良品",
    supplier_name="株式会社良品計画",
    invoice_number="MUJI",
    login_url="https://login-jp.muji.com/login",
    history_url="https://www.muji.com/jp/ja/store/cust/order/itemlist?web_store=my_menu_mem_list-orders",
    receipt_store_name="無印良品ネットストア",
    category_preferences=(
        ("日用品", "生活雑貨"),
        ("その他", "未分類"),
    ),
)


class AutoInput_Muji(AutoInputShopBase):
    """無印良品専用の注文履歴連携。"""

    SERVICE_CONFIG = MUJI_CONFIG

    def fetch_recent_orders(self, account_id, password, config, user_id):
        if not os.environ.get("DISPLAY"):
            self.update_login_status(config, user_id, "TEMPORARILY_UNAVAILABLE")
            raise Error(
                status_code=503,
                error_code="1000062",
                message="無印良品連携はArmbian上のXvfb表示環境で実行してください。",
            )

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**self.browser_launch_options())
            context = self.new_browser_context(browser)
            page = context.new_page()
            page.set_default_timeout(10000)
            try:
                login_post = {}
                page.on("request", self.capture_muji_login_request(login_post))
                page.on("response", self.capture_muji_login_response(login_post))
                page.on("requestfailed", self.capture_muji_login_failure(login_post))
                if not self.open_muji_login(page, config):
                    self.update_login_status(config, user_id, "TEMPORARILY_UNAVAILABLE")
                    raise Error(
                        status_code=503,
                        error_code="1000062",
                        message="無印良品のログインページをArmbian上のブラウザで読み込めません。時間をおいて再実行してください。",
                    )

                self.submit_muji_login(page, account_id, password)
                login_text = self.wait_for_muji_login_result(page, timeout_ms=15000)
                if self.needs_login(page):
                    if login_post.get("sent") and not login_post.get("status"):
                        self.update_login_status(config, user_id, "TEMPORARILY_UNAVAILABLE")
                        raise Error(
                            status_code=503,
                            error_code="1000062",
                            message="無印良品のログインリクエストがArmbian上のブラウザで応答しません。時間をおいて再実行してください。",
                        )
                    self.update_login_status(config, user_id, "LOGIN_FAILED")
                    detail = self.extract_login_error(login_text)
                    message = "無印良品へログインできませんでした。ログイン情報を確認してください。"
                    if detail:
                        message = f"{message}（{detail}）"
                    raise Error(status_code=400, error_code="1000062", message=message)

                if not self.goto_page(page, self.history_url(config), wait_until="domcontentloaded", timeout=25000):
                    self.update_login_status(config, user_id, "TEMPORARILY_UNAVAILABLE")
                    raise Error(
                        status_code=503,
                        error_code="1000062",
                        message="無印良品注文履歴をArmbian上のブラウザで読み込めません。時間をおいて再実行してください。",
                    )

                body_text = self.wait_for_muji_history(page, timeout_ms=20000)
                if self.needs_login(page):
                    self.update_login_status(config, user_id, "LOGIN_FAILED")
                    raise Error(
                        status_code=400,
                        error_code="1000062",
                        message="無印良品へログインできませんでした。ログイン情報を確認してください。",
                    )
                self.update_login_status(config, user_id, "LOGIN_SUCCESS")
                if "注文履歴はありません" in body_text or "ご注文履歴はありません" in body_text:
                    return []
                return self.parse_muji_orders(body_text)
            finally:
                context.close()
                browser.close()

    def open_muji_login(self, page, config):
        for _ in range(2):
            if self.goto_page(page, self.login_url(config), wait_until="domcontentloaded", timeout=25000):
                try:
                    page.wait_for_selector("#username", timeout=8000)
                    page.wait_for_selector("#password", timeout=5000)
                    return True
                except PlaywrightTimeoutError:
                    pass
            try:
                page.goto("about:blank", wait_until="commit", timeout=5000)
            except Exception:
                pass
            page.wait_for_timeout(3000)
        return False

    @staticmethod
    def capture_muji_login_request(login_post):
        def handler(request):
            if request.method == "POST" and request.url.startswith("https://login-jp.muji.com/login"):
                login_post["sent"] = True

        return handler

    @staticmethod
    def capture_muji_login_response(login_post):
        def handler(response):
            if response.request.method == "POST" and response.url.startswith("https://login-jp.muji.com/login"):
                login_post["status"] = response.status

        return handler

    @staticmethod
    def capture_muji_login_failure(login_post):
        def handler(request):
            if request.method == "POST" and request.url.startswith("https://login-jp.muji.com/login"):
                failure = request.failure or {}
                login_post["failure"] = str(failure)

        return handler

    @staticmethod
    def submit_muji_login(page, account_id, password):
        page.locator("#username").fill(account_id, timeout=5000)
        page.locator("#password").fill(password, timeout=5000)
        page.evaluate(
            """
            ([account, passwordValue]) => {
                const username = document.getElementById("username");
                const usernameForLogin = document.getElementById("usernameForLogin");
                const password = document.getElementById("password");
                username.value = account;
                usernameForLogin.value = account;
                password.value = passwordValue;
                username.dispatchEvent(new Event("input", { bubbles: true }));
                username.dispatchEvent(new Event("change", { bubbles: true }));
                password.dispatchEvent(new Event("input", { bubbles: true }));
                setTimeout(() => {
                    const form = document.getElementById("login_form");
                    if (form) {
                        form.submit();
                    }
                }, 0);
                return true;
            }
            """,
            [account_id, password],
        )

    def wait_for_muji_login_result(self, page, timeout_ms):
        deadline = datetime.now() + timedelta(milliseconds=timeout_ms)
        while datetime.now() < deadline:
            current_url = page.url.lower()
            if "login-jp.muji.com/login" not in current_url:
                break
            page.wait_for_timeout(1000)
        if "login-jp.muji.com/login" in page.url.lower():
            return ""
        return self.safe_body_text(page, timeout=2000)

    def wait_for_muji_history(self, page, timeout_ms):
        deadline = datetime.now() + timedelta(milliseconds=timeout_ms)
        last_text = ""
        while datetime.now() < deadline:
            last_text = self.safe_body_text(page, timeout=3000) or last_text
            if self.needs_login(page):
                return last_text
            if any(token in last_text for token in ("注文履歴", "購入履歴", "注文日", "ご注文", "注文履歴はありません", "ご注文履歴はありません")):
                return last_text
            page.wait_for_timeout(2000)
        return last_text

    @staticmethod
    def safe_body_text(page, timeout=3000):
        try:
            return page.locator("body").inner_text(timeout=timeout)
        except Exception:
            return ""

    def needs_login(self, page):
        current_url = page.url.lower()
        if "login-jp.muji.com/login" in current_url:
            return True
        try:
            if page.locator("#username").count() > 0 and page.locator("#password").count() > 0:
                return True
        except Exception:
            return False
        return False

    @staticmethod
    def has_login_error(body_text):
        return any(
            token in body_text
            for token in (
                "正しく入力",
                "一致しません",
                "ログインできません",
                "メールアドレスまたはパスワード",
                "認証できません",
                "エラー",
            )
        )

    def extract_login_error(self, body_text):
        if not body_text:
            return ""
        for line in body_text.splitlines():
            label = self.clean_label(line)
            if self.has_login_error(label):
                return label[:120]
        return ""

    def parse_muji_orders(self, body_text):
        tokens = [self.clean_label(line) for line in body_text.splitlines() if self.clean_label(line)]
        order_indexes = self.find_muji_order_indexes(tokens)
        orders = []
        for position, start_index in enumerate(order_indexes):
            end_index = order_indexes[position + 1] if position + 1 < len(order_indexes) else len(tokens)
            block = tokens[start_index:end_index]
            order_date = self.find_first_date(block)
            if not order_date or not self.is_recent_order(order_date):
                continue
            items = self.parse_generic_price_items(block)
            total_price = sum(int(item.get("totalPrice") or 0) for item in items)
            if total_price <= 0:
                total_price = self.find_total_price(block)
            if total_price <= 0:
                continue
            if not items:
                items = [{
                    "itemName": "無印良品注文",
                    "quantity": 1.0,
                    "unitPrice": total_price,
                    "totalPrice": total_price,
                }]
            order_id = self.find_order_number(block) or "MUJI-" + hashlib.sha256(
                json.dumps({"date": order_date, "items": items, "total": total_price}, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()[:16]
            orders.append({
                "orderId": order_id,
                "orderDate": order_date,
                "storeName": self.service.receipt_store_name,
                "items": items,
                "totalPrice": total_price,
            })
        return orders

    def find_muji_order_indexes(self, tokens):
        indexes = [
            index for index, token in enumerate(tokens)
            if token in {"注文日", "ご注文日"} or token.startswith("注文日") or token.startswith("ご注文日")
        ]
        if indexes:
            return indexes
        return [
            index for index, token in enumerate(tokens)
            if self.parse_date(token) and any("注文" in near for near in tokens[max(0, index - 4):index + 5])
        ]

    def parse_generic_price_items(self, block):
        items = []
        seen = set()
        skip_words = {"合計", "小計", "送料", "手数料", "税込", "税抜", "注文金額", "支払金額", "お支払い"}
        for index, token in enumerate(block):
            price = self.parse_price(token)
            if price is None:
                continue
            name = self.find_previous_item_name(block, index)
            if not name or any(word in name for word in skip_words):
                continue
            quantity = self.find_nearby_quantity(block, index)
            dedupe_key = (name, price, quantity)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            items.append({
                "itemName": name,
                "quantity": quantity,
                "unitPrice": price,
                "totalPrice": int(round(price * quantity)),
            })
        return items

    @staticmethod
    def find_previous_item_name(block, price_index):
        labels = {"商品", "商品名", "価格", "数量", "注文日", "ご注文日", "注文番号", "配送", "お届け"}
        for index in range(price_index - 1, max(price_index - 8, -1), -1):
            candidate = block[index]
            if candidate in labels or re.fullmatch(r"\d{5,}", candidate) or re.search(r"円", candidate):
                continue
            if len(candidate) >= 2:
                return candidate
        return ""

    def find_nearby_quantity(self, block, price_index):
        for index in range(price_index + 1, min(price_index + 8, len(block))):
            if block[index] in {"数量", "個数"} and index + 1 < len(block):
                return self.parse_quantity(block[index + 1])
        return 1.0

    def find_first_date(self, block):
        for token in block[:16]:
            parsed = self.parse_date(token)
            if parsed:
                return parsed
        return ""

    def find_total_price(self, block):
        for index, token in enumerate(block):
            if any(label in token for label in ("合計", "注文金額", "支払金額", "お支払い")):
                for price_index in range(index, min(index + 5, len(block))):
                    price = self.parse_price(block[price_index])
                    if price is not None:
                        return price
        prices = [self.parse_price(token) for token in block]
        prices = [price for price in prices if price is not None]
        return max(prices) if prices else 0

    @staticmethod
    def find_order_number(block):
        text = " ".join(block)
        match = re.search(r"(?:注文番号|ご注文番号)[:：]?\s*([0-9A-Z-]{6,})", text)
        return match.group(1) if match else ""
