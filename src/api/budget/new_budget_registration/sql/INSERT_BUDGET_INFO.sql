-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 Home Kakeibo System Contributors

INSERT INTO budget_info(
    CRE_PROG,
    UPD_PROG,
    CAT1,
    CAT2,
    BUT_AMT,
    CRE_DT,
    CRE_TM,
    UPD_DT,
    UPD_TM,
    DEL_FLAG
) VALUES (
    :CRE_PROG,
    :UPD_PROG,
    :CAT1,
    :CAT2,
    :BUT_AMT,
    :CRE_DT,
    :CRE_TM,
    :UPD_DT,
    :UPD_TM,
    :DEL_FLAG
)
