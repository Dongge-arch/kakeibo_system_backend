-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

INSERT INTO invoice_registration (
    CRE_PROG,
    UPD_PROG,
    INV_REG_NUM,
    SUP_NAME,
    TAX_FLAG,
    CRE_DT,
    CRE_TM,
    UPD_DT,
    UPD_TM,
    DEL_FLAG
) VALUES (
    :CRE_PROG,
    :UPD_PROG,
    :INV_REG_NUM,
    :SUP_NAME,
    :TAX_FLAG,
    :CRE_DT,
    :CRE_TM,
    :UPD_DT,
    :UPD_TM,
    :DEL_FLAG
);
