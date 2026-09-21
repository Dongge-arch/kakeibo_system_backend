"""入金の新規登録Lambda。"""

from src.api.kakeibo.income.new_income_registration.newIncomeRegistration import NewIncomeRegistration

def lambda_handler(event, context):
    return NewIncomeRegistration().lambda_handler(event, context)
