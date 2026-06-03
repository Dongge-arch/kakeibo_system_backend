-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

INSERT INTO receipt_info (
    CRE_PROG,
    UPD_PROG,
    RET_ID,
    INV_REG_NUM,
    SUP_NAME,
    RET_DT,
    RET_TM,
    TAX_FLAG,
    RET_DET_CNT,
    TOA_PRICE,
    CRE_DT,
    CRE_TM,
    UPD_DT,
    UPD_TM,
    CRE_USER_ID,
    UPD_USER_ID
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
