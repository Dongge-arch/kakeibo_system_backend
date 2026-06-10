UPDATE auto_csv_input_info
SET UPD_PROG = 'AutoLinkageApi',
    SUP_NAME = %(SUP_NAME)s,
    INV_REG_NUM = %(INV_REG_NUM)s,
    LOGIN_ID_1 = %(LOGIN_ID_1)s,
    LOGIN_PW_1 = %(LOGIN_PW_1)s,
    ENABLED = %(ENABLED)s,
    CONNECTION_TYPE = %(CONNECTION_TYPE)s,
    UPD_DT = %(UPD_DT)s,
    UPD_TM = %(UPD_TM)s,
    UPD_USER_ID = %(USER_ID)s
WHERE id = %(id)s
    AND CRE_USER_ID = %(USER_ID)s
    AND DEL_FLAG = 0