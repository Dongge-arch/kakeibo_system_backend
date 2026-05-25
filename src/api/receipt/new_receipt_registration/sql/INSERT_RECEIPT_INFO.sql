-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

INSERT INTO receipt_info (
    RET_ID,
    INV_REG_NUM,
    SUP_NAME,
    RET_DT,
    RET_TM,
    TAX_FLAG,
    RET_DET_CNT,
    TOA_PRICE
)
VALUES (
    :RET_ID,
    :INV_REG_NUM,
    :SUP_NAME,
    :RET_DT,
    :RET_TM,
    :TAX_FLAG,
    :RET_DET_CNT,
    :TOA_PRICE
)