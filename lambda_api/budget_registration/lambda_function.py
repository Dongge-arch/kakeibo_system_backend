from src.api.budget.new_budget_registration.newBudgetRegistration import NewBudgetRegistration

def lambda_handler(event, context):
    return NewBudgetRegistration().lambda_handler(event, context)
