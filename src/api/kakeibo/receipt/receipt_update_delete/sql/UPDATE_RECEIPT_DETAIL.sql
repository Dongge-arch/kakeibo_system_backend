-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

UPDATE RECEIPT_DETAIL
SET
UPD_PROG = %(UPD_PROG)s,
UPD_DT = %(UPD_DT)s,
UPD_TM = %(UPD_TM)s,
UPD_USER_ID = %(UPD_USER_ID)s,
DEL_FLAG = 1
WHERE RET_ID = %(RET_ID)s
AND CRE_USER_ID = %(CRE_USER_ID)s
AND DEL_FLAG = 0;
