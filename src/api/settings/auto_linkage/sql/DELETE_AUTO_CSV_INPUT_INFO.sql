UPDATE auto_csv_input_info
SET DEL_FLAG = 1, ENABLED = 0, UPD_PROG = 'AutoLinkageApi',
    UPD_DT = %(UPD_DT)s, UPD_TM = %(UPD_TM)s, UPD_USER_ID = %(USER_ID)s
WHERE id = %(id)s AND CRE_USER_ID = %(USER_ID)s AND DEL_FLAG = 0