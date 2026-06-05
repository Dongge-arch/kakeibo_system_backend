-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

INSERT INTO kakeibo.auto_csv_input_cont (
    CRE_PROG,
    UPD_PROG,
    INV_REG_NUM,
    RET_CONT,
    RET_DT,
    RET_TM,
    AUTO_INPUT_STATUS,
    CRE_DT,
    CRE_TM,
    UPD_DT,
    UPD_TM,
    CRE_USER_ID,
    UPD_USER_ID,
    DEL_FLAG
)
SELECT
    %(CRE_PROG)s,
    %(UPD_PROG)s,
    %(INV_REG_NUM)s,
    %(RET_CONT)s,
    %(RET_DT)s,
    %(RET_TM)s,
    %(AUTO_INPUT_STATUS)s,
    %(CRE_DT)s,
    %(CRE_TM)s,
    %(UPD_DT)s,
    %(UPD_TM)s,
    %(USER_ID)s,
    %(USER_ID)s,
    %(DEL_FLAG)s
WHERE NOT EXISTS (
    SELECT 1
    FROM kakeibo.auto_csv_input_cont
    WHERE INV_REG_NUM = %(INV_REG_NUM)s
      AND RET_DT = %(RET_DT)s
      AND RET_TM = %(RET_TM)s
      AND CRE_USER_ID = %(USER_ID)s
      AND AUTO_INPUT_STATUS = %(AUTO_INPUT_STATUS)s
      AND DEL_FLAG = 0
);
