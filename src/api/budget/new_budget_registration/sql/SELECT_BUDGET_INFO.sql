-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

SELECT 
* 
FROM 
budget_info 
WHERE 
CAT1 = %(CAT1)s 
AND 
CAT2 = %(CAT2)s
AND
CRE_USER_ID = %(USER_ID)s
AND
DEL_FLAG = 0
