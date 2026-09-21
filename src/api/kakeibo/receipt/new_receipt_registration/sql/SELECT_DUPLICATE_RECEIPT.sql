-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

SELECT RET_ID
FROM RECEIPT_INFO
WHERE SUP_NAME = %(SUP_NAME)s
  AND RET_DT = %(RET_DT)s -- 領収書日付
  AND RET_TM = %(RET_TM)s -- 領収書時刻
  AND TOA_PRICE = %(TOA_PRICE)s -- 領収書合計金額
  AND CRE_USER_ID = %(CRE_USER_ID)s -- ユーザーID
  AND DEL_FLAG = 0 -- 抹消フラグ
LIMIT 1
