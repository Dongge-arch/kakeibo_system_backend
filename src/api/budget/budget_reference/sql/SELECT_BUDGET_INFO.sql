-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

SELECT 
CAT1 as category1,
CAT2 as category2,
BUT_AMT as budgetAmount
FROM 
budget_info
WHERE
CAT1 = :CAT1
AND
CAT2 = :CAT2
AND
DEL_FLAG = 0