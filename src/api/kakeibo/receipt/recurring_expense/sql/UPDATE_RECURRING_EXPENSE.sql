UPDATE RECURRING_EXPENSE
SET UPD_PROG = 'RecurringExpenseApi',
    RULE_NAME = %(RULE_NAME)s,
    DAY_OF_MONTH = %(DAY_OF_MONTH)s,
    ITEM_NAME = %(ITEM_NAME)s,
    CAT1 = %(CAT1)s,
    CAT2 = %(CAT2)s,
    AMOUNT = %(AMOUNT)s,
    TAX_FLAG = %(TAX_FLAG)s,
    ENABLED = %(ENABLED)s,
    MEMO = %(MEMO)s,
    UPD_DT = %(UPD_DT)s,
    UPD_TM = %(UPD_TM)s,
    UPD_USER_ID = %(UPD_USER_ID)s
WHERE ID = %(ID)s
  AND CRE_USER_ID = %(CRE_USER_ID)s
  AND DEL_FLAG = 0
