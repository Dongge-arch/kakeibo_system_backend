# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import base64
import json
import logging
import os
import re
import time

import requests
from src.common.config import APP_CONFIG
from src.api.receipt.taxPrice import enrich_detail_prices, normalize_tax_rate


log = logging.getLogger(__name__)


def clean_json_text(text: str) -> str:
    """AI が ```json ... ``` を付けた場合に外側だけ取り除く。"""
    if not text:
        return ""

    text = text.strip()

    if text.startswith("```json"):
        text = text.replace("```json", "", 1)
    elif text.startswith("```"):
        text = text.replace("```", "", 1)

    if text.endswith("```"):
        text = text[:-3]

    return text.strip()


def to_int(value) -> int:
    """カンマ付き文字列や None を安全に整数へ変換する。"""
    if value is None:
        return 0
    if isinstance(value, int):
        return value

    try:
        return int(str(value).replace(",", "").strip())
    except Exception:
        return 0


def optional_int(value):
    """AIが返さなかった価格と、0円の価格を区別して整数へ変換する。"""
    if value in (None, ""):
        return None
    return to_int(value)


def normalize_date(value: str) -> str:
    """日付を画面入力で使う YYYY-MM-DD 形式へ寄せる。"""
    raw = str(value or "").strip()
    if not raw:
        return ""

    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", raw):
        y, m, d = raw.split("-")
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    digits = re.sub(r"\D", "", raw)
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"

    return raw


def normalize_time(value: str) -> str:
    """時刻を画面入力で使う HH:MM 形式へ寄せる。"""
    raw = str(value or "").strip()
    if not raw:
        return ""

    if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", raw):
        parts = raw.split(":")
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"

    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 4:
        return f"{digits[:2]}:{digits[2:4]}"

    return raw


def normalize_invoice_number(value: str) -> str:
    """登録番号は T + 13桁だけを有効扱いにする。"""
    digits = re.sub(r"\D", "", str(value or "").replace("T", "").replace("t", ""))
    return f"T{digits}" if len(digits) == 13 else ""


def clean_category_label(value) -> str:
    """AI が返しがちな「■ 食費」のような装飾を外す。"""
    return str(value or "").replace("■", "").strip()


def get_category_name(item: dict, key: str) -> str:
    """DB 由来の大文字キーを安全に読む。"""
    if not isinstance(item, dict):
        return ""
    aliases = {
        "CATEGORY1_NAME": ("CATEGORY1_NAME", "category1Name", "category1_name", "category1"),
        "CATEGORY2_NAME": ("CATEGORY2_NAME", "category2Name", "category2_name", "category2"),
    }
    for alias in aliases.get(key.upper(), (key, key.upper())):
        value = item.get(alias)
        if value not in (None, ""):
            return clean_category_label(value)
    return ""


def get_category_tax_rate(item: dict):
    """DB形式と画面のcamelCase形式の両方から税率を読む。"""
    if not isinstance(item, dict):
        return None
    for key in ("TAX_RATE", "taxRate", "tax_rate"):
        if item.get(key) not in (None, ""):
            return item.get(key)
    return None


def build_category_prompt(categories: dict) -> str:
    """
    ソフトから渡された分類マスタを AI に見せる文字列へ変換する。
    現在の家計簿は category1 / category2 の2階層。
    """
    if not isinstance(categories, dict):
        categories = {}

    category1_list = categories.get("category1") or []
    category2_list = categories.get("category2") or []

    category1_names = [
        get_category_name(item, "CATEGORY1_NAME")
        for item in category1_list
    ]
    category1_names = [name for name in category1_names if name]

    grouped = {}
    for item in category2_list:
        parent = get_category_name(item, "CATEGORY1_NAME")
        child = get_category_name(item, "CATEGORY2_NAME")
        tax_rate = get_category_tax_rate(item)

        if not parent or not child:
            continue

        grouped.setdefault(parent, []).append((child, tax_rate))

    lines = []

    for parent in category1_names:
        lines.append(f"■ {parent}")
        children = grouped.get(parent, [])

        if not children:
            lines.append("- 未分類")

        for child, tax_rate in children:
            suffix = f" / taxRate={tax_rate}" if tax_rate not in (None, "") else ""
            lines.append(f"- {child}{suffix}")

    for parent, children in grouped.items():
        if parent in category1_names:
            continue

        lines.append(f"■ {parent}")
        for child, tax_rate in children:
            suffix = f" / taxRate={tax_rate}" if tax_rate not in (None, "") else ""
            lines.append(f"- {child}{suffix}")

    return "\n".join(lines) if lines else "■ その他\n- 未分類"


