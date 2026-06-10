-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

SELECT RET_ID
FROM receipt_info
WHERE SUP_NAME = %(SUP_NAME)s
  AND RET_DT = %(RET_DT)s
  AND RET_TM = %(RET_TM)s
  AND TOA_PRICE = %(TOA_PRICE)s
  AND CRE_USER_ID = %(USER_ID)s
  AND DEL_FLAG = 0
LIMIT 1
