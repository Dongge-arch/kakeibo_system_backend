            UPDATE auto_input_info
            SET LAST_LOGIN_STATUS = %(STATUS)s, LAST_LOGIN_DT = %(LAST_LOGIN_DT)s, LAST_LOGIN_TM = %(LAST_LOGIN_TM)s
            WHERE id = %(id)s AND CRE_USER_ID = %(USER_ID)s AND DEL_FLAG = 0