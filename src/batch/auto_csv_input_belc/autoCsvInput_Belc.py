# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors


"""ベルク店舗HPにてCSVファイルをダウンロードし、レシート情報を自動登録するバッチクラス。"""

import json
import requests
import time
from bs4 import BeautifulSoup
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
from src.common.base.base_batch import BaseBatch
from src.common.functions.response import response
from src.common.auth_context import reset_current_user_id, set_current_user_id
from src.common.exception import Error
from src.api.receipt.new_receipt_registration.newReceiptRegistration import NewReceiptRegistration
from src.api.receipt.ai_receipt.receiptAnalyzer import (
    GeminiReceiptAnalyzer,
    build_category_pair_mapping_prompt,
    clean_category_label,
)
from src.api.receipt.taxPrice import normalize_tax_rate


BELC_INVOICE_NUMBER = "T8030001085963"
BELC_SUPPLIER_NAME = "ベルク"
AUTO_INPUT_STATUS_REGISTERED = "3"
BELC_REQUEST_RETRY_COUNT = 3
BELC_REQUEST_RETRY_BACKOFF_SECONDS = 1
BELC_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
BELC_CATEGORY_NAMES = {
    "01": "青果",
    "04": "精肉",
    "06": "パン",
    "07": "一般食品",
    "12": "卵・乳製品",
    "24": "ハム・ソーセージ",
    "25": "日配・チルド食品",
}


