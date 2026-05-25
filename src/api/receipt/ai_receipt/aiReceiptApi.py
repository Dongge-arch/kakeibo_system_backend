# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import json
import urllib.error
import urllib.request
import uuid

from src.api.utils import int_token, json_response, service_body, now_ymd_hms
from src.common.base import BaseRestApi


class AiReceiptApi(BaseRestApi):
    """AIレシート解析、解析履歴、AI利用量を扱うAPIクラス。"""

    def __init__(self, db_path=None, service_url="", api_key=""):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)
        self.service_url = service_url
        self.api_key = api_key

    def validate_body(self, request_dict):
        return super().validate_body(request_dict)

    def main(self, request_dict):
        """actionに応じてAI解析・履歴・利用量処理へ振り分ける。"""
        body = request_dict.get("body") or {}
        action = body.get("action")
        if action == "analyze":
            return self.analyze(body)
        if action == "list_history":
            return json_response(200, self.list_history())
        if action == "get_history":
            return json_response(200, self.get_history(body.get("analysisId")))
        if action == "save_final_receipt":
            return self.save_final_receipt(body)
        if action == "usage":
            return json_response(200, self.usage_summary())
        return json_response(400, {"errorMessage": "unknown ai receipt action"})

    def analyze(self, body):
        """画像とカテゴリ情報を外部AI解析サービスへ送り、結果を履歴へ保存する。"""
        if not self.service_url:
            return json_response(500, {
                "errorMessage": "AIレシート解析サービスのURLが未設定です。application.yaml を確認してください。"
            })

        image_base64 = body.get("imageBase64") or ""
        if "," in image_base64 and image_base64.startswith("data:"):
            image_base64 = image_base64.split(",", 1)[1]
        if not image_base64:
            return json_response(400, {"errorMessage": "画像データがありません。"})

        payload = {
            "imageBase64": image_base64,
            "imageMimeType": body.get("imageMimeType") or "image/jpeg",
            "categories": self.merge_categories(body.get("categories")),
        }

        try:
            request = urllib.request.Request(
                self.service_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key or "",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                parsed = json.loads(response.read().decode("utf-8") or "{}")

            status_code = parsed.get("statusCode", 200) if isinstance(parsed, dict) else 200
            self.record_usage(parsed, status_code)
            response_body = service_body(parsed)
            if isinstance(response_body, dict):
                analysis_id = self.create_history(
                    image_base64=image_base64,
                    image_mime_type=payload["imageMimeType"],
                    ai_output=response_body,
                )
                response_body["analysisId"] = analysis_id
                response_body["usageSummary"] = self.usage_summary()
            return json_response(status_code, response_body)

        except urllib.error.HTTPError as e:
            return json_response(e.code, {
                "errorMessage": "AIレシート解析サービスの呼び出しに失敗しました。",
                "detail": e.read().decode("utf-8", errors="replace"),
            })
        except Exception as e:
            return json_response(500, {"errorMessage": str(e)})

    def create_history(self, image_base64, image_mime_type, ai_output):
        """AI解析結果と送信画像を ai_receipt_analysis に保存する。"""
        analysis_id = uuid.uuid4().hex
        receipt = self.normalize_receipt(ai_output)
        ymd, hms = now_ymd_hms()
        self.database.insert(
            """
            INSERT INTO ai_receipt_analysis (
              CRE_PROG, UPD_PROG, ANALYSIS_ID, INV_REG_NUM, SUP_NAME, RET_DT, RET_TM,
              TAX_FLAG, TOA_PRICE, AI_IMAGE, AI_IMAGE_MIME_TYPE, AI_OUTPUT_JSON,
              EDITED_RECEIPT_JSON, STATUS, CRE_DT, CRE_TM, UPD_DT, UPD_TM, DEL_FLAG
            ) VALUES (
              :CRE_PROG, :UPD_PROG, :ANALYSIS_ID, :INV_REG_NUM, :SUP_NAME, :RET_DT, :RET_TM,
              :TAX_FLAG, :TOA_PRICE, :AI_IMAGE, :AI_IMAGE_MIME_TYPE, :AI_OUTPUT_JSON,
              :EDITED_RECEIPT_JSON, :STATUS, :CRE_DT, :CRE_TM, :UPD_DT, :UPD_TM, 0
            )
            """,
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
                "AI_IMAGE": image_base64,
                "AI_IMAGE_MIME_TYPE": image_mime_type,
                "AI_OUTPUT_JSON": json.dumps(ai_output, ensure_ascii=False),
                "EDITED_RECEIPT_JSON": "",
                "STATUS": "analyzed",
                "CRE_DT": ymd,
                "CRE_TM": hms,
                "UPD_DT": ymd,
                "UPD_TM": hms,
            },
        )
        return analysis_id

    def save_final_receipt(self, body):
        """手動編集後に実際保存されたレシート内容をAI解析履歴へ反映する。"""
        analysis_id = body.get("analysisId")
        receipt_info = (body.get("receiptInfo") or {}).copy()
        if not analysis_id:
            return json_response(200, {"ok": True})

        receipt_id = body.get("receiptId") or ""
        if not receipt_id:
            rows = self.database.select(
                """
                SELECT RET_ID FROM receipt_info
                WHERE DEL_FLAG = 0
                ORDER BY id DESC
                LIMIT 1
                """
            )
            receipt_id = rows[0].get("RET_ID") if rows else ""
        ymd, hms = now_ymd_hms()
        updated = self.database.execute(
            """
            UPDATE ai_receipt_analysis
            SET UPD_PROG = :UPD_PROG,
                RET_ID = :RET_ID,
                INV_REG_NUM = :INV_REG_NUM,
                SUP_NAME = :SUP_NAME,
                RET_DT = :RET_DT,
                RET_TM = :RET_TM,
                TAX_FLAG = :TAX_FLAG,
                TOA_PRICE = :TOA_PRICE,
                EDITED_RECEIPT_JSON = :EDITED_RECEIPT_JSON,
                STATUS = :STATUS,
                UPD_DT = :UPD_DT,
                UPD_TM = :UPD_TM
            WHERE ANALYSIS_ID = :ANALYSIS_ID
              AND DEL_FLAG = 0
            """,
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
                "ANALYSIS_ID": analysis_id,
            },
        )
        return json_response(200, {"ok": updated > 0, "receiptId": receipt_id})

    def list_history(self):
        """AI解析履歴を新しい順に最大200件取得する。"""
        rows = self.database.select(
            """
            SELECT
              ANALYSIS_ID as analysisId,
              RET_ID as receiptId,
              SUP_NAME as supplierName,
              RET_DT as receiptDate,
              RET_TM as receiptTime,
              TOA_PRICE as totalPrice,
              STATUS as status,
              CRE_DT as createdDate,
              CRE_TM as createdTime
            FROM ai_receipt_analysis
            WHERE DEL_FLAG = 0
            ORDER BY id DESC
            LIMIT 200
            """
        )
        return rows

    def get_history(self, analysis_id):
        """指定したAI解析履歴の画像、AI出力、編集後内容を取得する。"""
        if not analysis_id:
            return None
        rows = self.database.select(
            """
            SELECT
              ANALYSIS_ID as analysisId,
              RET_ID as receiptId,
              INV_REG_NUM as invoiceRegistrationNumber,
              SUP_NAME as supplierName,
              RET_DT as receiptDate,
              RET_TM as receiptTime,
              TAX_FLAG as taxFlag,
              TOA_PRICE as totalPrice,
              AI_IMAGE as imageBase64,
              AI_IMAGE_MIME_TYPE as imageMimeType,
              AI_OUTPUT_JSON as aiOutputJson,
              EDITED_RECEIPT_JSON as editedReceiptJson,
              STATUS as status,
              CRE_DT as createdDate,
              CRE_TM as createdTime
            FROM ai_receipt_analysis
            WHERE ANALYSIS_ID = :ANALYSIS_ID
              AND DEL_FLAG = 0
            LIMIT 1
            """,
            {"ANALYSIS_ID": analysis_id},
        )
        if not rows:
            return None
        row = rows[0]
        row["aiOutput"] = self.parse_json(row.pop("aiOutputJson"))
        row["editedReceipt"] = self.parse_json(row.pop("editedReceiptJson"))
        return row

    def normalize_receipt(self, raw):
        """AI出力の揺れを履歴テーブルの共通項目へ寄せる。"""
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
        """履歴テーブルに保存されたJSON文字列を画面返却用に復元する。"""
        if not value:
            return None
        try:
            return json.loads(value)
        except Exception:
            return value

    def merge_categories(self, raw_categories):
        """画面指定カテゴリが不足する場合はDBのマスタカテゴリで補完する。"""
        db_categories = self.load_categories()
        if not isinstance(raw_categories, dict):
            return db_categories

        category1 = raw_categories.get("category1")
        category2 = raw_categories.get("category2")
        return {
            "category1": category1 if isinstance(category1, list) and category1 else db_categories["category1"],
            "category2": category2 if isinstance(category2, list) and category2 else db_categories["category2"],
        }

    def load_categories(self):
        """AIへ渡す大分類・小分類マスタをDBから取得する。"""
        return {
            "category1": self.database.select(
                "SELECT DISTINCT CATEGORY1_NAME FROM receipt_info_category1 WHERE DEL_FLAG = 0"
            ) or [],
            "category2": self.database.select(
                "SELECT CATEGORY1_NAME, CATEGORY2_NAME, TAX_RATE FROM receipt_info_category2 WHERE DEL_FLAG = 0"
            ) or [],
        }

    def extract_usage(self, payload):
        """外部AIサービスのレスポンスから利用量情報を抽出する。"""
        if not isinstance(payload, dict):
            return {}
        body = service_body(payload)
        usage = payload.get("usage")
        if not usage and isinstance(body, dict):
            usage = body.get("usage")
        return usage if isinstance(usage, dict) else {}

    def record_usage(self, service_payload, status_code):
        """AIサービス呼び出し結果の利用量を ai_usage_log に記録する。"""
        usage = self.extract_usage(service_payload)
        body = service_body(service_payload)
        error_code = body.get("code") if isinstance(body, dict) else ""
        ymd, hms = now_ymd_hms()
        self.database.execute(
            """
            INSERT INTO ai_usage_log (
              CRE_PROG, PROVIDER, MODEL, FEATURE, STATUS_CODE, ERROR_CODE,
              PROMPT_TOKENS, OUTPUT_TOKENS, TOTAL_TOKENS, CACHED_TOKENS, THOUGHTS_TOKENS,
              CRE_DT, CRE_TM, DEL_FLAG
            ) VALUES (
              :CRE_PROG, :PROVIDER, :MODEL, :FEATURE, :STATUS_CODE, :ERROR_CODE,
              :PROMPT_TOKENS, :OUTPUT_TOKENS, :TOTAL_TOKENS, :CACHED_TOKENS, :THOUGHTS_TOKENS,
              :CRE_DT, :CRE_TM, 0
            )
            """,
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
            },
        )

    def usage_summary(self):
        """レシートAI機能の累計利用量を集計する。"""
        rows = self.database.select(
            """
            SELECT
              COUNT(*) as requestCount,
              COALESCE(SUM(PROMPT_TOKENS), 0) as promptTokens,
              COALESCE(SUM(OUTPUT_TOKENS), 0) as outputTokens,
              COALESCE(SUM(TOTAL_TOKENS), 0) as totalTokens,
              COALESCE(SUM(CACHED_TOKENS), 0) as cachedTokens,
              COALESCE(SUM(THOUGHTS_TOKENS), 0) as thoughtsTokens
            FROM ai_usage_log
            WHERE DEL_FLAG = 0
              AND FEATURE = 'receipt_ai'
            """
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
