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
    TO_PRE,
    UT_TAX_EXCLUDED,
    TO_TAX_EXCLUDED,
    UT_TAX_INCLUDED,
    TO_TAX_INCLUDED
) VALUES (
    :RET_ID,
    :ITEM_NAME,
    :CAT1,
    :CAT2,
    :TAX_RATE,
    :QTY,
    :UT,
    :UT_PRE,
    :TO_PRE,
    :UT_TAX_EXCLUDED,
    :TO_TAX_EXCLUDED,
    :UT_TAX_INCLUDED,
    :TO_TAX_INCLUDED
);
