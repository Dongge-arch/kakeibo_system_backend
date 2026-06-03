-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors


SELECT RET_ID as receipt_id
FROM receipt_info
WHERE RET_ID LIKE %(receipt_id_date)s
  AND CRE_USER_ID = %(USER_ID)s
ORDER BY RET_ID DESC
LIMIT 1;
