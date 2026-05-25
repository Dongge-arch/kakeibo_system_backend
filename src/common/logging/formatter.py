# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""ログ時刻の表示形式を調整するformatter。"""
import logging
from datetime import datetime, timedelta, timezone


class DatetimeFormatter(logging.Formatter):
    """
    ログ出力の時刻をUTCからJSTに変更するクラス
    """

    def formatTime(self, record: logging.LogRecord, datefmt=None) -> str:
        """
        ログ時刻をUTCからJSTに変換する
        """
        jst = timezone(timedelta(hours=+9), 'JST')
        dt = datetime.fromtimestamp(record.created, jst)
        return dt.strftime('%Y-%m-%d %H:%M:%S.%f')

    def format(self, record):
        """request_idの欠損を補完してから標準formatterへ委譲する。"""
        if not hasattr(record, "request_ids"):
            record.request_ids = "-"
        return super().format(record)
