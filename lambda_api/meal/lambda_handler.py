"""献立 API の HTTP ルーティング。"""

import json

from src.api.meal.recipeReference import RecipeReference
from src.api.meal.recipeRegistration import RecipeRegistration
from src.api.meal.recipeUpdateDelete import RecipeUpdateDelete
from src.api.meal.ingredientMasterReference import IngredientMasterReference
from src.api.meal.shoppingListExport import ShoppingListExport
from src.api.meal.shoppingListPreview import ShoppingListPreview
from src.api.meal.shoppingPlanReference import ShoppingPlanReference
from src.api.meal.shoppingPlanUpdate import ShoppingPlanUpdate


def lambda_handler(event, context):
    """
    献立 HTTP リクエストを該当する API 操作へ渡す。

    Args:
        event (dict): API Gateway イベント。
        context: Lambda コンテキスト。

    Returns:
        dict: HTTP レスポンス。
    """
    path = (event.get("rawPath") or event.get("path") or "").rstrip("/")
    method = (event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod") or "").upper()
    # ANY ルートで Lambda へ到達する CORS プリフライトは認証や業務ルーティングの前に完了させる。
    if method == "OPTIONS":
        return {"statusCode": 204, "body": ""}
    raw = event.get("body") or {}
    body = json.loads(raw) if isinstance(raw, str) else dict(raw)
    parts = path.strip("/").split("/")
    if parts and parts[0] == "kitchen":
        parts[0] = "meal"
    if parts == ["meal", "recipes"] and method == "GET":
        api = RecipeReference
    elif parts == ["meal", "recipes"] and method == "POST":
        body["action"] = "save_recipe"
        recipe = body.get("recipe")
        api = RecipeUpdateDelete if isinstance(recipe, dict) and recipe.get("recipeId") else RecipeRegistration
    elif len(parts) == 3 and parts[:2] == ["meal", "recipes"] and method == "DELETE":
        body.update(action="delete_recipe", recipeId=parts[2])
        api = RecipeUpdateDelete
    elif parts == ["meal", "plan"] and method == "GET":
        api = ShoppingPlanReference
    elif parts == ["meal", "plan"] and method == "PUT":
        api = ShoppingPlanUpdate
    elif parts == ["meal", "ingredient-master"] and method == "GET":
        api = IngredientMasterReference
    elif parts == ["meal", "shopping", "preview"] and method == "POST":
        api = ShoppingListPreview
    elif parts == ["meal", "shopping", "export"] and method == "POST":
        api = ShoppingListExport
    else:
        return {"statusCode": 404, "headers": {"Content-Type": "application/json"}, "body": '{"errorMessage":"操作が見つかりません。"}'}
    return api().lambda_handler({**event, "body": body}, context)
