# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import csv
import os

ERROR_CONST_CSV_FILENAME = "errorcode.csv"
ERROR_CONST_CSV_PATH = os.path.join(
    os.path.dirname(__file__),
    ERROR_CONST_CSV_FILENAME,
)
ERROR_CONST_CSV_ENCODING = "utf8"

ERROR_DICT = {}

with open(ERROR_CONST_CSV_PATH, "r", encoding=ERROR_CONST_CSV_ENCODING) as f:
    reader = csv.reader(f)
    for i, row in enumerate(reader):
        if i == 0 or not row or len(row) < 2:
            continue

        ERROR_DICT[row[0]] = {
            "errorCode": row[0],
            "errorMessage": row[1],
        }
