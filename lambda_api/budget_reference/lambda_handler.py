from src.api.kakeibo.budget.budget_reference.budgetReference import BudgetReference

def lambda_handler(event, context):
    return BudgetReference().lambda_handler(event, context)
