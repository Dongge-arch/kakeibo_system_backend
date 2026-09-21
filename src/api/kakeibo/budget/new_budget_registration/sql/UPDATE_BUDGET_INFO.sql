-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

UPDATE BUDGET_INFO
SET
UPD_PROG = %(UPD_PROG)s,
BUT_AMT = %(BUT_AMT)s,
UPD_DT = %(UPD_DT)s,
UPD_TM = %(UPD_TM)s,
UPD_USER_ID = %(UPD_USER_ID)s
WHERE
CAT1 = %(CAT1)s
AND
CAT2 = %(CAT2)s
AND
CRE_USER_ID = %(CRE_USER_ID)s
AND
DEL_FLAG = 0;
