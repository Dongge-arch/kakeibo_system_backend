# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""ニトリ注文履歴を取得し、家計簿レシートへ自動登録する。"""

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


NITORI_CONFIG = ReceiptShopConfig(
    connection_type="NITORI",
    display_name="ニトリ",
    supplier_name="株式会社ニトリ",
    invoice_number="NITORI",
    login_url="https://www.nitori-net.jp/ec/login",
    history_url="https://www.nitori-net.jp/ec/my-account/orders",
    receipt_store_name="ニトリネット",
    category_preferences=(
        ("住居", "家具"),
        ("日用品", "生活雑貨"),
        ("その他", "未分類"),
    ),
)


class AutoInput_Nitori(AutoInputShopBase):
    """ニトリ専用の注文履歴連携。"""

    SERVICE_CONFIG = NITORI_CONFIG

    def fetch_recent_orders(self, account_id, password, config, user_id):
        if not os.environ.get("DISPLAY"):
            self.update_login_status(config, user_id, "TEMPORARILY_UNAVAILABLE")
            raise Error(
                status_code=503,
                error_code="1000062",
                message="ニトリ連携はArmbian上のXvfb表示環境で実行してください。",
            )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**self.browser_launch_options())
            context = self.new_browser_context(browser)
            page = context.new_page()
            page.set_default_timeout(30000)
            try:
                token_failures = []
                page.on("response", self.capture_nitori_token_failure(token_failures))
                if not self.goto_page(page, self.login_url(config), wait_until="load", timeout=60000):
                    self.update_login_status(config, user_id, "TEMPORARILY_UNAVAILABLE")
                    raise Error(
                        status_code=503,
                        error_code="1000062",
                        message="ニトリのログインページをArmbian上のブラウザで読み込めません。時間をおいて再実行してください。",
                    )
                self.type_nitori_credentials(page, account_id, password)
                self.click_login_button(page)
                self.wait_for_nitori_login_result(page, token_failures, timeout_ms=30000)
                if token_failures:
                    self.update_login_status(config, user_id, "LOGIN_FAILED")
                    raise Error(
                        status_code=400,
                        error_code="1000062",
                        message=(
                            "ニトリのログインがサイト側のアクセス制限で拒否されました。"
                            "Armbianのブラウザからニトリへログインできる状態にしてから再実行してください。"
                        ),
                    )
                if not self.goto_page(page, self.history_url(config), wait_until="load", timeout=60000):
                    self.update_login_status(config, user_id, "TEMPORARILY_UNAVAILABLE")
                    raise Error(
                        status_code=503,
                        error_code="1000062",
                        message="ニトリ注文履歴をArmbian上のブラウザで読み込めません。時間をおいて再実行してください。",
                    )
                body_text = self.wait_for_nitori_orders(page, timeout_ms=45000)
                if "login" in page.url or page.locator('input[name="email"]').count() > 0:
                    self.update_login_status(config, user_id, "LOGIN_FAILED")
                    raise Error(
                        status_code=400,
                        error_code="1000062",
                        message="ニトリへログインできませんでした。ログイン情報を確認してください。",
                    )
                self.expand_nitori_order_items(page)
                body_text = page.locator("body").inner_text(timeout=20000) or body_text
                self.update_login_status(config, user_id, "LOGIN_SUCCESS")
                return self.parse_nitori_orders(body_text)
            finally:
                context.close()
                browser.close()

    def type_nitori_credentials(self, page, account_id, password):
        email_input = self.find_visible_input(
            page,
            lambda attrs: attrs.get("name") == "email" or attrs.get("type") == "email",
        )
        password_input = self.find_visible_input(
            page,
            lambda attrs: attrs.get("name") == "password" or attrs.get("type") == "password",
        )
        self.clear_and_type(page, email_input, account_id)
        self.clear_and_type(page, password_input, password)

    @staticmethod
    def find_visible_input(page, matcher):
        inputs = page.locator("input")
        for _ in range(30):
            count = inputs.count()
            for index in range(count):
                field = inputs.nth(index)
                try:
                    if not field.is_visible(timeout=500):
                        continue
                    attrs = {
                        "name": field.get_attribute("name", timeout=500),
                        "type": field.get_attribute("type", timeout=500),
                        "id": field.get_attribute("id", timeout=500),
                        "placeholder": field.get_attribute("placeholder", timeout=500),
                    }
                    if matcher(attrs):
                        return field
                except Exception:
                    continue
            page.wait_for_timeout(1000)
        raise Error(
            status_code=503,
            error_code="1000062",
            message="ニトリのログイン入力欄をArmbian上のブラウザで検出できません。",
        )

    @staticmethod
    def clear_and_type(page, locator, value):
        locator.click(timeout=5000)
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.type(value, delay=20)

    @staticmethod
    def click_login_button(page):
        buttons = page.locator("button")
        for _ in range(20):
            count = buttons.count()
            for index in range(count):
                button = buttons.nth(index)
                try:
                    text = re.sub(r"\s+", " ", button.inner_text(timeout=500)).strip()
                    if text != "ログイン" or not button.is_visible(timeout=500):
                        continue
                    if not button.is_enabled(timeout=500):
                        continue
                    box = button.bounding_box(timeout=1000)
                    if not box:
                        continue
                    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    return
                except Exception:
                    continue
            page.wait_for_timeout(1000)
        raise Error(
            status_code=503,
            error_code="1000062",
            message="ニトリのログインボタンが有効になりません。ログイン情報の形式を確認してください。",
        )

    @staticmethod
    def capture_nitori_token_failure(token_failures):
        def handler(response):
            if "/authorizationserver/oauth/token" not in response.url:
                return
            if response.status in {401, 403}:
                token_failures.append({"status": response.status})

        return handler

    @staticmethod
    def wait_for_nitori_login_result(page, token_failures, timeout_ms):
        deadline = datetime.now() + timedelta(milliseconds=timeout_ms)
        while datetime.now() < deadline:
            if token_failures:
                break
            current_url = page.url.lower()
            if "/ec/login" not in current_url and "inputmembermail" not in current_url:
                break
            page.wait_for_timeout(1000)
        try:
            page.evaluate("window.stop()")
        except Exception:
            pass

    def parse_nitori_orders(self, body_text):
        tokens = [self.clean_label(line) for line in body_text.splitlines() if self.clean_label(line)]
        orders = []
        order_indexes = [index for index, token in enumerate(tokens) if token == "注文日"]
        for position, start_index in enumerate(order_indexes):
            end_index = order_indexes[position + 1] if position + 1 < len(order_indexes) else len(tokens)
            block = tokens[start_index:end_index]
            order_date = self.parse_date(block[1] if len(block) > 1 else "")
            if not order_date or not self.is_recent_order(order_date):
                continue
            store_name = self.block_value(block, "注文店舗") or self.service.receipt_store_name
            status = self.block_value(block, "現在の状況") or ""
            if "キャンセル" in status:
                continue
            items = self.parse_nitori_items(block)
            total_price = sum(int(item.get("totalPrice") or 0) for item in items)
            if total_price <= 0:
                continue
            order_seed = {
                "date": order_date,
                "store": store_name,
                "status": status,
                "items": items,
            }
            order_id = "NITORI-" + hashlib.sha256(
                json.dumps(order_seed, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()[:16]
            orders.append({
                "orderId": order_id,
                "orderDate": order_date,
                "storeName": store_name,
                "status": status,
                "items": items,
                "totalPrice": total_price,
            })
        return orders

    def parse_nitori_items(self, block):
        items = []
        seen = set()
        for index, token in enumerate(block):
            price = self.parse_price(token)
            if price is None:
                continue
            item_code_index = index - 1
            if item_code_index < 1 or not re.fullmatch(r"\d{6,}", block[item_code_index]):
                continue
            item_name = block[item_code_index - 1]
            if item_name in {"ニトリ", "その他", "商品コード", "価格(税込)", "数量"}:
                continue
            quantity = 1.0
            for tail_index in range(index + 1, min(index + 8, len(block))):
                if block[tail_index] == "数量" and tail_index + 1 < len(block):
                    quantity = self.parse_quantity(block[tail_index + 1])
                    break
            dedupe_key = (block[item_code_index], item_name, price, quantity)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            items.append({
                "itemName": item_name,
                "itemCode": block[item_code_index],
                "quantity": quantity,
                "unitPrice": price,
                "totalPrice": int(round(price * quantity)),
            })
        return items

    @staticmethod
    def block_value(block, label):
        if label in block:
            index = block.index(label)
            if index + 1 < len(block):
                return block[index + 1]
        return ""

    def wait_for_nitori_orders(self, page, timeout_ms):
        deadline = datetime.now() + timedelta(milliseconds=timeout_ms)
        last_text = ""
        while datetime.now() < deadline:
            try:
                last_text = page.locator("body").inner_text(timeout=5000)
            except Exception:
                last_text = ""
            if "注文日" in last_text or "注文履歴はありません" in last_text:
                return last_text
            page.wait_for_timeout(2000)
        return last_text

    @staticmethod
    def expand_nitori_order_items(page):
        for _ in range(4):
            buttons = page.locator("text=商品をもっと見る")
            try:
                count = buttons.count()
            except Exception:
                return
            if count <= 0:
                return
            clicked = False
            for index in range(count):
                try:
                    buttons.nth(index).click(timeout=5000)
                    clicked = True
                except Exception:
                    continue
            if not clicked:
                return
            page.wait_for_timeout(1000)

    @staticmethod
    def wait_quietly(page, timeout):
        try:
            page.wait_for_load_state("networkidle", timeout=timeout)
        except PlaywrightTimeoutError:
            page.wait_for_timeout(1000)
