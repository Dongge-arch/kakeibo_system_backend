-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

INSERT INTO receipt_info (
    CRE_PROG, -- 登録プログラム
    UPD_PROG, -- 更新プログラム
    RET_ID, -- 領収書ID
    INV_REG_NUM, -- インボイス登録番号
    SUP_NAME, -- 取引先名
    RET_DT, -- 領収書日付
    RET_TM, -- 領収書時刻
    TAX_FLAG, -- 税区分
    RET_DET_CNT, -- 領収書明細件数
    TOA_PRICE, -- 領収書合計金額
    CRE_DT, -- 登録日
    CRE_TM, -- 登録時刻
    UPD_DT, -- 更新日
    UPD_TM, -- 更新時刻
    CRE_USER_ID, -- 登録ユーザーID
    UPD_USER_ID -- 更新ユーザーID
)
VALUES (
    %(CRE_PROG)s,
    %(UPD_PROG)s,
    %(RET_ID)s,
    %(INV_REG_NUM)s,
    %(SUP_NAME)s,
    %(RET_DT)s,
    %(RET_TM)s,
    %(TAX_FLAG)s,
    %(RET_DET_CNT)s,
    %(TOA_PRICE)s,
    %(CRE_DT)s,
    %(CRE_TM)s,
    %(UPD_DT)s,
    %(UPD_TM)s,
    %(USER_ID)s,
    %(USER_ID)s
)
