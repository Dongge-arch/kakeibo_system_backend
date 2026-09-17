SELECT DISTINCT
    re.RET_ID,
    re.INV_REG_NUM,
    re.SUP_NAME,
    re.RET_DT,
    re.RET_TM,
    re.TAX_FLAG,
    re.TOA_PRICE
FROM receipt_info re
WHERE re.DEL_FLAG = 0
    AND re.CRE_USER_ID = %(user_id)s