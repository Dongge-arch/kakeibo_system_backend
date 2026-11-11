from src.api.kakeibo.expense_source.expenseSourceApi import ExpenseSourceApi


def lambda_handler(event, context):
    event["body"] = {"action": "list"}
    return ExpenseSourceApi().lambda_handler(event, context)
