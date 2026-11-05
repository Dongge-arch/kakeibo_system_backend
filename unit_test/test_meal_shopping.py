"""キッチンのレシピ換算、集約、出力を検証する。"""

from io import BytesIO

from openpyxl import load_workbook

from src.api.meal.mealBase import normalize_recipe
from src.api.meal.recipeReference import RecipeReference
from src.api.meal.shoppingListExport import ShoppingListExport


def service_with_recipes(recipes):
    """DB接続を行わず買い物計算だけを使用する。"""
    service = RecipeReference.__new__(RecipeReference)
    service.list_recipes = lambda user_id: recipes
    return service


def material(item_id, name, amount, unit="g", unit_label="g", supplemental=None):
    """テスト用の材料を作成する。"""
    result = {
        "itemId": item_id,
        "name": name,
        "amount": amount,
        "unit": unit,
        "unitLabel": unit_label,
        "category": "野菜",
        "scalable": True,
        "shoppingRequired": True,
    }
    if supplemental:
        result["supplementalUnit"] = supplemental
    return result


def recipe(recipe_id, name, base_servings, materials, seasonings=None):
    """テスト用のレシピを作成する。"""
    return {
        "recipeId": recipe_id,
        "name": name,
        "baseServings": base_servings,
        "materials": materials,
        "seasonings": seasonings or [],
    }


def test_recipe_accepts_decimal_servings_and_fills_item_id():
    normalized = normalize_recipe({
        "name": "スープ",
        "baseServings": 2.5,
        "cookTimeMin": 20,
        "materials": [{
            "name": "玉ねぎ",
            "amount": 100,
            "unit": "g",
            "unitLabel": "g",
            "category": "野菜",
        }],
    })
    assert normalized["baseServings"] == 2.5
    assert normalized["materials"][0]["itemId"].startswith("item_")


def test_package_capacity_aggregates_before_rounding():
    supplemental = {
        "amount": 1,
        "unit": "bag",
        "unitLabel": "袋",
        "capacity": {"amount": 750, "unit": "g", "unitLabel": "g"},
    }
    service = service_with_recipes([
        recipe("a", "パンA", 2, [material("flour", "薄力粉", 400, supplemental=supplemental)]),
        recipe("b", "パンB", 4, [material("flour", "薄力粉", 400, supplemental=supplemental)]),
    ])
    preview = service.build_shopping_preview("user", [
        {"recipeId": "a", "targetServings": 2, "cookCount": 1},
        {"recipeId": "b", "targetServings": 4, "cookCount": 1},
    ])
    flour = preview["materialGroups"][0]["items"][0]
    assert flour["calculatedAmount"] > 1
    assert flour["purchaseAmount"] == 2
    assert flour["unitLabel"] == "袋"


def test_supplemental_unit_and_seasonings_are_aggregated():
    onion = material(
        "onion",
        "玉ねぎ",
        100,
        supplemental={"amount": 1, "unit": "count", "unitLabel": "個"},
    )
    salt = {
        **material("salt", "塩", 1, unit="tsp", unit_label="小さじ"),
        "category": "調味料",
        "usage": "仕上げ",
    }
    service = service_with_recipes([
        recipe("a", "料理A", 2, [onion], [salt]),
        recipe("b", "料理B", 2, [onion], [salt]),
    ])
    preview = service.build_shopping_preview("user", [
        {"recipeId": "a", "targetServings": 4, "cookCount": 1},
        {"recipeId": "b", "targetServings": 2, "cookCount": 1},
    ])
    onion_row = preview["materialGroups"][0]["items"][0]
    assert onion_row["purchaseAmount"] == 3
    assert len(preview["seasonings"]) == 1
    assert {source["recipeName"] for source in preview["seasonings"][0]["sources"]} == {"料理A", "料理B"}


def test_xlsx_export_contains_material_and_inventory_sheets():
    preview = {
        "materialGroups": [{
            "category": "野菜",
            "items": [{
                "name": "玉ねぎ",
                "purchaseAmount": 2,
                "unitLabel": "個",
                "sources": [{"recipeName": "スープ"}],
            }],
        }],
        "seasonings": [{
            "name": "塩",
            "sources": [{"recipeName": "スープ", "usage": "仕上げ"}],
        }],
        "selections": [{"recipeName": "スープ", "targetServings": 4, "cookCount": 1}],
    }
    content = ShoppingListExport.build_xlsx(preview)
    workbook = load_workbook(BytesIO(content))
    assert workbook.sheetnames == ["買い物リスト", "調味料・在庫確認", "選択したレシピ"]
    assert workbook["買い物リスト"]["C2"].value == "玉ねぎ"
    assert workbook["調味料・在庫確認"]["B2"].value == "塩"


def test_manual_shopping_items_are_normalized_and_exported():
    service = service_with_recipes([])
    manual = service.normalize_manual_items([
        {"manualId": "daily", "name": "キッチンペーパー", "quantity": "2ロール", "category": "日用品"},
    ])
    assert manual[0]["rowId"] == "manual-daily"
    preview = {"materialGroups": [], "seasonings": [], "selections": [], "manualItems": manual}
    workbook = load_workbook(BytesIO(ShoppingListExport.build_xlsx(preview)))
    assert workbook["買い物リスト"]["C2"].value == "キッチンペーパー"
    assert workbook["買い物リスト"]["D2"].value == "2ロール"