def category_pairs(categories: dict) -> set[tuple[str, str]]:
    """後処理で AI の分類が存在するか確認するための集合を作る。"""
    if not isinstance(categories, dict):
        return set()

    pairs = set()
    for item in categories.get("category2") or []:
        parent = get_category_name(item, "CATEGORY1_NAME")
        child = get_category_name(item, "CATEGORY2_NAME")
        if parent and child:
            pairs.add((parent, child))
    return pairs


def category_tax_rate_map(categories: dict) -> dict[tuple[str, str], float]:
    """分類ペアごとの税率を後処理で参照できるようにする。"""
    if not isinstance(categories, dict):
        return {}

    result = {}
    for item in categories.get("category2") or []:
        parent = get_category_name(item, "CATEGORY1_NAME")
        child = get_category_name(item, "CATEGORY2_NAME")
        if not parent or not child:
            continue
        result[(parent, child)] = get_category_tax_rate(item)
    return result


def fallback_category(item_name: str, pairs: set[tuple[str, str]]) -> tuple[str, str]:
    """
    AI が未分類を返した場合の最低限の補正。
    ここでは小票で頻出する食品・酒・レジ袋だけを強く補正する。
    """
    name = str(item_name or "")
    rules = [
        (("レジ袋", "袋"), ("日用品", "ゴミ袋・掃除用品")),
        (("酒", "ビール", "ハイボール", "カクテル", "ワイン", "焼酎", "チューハイ"), ("食費", "酒類・アルコール")),
        (("寿司", "刺身", "鮭", "魚", "まぐろ", "サーモン"), ("食費", "魚介・海産物")),
        (("豚", "牛", "鶏", "肉", "ハム", "ソーセージ"), ("食費", "肉・ハム・ソーセージ")),
        (("弁当", "惣菜", "テイクアウト"), ("食費", "惣菜・弁当・テイクアウト")),
        (("豆腐", "納豆", "ゆば", "大豆"), ("食費", "豆腐・納豆・豆類")),
        (("パン", "米", "麺"), ("食費", "米・パン・麺")),
        (("茶", "水", "コーヒー", "飲料"), ("食費", "飲料・水・お茶・コーヒー")),
    ]

    for keywords, pair in rules:
        if any(keyword in name for keyword in keywords) and pair in pairs:
            return pair

    return ("その他", "不明支出") if ("その他", "不明支出") in pairs else ("その他", "未分類")


NON_ITEM_NAME_PATTERN = re.compile(
    r"^(?:"
    r"小計|合計|総合計|お買上(?:金額|額)?|請求額|支払(?:額|金額)?|"
    r"現金|クレジット|カード|電子マネー|預り|お預り|釣銭|おつり|"
    r"消費税(?:等|額)?|内消費税|外税|内税|税額|"
    r"(?:8|10)(?:\.0)?%対象(?:額)?|軽減税率対象(?:額)?|"
    r"ガソリン税|揮発油税|地方揮発油税|"
    r"ポイント(?:利用|付与|残高)?"
    r")$",
    re.IGNORECASE,
)


def is_non_item_detail(item_name: str) -> bool:
    """税額、合計、支払情報などの商品ではない明細を除外する。"""
    normalized = re.sub(r"[\s:：()（）【】\[\]＊*※]+", "", str(item_name or ""))
    normalized = re.sub(r"[¥￥]?\d[\d,]*(?:円)?$", "", normalized)
    return not normalized or bool(NON_ITEM_NAME_PATTERN.fullmatch(normalized))


