# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import json

from src.api.utils import now_ymd_hms, parse_json_object, json_response
from src.common.base import BaseRestApi


def row_value(row, *keys, default=None):
    if not row:
        return default

    lower_map = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        if key in row:
            return row.get(key)
        normalized_key = str(key).lower()
        if normalized_key in lower_map:
            return lower_map.get(normalized_key)
    return default


def int_value(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class AppSettingsApi(BaseRestApi):
    """アプリ設定とダッシュボード配置を保存・取得するAPIクラス。"""

    def __init__(self, db_path=None):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)

    def validate_body(self, request_dict):
        return super().validate_body(request_dict)

    def main(self, request_dict):
        """actionに応じて設定取得・保存処理へ振り分ける。"""
        body = request_dict.get("body") or {}
        user_id = self.require_user_id(request_dict)
        action = body.get("action")

        if action == "get":
            return json_response(200, self.get_settings(user_id))
        if action == "save":
            self.save_settings(body.get("settings") or {}, user_id)
            return json_response(200, {"ok": True})
        if action == "get_dashboard_layout":
            return json_response(200, self.get_dashboard_layout(user_id))
        if action == "save_dashboard_layout":
            self.save_dashboard_layout(body.get("layout") or [], user_id)
            return json_response(200, {"ok": True})

        return json_response(400, {"errorMessage": "unknown settings action"})

    def get_settings(self, user_id):
        """最新のアプリ設定を画面用の項目名で取得する。"""
        rows = self.database.select(
            """
            SELECT
              BUT_ON_OFF as budgetEnabled,
              BUT_CAT,
              BUDGET_PERIOD as budgetPeriod,
              DAY_DARK as darkMode,
              AUTO_DAY_DARK as autoDark,
              SUNRISE as sunrise,
              SUNSET as sunset
            FROM setting_table
            WHERE DEL_FLAG = 0
              AND CRE_USER_ID = %(USER_ID)s
            ORDER BY id DESC
            LIMIT 1
            """,
            {"USER_ID": user_id},
        )
        row = rows[0] if rows else {}
        extra = parse_json_object(row_value(row, "BUT_CAT", "but_cat"))
        settings = {
            "budgetEnabled": str(row_value(row, "budgetEnabled", "BUT_ON_OFF", default="0")) in ("1", "true", "True", "on"),
            "budgetPeriod": row_value(row, "budgetPeriod", "BUDGET_PERIOD", default="month") or "month",
            "darkMode": str(row_value(row, "darkMode", "DAY_DARK", default="0")) in ("1", "true", "True", "on"),
            "autoDark": str(row_value(row, "autoDark", "AUTO_DAY_DARK", default="0")) in ("1", "true", "True", "on"),
            "sunrise": row_value(row, "sunrise", "SUNRISE", default="06:00") or "06:00",
            "sunset": row_value(row, "sunset", "SUNSET", default="18:00") or "18:00",
            "largeTextMode": bool(extra.get("largeTextMode", False)),
            "colorTheme": extra.get("colorTheme", "kakeibo"),
            "language": extra.get("language", "ja"),
        }
        settings["aiUsageSummary"] = self.get_ai_usage_summary(user_id)
        return settings

    def get_ai_usage_summary(self, user_id):
        """設定画面向けにAI利用量の合計を返す。"""
        try:
            ymd, _ = now_ymd_hms()
            month_prefix = ymd[:6]
            rows = self.database.select(
                """
                SELECT
                  COUNT(*) AS requestCount,
                  COALESCE(SUM(PROMPT_TOKENS), 0) AS promptTokens,
                  COALESCE(SUM(OUTPUT_TOKENS), 0) AS outputTokens,
                  COALESCE(SUM(TOTAL_TOKENS), 0) AS totalTokens,
                  COALESCE(SUM(CACHED_TOKENS), 0) AS cachedTokens,
                  COALESCE(SUM(THOUGHTS_TOKENS), 0) AS thoughtsTokens
                FROM ai_usage_log
                WHERE DEL_FLAG = 0
                  AND CRE_USER_ID = %(USER_ID)s
                  AND FEATURE = 'receipt_ai'
                """,
                {"USER_ID": user_id},
            )
            today_rows = self.database.select(
                """
                SELECT
                  COUNT(*) AS requestCount,
                  COALESCE(SUM(PROMPT_TOKENS), 0) AS promptTokens,
                  COALESCE(SUM(OUTPUT_TOKENS), 0) AS outputTokens,
                  COALESCE(SUM(TOTAL_TOKENS), 0) AS totalTokens,
                  COALESCE(SUM(CACHED_TOKENS), 0) AS cachedTokens,
                  COALESCE(SUM(THOUGHTS_TOKENS), 0) AS thoughtsTokens
                FROM ai_usage_log
                WHERE DEL_FLAG = 0
                  AND CRE_USER_ID = %(USER_ID)s
                  AND FEATURE = 'receipt_ai'
                  AND CRE_DT = %(CRE_DT)s
                """,
                {"CRE_DT": ymd, "USER_ID": user_id},
            )
            month_rows = self.database.select(
                """
                SELECT
                  COUNT(*) AS requestCount,
                  COALESCE(SUM(PROMPT_TOKENS), 0) AS promptTokens,
                  COALESCE(SUM(OUTPUT_TOKENS), 0) AS outputTokens,
                  COALESCE(SUM(TOTAL_TOKENS), 0) AS totalTokens,
                  COALESCE(SUM(CACHED_TOKENS), 0) AS cachedTokens,
                  COALESCE(SUM(THOUGHTS_TOKENS), 0) AS thoughtsTokens
                FROM ai_usage_log
                WHERE DEL_FLAG = 0
                  AND CRE_USER_ID = %(USER_ID)s
                  AND FEATURE = 'receipt_ai'
                  AND CRE_DT LIKE %(CRE_MONTH)s
                """,
                {"CRE_MONTH": f"{month_prefix}%", "USER_ID": user_id},
            )
            return {
                "total": self.format_usage_row(rows[0] if rows else {}),
                "today": self.format_usage_row(today_rows[0] if today_rows else {}),
                "month": self.format_usage_row(month_rows[0] if month_rows else {}),
            }
        except Exception:
            return {
                "total": self.format_usage_row({}),
                "today": self.format_usage_row({}),
                "month": self.format_usage_row({}),
            }

    def format_usage_row(self, row):
        return {
            "requestCount": int_value(row_value(row, "requestCount", "requestcount", default=0)),
            "promptTokens": int_value(row_value(row, "promptTokens", "prompttokens", default=0)),
            "outputTokens": int_value(row_value(row, "outputTokens", "outputtokens", default=0)),
            "totalTokens": int_value(row_value(row, "totalTokens", "totaltokens", default=0)),
            "cachedTokens": int_value(row_value(row, "cachedTokens", "cachedtokens", default=0)),
            "thoughtsTokens": int_value(row_value(row, "thoughtsTokens", "thoughtstokens", default=0)),
        }

    def save_settings(self, body, user_id):
        """アプリ設定を履歴型で新規行として保存する。"""
        rows = self.database.select(
            """
            SELECT BUT_CAT FROM setting_table
            WHERE DEL_FLAG = 0
              AND CRE_USER_ID = %(USER_ID)s
            ORDER BY id DESC
            LIMIT 1
            """,
            {"USER_ID": user_id},
        )
        extra = parse_json_object(row_value(rows[0], "BUT_CAT", "but_cat")) if rows else {}
        extra.update({
            "largeTextMode": bool(body.get("largeTextMode", False)),
            "colorTheme": body.get("colorTheme") or "kakeibo",
            "language": body.get("language") or "ja",
        })
        ymd, hms = now_ymd_hms()
        self.database.insert(
            """
            INSERT INTO setting_table (
              CRE_PROG, UPD_PROG,
              BUT_ON_OFF, BUT_CAT, BUDGET_PERIOD,
              DAY_DARK, AUTO_DAY_DARK, SUNRISE, SUNSET,
              CRE_DT, CRE_TM, UPD_DT, UPD_TM, CRE_USER_ID, UPD_USER_ID, DEL_FLAG
            ) VALUES (
              %(CRE_PROG)s, %(UPD_PROG)s,
              %(BUT_ON_OFF)s, %(BUT_CAT)s, %(BUDGET_PERIOD)s,
              %(DAY_DARK)s, %(AUTO_DAY_DARK)s, %(SUNRISE)s, %(SUNSET)s,
              %(CRE_DT)s, %(CRE_TM)s, %(UPD_DT)s, %(UPD_TM)s, %(USER_ID)s, %(USER_ID)s, %(DEL_FLAG)s
            )
            """,
            {
                "CRE_PROG": "app_settings",
                "UPD_PROG": "app_settings",
                "BUT_ON_OFF": "1" if body.get("budgetEnabled") else "0",
                "BUT_CAT": json.dumps(extra),
                "BUDGET_PERIOD": body.get("budgetPeriod") or "month",
                "DAY_DARK": "1" if body.get("darkMode") else "0",
                "AUTO_DAY_DARK": "1" if body.get("autoDark") else "0",
                "SUNRISE": body.get("sunrise") or "06:00",
                "SUNSET": body.get("sunset") or "18:00",
                "CRE_DT": ymd,
                "CRE_TM": hms,
                "UPD_DT": ymd,
                "UPD_TM": hms,
                "USER_ID": user_id,
                "DEL_FLAG": 0,
            },
        )

    def get_dashboard_layout(self, user_id):
        """設定JSONに保存されたダッシュボード配置を取得する。"""
        rows = self.database.select(
            """
            SELECT BUT_CAT FROM setting_table
            WHERE DEL_FLAG = 0
              AND CRE_USER_ID = %(USER_ID)s
            ORDER BY id DESC
            LIMIT 1
            """,
            {"USER_ID": user_id},
        )
        extra = parse_json_object(row_value(rows[0], "BUT_CAT", "but_cat")) if rows else {}
        return extra.get("dashboardLayout")

    def save_dashboard_layout(self, layout, user_id):
        """既存設定を引き継ぎながらダッシュボード配置だけを保存する。"""
        rows = self.database.select(
            """
            SELECT * FROM setting_table
            WHERE DEL_FLAG = 0
              AND CRE_USER_ID = %(USER_ID)s
            ORDER BY id DESC
            LIMIT 1
            """,
            {"USER_ID": user_id},
        )
        last = rows[0] if rows else {}
        extra = parse_json_object(row_value(last, "BUT_CAT", "but_cat"))
        extra["dashboardLayout"] = layout
        ymd, hms = now_ymd_hms()
        self.database.insert(
            """
            INSERT INTO setting_table (
              CRE_PROG, UPD_PROG, BUT_ON_OFF, BUT_CAT, BUDGET_PERIOD,
              DAY_DARK, AUTO_DAY_DARK, SUNRISE, SUNSET,
              CRE_DT, CRE_TM, UPD_DT, UPD_TM, CRE_USER_ID, UPD_USER_ID, DEL_FLAG
            ) VALUES (
              %(CRE_PROG)s, %(UPD_PROG)s, %(BUT_ON_OFF)s, %(BUT_CAT)s, %(BUDGET_PERIOD)s,
              %(DAY_DARK)s, %(AUTO_DAY_DARK)s, %(SUNRISE)s, %(SUNSET)s,
              %(CRE_DT)s, %(CRE_TM)s, %(UPD_DT)s, %(UPD_TM)s, %(USER_ID)s, %(USER_ID)s, 0
            )
            """,
            {
                "CRE_PROG": "dashboard_layout",
                "UPD_PROG": "dashboard_layout",
                "BUT_ON_OFF": row_value(last, "BUT_ON_OFF", default="0"),
                "BUT_CAT": json.dumps(extra),
                "BUDGET_PERIOD": row_value(last, "BUDGET_PERIOD", default="month"),
                "DAY_DARK": row_value(last, "DAY_DARK", default="0"),
                "AUTO_DAY_DARK": row_value(last, "AUTO_DAY_DARK", default="0"),
                "SUNRISE": row_value(last, "SUNRISE", default="06:00"),
                "SUNSET": row_value(last, "SUNSET", default="18:00"),
                "CRE_DT": ymd,
                "CRE_TM": hms,
                "UPD_DT": ymd,
                "UPD_TM": hms,
                "USER_ID": user_id,
            },
        )
