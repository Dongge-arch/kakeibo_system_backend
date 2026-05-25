# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""
filename datetime.py
Date    2024-09-01
"""

from enum import Enum

# 曜日
MONDAY = 0      # 月曜日
TUESDAY = 1     # 火曜日
WEDNESDAY = 2   # 水曜日
THURSDAY = 3    # 木曜日
FRIDAY = 4      # 金曜日
SATURDAY = 5    # 土曜日
SUNDAY = 6      # 日曜日

# 日付のフォーマット
DT_FORMAT_MD = r"%m%d"
DT_FORMAT_YMD = r"%Y%m%d"
DT_FORMAT_Y_M_D = r"%Y-%m-%d"
DT_FORMAT_YMDH24MSF6 = r"%Y%m%d%H%M%S%f"

# 時刻のフォーマット
DT_FORMAT_HHMMSS_IF = r"%H:%M:%S"
DT_FORMAT_HHMMSS_DB = r"%H%M%S"

# 日時フォーマット_DB
DATE_TIME_FORMAT_DB = r"%Y%m%d%H%M%S%f"

# 日時フォーマット_IF
DATE_TIME_FORMAT_IF = r"%Y-%m-%dT%H:%M:%S.%f"

# 日付フォーマット_DB
DATE_FORMAT_DB = r"%Y%m%d"

# 日付フォーマット_IF
DATE_FORMAT_IF = r"%Y-%m-%d"

# 時刻フォーマット_DB
TIME_FORMAT_DB = r"%H%M%S%f"

# 時刻フォーマット_IF
TIME_FORMAT_IF = r"%H:%M:%S.%f"

# 日時フォーマット_IF（正規表現）
TIME_FORMAT_PATTERN_IF = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}$"

# JST
TIME_ZONE_JST = "Asia/Tokyo"