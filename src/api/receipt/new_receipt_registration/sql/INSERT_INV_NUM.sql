-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

INSERT INTO invoice_registration (
    CRE_PROG,
    UPD_PROG,
    INV_REG_NUM,
    SUP_NAME,
    TAX_FLAG,
    CRE_DT,
    CRE_TM,
    UPD_DT,
    UPD_TM,
    CRE_USER_ID,
    UPD_USER_ID,
    DEL_FLAG
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
    %(USER_ID)s,
    %(USER_ID)s,
    %(DEL_FLAG)s
);
