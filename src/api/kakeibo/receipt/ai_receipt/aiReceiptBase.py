# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import json
import uuid

from src.api.kakeibo.receipt.ai_receipt.receiptAnalyzer import GeminiReceiptAnalyzer
from src.api.kakeibo.receipt.supplierLogoStorage import SupplierLogoStorage
from src.api.kakeibo.receipt.taxPrice import enrich_detail_prices, receipt_details_tax_included_total, to_number
from src.common.api_utils import (
    int_token,
    normalize_invoice_number,
    normalize_tax_flag,
    service_body,
    now_ymd_hms,
)
from src.common.base import BaseRestApi
from src.common.functions.response import response


class AiReceiptBase(BaseRestApi):
    """
    AIレシート解析、解析履歴、AI利用量を扱うAPIクラス。
    
    Args:
    
    """

    def __init__(
        self,
        db_path=None,
        service_url="",
        api_key="",
        gemini_api_key="",
        gemini_model="",
        analyzer=None,
    ):
        """
        クラスを初期化する。

        Args:
            db_path (Any): 旧呼び出し互換のためのDB指定。
            service_url (Any): service_urlの値。
            api_key (Any): api_keyの値。
            gemini_api_key (Any): gemini_api_keyの値。
            gemini_model (Any): gemini_modelの値。
            analyzer (Any): analyzerの値。

        Returns:
            None: 戻り値なし。
        """
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)
        self.service_url = service_url
        self.api_key = api_key
        self.gemini_api_key = gemini_api_key
        self.gemini_model = gemini_model
        self.logo_storage = SupplierLogoStorage()
        self.analyzer = analyzer

    def validate_body(self, request_dict):
        """
        リクエスト本文を検証する。

        Args:
            request_dict (Any): API呼び出し時のリクエスト情報。

        Returns:
            Any: 処理結果。
        """
        return super().validate_body(request_dict)

    def analyze(self, body, user_id):
        """
        画像とカテゴリ情報をAI解析クラスへ渡し、結果を履歴へ保存する。

        Args:
            body (Any): リクエスト本文。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        image_base64 = body.get("imageBase64") or ""
        if "," in image_base64 and image_base64.startswith("data:"):
            image_base64 = image_base64.split(",", 1)[1]
        receipt_text = (body.get("receiptText") or body.get("text") or "").strip()
        if not image_base64 and not receipt_text:
            return response(400, {"errorMessage": "画像またはレシート本文を入力してください。"})

        payload = {
            "imageBase64": image_base64,
            "imageMimeType": body.get("imageMimeType") or "image/jpeg",
            "receiptText": receipt_text,
            "inputType": "text" if receipt_text and not image_base64 else "image",
            "categories": self.merge_categories(body.get("categories"), user_id),
            "prompt": body.get("prompt"),
        }

        try:
            if self.analyzer is None:
                self.analyzer = GeminiReceiptAnalyzer(
                    api_key=self.gemini_api_key,
                    model=self.gemini_model,
                    timeout=40,
                )
            parsed = self.analyzer.analyze_payload(payload)
            status_code = parsed.get("statusCode", 200) if isinstance(parsed, dict) else 200
            self.record_usage(parsed, status_code, user_id)
            response_body = service_body(parsed)
            if isinstance(response_body, dict):
                if int(status_code) >= 400:
                    # 2026-06-28 Codex: 解析失敗は利用量だけ記録し、レシート履歴には正常候補として残さない。
                    response_body["usageSummary"] = self.usage_summary(user_id)
                    return response(status_code, response_body)
                # 2026-07-03 Codex: AI only extracts receipt facts; frontend resolves DB/user tax flag.
                response_body = self.mark_tax_decision_required(response_body)
                analysis_id = self.create_history(
                    user_id=user_id,
                    image_base64=image_base64,
                    image_mime_type=payload["imageMimeType"],
                    ai_output=response_body,
                )
                response_body["analysisId"] = analysis_id
                response_body["usageSummary"] = self.usage_summary(user_id)
            return response(status_code, response_body)

        except Exception as e:
            return response(500, {"errorMessage": str(e)})

    def mark_tax_decision_required(self, ai_output):
        """
        2026-07-03 Codex: Mark AI prices as raw printed amounts for frontend tax selection.

        Args:
            ai_output (Any): ai_outputの値。

        Returns:
            Any: 処理結果。
        """
        receipt = ai_output.get("receiptInfo") or ai_output.get("receipt")
        if isinstance(receipt, dict):
            receipt["taxFlag"] = "1"
            receipt["pricesAreRaw"] = True
            receipt["needsTaxSelection"] = True
        ai_output["needsTaxSelection"] = True
        return ai_output

    def apply_registered_supplier(self, ai_output, user_id):
        """
        AI結果の登録番号が場所マスタに存在する場合、DBの店舗情報を優先する。

        Args:
            ai_output (Any): ai_outputの値。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        receipt = ai_output.get("receiptInfo") or ai_output.get("receipt")
        if not isinstance(receipt, dict):
            return ai_output

        invoice_number = normalize_invoice_number(receipt.get("invoiceRegistrationNumber"))
        if not invoice_number:
            return ai_output

        rows = self.database.select(
            self.database.read_sql("SELECT_INVOICE_REGISTRATION", location=__file__),
            {"INV_REG_NUM": invoice_number, "USER_ID": user_id},
        )
        if not rows:
            return ai_output

        row = rows[0]
        tax_flag = str(normalize_tax_flag(row.get("TAX_FLAG", row.get("taxFlag"))))
        receipt["invoiceRegistrationNumber"] = invoice_number
        receipt["supplierName"] = row.get("SUP_NAME") or row.get("supplierName") or receipt.get("supplierName") or ""
        receipt["taxFlag"] = tax_flag

        supplier_image = self.logo_storage.url_for(invoice_number)
        if supplier_image:
            receipt["supplierImage"] = supplier_image

        # DBの税区分に合わせてフォーム表示用単価を選ぶ。税込合計は常に税込値を使う。
        for detail in receipt.get("receiptDetails") or []:
            if not isinstance(detail, dict):
                continue
            if tax_flag == "0" and detail.get("taxExcludedUnitPrice") is not None:
                detail["unitPrice"] = detail["taxExcludedUnitPrice"]
            elif tax_flag == "1" and detail.get("taxIncludedUnitPrice") is not None:
                detail["unitPrice"] = detail["taxIncludedUnitPrice"]
            if detail.get("taxIncludedTotalPrice") is not None:
                detail["totalPrice"] = detail["taxIncludedTotalPrice"]

        return ai_output

    def reconcile_ai_receipt_totals(self, ai_output):
        """
        2026-06-28 Codex: AIの金額ブレを補正し、補正不能な差異は画面確認対象にする。

        Args:
            ai_output (Any): ai_outputの値。

        Returns:
            Any: 処理結果。
        """
        receipt = ai_output.get("receiptInfo") or ai_output.get("receipt")
        if not isinstance(receipt, dict):
            return ai_output

        details = receipt.get("receiptDetails") or []
        if not isinstance(details, list) or not details:
            return ai_output

        tax_flag = receipt.get("taxFlag")
        header_total = int(to_number(receipt.get("totalPrice")))
        detail_total = receipt_details_tax_included_total(details, tax_flag)
        if header_total <= 0 and detail_total > 0:
            receipt["totalPrice"] = detail_total
            return ai_output
        if header_total <= 0 or detail_total <= 0 or abs(header_total - detail_total) <= 1:
            return ai_output

        if len(details) == 1:
            detail = details[0]
            detail["totalPrice"] = header_total
            detail["taxIncludedTotalPrice"] = header_total
            prices = enrich_detail_prices(detail, tax_flag)
            detail.update(prices)
            receipt["totalPrice"] = prices.get("taxIncludedTotalPrice") or header_total
            ai_output["reviewWarnings"] = ai_output.get("reviewWarnings") or []
            ai_output["reviewWarnings"].append(
                "AIの明細合計がレシート合計と異なったため、単一明細をレシート合計に合わせました。"
            )
            return ai_output

        ai_output["needsReview"] = True
        ai_output["reviewWarnings"] = ai_output.get("reviewWarnings") or []
        ai_output["reviewWarnings"].append(
            f"レシート合計({header_total})と明細合計({detail_total})が一致しません。"
        )
        return ai_output

    def create_history(self, user_id, image_base64, image_mime_type, ai_output):
        """
        AI解析結果と送信画像を ai_receipt_analysis に保存する。

        Args:
            user_id (Any): ユーザーID。
            image_base64 (Any): image_base64の値。
            image_mime_type (Any): image_mime_typeの値。
            ai_output (Any): ai_outputの値。

        Returns:
            Any: 処理結果。
        """
        self.ensure_ai_schema()
        analysis_id = uuid.uuid4().hex
        receipt = self.normalize_receipt(ai_output)
        ymd, hms = now_ymd_hms()
        self.database.insert(
            self.database.read_sql("INSERT_AI_RECEIPT_ANALYSIS", location=__file__),
            {
                "CRE_PROG": "ai_receipt_history",
                "UPD_PROG": "ai_receipt_history",
                "ANALYSIS_ID": analysis_id,
                "INV_REG_NUM": receipt.get("invoiceRegistrationNumber"),
                "SUP_NAME": receipt.get("supplierName"),
                "RET_DT": receipt.get("receiptDate"),
                "RET_TM": receipt.get("receiptTime"),
                "TAX_FLAG": receipt.get("taxFlag"),
                "TOA_PRICE": receipt.get("totalPrice"),
                "AI_IMAGE_MIME_TYPE": image_mime_type,
                "AI_OUTPUT_JSON": json.dumps(ai_output, ensure_ascii=False),
                "EDITED_RECEIPT_JSON": "",
                "STATUS": "analyzed",
                "CRE_DT": ymd,
                "CRE_TM": hms,
                "UPD_DT": ymd,
                "UPD_TM": hms,
                "USER_ID": user_id,
            },
        )
        return analysis_id

    def save_final_receipt(self, body, user_id):
        """
        手動編集後に実際保存されたレシート内容をAI解析履歴へ反映する。

        Args:
            body (Any): リクエスト本文。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        self.ensure_ai_schema()
        analysis_id = body.get("analysisId")
        receipt_info = (body.get("receiptInfo") or {}).copy()
        if not analysis_id:
            return response(200, {"ok": True})

        receipt_id = body.get("receiptId") or ""
        if not receipt_id:
            rows = self.database.select(
                self.database.read_sql("SELECT_RECEIPT_INFO", location=__file__),
                {"USER_ID": user_id},
            )
            receipt_id = rows[0].get("RET_ID") if rows else ""
        ymd, hms = now_ymd_hms()
        updated = self.database.execute(
            self.database.read_sql("UPDATE_AI_RECEIPT_ANALYSIS", location=__file__),
            {
                "UPD_PROG": "ai_receipt_final",
                "RET_ID": receipt_id,
                "INV_REG_NUM": receipt_info.get("invoiceRegistrationNumber"),
                "SUP_NAME": receipt_info.get("supplierName"),
                "RET_DT": receipt_info.get("receiptDate"),
                "RET_TM": receipt_info.get("receiptTime"),
                "TAX_FLAG": receipt_info.get("taxFlag"),
                "TOA_PRICE": receipt_info.get("totalPrice"),
                "EDITED_RECEIPT_JSON": json.dumps(receipt_info, ensure_ascii=False),
                "STATUS": "saved",
                "UPD_DT": ymd,
                "UPD_TM": hms,
                "USER_ID": user_id,
                "ANALYSIS_ID": analysis_id,
            },
        )
        return response(200, {"ok": updated > 0, "receiptId": receipt_id})

    def list_history(self, user_id):
        """
        AI解析履歴を新しい順に最大200件取得する。

        Args:
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        self.ensure_ai_schema()
        rows = self.database.select(
            self.database.read_sql("SELECT_AI_RECEIPT_ANALYSIS", location=__file__),
            {"USER_ID": user_id},
        )
        return [
            {
                "analysisId": row.get("analysisId") or "",
                "receiptId": row.get("receiptId") or "",
                "supplierName": row.get("supplierName") or "",
                "receiptDate": row.get("receiptDate") or "",
                "receiptTime": row.get("receiptTime") or "",
                "totalPrice": row.get("totalPrice") or 0,
                "status": row.get("status") or "",
                "createdDate": row.get("createdDate") or "",
                "createdTime": row.get("createdTime") or "",
            }
            for row in rows
        ]

    def get_history(self, analysis_id, user_id):
        """
        指定したAI解析履歴の画像、AI出力、編集後内容を取得する。

        Args:
            analysis_id (Any): analysis_idの値。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        self.ensure_ai_schema()
        if not analysis_id:
            return None
        rows = self.database.select(
            self.database.read_sql("SELECT_AI_RECEIPT_ANALYSIS_02", location=__file__),
            {"ANALYSIS_ID": analysis_id, "USER_ID": user_id},
        )
        if not rows:
            return None
        row = rows[0]
        # Lambda/API Gatewayのレスポンス上限を超えないよう、画像base64は詳細レスポンスへ含めない。
        return {
            "analysisId": row.get("analysisId") or "",
            "receiptId": row.get("receiptId") or "",
            "invoiceRegistrationNumber": row.get("invoiceRegistrationNumber") or "",
            "supplierName": row.get("supplierName") or "",
            "receiptDate": row.get("receiptDate") or "",
            "receiptTime": row.get("receiptTime") or "",
            "taxFlag": row.get("taxFlag"),
            "totalPrice": row.get("totalPrice") or 0,
            "imageMimeType": row.get("imageMimeType") or "",
            "hasImage": bool(row.get("hasImage")),
            "aiOutput": self.parse_json(row.get("aiOutputJson")),
            "editedReceipt": self.parse_json(row.get("editedReceiptJson")),
            "status": row.get("status") or "",
            "createdDate": row.get("createdDate") or "",
            "createdTime": row.get("createdTime") or "",
        }

    def normalize_receipt(self, raw):
        """
        AI出力の揺れを履歴テーブルの共通項目へ寄せる。

        Args:
            raw (Any): rawの値。

        Returns:
            Any: 処理結果。
        """
        data = raw.get("receiptInfo") or raw.get("receipt") or raw
        return {
            "invoiceRegistrationNumber": data.get("invoiceRegistrationNumber") or data.get("invoiceNo") or "",
            "supplierName": data.get("supplierName") or data.get("storeName") or "",
            "receiptDate": data.get("receiptDate") or data.get("date") or "",
            "receiptTime": data.get("receiptTime") or data.get("time") or "",
            "taxFlag": data.get("taxFlag") if data.get("taxFlag") is not None else 0,
            "totalPrice": data.get("totalPrice") or data.get("total") or 0,
        }

    def parse_json(self, value):
        """
        履歴テーブルに保存されたJSON文字列を画面返却用に復元する。

        Args:
            value (Any): valueの値。

        Returns:
            Any: 処理結果。
        """
        if not value:
            return None
        try:
            return json.loads(value)
        except Exception:
            return value

    def ensure_ai_schema(self):
        """
        AI履歴テーブルが古いDBでも動くよう、必要な列を補完する。

        Args:
            None: 引数なし。

        Returns:
            Any: 処理結果。
        """
        statements = (
            "CREATE_AI_USAGE_LOG", "ALTER_AI_USAGE_LOG_CRE_USER_ID",
            "ALTER_AI_USAGE_LOG_UPD_USER_ID", "ALTER_AI_USAGE_LOG_CREATED_AT",
            "CREATE_AI_RECEIPT_ANALYSIS", "ALTER_AI_RECEIPT_ANALYSIS_CRE_USER_ID",
            "ALTER_AI_RECEIPT_ANALYSIS_UPD_USER_ID", "ALTER_AI_RECEIPT_ANALYSIS_CREATED_AT",
        )
        for sql_name in statements:
            self.database.execute(self.database.read_sql(sql_name, location=__file__))

    def merge_categories(self, raw_categories, user_id):
        """
        画面指定カテゴリが不足する場合はDBのマスタカテゴリで補完する。

        Args:
            raw_categories (Any): raw_categoriesの値。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        db_categories = self.load_categories(user_id)
        if not isinstance(raw_categories, dict):
            return db_categories

        category1 = raw_categories.get("category1")
        category2 = raw_categories.get("category2")
        return {
            "category1": category1 if isinstance(category1, list) and category1 else db_categories["category1"],
            "category2": category2 if isinstance(category2, list) and category2 else db_categories["category2"],
        }

    def load_categories(self, user_id):
        """
        AIへ渡す大分類・小分類マスタをDBから取得する。

        Args:
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        return {
            "category1": self.database.select(
                self.database.read_sql("SELECT_RECEIPT_INFO_CATEGORY1", location=__file__),
                {"USER_ID": user_id},
            ) or [],
            "category2": self.database.select(
                self.database.read_sql("SELECT_RECEIPT_INFO_CATEGORY2", location=__file__),
                {"USER_ID": user_id},
            ) or [],
        }

    def extract_usage(self, payload):
        """
        外部AIサービスのレスポンスから利用量情報を抽出する。

        Args:
            payload (Any): payloadの値。

        Returns:
            Any: 処理結果。
        """
        if not isinstance(payload, dict):
            return {}
        body = service_body(payload)
        usage = payload.get("usage")
        if not usage and isinstance(body, dict):
            usage = body.get("usage")
        return usage if isinstance(usage, dict) else {}

    def record_usage(self, service_payload, status_code, user_id):
        """
        AIサービス呼び出し結果の利用量を ai_usage_log に記録する。

        Args:
            service_payload (Any): service_payloadの値。
            status_code (Any): status_codeの値。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        self.ensure_ai_schema()
        usage = self.extract_usage(service_payload)
        body = service_body(service_payload)
        error_code = body.get("code") if isinstance(body, dict) else ""
        ymd, hms = now_ymd_hms()
        self.database.execute(
            self.database.read_sql("INSERT_AI_USAGE_LOG", location=__file__),
            {
                "CRE_PROG": "ai_receipt_analyze",
                "PROVIDER": "gemini",
                "MODEL": usage.get("model") or "",
                "FEATURE": "receipt_ai",
                "STATUS_CODE": int_token(status_code),
                "ERROR_CODE": error_code or "",
                "PROMPT_TOKENS": int_token(usage.get("promptTokens")),
                "OUTPUT_TOKENS": int_token(usage.get("outputTokens")),
                "TOTAL_TOKENS": int_token(usage.get("totalTokens")),
                "CACHED_TOKENS": int_token(usage.get("cachedTokens")),
                "THOUGHTS_TOKENS": int_token(usage.get("thoughtsTokens")),
                "CRE_DT": ymd,
                "CRE_TM": hms,
                "USER_ID": user_id,
            },
        )

    def usage_summary(self, user_id):
        """
        レシートAI機能の累計利用量を集計する。

        Args:
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        self.ensure_ai_schema()
        rows = self.database.select(
            self.database.read_sql("SELECT_AI_USAGE_LOG", location=__file__),
            {"USER_ID": user_id},
        )
        row = rows[0] if rows else {}
        return {
            "requestCount": int_token(row.get("requestCount")),
            "promptTokens": int_token(row.get("promptTokens")),
            "outputTokens": int_token(row.get("outputTokens")),
            "totalTokens": int_token(row.get("totalTokens")),
            "cachedTokens": int_token(row.get("cachedTokens")),
            "thoughtsTokens": int_token(row.get("thoughtsTokens")),
        }
