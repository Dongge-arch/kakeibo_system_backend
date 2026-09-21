# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import json

from src.common.api_utils import now_ymd_hms, parse_json_object
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


class AppSettingsBase(BaseRestApi):
    """アプリ設定とダッシュボード配置の共通DB操作。"""

    def __init__(self, db_path=None):
        """
        クラスを初期化する。

        Args:
            db_path (Any): 旧呼び出し互換のためのDB指定。

        Returns:
            None: 戻り値なし。
        """
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)

    def validate_body(self, request_dict):
        """
        リクエスト本文を検証する。

        Args:
            request_dict (Any): API呼び出し時のリクエスト情報。

        Returns:
            Any: 処理結果。
        """
        return super().validate_body(request_dict)

    def get_settings(self, user_id):
        """
        最新のアプリ設定を画面用の項目名で取得する。

        Args:
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        rows = self.database.select(
            self.database.read_sql("SELECT_SETTING_TABLE", location=__file__),
            {"CRE_USER_ID": user_id},
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
            "autoLinkageEnabled": bool(extra.get("autoLinkageEnabled", False)),
            "colorTheme": extra.get("colorTheme", "kakeibo"),
            "language": extra.get("language", "ja"),
        }
        settings["aiUsageSummary"] = self.get_ai_usage_summary(user_id)
        return settings

    def get_ai_usage_summary(self, user_id):
        """
        設定画面向けにAI利用量の合計を返す。

        Args:
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        try:
            ymd, _ = now_ymd_hms()
            month_prefix = ymd[:6]
            rows = self.database.select(
                self.database.read_sql("SELECT_AI_USAGE_LOG", location=__file__),
                {"CRE_USER_ID": user_id},
            )
            today_rows = self.database.select(
                self.database.read_sql("SELECT_AI_USAGE_LOG_02", location=__file__),
                {"CRE_DT": ymd, "CRE_USER_ID": user_id},
            )
            month_rows = self.database.select(
                self.database.read_sql("SELECT_AI_USAGE_LOG_03", location=__file__),
                {"CRE_DT": f"{month_prefix}%", "CRE_USER_ID": user_id},
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
        """
        format_usage_rowの処理を実行する。

        Args:
            row (Any): rowの値。

        Returns:
            Any: 処理結果。
        """
        return {
            "requestCount": int_value(row_value(row, "requestCount", "requestcount", default=0)),
            "promptTokens": int_value(row_value(row, "promptTokens", "prompttokens", default=0)),
            "outputTokens": int_value(row_value(row, "outputTokens", "outputtokens", default=0)),
            "totalTokens": int_value(row_value(row, "totalTokens", "totaltokens", default=0)),
            "cachedTokens": int_value(row_value(row, "cachedTokens", "cachedtokens", default=0)),
            "thoughtsTokens": int_value(row_value(row, "thoughtsTokens", "thoughtstokens", default=0)),
        }

    def save_settings(self, body, user_id):
        """
        アプリ設定を履歴型で新規行として保存する。

        Args:
            body (Any): リクエスト本文。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        rows = self.database.select(
            self.database.read_sql("SELECT_SETTING_TABLE_02", location=__file__),
            {"CRE_USER_ID": user_id},
        )
        extra = parse_json_object(row_value(rows[0], "BUT_CAT", "but_cat")) if rows else {}
        extra.update({
            "largeTextMode": bool(body.get("largeTextMode", False)),
            "autoLinkageEnabled": bool(body.get("autoLinkageEnabled", False)),
            "colorTheme": body.get("colorTheme") or "kakeibo",
            "language": body.get("language") or "ja",
        })
        ymd, hms = now_ymd_hms()
        self.database.insert(
            self.database.read_sql("INSERT_SETTING_TABLE", location=__file__),
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
                "CRE_USER_ID": user_id,
                "UPD_USER_ID": user_id,
                "DEL_FLAG": 0,
            },
        )

    def get_dashboard_layout(self, user_id):
        """
        設定JSONに保存されたダッシュボード配置を取得する。

        Args:
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        rows = self.database.select(
            self.database.read_sql("SELECT_SETTING_TABLE_03", location=__file__),
            {"CRE_USER_ID": user_id},
        )
        extra = parse_json_object(row_value(rows[0], "BUT_CAT", "but_cat")) if rows else {}
        return extra.get("dashboardLayout")

    def save_dashboard_layout(self, layout, user_id):
        """
        既存設定を引き継ぎながらダッシュボード配置だけを保存する。

        Args:
            layout (Any): layoutの値。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        rows = self.database.select(
            self.database.read_sql("SELECT_SETTING_TABLE_04", location=__file__),
            {"CRE_USER_ID": user_id},
        )
        last = rows[0] if rows else {}
        extra = parse_json_object(row_value(last, "BUT_CAT", "but_cat"))
        extra["dashboardLayout"] = layout
        ymd, hms = now_ymd_hms()
        self.database.insert(
            self.database.read_sql("INSERT_SETTING_TABLE_02", location=__file__),
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
                "CRE_USER_ID": user_id,
                "UPD_USER_ID": user_id,
            },
        )
