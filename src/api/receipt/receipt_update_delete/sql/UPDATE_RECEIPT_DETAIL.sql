-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

UPDATE receipt_detail
SET 
UPD_PROG = %(UPD_PROG)s,
UPD_DT = %(UPD_DT)s,
UPD_TM = %(UPD_TM)s,
del_flag = 1    
WHERE RET_ID = %(receipt_id)s
AND del_flag = 0;