def build_receipt_prompt(categories: dict) -> str:
    """レシート解析用の最終プロンプトを作る。"""
    category_text = build_category_prompt(categories)

    return f"""レシート画像を読み取り、家計簿登録用の JSON だけを返してください。
説明文、Markdown、コードブロックは禁止です。

レシートではない画像の場合は no@#@#@# だけを返してください。
画像が暗い、ブレている、文字が小さい、金額や商品名が読めないなど、登録に必要な内容を十分に識別できない場合は AI_RECEIPT_UNREADABLE だけを返してください。

分類は必ず下の分類一覧から選んでください。自由入力は禁止です。
receiptDetails の各明細は category1/category2/taxRate を必ず入れてください。空文字は禁止です。
category1 には「■」の分類名、category2 にはその下の項目名を入れてください。
迷う場合も「未分類」にせず、商品名から最も近い分類を選んでください。

【分類一覧】
{category_text}

【読み取りルール】
- あなたの担当は印字内容の読み取り、商品行の識別、分類候補の選択です。税計算の推測を優先しないでください。
- 商品名、数量、印字単価、値引き、印字行金額をレシートに書かれた通りに読み取ってください。
- 読めない数字を周辺の合計から無理に逆算しないでください。主要項目が読めない場合は AI_RECEIPT_UNREADABLE を返してください。
- 店舗名（○○ ××店）(例：ローソン 秦野平沢店)、日付、時刻、登録番号が読める場合は入れてください。
- 店舗名、日付、合計金額、明細の大部分が読めない場合は推測せず AI_RECEIPT_UNREADABLE を返してください。
- 画像が横向き・逆向きでも、文字の向きを補正して読んでください。
- 日付は YYYY-MM-DD、時刻は HH:MM にしてください。
- invoiceRegistrationNumber は T + 13桁で読めた場合だけ入れてください。読めない場合は空文字。
- 日本のスーパーのように商品行が税抜で、下部に「8.0%対象」「10.0%対象」「消費税等」「合計」がある場合、taxFlag は "0" にしてください。
- 商品行が税込価格として印字されている場合又は「小計」と「合計」金額が違うの時 taxFlag は "1" にしてください。判断できない場合は "0"。
- receiptInfo.totalPrice は必ずレシート下部の「合計」「お買上額」「ご請求額」に相当する最終支払前の合計金額を入れてください。「小計」「税額」「お預り」「おつり」「ポイント」は入れないでください。
- quantity が読めない場合は 1。
- discount がない場合は 0。値引きがある場合、discount は必ず正の整数で入れてください。マイナス値は禁止です。
- 商品の直下や近くに「値引」「割引」「50%」「40%」「30%」などの行がある場合は、別明細に分けず、直前の商品明細の discount に入れてください。
- unitPrice は taxFlag に対応する値引き前の商品単価、totalPrice は値引き後の税込明細金額を入れてください。
- 各明細は税抜・税込の両方を返してください。taxExcludedUnitPrice / taxExcludedTotalPrice は税抜、taxIncludedUnitPrice / taxIncludedTotalPrice は税込です。
- レシートに片方しか印字されていない場合は、taxRate を使ってもう片方を計算してください。金額は1円単位で四捨五入してください。
- taxFlag が "0" の場合は unitPrice に税抜単価、taxFlag が "1" の場合は unitPrice に税込単価を入れてください。totalPrice は税込明細金額を入れてください。
- taxExcludedTotalPrice は税抜単価 × 数量 - 税抜値引額、taxIncludedTotalPrice は税込単価 × 数量 - 税込値引額を基本にしてください。
- レジ袋は商品明細として残し、日用品に分類してください。
- 商品名はレシート上の省略語、カナ、英数字を補完し、何を買ったか分かる自然な名前にしてください。
- ブランド名、容量、味、種類、部位、個数などが読める場合は itemName に含めてください。読めない内容は推測しすぎないでください。
- ポイント付与、ポイント利用、ポイント残高、会員番号、支払方法、預り金、おつり、税率別対象額、消費税額は receiptDetails に入れないでください。
- 8%対象/10%対象の税額行そのものは receiptDetails に入れないでください。税率は分類の taxRate から後続システムが計算します。
- 小計、合計、内税、外税、消費税、ガソリン税、支払額、現金、カードの行は絶対に商品明細にしないでください。
- taxRate は選択した category1/category2 の分類一覧に記載された値をそのまま返してください。独自判断で変更しないでください。
- taxExcludedUnitPrice、taxExcludedTotalPrice、taxIncludedUnitPrice、taxIncludedTotalPrice は後続システムで再計算されます。印字から確定できない値は 0 にしてください。
- 読み取った明細 totalPrice の合計に税を加えた金額が receiptInfo.totalPrice と大きく合わない場合、明細の読み落としや値引きの紐付けを見直してください。

【出力形式】
{{
  "receiptInfo": {{
    "invoiceRegistrationNumber": "",
    "supplierName": "",
    "receiptDate": "",
    "receiptTime": "",
    "taxFlag": "0",
    "totalPrice": 0,
    "receiptDetails": [
      {{
        "itemName": "",
        "category1": "",
        "category2": "",
        "taxRate": 0.1,
        "quantity": 1,
        "unitPrice": 0,
        "discount": 0,
        "totalPrice": 0,
        "taxExcludedUnitPrice": 0,
        "taxExcludedTotalPrice": 0,
        "taxIncludedUnitPrice": 0,
        "taxIncludedTotalPrice": 0
      }}
    ]
  }}
}}
"""


