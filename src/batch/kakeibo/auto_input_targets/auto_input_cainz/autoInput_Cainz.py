# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""CAINZ注文履歴を取得し、家計簿レシートへ自動登録する。"""

import hashlib
import json
import re
from datetime import datetime, timedelta

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from src.batch.kakeibo.auto_input_targets.auto_input_common.autoInputShopBase import (
    AutoInputShopBase,
    ReceiptShopConfig,
)
from src.common.exception import Error


CAINZ_CONFIG = ReceiptShopConfig(
    connection_type="CAINZ",
    display_name="CAINZ",
    supplier_name="株式会社カインズ",
    invoice_number="CAINZ",
    login_url="https://www.cainz.com/signin/?from=order-history",
    history_url="https://www.cainz.com/mypage/order-history/",
    receipt_store_name="CAINZオンラインショップ",
    category_preferences=(
        ("日用品", "生活雑貨"),
        ("住居", "家具"),
        ("その他", "未分類"),
    ),
)


class AutoInput_Cainz(AutoInputShopBase):
    """CAINZ専用の注文履歴連携。"""

    SERVICE_CONFIG = CAINZ_CONFIG

    def fetch_recent_orders(self, account_id, password, config, user_id):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**self.browser_launch_options())
            context = self.new_browser_context(browser)
            page = context.new_page()
            page.set_default_timeout(30000)
            try:
                if not self.goto_page(page, self.history_url(config), timeout=45000):
                    self.update_login_status(config, user_id, "TEMPORARILY_UNAVAILABLE")
                    raise Error(
                        status_code=503,
                        error_code="1000062",
                        message="CAINZ注文履歴をArmbian上のブラウザで読み込めません。時間をおいて再実行してください。",
                    )
                if self.needs_login(page):
                    if page.locator("text=ログインする").count() > 0:
                        page.locator("text=ログインする").first.click()
                    page.wait_for_selector('input[type="email"]', timeout=45000)
                    page.fill('input[type="email"]', account_id)
                    page.fill('input[type="password"]', password)
                    page.locator('button[type="submit"]').filter(has_text="ログインする").last.click()
                    self.wait_for_cainz_history(page, timeout_ms=30000)
                if "order-history" not in page.url:
                    if not self.goto_page(page, self.history_url(config), timeout=45000):
                        self.update_login_status(config, user_id, "TEMPORARILY_UNAVAILABLE")
                        raise Error(
                            status_code=503,
                            error_code="1000062",
                            message="CAINZ注文履歴をArmbian上のブラウザで読み込めません。時間をおいて再実行してください。",
                        )
                body_text = self.wait_for_cainz_history(page, timeout_ms=30000)
                if not body_text and not self.goto_page(page, self.history_url(config), wait_until="commit", timeout=45000):
                    self.update_login_status(config, user_id, "TEMPORARILY_UNAVAILABLE")
                    raise Error(
                        status_code=503,
                        error_code="1000062",
                        message="CAINZ注文履歴をArmbian上のブラウザで読み込めません。時間をおいて再実行してください。",
                    )
                body_text = body_text or self.wait_for_cainz_history(page, timeout_ms=30000)
                if self.needs_login(page):
                    self.update_login_status(config, user_id, "LOGIN_FAILED")
                    raise Error(
                        status_code=400,
                        error_code="1000062",
                        message="CAINZへログインできませんでした。ログイン情報を確認してください。",
                    )
                body_text = body_text or page.locator("body").inner_text(timeout=20000)
                self.update_login_status(config, user_id, "LOGIN_SUCCESS")
                if "注文履歴はありません" in body_text:
                    return []
                return self.parse_cainz_orders(body_text)
            finally:
                context.close()
                browser.close()

    def needs_login(self, page):
        current_url = page.url.lower()
        if "signin" in current_url or "customer.cainz.com" in current_url:
            return True
        try:
            body_text = page.locator("body").inner_text(timeout=3000)
            if "オンライン会員に登録済みの方" in body_text and "ログインする" in body_text:
                return True
            return page.locator('input[type="email"]').count() > 0
        except Exception:
            return False

    def wait_for_cainz_history(self, page, timeout_ms):
        deadline = datetime.now() + timedelta(milliseconds=timeout_ms)
        last_text = ""
        while datetime.now() < deadline:
            try:
                last_text = page.locator("body").inner_text(timeout=3000)
            except Exception:
                last_text = ""
            if "注文履歴はありません" in last_text:
                return last_text
            if "過去3ヶ月間" in last_text and "注文履歴" in last_text and "オンライン会員に登録済みの方" not in last_text:
                return last_text
            page.wait_for_timeout(2000)
        return last_text

    def parse_cainz_orders(self, body_text):
        tokens = [self.clean_label(line) for line in body_text.splitlines() if self.clean_label(line)]
        orders = []
        order_date_indexes = [
            index for index, token in enumerate(tokens)
            if token in {"注文日", "ご注文日"} or token.startswith("注文日")
        ]
        for position, start_index in enumerate(order_date_indexes):
            end_index = order_date_indexes[position + 1] if position + 1 < len(order_date_indexes) else len(tokens)
            block = tokens[start_index:end_index]
            order_date = self.find_first_date(block)
            if not order_date or not self.is_recent_order(order_date):
                continue
            items = self.parse_generic_price_items(block)
            total_price = sum(int(item.get("totalPrice") or 0) for item in items)
            if total_price <= 0:
                continue
            order_id = self.find_order_number(block) or "CAINZ-" + hashlib.sha256(
                json.dumps({"date": order_date, "items": items}, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()[:16]
            orders.append({
                "orderId": order_id,
                "orderDate": order_date,
                "storeName": self.service.receipt_store_name,
                "items": items,
                "totalPrice": total_price,
            })
        return orders

    def parse_generic_price_items(self, block):
        items = []
        seen = set()
        skip_words = {"合計", "小計", "送料", "手数料", "税込", "税抜", "注文金額", "支払金額"}
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
        labels = {"商品", "商品名", "価格", "数量", "注文日", "ご注文日", "注文番号"}
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
        for token in block[:12]:
            parsed = self.parse_date(token)
            if parsed:
                return parsed
        return ""

    @staticmethod
    def find_order_number(block):
        text = " ".join(block)
        match = re.search(r"注文番号[:：]?\s*([0-9A-Z-]{6,})", text)
        return match.group(1) if match else ""

    @staticmethod
    def wait_quietly(page, timeout):
        try:
            page.wait_for_load_state("networkidle", timeout=timeout)
        except PlaywrightTimeoutError:
            page.wait_for_timeout(1000)
