-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

INSERT INTO budget_info(
    CRE_PROG,
    UPD_PROG,
    CAT1,
    CAT2,
    BUT_AMT,
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
    %(CAT1)s,
    %(CAT2)s,
    %(BUT_AMT)s,
    %(CRE_DT)s,
    %(CRE_TM)s,
    %(UPD_DT)s,
    %(UPD_TM)s,
    %(USER_ID)s,
    %(USER_ID)s,
    %(DEL_FLAG)s
)