def build_receipt_category_mapping_prompt(categories: dict) -> str:
    """抽出済みレシート明細を家計簿カテゴリへ寄せるプロンプトを作る。"""
    category_text = build_category_prompt(categories)

    return f"""抽出済みレシートJSONを、家計簿登録用のカテゴリへ分類し直してください。
説明文、Markdown、コードブロックは禁止です。JSONだけを返してください。

分類は必ず下の分類一覧から選んでください。自由入力は禁止です。
receiptDetails の各明細は category1/category2/taxRate を必ず入れてください。空文字は禁止です。
category1 には「■」の分類名、category2 にはその下の項目名を入れてください。
迷う場合も「未分類」にせず、商品名から最も近い分類を選んでください。

【分類一覧】
{category_text}

【変換ルール】
- 入力JSONの receiptInfo 構造を保ったまま返してください。
- 商品名、数量、単価、値引、明細金額、合計金額、日付、時刻、店舗名、登録番号は変更しないでください。
- taxExcludedUnitPrice / taxExcludedTotalPrice / taxIncludedUnitPrice / taxIncludedTotalPrice も変更しないでください。
- 変更してよい項目は receiptDetails の category1/category2/taxRate だけです。
- 入力明細に belcCategoryCode / belcCategoryName がある場合、それはベルク側の商品分類です。分類判断の参考にしてください。
- belcCategoryCode / belcCategoryName を category1/category2 にそのまま入れることは禁止です。最終分類は必ず分類一覧から選んでください。
- taxRate は分類一覧に taxRate がある場合はそれを優先してください。
- 入力に軽減税率由来の taxRate=0.08 がある食品は、分類一覧と矛盾しない範囲で 0.08 を維持してください。
- レジ袋や日用品は食品分類に入れないでください。
- ポイント、支払方法、税額行、合計行が明細に混ざっている場合は receiptDetails から除外してください。
- receiptDetailCount は返却する receiptDetails の件数に合わせてください。

【出力形式】
{{
  "receiptInfo": {{
    "invoiceRegistrationNumber": "",
    "supplierName": "",
    "receiptDate": "",
    "receiptTime": "",
    "taxFlag": "0",
    "totalPrice": 0,
    "receiptDetails": [
      {{
        "itemName": "",
        "category1": "",
        "category2": "",
        "taxRate": 0.1,
        "quantity": 1,
        "unitPrice": 0,
        "discount": 0,
        "totalPrice": 0,
        "taxExcludedUnitPrice": 0,
        "taxExcludedTotalPrice": 0,
        "taxIncludedUnitPrice": 0,
        "taxIncludedTotalPrice": 0
      }}
    ]
  }}
}}
"""


def build_category_pair_mapping_prompt(categories: dict) -> str:
    """外部サービス側カテゴリを家計簿カテゴリへ対応付けるプロンプトを作る。"""
    category_text = build_category_prompt(categories)

    return f"""外部サービス側の商品カテゴリを、家計簿カテゴリへ対応付けてください。
説明文、Markdown、コードブロックは禁止です。JSONだけを返してください。

家計簿カテゴリは必ず下の分類一覧から選んでください。自由入力は禁止です。
category1 には「■」の分類名、category2 にはその下の項目名を入れてください。

【家計簿分類一覧】
{category_text}

【対応付けルール】
- 入力の belcCategoryCode / belcCategoryName はベルク側の商品分類です。
- ベルク側分類をそのまま category1/category2 に入れることは禁止です。
- それぞれのベルク側分類に最も近い家計簿分類を1つだけ選んでください。
- taxRate は選んだ家計簿分類の taxRate を優先してください。
- 判断に迷う場合も、分類一覧の中から最も近いものを選んでください。

【出力形式】
{{
  "mappings": [
    {{
      "belcCategoryCode": "",
      "belcCategoryName": "",
      "category1": "",
      "category2": "",
      "taxRate": 0.1
    }}
  ]
}}
"""


