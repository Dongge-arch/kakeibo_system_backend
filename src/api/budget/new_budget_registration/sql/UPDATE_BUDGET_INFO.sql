-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

UPDATE budget_info
SET 
UPD_PROG = :UPD_PROG,
BUT_AMT = :BUT_AMT,
UPD_DT = :UPD_DT,
UPD_TM = :UPD_TM   
WHERE 
CAT1 = :CAT1
AND
CAT2 = :CAT2
AND 
del_flag = 0;