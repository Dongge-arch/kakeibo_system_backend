SELECT * FROM auto_csv_input_info
            WHERE CRE_USER_ID = %(USER_ID)s
              AND DEL_FLAG = 0
              AND (CONNECTION_TYPE = %(CONNECTION_TYPE)s OR UPPER(SUP_NAME) = %(CONNECTION_TYPE)s)
            ORDER BY id DESC
            LIMIT 1