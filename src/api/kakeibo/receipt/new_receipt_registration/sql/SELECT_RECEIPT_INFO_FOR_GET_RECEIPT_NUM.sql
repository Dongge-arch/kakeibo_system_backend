SELECT RET_ID
                FROM RECEIPT_INFO
                WHERE INV_REG_NUM = %(INV_REG_NUM)s
                  AND DEL_FLAG = 0
                  AND CRE_USER_ID = %(CRE_USER_ID)s
                LIMIT 1
