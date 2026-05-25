-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

SELECT * FROM invoice_registration WHERE INV_REG_NUM = :INV_REG_NUM AND DEL_FLAG = 0;