class GeminiReceiptAnalyzer:
    """Gemini REST API を使ってレシート画像またはレシート本文を解析する。"""

    api_retry_count = 5
    api_retry_delay_seconds = 1

    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: int = 40):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or APP_CONFIG.get("ai_receipt", {}).get("api_key", "")
        self.model = model or os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash-lite"
        self.timeout = timeout

    def normalize_usage(self, usage: dict) -> dict:
        """Gemini の usageMetadata を画面・DB保存用の名前へ変換する。"""
        usage = usage or {}
        prompt_tokens = to_int(usage.get("promptTokenCount") or usage.get("prompt_token_count"))
        output_tokens = to_int(usage.get("candidatesTokenCount") or usage.get("candidates_token_count"))
        total_tokens = to_int(usage.get("totalTokenCount") or usage.get("total_token_count"))
        cached_tokens = to_int(usage.get("cachedContentTokenCount") or usage.get("cached_content_token_count"))
        thoughts_tokens = to_int(usage.get("thoughtsTokenCount") or usage.get("thoughts_token_count"))

        if not total_tokens:
            total_tokens = prompt_tokens + output_tokens + thoughts_tokens

        return {
            "model": self.model,
            "promptTokens": prompt_tokens,
            "outputTokens": output_tokens,
            "totalTokens": total_tokens,
            "cachedTokens": cached_tokens,
            "thoughtsTokens": thoughts_tokens,
        }

    def generate_content(self, parts: list[dict]) -> tuple[str, dict]:
        """Gemini REST API に parts を渡す。"""
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY が設定されていません。")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        payload = {"contents": [{"parts": parts}]}

        response = self.post_with_retry(url, payload)
        response.raise_for_status()
        data = response.json()

        usage = self.normalize_usage(data.get("usageMetadata") or data.get("usage_metadata"))
        log.info(
            "Gemini token usage: prompt=%s, output=%s, total=%s, cached=%s, thoughts=%s",
            usage["promptTokens"],
            usage["outputTokens"],
            usage["totalTokens"],
            usage["cachedTokens"],
            usage["thoughtsTokens"],
        )

        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini から candidates が返っていません。")

        content_parts = candidates[0].get("content", {}).get("parts", [])
        if not content_parts or not content_parts[0].get("text"):
            raise ValueError("Gemini の返答に text がありません。")

        return content_parts[0]["text"], usage

    def post_with_retry(self, url: str, payload: dict):
        """Gemini API retry: 5 attempts, 1 second wait for any HTTP/API connection error."""
        last_error = None
        for attempt in range(1, self.api_retry_count + 1):
            try:
                response = requests.post(url, json=payload, timeout=self.timeout)
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.api_retry_count:
                    raise
                log.warning(
                    "Gemini API call failed (%s/%s); retrying in %s second.",
                    attempt,
                    self.api_retry_count,
                    self.api_retry_delay_seconds,
                )
                time.sleep(self.api_retry_delay_seconds)
        raise last_error

    def should_retry_api_error(self, exc: Exception) -> bool:
        return isinstance(exc, requests.RequestException)

    def call_gemini_with_image_bytes(self, image_bytes: bytes, mime_type: str, prompt: str) -> tuple[str, dict]:
        """画像バイナリとプロンプトを Gemini REST API に渡す。"""
        encoded_image = base64.b64encode(image_bytes).decode("utf-8")
        return self.generate_content([
            {"text": prompt},
            {
                "inline_data": {
                    "mime_type": mime_type or "image/jpeg",
                    "data": encoded_image,
                }
            },
        ])

    def call_gemini_with_receipt_text(self, receipt_text: str, prompt: str) -> tuple[str, dict]:
        """OCR済みのレシート本文とプロンプトを Gemini REST API に渡す。"""
        return self.call_gemini_with_text(receipt_text, prompt, label="レシート本文")

    def call_gemini_with_text(self, text: str, prompt: str, label: str = "入力データ") -> tuple[str, dict]:
        """任意のテキストとプロンプトを Gemini REST API に渡す共通入口。"""
        text_prompt = (
            f"{prompt}\n\n"
            f"【{label}】\n"
            f"{text}\n"
        )
        return self.generate_content([{"text": text_prompt}])

    def normalize_ai_receipt(self, data: dict, categories: dict | None = None) -> dict:
        """
        AI が少し違うキー名で返した場合でも、家計簿側の receiptInfo 形式へ寄せる。
        """
        if not isinstance(data, dict):
            raise ValueError("AI JSON がオブジェクトではありません。")

        receipt = data.get("receiptInfo") or data.get("receipt") or data
        raw_items = receipt.get("receiptDetails") or receipt.get("items") or data.get("items") or []
        details = []
        valid_pairs = category_pairs(categories or {})
        tax_rates = category_tax_rate_map(categories or {})
        tax_flag = str(receipt.get("taxFlag") if receipt.get("taxFlag") is not None else "0")

        for item in raw_items if isinstance(raw_items, list) else []:
            if not isinstance(item, dict):
                continue

            item_name = str(item.get("itemName") or item.get("name") or "不明商品").strip()
            if is_non_item_detail(item_name):
                log.info("Ignored non-item receipt detail: %s", item_name)
                continue

            total_price = to_int(
                item.get("totalPrice")
                if item.get("totalPrice") is not None
                else item.get("price")
                if item.get("price") is not None
                else item.get("amount")
            )
            quantity = to_int(item.get("quantity")) or 1
            unit_price = to_int(item.get("unitPrice") or item.get("unit_price")) or total_price

            category1 = clean_category_label(item.get("category1") or item.get("category_1") or "")
            category2 = clean_category_label(item.get("category2") or item.get("category_2") or item.get("category_3") or "")
            if valid_pairs and (category1, category2) not in valid_pairs:
                category1, category2 = fallback_category(item_name, valid_pairs)
            if valid_pairs and (category1, category2) not in valid_pairs and tax_rates:
                category1, category2 = next(iter(tax_rates.keys()))

            master_tax_rate = tax_rates.get((category1, category2))
            ai_tax_rate = (
                item.get("taxRate")
                if item.get("taxRate") is not None
                else item.get("tax_rate")
            )
            tax_rate = normalize_tax_rate(
                master_tax_rate if master_tax_rate not in (None, "") else ai_tax_rate,
                0.1,
            )

            normalized_detail = {
                "itemName": item_name,
                "category1": category1,
                "category2": category2,
                "taxRate": tax_rate,
                "quantity": quantity,
                "unitPrice": unit_price,
                "discount": to_int(item.get("discount")),
                "totalPrice": total_price,
                "taxExcludedUnitPrice": optional_int(item.get("taxExcludedUnitPrice")),
                "taxExcludedTotalPrice": optional_int(item.get("taxExcludedTotalPrice")),
                "taxIncludedUnitPrice": optional_int(item.get("taxIncludedUnitPrice")),
                "taxIncludedTotalPrice": optional_int(item.get("taxIncludedTotalPrice")),
            }
            prices = enrich_detail_prices(normalized_detail, tax_flag)
            normalized_detail.update(prices)
            # フォームの単価は税区分に合わせ、明細合計は常に税込で表示する。
            normalized_detail["unitPrice"] = (
                prices["taxExcludedUnitPrice"]
                if tax_flag == "0"
                else prices["taxIncludedUnitPrice"]
            )
            normalized_detail["totalPrice"] = prices["taxIncludedTotalPrice"]
            details.append(normalized_detail)

        total_price = to_int(
            receipt.get("totalPrice")
            if receipt.get("totalPrice") is not None
            else receipt.get("total")
        )
        if not total_price:
            total_price = sum(item["totalPrice"] for item in details)
        detail_total = sum(item["totalPrice"] for item in details)
        if total_price and details and detail_total != total_price:
            log.warning(
                "Receipt total mismatch after normalization: receipt=%s, details=%s, difference=%s",
                total_price,
                detail_total,
                total_price - detail_total,
            )

        return {
            "receiptInfo": {
                "invoiceRegistrationNumber": normalize_invoice_number(
                    receipt.get("invoiceRegistrationNumber")
                    or receipt.get("invoiceNo")
                    or receipt.get("invoiceNumber")
                ),
                "supplierName": str(
                    receipt.get("supplierName")
                    or receipt.get("store")
                    or receipt.get("storeName")
                    or receipt.get("shopName")
                    or ""
                ).strip(),
                "receiptDate": normalize_date(receipt.get("receiptDate") or receipt.get("date")),
                "receiptTime": normalize_time(receipt.get("receiptTime") or receipt.get("time")),
                "taxFlag": tax_flag,
                "totalPrice": total_price,
                "receiptDetailCount": len(details),
                "receiptDetails": details,
            }
        }

    def attach_usage(self, response: dict, usage: dict | None) -> dict:
        """レスポンス直下と body の両方に token 使用量を入れて、後続処理で取りやすくする。"""
        response["usage"] = usage or self.normalize_usage({})

        body = response.get("body")
        if isinstance(body, dict):
            body["usage"] = response["usage"]

        return response

    def parse_gemini_receipt_text(self, ai_text: str, usage=None, categories=None) -> dict:
        """AI の生テキストを家計簿が使える API レスポンスへ変換する。"""
        raw_text = clean_json_text(ai_text)
        log.info("Gemini raw text cleaned: %s", raw_text[:1000])

        if raw_text.strip().lower() == "no@#@#@#":
            return self.attach_usage({
                "statusCode": 204,
                "body": {
                    "code": "NOT_RECEIPT",
                    "errorMessage": "この画像はレシートではありません。",
                },
            }, usage)

        if raw_text.strip().upper() == "AI_RECEIPT_UNREADABLE":
            return self.attach_usage({
                "statusCode": 422,
                "body": {
                    "code": "AI_RECEIPT_UNREADABLE",
                    "errorMessage": "画像が不鮮明なため、レシート内容を十分に識別できませんでした。撮り直してください。",
                },
            }, usage)

        return self.attach_usage({
            "statusCode": 200,
            "body": self.normalize_ai_receipt(json.loads(raw_text), categories),
        }, usage)

    def analyze_text_with_prompt(self, text: str, prompt: str, categories=None, label: str = "入力データ") -> dict:
        """用途別プロンプトでテキストを解析し、receiptInfo形式へ正規化する。"""
        try:
            if not str(text or "").strip():
                return {
                    "statusCode": 400,
                    "body": {"errorMessage": "解析対象テキストを入力してください。"},
                }
            ai_text, usage = self.call_gemini_with_text(str(text), prompt, label=label)
            return self.parse_gemini_receipt_text(ai_text, usage, categories)
        except Exception as e:
            log.exception("Receipt AI text analyze failed.")
            return {
                "statusCode": 400,
                "body": {"errorMessage": str(e)},
            }

    def analyze_json_with_prompt(self, text: str, prompt: str, label: str = "入力データ") -> dict:
        """用途別プロンプトでJSON応答を受け取る共通入口。"""
        try:
            if not str(text or "").strip():
                return {
                    "statusCode": 400,
                    "body": {"errorMessage": "解析対象テキストを入力してください。"},
                }
            ai_text, usage = self.call_gemini_with_text(str(text), prompt, label=label)
            raw_text = clean_json_text(ai_text)
            log.info("Gemini raw json text cleaned: %s", raw_text[:1000])
            return self.attach_usage({
                "statusCode": 200,
                "body": json.loads(raw_text),
            }, usage)
        except Exception as e:
            log.exception("Receipt AI json analyze failed.")
            return {
                "statusCode": 400,
                "body": {"errorMessage": str(e)},
            }

    def analyze_payload(self, request: dict) -> dict:
        """HTTP でも Lambda 直接呼び出しでも使う、実際の解析処理。"""
        try:
            image_base64 = str((request or {}).get("imageBase64") or "")
            mime_type = str((request or {}).get("imageMimeType") or "image/jpeg")
            receipt_text = str((request or {}).get("receiptText") or (request or {}).get("text") or "").strip()
            categories = (request or {}).get("categories") or {}

            if image_base64.startswith("data:") and "," in image_base64:
                image_base64 = image_base64.split(",", 1)[1]

            if not image_base64 and not receipt_text:
                return {
                    "statusCode": 400,
                    "body": {"errorMessage": "画像またはレシート本文を入力してください。"},
                }

            prompt = (request or {}).get("prompt") or build_receipt_prompt(categories)
            if image_base64:
                image_bytes = base64.b64decode(image_base64)
                log.info(
                    "Receipt image received: size=%s bytes, mime=%s",
                    len(image_bytes),
                    mime_type,
                )
                ai_text, usage = self.call_gemini_with_image_bytes(image_bytes, mime_type, prompt)
            else:
                log.info("Receipt text received: length=%s chars", len(receipt_text))
                ai_text, usage = self.call_gemini_with_receipt_text(receipt_text, prompt)

            return self.parse_gemini_receipt_text(ai_text, usage, categories)

        except Exception as e:
            log.exception("Receipt AI analyze failed.")
            return {
                "statusCode": 400,
                "body": {"errorMessage": str(e)},
            }
