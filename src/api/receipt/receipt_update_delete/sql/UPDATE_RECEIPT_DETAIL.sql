-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

UPDATE receipt_detail
SET 
UPD_PROG = %(UPD_PROG)s,
UPD_DT = %(UPD_DT)s,
UPD_TM = %(UPD_TM)s,
UPD_USER_ID = %(USER_ID)s,
del_flag = 1    
WHERE RET_ID = %(receipt_id)s
AND CRE_USER_ID = %(USER_ID)s
AND del_flag = 0;
