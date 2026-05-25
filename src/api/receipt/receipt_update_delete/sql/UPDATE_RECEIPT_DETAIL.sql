-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

UPDATE receipt_detail
SET 
UPD_PROG = :UPD_PROG,
UPD_DT = :UPD_DT,
UPD_TM = :UPD_TM,
del_flag = 1    
WHERE RET_ID = :receipt_id
AND del_flag = 0;