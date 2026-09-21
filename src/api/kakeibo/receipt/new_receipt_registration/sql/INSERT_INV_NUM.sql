-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

INSERT INTO INVOICE_REGISTRATION (
    CRE_PROG, -- 登録プログラム
    UPD_PROG, -- 更新プログラム
    INV_REG_NUM, -- インボイス登録番号
    SUP_NAME, -- 取引先名
    TAX_FLAG, -- 税区分
    CRE_DT, -- 登録日
    CRE_TM, -- 登録時刻
    UPD_DT, -- 更新日
    UPD_TM, -- 更新時刻
    CRE_USER_ID, -- 登録ユーザーID
    UPD_USER_ID, -- 更新ユーザーID
    DEL_FLAG -- 削除フラグ
) VALUES (
    %(CRE_PROG)s,
    %(UPD_PROG)s,
    %(INV_REG_NUM)s,
    %(SUP_NAME)s,
    %(TAX_FLAG)s,
    %(CRE_DT)s,
    %(CRE_TM)s,
    %(UPD_DT)s,
    %(UPD_TM)s,
    %(CRE_USER_ID)s,
    %(UPD_USER_ID)s,
    %(DEL_FLAG)s
);
