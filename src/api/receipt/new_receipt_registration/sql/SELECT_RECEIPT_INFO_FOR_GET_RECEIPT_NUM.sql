 SELECT RET_ID
                FROM receipt_info
                WHERE INV_REG_NUM = %(INV_REG_NUM)s
                  AND DEL_FLAG = 0
                  AND CRE_USER_ID = %(USER_ID)s
                LIMIT 1