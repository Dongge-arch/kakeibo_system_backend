# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""ETC利用照会サービスの利用明細を自動入力する。"""

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.common.base.base_auto_input import BaseAutoInput
from src.common.functions.response import response


ETC_INVOICE_NUMBER = "T9010001095716"
ETC_SUPPLIER_NAME = "東日本高速道路株式会社"
ETC_LOGIN_URL = "https://www2.etc-meisai.jp/etc/R?funccode=1013000000&nextfunc=1013000000"


class AutoInput_Etc(BaseAutoInput):
    """ETC利用照会サービスから未登録の高速道路利用明細を取り込む。"""

    def __init__(self, db_path=None):
        """
        ETC自動入力バッチを初期化する。

        Args:
            db_path (Optional[str]): ローカル実行時に使用するDBパス。
        """
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)

    def main(self, request_dict):
        """
        ETCへログインし、未登録の利用明細を領収書として登録する。

        Args:
            request_dict (dict): リクエスト情報。

        Returns:
            dict: 取得件数、重複件数、登録件数を含むレスポンス。
        """
        user_id = self.require_user_id(request_dict)
        config = self.get_auto_input_config(user_id, "ETC")
        account_id = self.value(config, "LOGIN_ID_1", "login_id_1")
        password = self.value(config, "LOGIN_PW_1", "login_pw_1")
        if not account_id or not password:
            raise RuntimeError("ETCのログイン情報が設定されていません。")

        session = self.new_session()
        login_page = self.request_external(
            session, "GET", self.value(config, "PAGE_URL_2", "page_url_2") or ETC_LOGIN_URL,
            "ログイン画面取得", "ETC",
        )
        login_soup = BeautifulSoup(login_page.content, "html.parser")
        form = login_soup.find("form", attrs={"name": "frm"})
        if not form:
            raise RuntimeError("ETCのログインフォームを取得できませんでした。")
        payload = {
            element.get("name"): element.get("value") or ""
            for element in form.find_all("input")
            if element.get("name") and (element.get("type") or "").lower() == "hidden"
        }
        payload.update({"risLoginId": account_id, "risPassword": password})
        login_url = urljoin(login_page.url, self.value(config, "PAGE_URL_3", "page_url_3") or ETC_LOGIN_URL)
        history_page = self.request_external(
            session, "POST", login_url, "ログイン", "ETC",
            data=payload, headers={"Referer": login_page.url}, allow_redirects=True,
        )
        history_soup = BeautifulSoup(history_page.content, "html.parser")
        if history_soup.find("input", attrs={"name": "risLoginId"}):
            raise RuntimeError("ETCへのログインに失敗しました。ユーザーIDとパスワードを確認してください。")

        rows = self.fetch_target_month_rows(session, history_page)
        registered_keys = self.get_registered_source_keys(user_id)
        pending = [row for row in rows if row["sourceKey"] not in registered_keys]
        grouped_rows = self.group_rows_by_date(pending)
        registered_count = 0
        failed_count = 0
        for receipt_date, date_rows in grouped_rows.items():
            try:
                result = self.register_receipt(
                    self.to_receipt_info(receipt_date, date_rows),
                    user_id,
                )
                status_code = int(result.get("statusCode", 500))
                if status_code == 409:
                    self.save_content_rows(date_rows, user_id, "DUPLICATE")
                    self.database.commit()
                    continue
                if status_code >= 400:
                    raise RuntimeError(f"ETC利用明細の登録に失敗しました: {result}")
                self.save_content_rows(date_rows, user_id, "3")
                self.database.commit()
                registered_count += len(date_rows)
            except Exception as error:
                failed_count += len(date_rows)
                self.logger.error("ETC利用明細の登録に失敗しました: %s", error)

        return response(200, {
            "totalFetched": len(rows),
            "alreadyRegistered": len(rows) - len(pending),
            "needToRegister": len(pending),
            "registered": registered_count,
            "failed": failed_count,
        })

    @staticmethod
    def group_rows_by_date(rows):
        """
        ETC利用明細を出場日単位でグループ化する。

        Args:
            rows (list[dict]): ETC利用明細。

        Returns:
            dict[str, list[dict]]: 出場日をキーとする利用明細一覧。
        """
        grouped = {}
        for row in sorted(rows, key=lambda item: (item["exitDate"], item["exitTime"], item["sourceKey"])):
            grouped.setdefault(row["exitDate"], []).append(row)
        return grouped

    def save_content_rows(self, rows, user_id, status):
        """
        日次領収書へ含めた各ETC利用明細を管理テーブルへ登録する。

        Args:
            rows (list[dict]): 登録対象のETC利用明細。
            user_id (str): ユーザーID。
            status (str): 自動入力状態。
        """
        for row in rows:
            self.insert_auto_input_content(
                user_id=user_id,
                connection_type="ETC",
                invoice_number=ETC_INVOICE_NUMBER,
                receipt_date=row["exitDate"].replace("-", ""),
                receipt_time=row["exitTime"].replace(":", "") + "00",
                content=row,
                status=status,
                source_key=row["sourceKey"],
            )

    def fetch_target_month_rows(self, session, authenticated_page):
        """
        当月と前月の利用明細を、各月の全ページから取得する。

        Args:
            session (requests.Session): ログイン済みHTTPセッション。
            authenticated_page (requests.Response): ログイン直後の利用明細レスポンス。

        Returns:
            list[dict]: 重複を除いた2か月分の利用明細。
        """
        now = datetime.now()
        previous_month = now.month - 1 or 12
        previous_year = now.year - 1 if now.month == 1 else now.year
        target_months = (f"{now.year:04d}{now.month:02d}", f"{previous_year:04d}{previous_month:02d}")
        rows_by_key = {}
        for target_month in target_months:
            month_url = urljoin(
                authenticated_page.url,
                f"/etc/R?funccode=1013000000&nextfunc=1013200000&taisyoYM={target_month}",
            )
            month_page = self.submit_etc_page(
                session=session,
                source_page=authenticated_page,
                target_url=month_url,
                operation_name=f"{target_month}利用明細取得",
            )
            for row in self.fetch_all_pages(session, month_page):
                rows_by_key[row["sourceKey"]] = row
        return list(rows_by_key.values())

    def fetch_all_pages(self, session, first_page):
        """
        利用明細のページ遷移リンクをたどり、全ページの明細を取得する。

        Args:
            session (requests.Session): ログイン済みHTTPセッション。
            first_page (requests.Response): 対象月の先頭ページ。

        Returns:
            list[dict]: 対象月の全利用明細。
        """
        pending = [(first_page.url, first_page)]
        visited = set()
        rows_by_key = {}
        while pending:
            page_url, page_response = pending.pop(0)
            normalized_url = page_url.replace("&amp;", "&")
            if normalized_url in visited:
                continue
            visited.add(normalized_url)
            soup = BeautifulSoup(page_response.content, "html.parser")
            for row in self.parse_history(soup):
                rows_by_key[row["sourceKey"]] = row
            for next_url in self.extract_page_urls(soup, page_response.url):
                if next_url in visited or any(url == next_url for url, _ in pending):
                    continue
                next_page = self.submit_etc_page(
                    session=session,
                    source_page=page_response,
                    target_url=next_url,
                    operation_name="利用明細ページ取得",
                )
                pending.append((next_url, next_page))
        return list(rows_by_key.values())

    def submit_etc_page(self, session, source_page, target_url, operation_name):
        """
        ETC画面のhidden項目を引き継いで次画面へPOSTする。

        Args:
            session (requests.Session): ログイン済みHTTPセッション。
            source_page (requests.Response): 遷移元レスポンス。
            target_url (str): 遷移先URL。
            operation_name (str): ログ用操作名。

        Returns:
            requests.Response: 遷移先レスポンス。
        """
        soup = BeautifulSoup(source_page.content, "html.parser")
        form = soup.find("form", attrs={"name": "frm"})
        if not form:
            raise RuntimeError("ETC利用明細の画面遷移フォームを取得できませんでした。")
        payload = {
            element.get("name"): element.get("value") or ""
            for element in form.find_all("input")
            if element.get("name") and (element.get("type") or "").lower() == "hidden"
        }
        return self.request_external(
            session, "POST", target_url, operation_name, "ETC",
            data=payload, headers={"Referer": source_page.url}, allow_redirects=True,
        )

    @staticmethod
    def extract_page_urls(soup, base_url):
        """
        利用明細画面のページ番号・前後ページ遷移URLを抽出する。

        Args:
            soup (BeautifulSoup): 利用明細ページ。
            base_url (str): 相対URL解決用URL。

        Returns:
            list[str]: ページ遷移URL。
        """
        urls = []
        pattern = re.compile(r"submitPage\([^,]+,\s*['\"]([^'\"]+)['\"]")
        for element in soup.select(
            ".plink button[onclick], .plink_no button[onclick], "
            "button.plink[onclick], button.plink_no[onclick]"
        ):
            match = pattern.search(element.get("onclick") or "")
            if match:
                urls.append(urljoin(base_url, match.group(1).replace("&amp;", "&")))
        return list(dict.fromkeys(urls))

    def parse_history(self, soup):
        """
        ETC利用明細ページの表から走行単位の明細を抽出する。

        Args:
            soup (BeautifulSoup): 利用明細ページ。

        Returns:
            list[dict]: ETC利用明細。
        """
        result = []
        for row in soup.select("tr.meisai, tr.meisai_r"):
            checkbox = row.find("input", attrs={"name": "hakkoMeisai"})
            cells = row.find_all("td", recursive=False)
            if not checkbox or len(cells) < 6:
                continue
            date_places = [
                self.clean_text(value.get_text(" ", strip=True))
                for value in cells[1].select(".meisaivalue")
            ]
            if len(date_places) < 2:
                continue
            entry = self.parse_date_place(date_places[0])
            exit_info = self.parse_date_place(date_places[1])
            amount = self.extract_amount(cells[3].get_text(" ", strip=True))
            if amount is None:
                amount = self.extract_amount(cells[2].get_text(" ", strip=True))
            if amount is None:
                continue
            result.append({
                "sourceKey": f"ETC:{checkbox.get('value')}",
                "entryDate": entry["date"],
                "entryTime": entry["time"],
                "entryPlace": entry["place"],
                "exitDate": exit_info["date"],
                "exitTime": exit_info["time"],
                "exitPlace": exit_info["place"],
                "amount": amount,
                "note": self.clean_text(cells[5].get_text(" ", strip=True)),
            })
        return result

    @staticmethod
    def clean_text(value):
        """HTML内の空白を単一スペースへ正規化する。"""
        return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()

    @staticmethod
    def parse_date_place(value):
        """YY/MM/DD、HH:MM、料金所名を分解する。"""
        match = re.search(r"(\d{2})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2})\s*(.*)", value)
        if not match:
            raise RuntimeError(f"ETC利用日時を解析できません: {value}")
        year, month, day, hour, minute, place = match.groups()
        return {
            "date": f"20{year}-{month}-{day}",
            "time": f"{hour}:{minute}",
            "place": place.strip(),
        }

    @staticmethod
    def extract_amount(value):
        """金額欄から請求額を取得する。"""
        numbers = re.findall(r"-?\d[\d,]*", value)
        return int(numbers[-1].replace(",", "")) if numbers else None

    def get_registered_source_keys(self, user_id):
        """登録済みETC明細の一意キーを取得する。"""
        rows = self.database.select(
            """
            SELECT SOURCE_KEY FROM kakeibo.auto_input_cont
            WHERE CRE_USER_ID = %(USER_ID)s
              AND CONNECTION_TYPE = 'ETC'
              AND DEL_FLAG = 0
            """,
            {"USER_ID": user_id},
        )
        return {
            str(self.value(row, "SOURCE_KEY", "source_key") or "")
            for row in rows
            if self.value(row, "SOURCE_KEY", "source_key")
        }

    @staticmethod
    def to_receipt_info(receipt_date, rows):
        """
        同日のETC利用明細を1枚の領収書へ変換する。

        Args:
            receipt_date (str): 出場日。
            rows (list[dict]): 同日に利用したETC明細。

        Returns:
            dict: 領収書登録情報。
        """
        details = [AutoInput_Etc.to_receipt_detail(row) for row in rows]
        return {
            "invoiceRegistrationNumber": ETC_INVOICE_NUMBER,
            "supplierName": ETC_SUPPLIER_NAME,
            "receiptDate": receipt_date,
            "receiptTime": "00:00",
            "taxFlag": 1,
            "receiptDetailCount": len(details),
            "receiptDetails": details,
            "totalPrice": sum(detail["totalPrice"] for detail in details),
        }

    @staticmethod
    def to_receipt_detail(row):
        """
        ETC走行1件を時刻付きの領収書明細へ変換する。

        Args:
            row (dict): ETC利用明細。

        Returns:
            dict: 領収書明細。
        """
        entry = " ".join(value for value in (row["entryTime"], row["entryPlace"]) if value)
        exit_value = " ".join(value for value in (row["exitTime"], row["exitPlace"]) if value)
        route = " → ".join(value for value in (entry, exit_value) if value)
        item_name = f"ETC高速道路料金 {route}".strip()
        amount = abs(int(row["amount"]))
        return {
            "itemName": item_name,
            "category1": "交通費",
            "category2": "高速道路",
            "taxRate": 0.10,
            "quantity": 1,
            "unit": "件",
            "unitPrice": amount,
            "totalPrice": amount,
            "taxIncludedUnitPrice": amount,
            "taxIncludedTotalPrice": amount,
        }
