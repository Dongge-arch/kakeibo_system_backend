-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

UPDATE budget_info
SET 
UPD_PROG = %(UPD_PROG)s,
BUT_AMT = %(BUT_AMT)s,
UPD_DT = %(UPD_DT)s,
UPD_TM = %(UPD_TM)s,
UPD_USER_ID = %(USER_ID)s   
WHERE 
CAT1 = %(CAT1)s
AND
CAT2 = %(CAT2)s
AND 
CRE_USER_ID = %(USER_ID)s
AND 
del_flag = 0;