class AutoCsvInput_Belc(BaseBatch):
    """ベルク店舗HPにてCSVファイルをダウンロードし、レシート情報を自動登録するバッチクラス。"""

    def __init__(self, db_path=None):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path or None)
        self._validate_headers_functions = {}
        self._validate_body_functions = {}

    def validate_headers(self, request_dict):

        return super().validate_headers(request_dict)

    def validate_body(self, request_dict):
        # 既存のBaseRestApiバリデーションフローへ委譲する。
        return super().validate_body(request_dict)

    def main(self, request_dict: dict) -> dict:
    
        """
        Args:
            request_dict (Dict[str, Any]): 正規化済みのリクエストコンテキスト。

        Returns:
            Dict[str, Any]: 標準化されたAPIレスポンス。
        """
        headers= request_dict.get("headers", {})
        user_id= headers.get("x-kakeibo-user-id")

        request_info = self.get_request_info(user_id)
        if not request_info:
            raise RuntimeError("auto_csv_input_info configuration not found")

        history_URL = request_info.get("page_url_1")
        login_page_URL = request_info.get("page_url_2")
        login_post_URL = request_info.get("page_url_3")
        history_search_URL = request_info.get("page_url_4")

        login_email = request_info.get("login_id_1")
        login_password = request_info.get("login_pw_1")

        if not all([history_URL, login_page_URL, login_post_URL, history_search_URL, login_email, login_password]):
            raise RuntimeError("Belc auto CSV input configuration is incomplete")

        session = requests.Session()

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/148.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }


        login_page = self.request_belc(
            session,
            "GET",
            login_page_URL,
            headers=headers,
            operation_name="ログインページ取得",
        )

        soup = BeautifulSoup(login_page.text, "html.parser")

        payload = {}
        for inp in soup.find_all("input"):
            name = inp.get("name")
            if not name:
                continue

            input_type = (inp.get("type") or "").lower()

            if input_type == "hidden":
                payload[name] = inp.get("value", "")

        # ログイン情報をペイロードに追加
        payload.update({
            "LoginId": login_email,
            "Password": login_password,
        })


        # ログイン操作
        login_res = self.request_belc(
            session,
            "POST",
            login_post_URL,
            data=payload,
            headers={
                **headers,
                "Referer": login_page_URL,
                "Origin": "https://cust-bf.belc.jp",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            allow_redirects=True,
            operation_name="ログイン",
        )

        # ログイン後のクッキーを確認
        history_res = self.request_belc(
            session,
            "GET",
            history_URL,
            headers={
                **headers,
                "Referer": login_page_URL,
            },
            operation_name="購入履歴取得",
        )
        if "/mypage/Login" in history_res.url:
            raise RuntimeError("Login failed for Belc PurchaseHistory access")

        all_datetimes = self.get_all_purchase_datetimes(
            session,
            headers,
            history_URL,
            history_search_URL,
            first_html=history_res.text,
        )
        self.logger.info(f"all_datetimes (JP format): {all_datetimes}")
        
        # 日時だけでは同一分内の別レシートを区別できないため、全行のhidden値から一意キーを作る。
        all_purchase_rows = self.select_purchase_rows(
            session,
            headers,
            history_URL,
            history_search_URL,
            all_datetimes,
            first_html=history_res.text,
        )
        registered_records = self.get_registered_purchase_records(user_id)
        selected_checkboxes = [
            row for row in all_purchase_rows
            if not self.is_registered_purchase(row, registered_records)
        ]
        already_registered_count = len(all_purchase_rows) - len(selected_checkboxes)
        self.logger.info(
            "Belc purchase rows: total=%s, already_registered=%s, need_to_register=%s",
            len(all_purchase_rows),
            already_registered_count,
            len(selected_checkboxes),
        )
        self.logger.info(f"selected_checkboxes={self.summarize_selected_checkboxes(selected_checkboxes)}")

        # Process each selected receipt and register it
        registration_api = NewReceiptRegistration()
        ai_analyzer = GeminiReceiptAnalyzer(timeout=40)
        categories = self.load_receipt_categories(user_id)
        registered_count = 0
        failed_count = 0
        for checkbox_info in selected_checkboxes:
            try:
                receipt_detail_html = self.fetch_receipt_detail(
                    session,
                    headers,
                    checkbox_info,
                )
                receipt_info = self.parse_receipt_info(receipt_detail_html, user_id, checkbox_info)
                if not receipt_info.get("receiptDetails"):
                    self.save_debug_detail_html(receipt_detail_html, receipt_info)
                    raise RuntimeError(
                        "Belc receipt detail items were not found; skipped receipt registration "
                        f"for receiptNo={receipt_info.get('receiptNo')}, date={receipt_info.get('receiptDate')}."
                    )
                receipt_info = self.map_receipt_categories(
                    receipt_info=receipt_info,
                    categories=categories,
                    analyzer=ai_analyzer,
                )
                auth_token = set_current_user_id(user_id)
                try:
                    result = registration_api.call(
                        headers={"x-kakeibo-user-id": user_id, "Content-Type": "application/json"},
                        body={"receiptInfo": receipt_info},
                    )
                finally:
                    reset_current_user_id(auth_token)
                if int(result.get("statusCode", 500)) >= 400:
                    raise RuntimeError(f"Receipt registration failed: {result}")
                self.insert_auto_input_cont(receipt_info, user_id)
                self.logger.info(f"Receipt registered: {result}")
                registered_count += 1
            except Error:
                # 外部サービス障害は処理済み扱いにせず、呼び出し元へ返却する。
                raise
            except Exception as e:
                failed_count += 1
                self.logger.error(f"Failed to register receipt: {e}")

        return response(status_code=200, body={
            "totalFetched": len(all_purchase_rows),
            "alreadyRegistered": already_registered_count,
            "needToRegister": len(selected_checkboxes),
            "registered": registered_count,
            "failed": failed_count,
        })

    def request_belc(self, session, method: str, url: str, operation_name: str, **kwargs):
        """
        BelcサイトへのHTTP通信を実行し、一時的な障害の場合だけ再試行する。
        """
        kwargs.setdefault("timeout", 20)
        last_error = None

        for attempt in range(1, BELC_REQUEST_RETRY_COUNT + 1):
            try:
                result = session.request(method=method, url=url, **kwargs)
                if result.status_code not in BELC_RETRY_STATUS_CODES:
                    result.raise_for_status()
                    return result

                last_error = requests.HTTPError(
                    f"{result.status_code} Server Error for url: {url}",
                    response=result,
                )
                # Lambda側だけ失敗する場合に、WAF・ロードバランサー・アクセス制限を判別できる情報を残す。
                response_preview = " ".join((result.text or "")[:300].split())
                self.logger.warning(
                    "Belc通信一時エラー operation=%s status=%s attempt=%s/%s "
                    "response_url=%s server=%s via=%s retry_after=%s body=%s",
                    operation_name,
                    result.status_code,
                    attempt,
                    BELC_REQUEST_RETRY_COUNT,
                    result.url,
                    result.headers.get("Server", ""),
                    result.headers.get("Via", ""),
                    result.headers.get("Retry-After", ""),
                    response_preview,
                )
            except requests.RequestException as exc:
                last_error = exc
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code not in BELC_RETRY_STATUS_CODES and status_code is not None:
                    raise
                self.logger.warning(
                    "Belc通信失敗 operation=%s status=%s attempt=%s/%s error=%s",
                    operation_name,
                    status_code,
                    attempt,
                    BELC_REQUEST_RETRY_COUNT,
                    exc,
                )

            if attempt < BELC_REQUEST_RETRY_COUNT:
                # リトライ間隔を段階的に延ばし、外部サイトへの連続アクセスを避ける。
                time.sleep(BELC_REQUEST_RETRY_BACKOFF_SECONDS * attempt)

        self.logger.error(
            "Belc通信が再試行後も失敗しました operation=%s url=%s error=%s",
            operation_name,
            url,
            last_error,
        )
        raise Error(
            status_code=503,
            error_code="1000062",
            message="ベルクのサービスが一時的に利用できません。時間をおいて再実行してください。",
        )


    def exception(self, e: Exception) -> dict:
        """
            例外処理を行う。

            Args:
                e(Exception): 発生した例外。

            Returns:
                dict: REST APIのレスポンスとしてエラーコードを返す。
            """
        return super().exception(e)


    def extract_purchase_datetimes(self, html: str) -> list[str]:
        """
        購入履歴ページのHTMLから、購入日時のリストを抽出する。
         - 購入日時は、"2026年05月29日 11:01" のような形式で表示されていると仮定する。
         - 購入日時は、HTML内の特定のクラス名を持つ要素（例: <span class="mod-purchase-list__title">）に含まれていると仮定する。
         - 正規表現を用いて、購入日時の形式にマッチするテキストを抽出する。
         - 抽出した購入日時のリストを返す。
        """
        soup = BeautifulSoup(html, "html.parser")

        result = []

        for span in soup.select("span.mod-purchase-list__title"):
            text = span.get_text(strip=True)

            if re.match(r"^\d{4}年\d{2}月\d{2}日\s+\d{2}:\d{2}$", text):
                result.append(text)

        return result


    def extract_update_date(self, html: str) -> str | None:
        """
        ページ上部に表示される「最終更新日時」を抽出する。
        """
        soup = BeautifulSoup(html, "html.parser")

        elem = soup.select_one(".update-datetime")
        if not elem:
            return None

        return elem.get_text(strip=True)




    def extract_max_page(self, html: str) -> int:
        """
        分页区域から最大ページ数を抽出する。
        """
        soup = BeautifulSoup(html, "html.parser")

        max_page = 1

        for span in soup.select("ul.pager span"):
            text = span.get_text(strip=True)

            if text.isdigit():
                max_page = max(max_page, int(text))

        return max_page


    def extract_request_verification_token(self,html: str) -> str:
        """
        各ページの POST Search 時に必要な __RequestVerificationToken を抽出する。
        """
        soup = BeautifulSoup(html, "html.parser")

        token_input = soup.find("input", {"name": "__RequestVerificationToken"})
        if not token_input:
            raise RuntimeError("__RequestVerificationToken not found")

        return token_input["value"]


    def get_purchase_history_page(self, session, headers, history_URL: str, history_search_URL: str, page: int, current_html: str | None = None) -> str:
        """
        購入履歴の指定ページを取得する。
        - page: 取得したいページ番号
        - current_html: 既に取得しているHTML（最初のページを取得した後、次のページを取得する際に必要。最初のページはGETで
        """
        if page == 1 and current_html:
            return current_html

        if not current_html:
            raise RuntimeError("current_html is required to get token")

        token = self.extract_request_verification_token(current_html)

        payload = {
            "Page": str(page),
            "__RequestVerificationToken": token,
        }

        res = self.request_belc(
            session,
            "POST",
            history_search_URL,
            data=payload,
            headers={
                **headers,
                "Referer": history_URL,
                "Origin": "https://cust-bf.belc.jp",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            allow_redirects=True,
            operation_name=f"購入履歴ページ取得 page={page}",
        )

        if "/mypage/PurchaseHistory" not in res.url:
            raise RuntimeError(f"PurchaseHistory page access failed. url={res.url}")

        return res.text


    def get_all_purchase_datetimes(self, session, headers, history_URL: str, history_search_URL: str, first_html: str | None = None) -> list[str]:
        """
        購入履歴ページから全ての購入日時を取得する。

        args:
            - session: ログイン済みHTTPセッション。
            - headers (dict): リクエストヘッダー。
            - history_URL (str): 購入履歴ページURL。
            - history_search_URL (str): 購入履歴検索URL。
            - first_html (str | None): 取得済みの1ページ目HTML。
        returns:
            - list[str]: 全ページの購入日時。
        """
        if first_html is None:
            first_res = self.request_belc(
                session,
                "GET",
                history_URL,
                headers={
                    **headers,
                    "Referer": "https://cust-bf.belc.jp/mypage/Home",
                },
                allow_redirects=True,
                operation_name="購入履歴初期ページ取得",
            )
            if "/mypage/PurchaseHistory" not in first_res.url:
                raise RuntimeError(f"PurchaseHistory access failed. url={first_res.url}")
            first_html = first_res.text

        update_date = self.extract_update_date(first_html)
        max_page = self.extract_max_page(first_html) # 最大ページ数を取得

        print("update_date:", update_date)
        print("max_page:", max_page)

        all_datetimes = []

        current_html = first_html

        # 2. ページネーションに従って、2ページ目以降も取得
        for page in range(1, max_page + 1):
            print(f"fetch page: {page}")

            html = self.get_purchase_history_page(
                session=session,
                headers=headers,
                history_URL=history_URL,
                history_search_URL=history_search_URL,
                page=page,
                current_html=current_html,
            )

            page_datetimes = self.extract_purchase_datetimes(html)

            print(f"page {page} datetimes:", page_datetimes)

            all_datetimes.extend(page_datetimes)

            # 次ページの検証トークンとして直前のHTMLを使用する。
            current_html = html

        return all_datetimes

    def find_matching_checkboxes(self, html: str, target_datetimes: list[str]) -> list[dict]:
        """
        HTMLから対象日時に一致するチェックボックスのnameとvalueを取得する。
        target_datetimes は日本文本形式であることを想定: "2026年05月29日 11:01"
        """
        soup = BeautifulSoup(html, "html.parser")
        target_texts = set(target_datetimes)

        matches = []
        all_checkboxes = soup.find_all("input", {"type": "checkbox"})
        self.logger.info(f"Found {len(all_checkboxes)} total checkboxes")
        
        for idx, checkbox in enumerate(all_checkboxes):
            # Note: Some checkboxes may have id instead of name
            name = checkbox.get("name")
            value = checkbox.get("value")
            checkbox_id = checkbox.get("id")
            
            # Use id or name for identification
            identifier = name or checkbox_id
            
            if not identifier or not value:
                continue

            form = checkbox.find_parent("form")
            container = form or checkbox.find_parent(["tr", "li", "div", "label"]) or checkbox
            row_text = " ".join(container.get_text(" ", strip=True).split())
            
            # Debug logging - show matches
            if any(target in row_text for target in target_texts):
                self.logger.info(f"Matched checkbox {idx}: id={checkbox_id}, name={name}, value={value}")
                self.logger.info(f"  Row text: {row_text[:150]}")
                form_data = {}
                if form:
                    for inp in form.find_all("input"):
                        input_name = inp.get("name")
                        if input_name:
                            form_data[input_name] = inp.get("value", "")

                matches.append({
                    "name": name,
                    "id": checkbox_id,
                    "value": value,
                    "row_text": row_text,
                    "detail_url": form.get("action") if form else "",
                    "form_data": form_data,
                })

        self.logger.info(f"Matched {len(matches)} checkboxes out of {len(all_checkboxes)}")
        return matches

    def summarize_selected_checkboxes(self, selected_checkboxes: list[dict]) -> list[dict]:
        """
        ログ出力用に、CSRF tokenなどの値を含めず選択結果を要約する。
        """
        summaries = []
        for item in selected_checkboxes:
            form_data = item.get("form_data") or {}
            summaries.append({
                "id": item.get("id"),
                "value": item.get("value"),
                "row_text": item.get("row_text"),
                "detail_url": item.get("detail_url"),
                "form_fields": list(form_data.keys()),
            })
        return summaries

    def format_datetime_for_page(self, datetime_iso: str) -> str:
        """
        ISOフォーマットの日付をページ表示用の和文日付に変換する。
        """
        try:
            dt = datetime.fromisoformat(datetime_iso)
            return dt.strftime("%Y年%m月%d日 %H:%M")
        except ValueError:
            return datetime_iso

    def take_datetimes_to_list(self, datetimes: list[str]) -> list[str]:
        """
        取得した購入日時のリストを、さらに加工してリスト化する。
        例えば、"2026年05月29日 11:01" という文字列を "2026-05-29T11:01:00" のようなISOフォーマットに変換する。
        """
        result = []

        for dt in datetimes:
            match = re.match(r"^(\d{4})年(\d{2})月(\d{2})日\s+(\d{2}):(\d{2})$", dt)
            if not match:
                continue

            year, month, day, hour, minute = match.groups()
            iso_dt = f"{year}-{month}-{day}T{hour}:{minute}:00"
            result.append(iso_dt)

        return result

    def get_request_info(self, user_id: str) -> dict | None:
        """
        リクエスト情報を取得する。
        """
        sql = self.database.read_sql("SELECT_AUTO_CSV_INPUT_INFO", __file__)
        params = {
            "INV_REG_NUM": BELC_INVOICE_NUMBER,
            "CRE_USER_ID": user_id
        }
        result = self.database.select(sql, params)
        row = result[0] if result else None
        if not row:
            return None

        return result[0]

    def get_registered_purchase_records(self, user_id: str) -> dict:
        """
        登録済みBelcレシートの一意キーと、旧データ互換用の日時・レシート番号を取得する。
        """
        sql = self.database.read_sql("SELECT_AUTO_CSV_INPUT_CONT", __file__)
        params = {
            "INV_REG_NUM": BELC_INVOICE_NUMBER,
            "CRE_USER_ID": user_id,
            "AUTO_INPUT_STATUS": AUTO_INPUT_STATUS_REGISTERED # 登録済みのレコードのみ取得
        }
        result = self.database.select(sql, params)
        source_keys = set()
        legacy_keys = set()
        for row in result:
            source_key = str(row.get("SOURCE_KEY") or row.get("source_key") or "").strip()
            if source_key:
                source_keys.add(source_key)
            date_text = self.normalize_auto_input_date(row.get("RET_DT") or row.get("ret_dt"))
            time_text = self.normalize_auto_input_time(row.get("RET_TM") or row.get("ret_tm"))
            receipt_no = str(row.get("RET_CONT") or row.get("ret_cont") or "").strip()
            if date_text and time_text and receipt_no:
                legacy_keys.add((date_text, time_text, receipt_no))
        return {"sourceKeys": source_keys, "legacyKeys": legacy_keys}

    def purchase_source_key(self, checkbox_info: dict) -> str:
        """
        Belcの店舗・POS・日付・レシート番号から安定した一意キーを作る。
        """
        form_data = checkbox_info.get("form_data") or {}
        date_digits = re.sub(r"\D", "", str(form_data.get("Date") or ""))[:8]
        parts = [
            str(form_data.get("StoreCode") or "").strip(),
            str(form_data.get("PosNo") or "").strip(),
            date_digits,
            str(form_data.get("ReceiptNo") or "").strip(),
        ]
        if not all(parts):
            return ""
        return f"BELC:{':'.join(parts)}"

    def purchase_legacy_key(self, checkbox_info: dict) -> tuple[str, str, str] | None:
        """
        SOURCE_KEY導入前のレコードと比較するため、購入日時とレシート番号を取り出す。
        """
        form_data = checkbox_info.get("form_data") or {}
        receipt_no = str(form_data.get("ReceiptNo") or "").strip()
        receipt_datetime = self.extract_receipt_datetime(checkbox_info.get("row_text") or "")
        if not receipt_no or not receipt_datetime:
            return None
        return (
            receipt_datetime.strftime("%Y%m%d"),
            receipt_datetime.strftime("%H%M%S"),
            receipt_no,
        )

    def is_registered_purchase(self, checkbox_info: dict, registered_records: dict) -> bool:
        """
        新一意キーを優先し、旧レコードは日時・レシート番号で重複判定する。
        """
        source_key = self.purchase_source_key(checkbox_info)
        if source_key and source_key in registered_records.get("sourceKeys", set()):
            return True
        legacy_key = self.purchase_legacy_key(checkbox_info)
        return bool(legacy_key and legacy_key in registered_records.get("legacyKeys", set()))

    def insert_auto_input_cont(self, receipt_info: dict, user_id: str) -> None:
        """
        自動登録済みの購入日時を記録し、次回以降の重複登録を防ぐ。
        """
        receipt_date = self.normalize_auto_input_date(receipt_info.get("receiptDate"))
        receipt_time = self.normalize_auto_input_time(receipt_info.get("receiptTime"))
        if not receipt_date or not receipt_time:
            self.logger.warning(f"Skipped auto_csv_input_cont insert because receipt date/time is empty: {receipt_info}")
            return

        sql = self.database.read_sql("INSERT_AUTO_CSV_INPUT_CONT", __file__)
        params = {
            "CRE_PROG": self.__class__.__name__,
            "UPD_PROG": self.__class__.__name__,
            "INV_REG_NUM": receipt_info.get("invoiceRegistrationNumber") or BELC_INVOICE_NUMBER,
            "RET_CONT": receipt_info.get("receiptNo") or receipt_info.get("supplierName") or "",
            "RET_DT": receipt_date,
            "RET_TM": receipt_time,
            "AUTO_INPUT_STATUS": AUTO_INPUT_STATUS_REGISTERED,
            "CONNECTION_TYPE": "BELC",
            "SOURCE_KEY": self.purchase_source_key({
                "form_data": {
                    "StoreCode": receipt_info.get("storeCode"),
                    "PosNo": receipt_info.get("posNo"),
                    "Date": receipt_date,
                    "ReceiptNo": receipt_info.get("receiptNo"),
                }
            }),
            "CRE_DT": datetime.now().strftime("%Y%m%d"),
            "CRE_TM": datetime.now().strftime("%H%M%S"),
            "UPD_DT": datetime.now().strftime("%Y%m%d"),
            "UPD_TM": datetime.now().strftime("%H%M%S"),
            "USER_ID": user_id,
            "DEL_FLAG": 0,
        }
        inserted = self.database.insert(sql, params)
        self.logger.info(
            f"auto_csv_input_cont registered: inserted={inserted}, inv={params['INV_REG_NUM']}, ret_dt={receipt_date}, ret_tm={receipt_time}"
        )

    def load_receipt_categories(self, user_id: str) -> dict:
        """
        AI分類に渡す家計簿側のカテゴリマスタを取得する。
        """
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

    def map_receipt_categories(self, receipt_info: dict, categories: dict, analyzer: GeminiReceiptAnalyzer) -> dict:
        """
        Belc側カテゴリを家計簿カテゴリへ変換し、商品明細へ反映する。
        """
        if not (categories.get("category2") if isinstance(categories, dict) else None):
            raise RuntimeError("receipt category master is empty; skipped AI category mapping.")

        # 先にローカルでカテゴリ名同士を照合し、AIへ渡すカテゴリ数を減らす。
        category_map = self.build_local_belc_category_map(receipt_info, categories)
        unresolved_categories = self.find_unresolved_belc_categories(receipt_info, category_map)
        if unresolved_categories:
            category_map.update(self.map_unresolved_belc_categories_with_ai(
                belc_categories=unresolved_categories,
                categories=categories,
                analyzer=analyzer,
            ))

        return self.apply_belc_category_map(receipt_info, category_map)

    def build_local_belc_category_map(self, receipt_info: dict, categories: dict) -> dict:
        """
        Belcカテゴリ名と家計簿カテゴリ名をローカルで照合する。
        """
        category_map = {}
        for belc_category in self.extract_unique_belc_categories(receipt_info):
            matched = self.find_local_category_match(belc_category, categories)
            if matched:
                category_map[self.belc_category_key(belc_category)] = matched
        return category_map

    def map_unresolved_belc_categories_with_ai(self, belc_categories: list[dict], categories: dict, analyzer: GeminiReceiptAnalyzer) -> dict:
        """
        ローカル照合できなかったBelcカテゴリだけをAIへ渡して対応表を作る。
        """
        prompt = build_category_pair_mapping_prompt(categories)
        input_categories = [
            {
                "belcCategoryCode": item.get("code") or "",
                "belcCategoryName": item.get("name") or "",
            }
            for item in belc_categories
        ]
        input_text = json.dumps({"belcCategories": input_categories}, ensure_ascii=False)
        parsed = analyzer.analyze_json_with_prompt(
            text=input_text,
            prompt=prompt,
            label="Belcカテゴリ一覧",
        )
        status_code = int(parsed.get("statusCode", 500)) if isinstance(parsed, dict) else 500
        if status_code >= 400:
            raise RuntimeError(f"AI category mapping failed: {parsed}")

        mapped_body = parsed.get("body") if isinstance(parsed, dict) else {}
        mappings = mapped_body.get("mappings") if isinstance(mapped_body, dict) else None
        if not isinstance(mappings, list) or not mappings:
            raise RuntimeError(f"AI category mapping returned no mappings: {parsed}")

        result = {}
        valid_pairs = self.category_pair_map(categories)
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            belc_category = {
                "code": str(mapping.get("belcCategoryCode") or ""),
                "name": str(mapping.get("belcCategoryName") or ""),
            }
            category1 = clean_category_label(mapping.get("category1"))
            category2 = clean_category_label(mapping.get("category2"))
            pair_key = (category1, category2)
            if pair_key not in valid_pairs:
                raise RuntimeError(f"AI category mapping returned unknown category: {mapping}")
            result[self.belc_category_key(belc_category)] = {
                "category1": category1,
                "category2": category2,
                "taxRate": normalize_tax_rate(mapping.get("taxRate") or valid_pairs[pair_key].get("taxRate")),
            }
        return result

    def apply_belc_category_map(self, receipt_info: dict, category_map: dict) -> dict:
        """
        Belcカテゴリ対応表を各商品明細へ適用する。
        """
        result = dict(receipt_info)
        details = []
        for detail in receipt_info.get("receiptDetails") or []:
            next_detail = dict(detail)
            belc_category = {
                "code": str(next_detail.get("belcCategoryCode") or ""),
                "name": str(next_detail.get("belcCategoryName") or ""),
            }
            mapped = category_map.get(self.belc_category_key(belc_category))
            if not mapped:
                raise RuntimeError(f"Belc category mapping not found: {belc_category}")
            next_detail["category1"] = mapped.get("category1")
            next_detail["category2"] = mapped.get("category2")
            next_detail["taxRate"] = mapped.get("taxRate")
            details.append(next_detail)

        result["receiptDetails"] = details
        result["receiptDetailCount"] = len(details)
        return result

    def extract_unique_belc_categories(self, receipt_info: dict) -> list[dict]:
        """
        レシート明細に含まれるBelcカテゴリを重複なしで取り出す。
        """
        result = []
        seen = set()
        for detail in receipt_info.get("receiptDetails") or []:
            belc_category = {
                "code": str(detail.get("belcCategoryCode") or ""),
                "name": str(detail.get("belcCategoryName") or ""),
            }
            key = self.belc_category_key(belc_category)
            if key in seen:
                continue
            seen.add(key)
            result.append(belc_category)
        return result

    def find_unresolved_belc_categories(self, receipt_info: dict, category_map: dict) -> list[dict]:
        """
        ローカル照合で解決できなかったBelcカテゴリだけを抽出する。
        """
        return [
            belc_category
            for belc_category in self.extract_unique_belc_categories(receipt_info)
            if self.belc_category_key(belc_category) not in category_map
        ]

    def find_local_category_match(self, belc_category: dict, categories: dict) -> dict | None:
        """
        Belcカテゴリ名と家計簿カテゴリ名を、完全一致・部分一致の順に照合する。
        """
        belc_name = belc_category.get("name") or ""
        if not belc_name:
            return None

        category_rows = self.category_rows(categories)
        belc_key = self.normalize_category_match_text(belc_name)
        exact_matches = []
        partial_matches = []
        for row in category_rows:
            category1_key = self.normalize_category_match_text(row.get("category1"))
            category2_key = self.normalize_category_match_text(row.get("category2"))
            if belc_key and belc_key == category2_key:
                exact_matches.append(row)
            elif belc_key and belc_key == category1_key:
                exact_matches.append(row)
            elif belc_key and (belc_key in category2_key or category2_key in belc_key):
                partial_matches.append(row)
            elif belc_key and (belc_key in category1_key or category1_key in belc_key):
                partial_matches.append(row)

        matched = exact_matches[0] if exact_matches else partial_matches[0] if partial_matches else None
        if not matched:
            return None
        return {
            "category1": matched.get("category1"),
            "category2": matched.get("category2"),
            "taxRate": normalize_tax_rate(matched.get("taxRate")),
        }

    def category_rows(self, categories: dict) -> list[dict]:
        """
        DB行の大文字キーを扱いやすい形式へ正規化する。
        """
        rows = []
        for item in categories.get("category2") or []:
            if not isinstance(item, dict):
                continue
            category1 = clean_category_label(item.get("CATEGORY1_NAME") or item.get("category1Name"))
            category2 = clean_category_label(item.get("CATEGORY2_NAME") or item.get("category2Name"))
            if not category1 or not category2:
                continue
            rows.append({
                "category1": category1,
                "category2": category2,
                "taxRate": item.get("TAX_RATE") if item.get("TAX_RATE") is not None else item.get("taxRate"),
            })
        return rows

    def category_pair_map(self, categories: dict) -> dict:
        """
        AI結果検証用に、存在する家計簿カテゴリのペアを作る。
        """
        return {
            (row.get("category1"), row.get("category2")): row
            for row in self.category_rows(categories)
        }

    def belc_category_key(self, belc_category: dict) -> str:
        """
        Belcカテゴリコードと名称から対応表用キーを作る。
        """
        return f"{belc_category.get('code') or ''}:{belc_category.get('name') or ''}"

    def normalize_category_match_text(self, value) -> str:
        """
        カテゴリ名照合用に空白・記号を取り除く。
        """
        return re.sub(r"[\s\u3000・･/／\-ー_]+", "", str(value or "").lower())

    def merge_ai_mapped_receipt_info(self, original: dict, mapped: dict) -> dict:
        """
        AI分類結果を反映しつつ、Belcから確定取得したヘッダ・金額情報を保持する。
        """
        result = dict(original)
        mapped_details = mapped.get("receiptDetails") or []
        original_details = original.get("receiptDetails") or []

        details = []
        for idx, mapped_detail in enumerate(mapped_details):
            base_detail = dict(original_details[idx]) if idx < len(original_details) and isinstance(original_details[idx], dict) else {}
            base_detail.update({
                "category1": mapped_detail.get("category1") or base_detail.get("category1"),
                "category2": mapped_detail.get("category2") or base_detail.get("category2"),
                "taxRate": mapped_detail.get("taxRate") if mapped_detail.get("taxRate") is not None else base_detail.get("taxRate"),
            })
            details.append(base_detail)

        result["receiptDetails"] = details
        result["receiptDetailCount"] = len(details)
        for key in (
            "userId",
            "invoiceRegistrationNumber",
            "supplierName",
            "storeName",
            "storeCode",
            "posNo",
            "receiptNo",
            "receiptDate",
            "receiptTime",
            "taxFlag",
            "totalPrice",
            "supplierImage",
        ):
            result[key] = original.get(key)
        return result

    def normalize_auto_input_date(self, value) -> str:
        """
        YYYY-MM-DD / YYYYMMDD を auto_csv_input_cont 用の YYYYMMDD にそろえる。
        """
        raw = str(value or "").strip()
        if re.fullmatch(r"\d{8}", raw):
            return raw
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return raw.replace("-", "")
        return ""

    def normalize_auto_input_time(self, value) -> str:
        """
        HH:MM / HH:MM:SS / HHMMSS / HHMM を auto_csv_input_cont 用の HHMMSS にそろえる。
        """
        raw = str(value or "").strip()
        if re.fullmatch(r"\d{6}", raw):
            return raw
        if re.fullmatch(r"\d{4}", raw):
            return f"{raw}00"
        match = re.fullmatch(r"(\d{2}):(\d{2})(?::(\d{2}))?", raw)
        if match:
            hour, minute, second = match.groups()
            return f"{hour}{minute}{second or '00'}"
        return ""

    def auto_input_datetime_to_iso(self, date_value, time_value) -> str:
        """
        auto_csv_input_cont の RET_DT/RET_TM を購入履歴比較用の ISO 文字列に変換する。
        """
        date_text = self.normalize_auto_input_date(date_value)
        time_text = self.normalize_auto_input_time(time_value)
        if not date_text or not time_text:
            return ""
        return f"{date_text[0:4]}-{date_text[4:6]}-{date_text[6:8]}T{time_text[0:2]}:{time_text[2:4]}:{time_text[4:6]}"

    def fetch_receipt_detail(self, session, headers, checkbox_info: dict) -> str:
        """
        チェックボックス情報に基づいて、明細ページを取得する。
        """
        detail_url = urljoin(
            "https://cust-bf.belc.jp",
            checkbox_info.get("detail_url") or "/mypage/PurchaseHistory?handler=Detail",
        )

        form_data = dict(checkbox_info.get("form_data") or {})
        checkbox_name = checkbox_info.get("name")
        if checkbox_name:
            form_data[checkbox_name] = checkbox_info.get("value", "")

        if not form_data:
            raise RuntimeError(f"Belc receipt detail form fields not found: {checkbox_info}")
        
        response = self.request_belc(
            session,
            "POST",
            detail_url,
            data=form_data,
            headers={
                **headers,
                "Referer": "https://cust-bf.belc.jp/mypage/PurchaseHistory",
                "Origin": "https://cust-bf.belc.jp",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            allow_redirects=True,
            operation_name=f"購入明細取得 receiptNo={form_data.get('ReceiptNo', '')}",
        )
        return response.text

    def parse_receipt_info(self, detail_html: str, user_id: str, checkbox_info: dict | None = None) -> dict:
        """
        明細ページのHTMLから、receiptInfoを構築する。
        """
        soup = BeautifulSoup(detail_html, "html.parser")
        checkbox_info = checkbox_info or {}
        form_data = checkbox_info.get("form_data") or {}
        row_text = checkbox_info.get("row_text") or ""
        store_name = self.extract_store_name(row_text)
        receipt_datetime = self.extract_receipt_datetime(row_text)
        receipt_total = self.extract_total_price(row_text)
        
        receipt_info = {
            "userId": user_id,
            "invoiceRegistrationNumber": BELC_INVOICE_NUMBER,
            "supplierName": f"{BELC_SUPPLIER_NAME} {store_name}" if store_name else BELC_SUPPLIER_NAME,
            "storeName": store_name,
            "storeCode": form_data.get("StoreCode", ""),
            "posNo": form_data.get("PosNo", ""),
            "receiptNo": form_data.get("ReceiptNo", ""),
            "receiptDate": "",
            "receiptTime": "",
            "taxFlag": 0,
            "receiptDetailCount": 0,
            "receiptDetails": [],
            "totalPrice": receipt_total,
            "supplierImage": None,
        }
        
        if receipt_datetime:
            receipt_info["receiptDate"] = receipt_datetime.strftime("%Y-%m-%d")
            receipt_info["receiptTime"] = receipt_datetime.strftime("%H:%M")

        if form_data.get("Date") and not receipt_info["receiptDate"]:
            date_str = str(form_data.get("Date", ""))
            if len(date_str) == 8:
                receipt_info["receiptDate"] = f"{date_str[0:4]}-{date_str[4:6]}-{date_str[6:8]}"

        # Extract date from hidden inputs
        date_input = soup.select_one("input[name='Date']")
        if date_input and not receipt_info["receiptDate"]:
            date_str = date_input.get("value", "")
            if len(date_str) == 8:
                receipt_info["receiptDate"] = f"{date_str[0:4]}-{date_str[4:6]}-{date_str[6:8]}"
        
        # Extract receipt details (product items)
        receipt_details = self.extract_receipt_details(soup)
        
        receipt_info["receiptDetails"] = receipt_details
        receipt_info["receiptDetailCount"] = len(receipt_details)
        if not receipt_info["totalPrice"]:
            receipt_info["totalPrice"] = sum(detail.get("totalPrice", 0) for detail in receipt_details)
        
        return receipt_info

    def extract_receipt_details(self, soup: BeautifulSoup) -> list[dict]:
        """
        Belc明細HTMLから商品明細を抽出する。
        """
        receipt_details = self.extract_belc_itemlist_details(soup)
        if receipt_details:
            return receipt_details

        receipt_details = self.extract_receipt_details_by_known_selectors(soup)
        if receipt_details:
            return receipt_details

        receipt_details = self.extract_receipt_details_from_tables(soup)
        if receipt_details:
            return receipt_details

        return self.extract_receipt_details_from_text(soup)

    def extract_belc_itemlist_details(self, soup: BeautifulSoup) -> list[dict]:
        """
        Belcのお買い物履歴明細ページの購入商品ブロックを抽出する。
        """
        receipt_details = []
        for block in soup.select(".mod-confirm__itemlist-block"):
            name_elem = block.select_one(".mod-confirm__itemlist-detail-name")
            if not name_elem:
                continue

            raw_name = name_elem.get_text(" ", strip=True)
            belc_category = self.extract_belc_category(raw_name)
            item_name = self.clean_belc_item_name(raw_name)
            if not item_name:
                continue

            price_elem = self.find_belc_item_price_element(block, name_elem)
            line_price = self.parse_amount(price_elem.get_text(" ", strip=True) if price_elem else "")
            quantity_elem = block.select_one(".mod-confirm__itemlist-detail-number")
            quantity = self.parse_quantity(quantity_elem.get_text(" ", strip=True) if quantity_elem else "")
            discount_elem = block.select_one(".mod-confirm__price-content-discount")
            discount = abs(self.parse_signed_amount(discount_elem.get_text(" ", strip=True) if discount_elem else ""))

            total_price = max(line_price - discount, 0)
            if line_price <= 0 or total_price <= 0:
                continue

            receipt_details.append({
                **self.build_receipt_detail(
                    item_name=item_name,
                    quantity=quantity,
                    unit_price=int(round(line_price / quantity)) if quantity else line_price,
                    total_price=total_price,
                ),
                "discount": discount,
                "taxRate": 0.08 if "*" in raw_name else 0.1,
                "belcCategoryCode": belc_category.get("code"),
                "belcCategoryName": belc_category.get("name"),
            })
        return receipt_details

    def extract_belc_category(self, value: str) -> dict:
        """
        Belcの商品名先頭に付く部門コードをAI分類用の参考情報として抽出する。
        """
        text = self.clean_cell_text(value).replace("*", "").strip()
        match = re.match(r"^(\d{2})\s+", text)
        if not match:
            return {"code": "", "name": ""}
        code = match.group(1)
        return {
            "code": code,
            "name": BELC_CATEGORY_NAMES.get(code, ""),
        }

    def clean_belc_item_name(self, value: str) -> str:
        """
        Belc明細の商品名から軽減税率記号や部門コードを取り除く。
        """
        text = self.clean_cell_text(value)
        text = text.replace("*", "").strip()
        text = re.sub(r"^\d{2}\s+", "", text)
        return text.strip()

    def find_belc_item_price_element(self, block, name_elem):
        """
        商品名の直後にある価格spanを取得する。
        """
        for elem in name_elem.find_all_next(["span", "div"]):
            if block not in elem.parents:
                break
            classes = elem.get("class") or []
            if "mod-confirm__itemlist-detail-symbol" in classes:
                continue
            if "mod-confirm__itemlist-detail-number" in classes:
                continue
            if "mod-confirm__price-content-discount" in classes:
                continue
            text = elem.get_text(" ", strip=True)
            if re.search(r"[0-9,]+円", text):
                return elem
        return None

    def extract_receipt_details_by_known_selectors(self, soup: BeautifulSoup) -> list[dict]:
        """
        class/data属性が付いている明細行を抽出する。
        """
        receipt_details = []
        for row in soup.select("tr[data-item], .receipt-detail-row, .detail-row, .item-row"):
            item_name = row.select_one(".item-name, [data-item-name], .product-name, .goods-name")
            quantity = row.select_one(".quantity, [data-quantity], .qty")
            unit_price = row.select_one(".unit-price, [data-unit-price], .price")
            total_price = row.select_one(".total-price, [data-total-price], .amount")

            if item_name and total_price:
                unit_price_value = self.parse_amount(unit_price.get_text(strip=True) if unit_price else total_price.get_text(strip=True))
                total_price_value = self.parse_amount(total_price.get_text(strip=True))
                if total_price_value <= 0:
                    continue
                receipt_details.append(self.build_receipt_detail(
                    item_name=item_name.get_text(" ", strip=True),
                    quantity=self.parse_quantity(quantity.get_text(strip=True) if quantity else ""),
                    unit_price=unit_price_value or total_price_value,
                    total_price=total_price_value,
                ))
        return receipt_details

    def extract_receipt_details_from_tables(self, soup: BeautifulSoup) -> list[dict]:
        """
        HTML table の列名や位置から商品明細を抽出する。
        """
        receipt_details = []
        for table in soup.find_all("table"):
            headers = self.extract_table_headers(table)
            for row in table.find_all("tr"):
                cells = [self.clean_cell_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
                cells = [cell for cell in cells if cell]
                if len(cells) < 2 or self.is_header_row(cells) or self.is_summary_row(cells):
                    continue

                detail = self.detail_from_cells(cells, headers)
                if detail:
                    receipt_details.append(detail)
        return receipt_details

    def extract_receipt_details_from_text(self, soup: BeautifulSoup) -> list[dict]:
        """
        最後の手段として、本文の1行から「商品名 金額」を推定する。
        """
        receipt_details = []
        lines = [self.clean_cell_text(line) for line in soup.get_text("\n", strip=True).splitlines()]
        for line in lines:
            if not line or self.is_summary_row([line]):
                continue
            match = re.match(r"^(.+?)\s+([0-9,]+)円?$", line)
            if not match:
                continue
            item_name = match.group(1).strip()
            total_price = self.parse_amount(match.group(2))
            if not item_name or total_price <= 0:
                continue
            receipt_details.append(self.build_receipt_detail(item_name, 1, total_price, total_price))
        return receipt_details

    def extract_table_headers(self, table) -> list[str]:
        """
        table の見出し行を抽出する。
        """
        for row in table.find_all("tr"):
            headers = [self.clean_cell_text(cell.get_text(" ", strip=True)) for cell in row.find_all("th")]
            headers = [header for header in headers if header]
            if headers:
                return headers
        return []

    def detail_from_cells(self, cells: list[str], headers: list[str]) -> dict | None:
        """
        表のセル配列から商品明細を1件作る。
        """
        item_name = self.pick_item_name(cells, headers)
        total_price = self.pick_total_price(cells, headers)
        quantity = self.pick_quantity(cells, headers)
        unit_price = self.pick_unit_price(cells, headers, total_price, quantity)

        if not item_name or total_price <= 0:
            return None
        return self.build_receipt_detail(item_name, quantity, unit_price, total_price)

    def pick_item_name(self, cells: list[str], headers: list[str]) -> str:
        item_header_indexes = [
            idx for idx, header in enumerate(headers)
            if any(keyword in header for keyword in ("商品", "品名", "名称", "明細"))
        ]
        for idx in item_header_indexes:
            if idx < len(cells):
                return cells[idx]

        for cell in cells:
            if self.parse_amount(cell) == 0 and not re.fullmatch(r"\d+(\.\d+)?", cell):
                return cell
        return cells[0] if cells else ""

    def pick_total_price(self, cells: list[str], headers: list[str]) -> int:
        total_header_indexes = [
            idx for idx, header in enumerate(headers)
            if any(keyword in header for keyword in ("金額", "合計", "小計"))
        ]
        for idx in reversed(total_header_indexes):
            if idx < len(cells):
                amount = self.parse_amount(cells[idx])
                if amount:
                    return amount

        amounts = [self.parse_amount(cell) for cell in cells]
        amounts = [amount for amount in amounts if amount]
        return amounts[-1] if amounts else 0

    def pick_quantity(self, cells: list[str], headers: list[str]) -> float:
        quantity_header_indexes = [
            idx for idx, header in enumerate(headers)
            if any(keyword in header for keyword in ("数量", "点数", "個数"))
        ]
        for idx in quantity_header_indexes:
            if idx < len(cells):
                quantity = self.parse_quantity(cells[idx])
                if quantity:
                    return quantity
        return 1

    def pick_unit_price(self, cells: list[str], headers: list[str], total_price: int, quantity: float) -> int:
        unit_header_indexes = [
            idx for idx, header in enumerate(headers)
            if any(keyword in header for keyword in ("単価", "価格"))
        ]
        for idx in unit_header_indexes:
            if idx < len(cells):
                amount = self.parse_amount(cells[idx])
                if amount:
                    return amount

        amounts = [self.parse_amount(cell) for cell in cells]
        amounts = [amount for amount in amounts if amount]
        if len(amounts) >= 2:
            return amounts[-2]
        return int(round(total_price / quantity)) if quantity else total_price

    def build_receipt_detail(self, item_name: str, quantity: float, unit_price: int, total_price: int) -> dict:
        return {
            "itemName": item_name,
            "category1": "その他",
            "category2": "その他",
            "taxRate": 10,
            "quantity": quantity or 1,
            "unit": "個",
            "unitPrice": unit_price,
            "discount": 0,
            "totalPrice": total_price,
        }

    def parse_amount(self, value) -> int:
        raw = str(value or "").strip()
        match = re.search(r"-?[0-9][0-9,]*", raw)
        if not match:
            return 0
        return abs(int(match.group(0).replace(",", "")))

    def parse_signed_amount(self, value) -> int:
        raw = str(value or "").strip()
        match = re.search(r"-?[0-9][0-9,]*", raw)
        if not match:
            return 0
        return int(match.group(0).replace(",", ""))

    def parse_quantity(self, value) -> float:
        raw = str(value or "").strip()
        match = re.search(r"\d+(?:\.\d+)?", raw)
        if not match:
            return 1
        return float(match.group(0))

    def clean_cell_text(self, value: str) -> str:
        return " ".join(str(value or "").replace("\u3000", " ").split())

    def is_header_row(self, cells: list[str]) -> bool:
        joined = " ".join(cells)
        return bool(cells) and any(keyword in joined for keyword in ("商品", "品名", "数量", "単価", "金額")) and not any(self.parse_amount(cell) for cell in cells)

    def is_summary_row(self, cells: list[str]) -> bool:
        joined = " ".join(cells)
        return any(keyword in joined for keyword in (
            "合計", "小計", "総計", "消費税", "税額", "対象", "ポイント",
            "お預り", "お釣", "おつり", "レシートNo", "店舗購入", "獲得"
        ))

    def save_debug_detail_html(self, detail_html: str, receipt_info: dict) -> None:
        """
        明細解析に失敗したHTMLを保存する。
        """
        debug_dir = Path(__file__).resolve().parents[3] / "log" / "belc_debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        receipt_no = re.sub(r"[^0-9A-Za-z_-]", "_", str(receipt_info.get("receiptNo") or "unknown"))
        receipt_date = re.sub(r"[^0-9A-Za-z_-]", "_", str(receipt_info.get("receiptDate") or "unknown"))
        path = debug_dir / f"detail_{receipt_date}_{receipt_no}.html"
        path.write_text(detail_html, encoding="utf-8")
        self.logger.warning(f"Saved Belc detail HTML for selector debugging: {path}")

    def extract_store_name(self, row_text: str) -> str:
        """
        購入履歴行テキストから店舗名を取り出す。
        """
        match = re.search(r"\d{4}年\d{2}月\d{2}日\s+\d{2}:\d{2}\s+(.+?)(?:\s+店舗購入|\s+レシートNo：|$)", row_text)
        return match.group(1).strip() if match else ""

    def extract_receipt_datetime(self, row_text: str) -> datetime | None:
        """
        購入履歴行テキストから購入日時を取り出す。
        """
        match = re.search(r"(\d{4})年(\d{2})月(\d{2})日\s+(\d{2}):(\d{2})", row_text)
        if not match:
            return None
        year, month, day, hour, minute = map(int, match.groups())
        return datetime(year, month, day, hour, minute)

    def extract_total_price(self, row_text: str) -> int:
        """
        購入履歴行テキストから合計金額を取り出す。
        """
        match = re.search(r"合計金額：\s*([0-9,]+)円", row_text)
        return int(match.group(1).replace(",", "")) if match else 0

    def select_purchase_rows(self, session, headers, history_URL: str, history_search_URL: str, target_datetimes: list[str], first_html: str) -> list[dict]:
        """
        全ページを検索して対象日付に一致するチェックボックスを見つける。
        """
        selected_checkboxes = []
        page = 1
        max_page = 1
        current_html = first_html
        
        self.logger.info(f"Looking for {len(target_datetimes)} target datetimes: {target_datetimes}")
        
        while page <= max_page:
            if page == 1:
                html = first_html
            else:
                html = self.get_purchase_history_page(session, headers, history_URL, history_search_URL, page, current_html)
            
            # Extract max_page from first page
            if page == 1:
                soup = BeautifulSoup(html, "html.parser")
                pagination = soup.select_one(".pagination, .paging, [data-max-page]")
                if pagination and pagination.get("data-max-page"):
                    max_page = int(pagination.get("data-max-page"))
                else:
                    max_page = self.extract_max_page(html)
                self.logger.info(f"max_page={max_page}")
            
            # Find matching checkboxes on current page
            self.logger.info(f"Searching for matches on page {page}")
            matches = self.find_matching_checkboxes(html, target_datetimes)
            selected_checkboxes.extend(matches)

            # 次ページの検証トークンとして直前のHTMLを使用する。
            current_html = html
            page += 1
        
        self.logger.info(f"Total matches found: {len(selected_checkboxes)}")
        return selected_checkboxes
