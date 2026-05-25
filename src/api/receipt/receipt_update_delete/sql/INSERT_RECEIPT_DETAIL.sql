-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

INSERT INTO receipt_detail (
    RET_ID,
    ITEM_NAME,
    CAT1,
    CAT2,
    TAX_RATE,
    QTY,
    UT,
    UT_PRE,
    TO_PRE
) VALUES (
    :RET_ID,
    :ITEM_NAME,
    :CAT1,
    :CAT2,
    :TAX_RATE,
    :QTY,
    :UT,
    :UT_PRE,
    :TO_PRE
);