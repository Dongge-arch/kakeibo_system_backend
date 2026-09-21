-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

INSERT INTO RECEIPT_DETAIL (
    CRE_PROG, -- 登録プログラム
    UPD_PROG, -- 更新プログラム
    RET_ID, -- 領収書ID
    ITEM_NAME, -- 領収書明細品目名
    CAT1, -- 領収書明細大分類
    CAT2, -- 領収書明細中分類
    TAX_RATE,  -- 領収書明細税率
    QTY, -- 領収書明細数量
    UT, -- 領収書明細単価
    UT_PRE, -- 領収書明細単価（税抜）
    TO_PRE, -- 領収書明細合計金額（税抜）
    UT_TAX_EXCLUDED, -- 領収書明細単価（税抜）
    TO_TAX_EXCLUDED, -- 領収書明細合計金額（税抜）
    UT_TAX_INCLUDED, -- 領収書明細単価（税込）
    TO_TAX_INCLUDED, -- 領収書明細合計金額（税込）
    CRE_DT, -- 登録日
    CRE_TM, -- 登録時刻
    UPD_DT, -- 更新日
    UPD_TM, -- 更新時刻
    CRE_USER_ID, -- 登録ユーザーID
    UPD_USER_ID -- 更新ユーザーID
) VALUES (
    %(CRE_PROG)s,
    %(UPD_PROG)s,
    %(RET_ID)s,
    %(ITEM_NAME)s,
    %(CAT1)s,
    %(CAT2)s,
    %(TAX_RATE)s,
    %(QTY)s,
    %(UT)s,
    %(UT_PRE)s,
    %(TO_PRE)s,
    %(UT_TAX_EXCLUDED)s,
    %(TO_TAX_EXCLUDED)s,
    %(UT_TAX_INCLUDED)s,
    %(TO_TAX_INCLUDED)s,
    %(CRE_DT)s,
    %(CRE_TM)s,
    %(UPD_DT)s,
    %(UPD_TM)s,
    %(CRE_USER_ID)s,
    %(UPD_USER_ID)s
);
