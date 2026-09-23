# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""ECサイト系の独立バッチで共通利用する登録処理。"""

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from src.api.kakeibo.receipt.new_receipt_registration.newReceiptRegistration import NewReceiptRegistration
from src.api.kakeibo.receipt.taxPrice import normalize_tax_rate
from src.common.api_utils import now_ymd_hms
from src.common.auth_context import reset_current_user_id, set_current_user_id
from src.common.base.base_auto_input import BaseAutoInput
from src.common.exception import Error
from src.common.functions.response import response


AUTO_INPUT_STATUS_FETCHED = "FETCHED"
AUTO_INPUT_STATUS_REGISTERED = "3"
SHOP_LOOKBACK_DAYS = 92


@dataclass(frozen=True)
class ReceiptShopConfig:
    connection_type: str
    display_name: str
    supplier_name: str
    invoice_number: str
    login_url: str
    history_url: str
    receipt_store_name: str
    category_preferences: tuple


class AutoInputShopBase(BaseAutoInput):
    """店ごとに独立した自動入力バッチが使う共通処理。"""

    SERVICE_CONFIG = None

    def __init__(self, db_path=None):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path or None)
        self._validate_headers_functions = {}
        self._validate_body_functions = {}

    def main(self, request_dict):
        user_id = self.require_user_id(request_dict)
        config = self.get_auto_input_config(user_id, self.service.connection_type)
        account_id = str(self.value(config, "LOGIN_ID_1", "login_id_1") or "").strip()
        password = str(self.value(config, "LOGIN_PW_1", "login_pw_1") or "")
        if not config or not account_id or not password:
            raise Error(
                status_code=400,
                error_code="1000062",
                message=f"先に{self.service.display_name}のログイン情報を保存してください。",
            )

        try:
            rows = self.fetch_recent_orders(account_id, password, config, user_id)
        except Error as exc:
            return exc.response()
        inserted_count = self.save_order_rows(rows, user_id)
        registered_count, failed_count = self.register_pending_orders(user_id)
        duplicate_count = len(rows) - inserted_count
        return response(200, {
            "ok": True,
            "status": "COMPLETED",
            "message": f"{self.service.display_name}注文履歴の取得が完了しました。",
            "totalFetched": len(rows),
            "fetchedCount": len(rows),
            "needToRegister": inserted_count,
            "insertedCount": inserted_count,
            "alreadyRegistered": duplicate_count,
            "duplicateCount": duplicate_count,
            "registered": registered_count,
            "registeredCount": registered_count,
            "failed": failed_count,
            "failedCount": failed_count,
        })

    @property
    def service(self):
        if self.SERVICE_CONFIG is None:
            raise RuntimeError("SERVICE_CONFIG is not set.")
        return self.SERVICE_CONFIG

    def history_url(self, config):
        return self.value(config, "PAGE_URL_1", "page_url_1") or self.service.history_url

    def login_url(self, config):
        return self.value(config, "PAGE_URL_2", "page_url_2") or self.service.login_url

    def browser_launch_options(self):
        executable_path = os.environ.get("KAKEIBO_CHROMIUM_PATH") or "/usr/bin/chromium"
        explicit_headless = str(os.environ.get("KAKEIBO_BROWSER_HEADLESS") or "").strip().lower()
        if explicit_headless in {"1", "true", "yes"}:
            headless = True
        elif explicit_headless in {"0", "false", "no"}:
            headless = False
        else:
            headless = not bool(os.environ.get("DISPLAY"))
        args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-http2",
            "--window-size=1366,900",
        ]
        return {
            "executable_path": executable_path if os.path.exists(executable_path) else None,
            "headless": headless,
            "args": args,
        }

    def new_browser_context(self, browser):
        options = {
            "locale": "ja-JP",
            "timezone_id": "Asia/Tokyo",
            "viewport": {"width": 1366, "height": 900},
            "extra_http_headers": {"Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7"},
        }
        user_agent = str(os.environ.get("KAKEIBO_BROWSER_USER_AGENT") or "").strip()
        if user_agent:
            options["user_agent"] = user_agent
        return browser.new_context(**options)

    def goto_page(self, page, url, wait_until="domcontentloaded", timeout=45000):
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout)
            return True
        except PlaywrightTimeoutError:
            self.logger.warning(
                "%s page navigation timed out url=%s current=%s",
                self.service.connection_type,
                url,
                page.url,
            )
            return bool(page.url and page.url not in {"about:blank", "chrome-error://chromewebdata/"})
        except Exception as exc:
            if "ERR_ABORTED" in str(exc) and page.url and page.url != "about:blank":
                self.logger.warning(
                    "%s page navigation was aborted after redirect url=%s current=%s",
                    self.service.connection_type,
                    url,
                    page.url,
                )
                return True
            self.logger.warning(
                "%s page navigation failed url=%s current=%s error=%s",
                self.service.connection_type,
                url,
                page.url,
                exc,
            )
            return False

    def fetch_recent_orders(self, account_id, password, config, user_id):
        raise NotImplementedError

    def save_order_rows(self, rows, user_id):
        inserted_count = 0
        ymd, hms = now_ymd_hms()
        for row in rows:
            source_key = self.order_source_key(row)
            existing = self.database.select(
                self.database.read_sql("SELECT_AUTO_INPUT_CONTENT", location=__file__),
                {
                    "CRE_USER_ID": user_id,
                    "CONNECTION_TYPE": self.service.connection_type,
                    "SOURCE_KEY": source_key,
                },
            )
            if existing:
                continue
            content = json.dumps(row, ensure_ascii=False, sort_keys=True)
            self.database.insert(
                self.database.read_sql("INSERT_AUTO_INPUT_CONTENT", location=__file__),
                {
                    "CRE_PROG": self.__class__.__name__,
                    "UPD_PROG": self.__class__.__name__,
                    "INV_REG_NUM": self.service.invoice_number,
                    "RET_CONT": content,
                    "RET_DT": str(row.get("orderDate") or "").replace("-", ""),
                    "RET_TM": "000000",
                    "AUTO_INPUT_STATUS": AUTO_INPUT_STATUS_FETCHED,
                    "CONNECTION_TYPE": self.service.connection_type,
                    "SOURCE_KEY": source_key,
                    "CRE_DT": ymd,
                    "CRE_TM": hms,
                    "UPD_DT": ymd,
                    "UPD_TM": hms,
                    "CRE_USER_ID": user_id,
                    "UPD_USER_ID": user_id,
                },
            )
            inserted_count += 1
        return inserted_count

    def register_pending_orders(self, user_id):
        rows = self.database.select(
            self.database.read_sql("SELECT_PENDING_AUTO_INPUT_CONTENT", location=__file__),
            {
                "CRE_USER_ID": user_id,
                "CONNECTION_TYPE": self.service.connection_type,
                "AUTO_INPUT_STATUS": AUTO_INPUT_STATUS_FETCHED,
            },
        ) or []
        if not rows:
            return 0, 0

        categories = self.load_receipt_categories(user_id)
        registration_api = NewReceiptRegistration()
        registered_count = 0
        failed_count = 0
        for row in rows:
            try:
                order = json.loads(self.value(row, "RET_CONT", "ret_cont") or "{}")
                receipt_info = self.build_receipt_info(order, categories, user_id)
                auth_token = set_current_user_id(user_id)
                try:
                    result = registration_api.call(
                        headers={"x-kakeibo-user-id": user_id, "Content-Type": "application/json"},
                        body={"receiptInfo": receipt_info},
                    )
                finally:
                    reset_current_user_id(auth_token)
                status_code = int(result.get("statusCode", 500))
                if status_code == 409:
                    self.mark_order_registered(row)
                    continue
                if status_code >= 400:
                    raise RuntimeError(f"{self.service.connection_type} receipt registration failed: {result}")
                self.mark_order_registered(row)
                registered_count += 1
            except Exception as exc:
                failed_count += 1
                self.logger.error("Failed to register %s order: %s", self.service.connection_type, exc)
        return registered_count, failed_count

    def build_receipt_info(self, order, categories, user_id):
        details = self.build_receipt_details(order, categories)
        return {
            "userId": user_id,
            "invoiceRegistrationNumber": self.service.invoice_number,
            "supplierName": self.service.supplier_name,
            "storeName": order.get("storeName") or self.service.receipt_store_name,
            "storeCode": "",
            "posNo": "",
            "receiptNo": order.get("orderId") or self.order_source_key(order)[:16],
            "receiptDate": order.get("orderDate") or datetime.now().strftime("%Y-%m-%d"),
            "receiptTime": "00:00",
            "taxFlag": 1,
            "receiptDetailCount": len(details),
            "receiptDetails": details,
            "totalPrice": int(order.get("totalPrice") or sum(int(item.get("totalPrice") or 0) for item in details)),
            "supplierImage": "",
        }

    def build_receipt_details(self, order, categories):
        default_category = self.default_category_mapping(categories)
        details = []
        items = order.get("items") or []
        for item in items:
            item_name = str(item.get("itemName") or self.service.display_name).strip()
            quantity = float(item.get("quantity") or 1)
            unit_price = int(item.get("unitPrice") or item.get("totalPrice") or 0)
            total_price = int(item.get("totalPrice") or round(unit_price * quantity))
            details.append({
                "itemName": item_name[:255],
                "category1": default_category.get("category1"),
                "category2": default_category.get("category2"),
                "taxRate": default_category.get("taxRate"),
                "quantity": quantity,
                "unit": "個",
                "unitPrice": unit_price,
                "discount": 0,
                "totalPrice": total_price,
            })
        if details:
            return details
        total_price = int(order.get("totalPrice") or 0)
        return [{
            "itemName": f"{self.service.display_name}注文",
            "category1": default_category.get("category1"),
            "category2": default_category.get("category2"),
            "taxRate": default_category.get("taxRate"),
            "quantity": 1.0,
            "unit": "個",
            "unitPrice": total_price,
            "discount": 0,
            "totalPrice": total_price,
        }]

    def default_category_mapping(self, categories):
        rows = self.category_rows(categories)
        for preference in self.service.category_preferences:
            for row in rows:
                if row.get("category1") == preference[0] and row.get("category2") == preference[1]:
                    return row
        for row in rows:
            if row.get("category1") == "その他" and row.get("category2") == "未分類":
                return row
        if rows:
            return rows[0]
        return {"category1": "その他", "category2": "未分類", "taxRate": 0.10}

    def load_receipt_categories(self, user_id):
        return {
            "category2": self.database.select(
                self.database.read_sql("SELECT_RECEIPT_CATEGORY2", location=__file__),
                {"CRE_USER_ID": user_id},
            ) or [],
        }

    def category_rows(self, categories):
        rows = []
        for item in categories.get("category2") or []:
            if not isinstance(item, dict):
                continue
            category1 = self.clean_label(item.get("CATEGORY1_NAME") or item.get("category1Name") or item.get("category1_name"))
            category2 = self.clean_label(item.get("CATEGORY2_NAME") or item.get("category2Name") or item.get("category2_name"))
            if category1 and category2:
                rows.append({
                    "category1": category1,
                    "category2": category2,
                    "taxRate": normalize_tax_rate(item.get("TAX_RATE") if item.get("TAX_RATE") is not None else item.get("taxRate") or item.get("tax_rate")),
                })
        return rows

    def mark_order_registered(self, row):
        ymd, hms = now_ymd_hms()
        self.database.update(
            self.database.read_sql("UPDATE_AUTO_INPUT_CONTENT_STATUS", location=__file__),
            {
                "AUTO_INPUT_STATUS": AUTO_INPUT_STATUS_REGISTERED,
                "UPD_PROG": self.__class__.__name__,
                "UPD_DT": ymd,
                "UPD_TM": hms,
                "ID": self.value(row, "id", "ID"),
            },
        )

    def update_login_status(self, config, user_id, status):
        ymd, hms = now_ymd_hms()
        self.database.update(
            self.database.read_sql("UPDATE_AUTO_INPUT_LOGIN_STATUS", location=__file__),
            {
                "LAST_LOGIN_STATUS": status,
                "LAST_LOGIN_DT": ymd,
                "LAST_LOGIN_TM": hms,
                "UPD_PROG": self.__class__.__name__,
                "UPD_DT": ymd,
                "UPD_TM": hms,
                "UPD_USER_ID": user_id,
                "ID": self.value(config, "id", "ID"),
                "CRE_USER_ID": user_id,
            },
        )

    @staticmethod
    def order_source_key(order):
        stable = {
            "orderId": order.get("orderId") or "",
            "orderDate": order.get("orderDate") or "",
            "storeName": order.get("storeName") or "",
            "totalPrice": order.get("totalPrice") or 0,
            "items": order.get("items") or [],
        }
        return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    @staticmethod
    def clean_label(value):
        return re.sub(r"\s+", " ", str(value or "").strip())

    @staticmethod
    def parse_price(value):
        match = re.search(r"([0-9][0-9,]*)\s*円", str(value or ""))
        return int(match.group(1).replace(",", "")) if match else None

    @staticmethod
    def parse_quantity(value):
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(value or ""))
        return float(match.group(1)) if match else 1.0

    @staticmethod
    def parse_date(value):
        text = str(value or "").strip()
        match = re.search(r"(\d{4})[年/-]\s*(\d{1,2})[月/-]\s*(\d{1,2})", text)
        if not match:
            return ""
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    @staticmethod
    def is_recent_order(order_date):
        try:
            parsed = datetime.strptime(order_date, "%Y-%m-%d").date()
        except ValueError:
            return True
        cutoff = (datetime.now() - timedelta(days=SHOP_LOOKBACK_DAYS)).date()
        return parsed >= cutoff
