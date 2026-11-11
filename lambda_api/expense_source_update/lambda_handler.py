from src.api.kakeibo.expense_source.expenseSourceApi import ExpenseSourceApi


def lambda_handler(event, context):
    return ExpenseSourceApi().lambda_handler(event, context)
