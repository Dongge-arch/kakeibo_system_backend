-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

SELECT INV_REG_NUM, SUP_NAME, TAX_FLAG
FROM invoice_registration
WHERE INV_REG_NUM = %(INV_REG_NUM)s
  AND CRE_USER_ID = %(USER_ID)s
  AND DEL_FLAG = 0;
