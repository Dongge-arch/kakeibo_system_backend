# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""献立、レシピ、買い物計画を扱うAPI。"""

import hashlib
import json
import math
import re
import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from src.common.base import BaseRestApi
from src.common.const.datetime import TIME_ZONE_JST
from src.common.functions.response import response


COUNT_UNITS = {"count", "pack", "bag", "bunch", "block", "bottle", "box"}
COUNT_LABELS = {"個", "本", "袋", "パック", "束", "丁", "瓶", "箱", "枚", "玉"}
MASS_UNIT_IN_GRAMS = {"g": Decimal("1"), "kg": Decimal("1000")}
VOLUME_UNIT_IN_MILLILITERS = {
    "ml": Decimal("1"),
    "l": Decimal("1000"),
    "tbsp": Decimal("15"),
    "tsp": Decimal("5"),
}
DRY_GRAMS_PER_UNIT = {
    ("potato_starch", "tbsp"): Decimal("9"),
    ("potato_starch", "tsp"): Decimal("3"),
    ("wheat_flour", "tbsp"): Decimal("9"),
    ("wheat_flour", "tsp"): Decimal("3"),
}


class RecipeValidationError(ValueError):
    """画面へ返せるレシピ入力エラー。"""


def decimal_value(value, field_name, minimum=None, maximum=None, allow_none=False):
    """有限なDecimalへ変換し、範囲を検証する。"""
    if value is None and allow_none:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise RecipeValidationError(f"{field_name}を正しく入力してください。") from error
    if not number.is_finite():
        raise RecipeValidationError(f"{field_name}を正しく入力してください。")
    if minimum is not None and number < Decimal(str(minimum)):
        raise RecipeValidationError(f"{field_name}を正しく入力してください。")
    if maximum is not None and number > Decimal(str(maximum)):
        raise RecipeValidationError(f"{field_name}を正しく入力してください。")
    return number


def display_number(value):
    """DecimalをJSONで扱いやすい整数または小数へ変換する。"""
    if value is None:
        return None
    rounded = value.quantize(Decimal("0.001"))
    if rounded == rounded.to_integral():
        return int(rounded)
    return float(rounded.normalize())


def stable_item_id(name):
    """未採番の食材へ名称由来の安定IDを付与する。"""
    digest = hashlib.sha1(str(name).strip().encode("utf-8")).hexdigest()[:12]
    return f"item_{digest}"


def clean_text(value, maximum):
    """文字列の前後空白を除去し、保存上限へ収める。"""
    return str(value or "").strip()[:maximum]


def normalize_capacity(capacity):
    """包装内容量を検証する。"""
    if not capacity:
        return None
    if not isinstance(capacity, dict):
        raise RecipeValidationError("包装内容量の形式が正しくありません。")
    amount = decimal_value(capacity.get("amount"), "包装内容量", minimum="0.001", maximum=1000000)
    unit = clean_text(capacity.get("unit"), 40)
    unit_label = clean_text(capacity.get("unitLabel"), 20)
    if not unit or not unit_label:
        raise RecipeValidationError("包装内容量の単位を入力してください。")
    return {"amount": display_number(amount), "unit": unit, "unitLabel": unit_label}


def normalize_supplemental_unit(value):
    """購入用の補助単位を検証する。"""
    if not value:
        return None
    if not isinstance(value, dict):
        raise RecipeValidationError("補助単位の形式が正しくありません。")
    amount = decimal_value(value.get("amount"), "補助単位の数量", minimum="0.001", maximum=1000000)
    unit = clean_text(value.get("unit"), 40)
    unit_label = clean_text(value.get("unitLabel"), 20)
    if not unit or not unit_label:
        raise RecipeValidationError("補助単位を入力してください。")
    result = {"amount": display_number(amount), "unit": unit, "unitLabel": unit_label}
    capacity = normalize_capacity(value.get("capacity"))
    if capacity:
        result["capacity"] = capacity
    return result


def normalize_ingredient(value, kind):
    """材料または調味料の一行を検証する。"""
    if not isinstance(value, dict):
        raise RecipeValidationError("材料の形式が正しくありません。")
    name = clean_text(value.get("name"), 120)
    unit = clean_text(value.get("unit"), 40)
    unit_label = clean_text(value.get("unitLabel") or value.get("unit"), 20)
    category = clean_text(value.get("category") or ("調味料" if kind == "seasoning" else "その他"), 60)
    if not name or not unit or not unit_label or not category:
        raise RecipeValidationError("材料名、単位、カテゴリを入力してください。")

    raw_amount = value.get("amount", value.get("quantity"))
    amount = decimal_value(
        raw_amount,
        f"{name}の分量",
        minimum="0.001",
        maximum=1000000,
        allow_none=unit == "as_needed",
    )
    if unit == "as_needed":
        amount = None
    item_id = clean_text(value.get("itemId"), 100) or stable_item_id(name)
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", item_id):
        raise RecipeValidationError(f"{name}の食材IDが正しくありません。")

    usages = []
    if isinstance(value.get("usages"), list):
        for usage in value["usages"][:50]:
            if not isinstance(usage, dict):
                continue
            usage_name = clean_text(usage.get("usage"), 80)
            usage_unit = clean_text(usage.get("unit") or unit, 40)
            usage_unit_label = clean_text(usage.get("unitLabel") or unit_label, 20)
            usage_amount = decimal_value(
                usage.get("amount"),
                f"{name}の用途別分量",
                minimum="0",
                maximum=1000000,
                allow_none=True,
            )
            if usage_name:
                usages.append({
                    "usage": usage_name,
                    "amount": display_number(usage_amount),
                    "unit": usage_unit,
                    "unitLabel": usage_unit_label,
                })

    result = {
        "itemId": item_id,
        "name": name,
        "amount": display_number(amount),
        "unit": unit,
        "unitLabel": unit_label,
        "category": category,
        "scalable": bool(value.get("scalable", unit != "as_needed")),
        "shoppingRequired": bool(value.get("shoppingRequired", True)),
    }
    usage = clean_text(value.get("usage"), 80)
    if usage:
        result["usage"] = usage
    if usages:
        result["usages"] = usages
    supplemental = normalize_supplemental_unit(value.get("supplementalUnit"))
    if supplemental:
        result["supplementalUnit"] = supplemental
    return result


def normalize_recipe(recipe):
    """新旧双方のレシピ形式をAWS保存用の共通形式へ変換する。"""
    if not isinstance(recipe, dict):
        raise RecipeValidationError("レシピの形式が正しくありません。")
    name = clean_text(recipe.get("name"), 160)
    if not name:
        raise RecipeValidationError("レシピ名を入力してください。")
    base_servings = decimal_value(recipe.get("baseServings"), "基準人数", minimum="0.1", maximum=100)
    if base_servings.as_tuple().exponent < -1:
        raise RecipeValidationError("基準人数は0.1人単位で入力してください。")
    cook_time = decimal_value(recipe.get("cookTimeMin", 0), "調理時間", minimum=0, maximum=1440)
    if cook_time != cook_time.to_integral():
        raise RecipeValidationError("調理時間は分単位の整数で入力してください。")

    material_values = recipe.get("materials")
    if material_values is None:
        material_values = recipe.get("ingredients")
    seasoning_values = recipe.get("seasonings") or []
    if not isinstance(material_values, list) or not 1 <= len(material_values) <= 200:
        raise RecipeValidationError("材料を1〜200件入力してください。")
    if not isinstance(seasoning_values, list) or len(seasoning_values) > 100:
        raise RecipeValidationError("調味料は100件以内で入力してください。")

    steps = recipe.get("steps") or []
    if not isinstance(steps, list) or len(steps) > 100:
        raise RecipeValidationError("手順の形式が正しくありません。")
    video_url = clean_text(recipe.get("videoUrl"), 1000)
    if video_url and urlparse(video_url).scheme not in ("https", "http"):
        raise RecipeValidationError("動画URLはhttp(s)で指定してください。")
    recipe_id = clean_text(recipe.get("recipeId"), 100)
    if recipe_id and not re.fullmatch(r"[a-zA-Z0-9_-]+", recipe_id):
        raise RecipeValidationError("レシピIDが正しくありません。")

    return {
        "schemaVersion": "shopping_recipe_v4",
        "recipeId": recipe_id,
        "name": name,
        "source": clean_text(recipe.get("source"), 160),
        "baseServings": display_number(base_servings),
        "servingUnit": clean_text(recipe.get("servingUnit") or "人", 20),
        "cookTimeMin": int(cook_time),
        "materials": [normalize_ingredient(item, "material") for item in material_values],
        "seasonings": [normalize_ingredient(item, "seasoning") for item in seasoning_values],
        "steps": [clean_text(step, 1000) for step in steps if clean_text(step, 1000)],
        "videoUrl": video_url,
        "notes": clean_text(recipe.get("notes"), 3000),
    }


def rounded(value, digits=3):
    """画面へ浮動小数点誤差を出さない。"""
    quantizer = Decimal("1").scaleb(-digits)
    return display_number(Decimal(value).quantize(quantizer))


def purchase_quantity(value, unit, unit_label):
    """使用量を購入しやすい目安数量へ切り上げる。"""
    if value is None:
        return None
    number = Decimal(value)
    if unit in COUNT_UNITS or unit_label in COUNT_LABELS:
        return int(number.to_integral_value(rounding="ROUND_CEILING"))
    if unit in {"g", "ml"} or unit_label in {"g", "ml"}:
        return int((number / Decimal("10")).to_integral_value(rounding="ROUND_CEILING") * 10)
    if unit in {"kg", "l"}:
        return display_number((number * 10).to_integral_value(rounding="ROUND_CEILING") / 10)
    return rounded(number, 2)


def convert_quantity(item_id, value, source_unit, target_unit):
    """包装内容量へ換算できる単位同士を変換する。"""
    if source_unit == target_unit:
        return value
    if source_unit in MASS_UNIT_IN_GRAMS and target_unit in MASS_UNIT_IN_GRAMS:
        grams = value * MASS_UNIT_IN_GRAMS[source_unit]
        return grams / MASS_UNIT_IN_GRAMS[target_unit]
    if source_unit in VOLUME_UNIT_IN_MILLILITERS and target_unit in VOLUME_UNIT_IN_MILLILITERS:
        milliliters = value * VOLUME_UNIT_IN_MILLILITERS[source_unit]
        return milliliters / VOLUME_UNIT_IN_MILLILITERS[target_unit]
    grams_per_unit = DRY_GRAMS_PER_UNIT.get((item_id, source_unit))
    if grams_per_unit is not None and target_unit in MASS_UNIT_IN_GRAMS:
        return value * grams_per_unit / MASS_UNIT_IN_GRAMS[target_unit]
    return None


def scale_line(line, scale):
    """補助単位を優先して材料一行を購入単位へ換算する。"""
    effective_scale = scale if line.get("scalable", True) else Decimal("1")
    supplemental = line.get("supplementalUnit")
    amount_value = line.get("amount")
    if supplemental:
        supplemental_amount = Decimal(str(supplemental["amount"]))
        if amount_value is None:
            return None, supplemental["unit"], supplemental["unitLabel"], supplemental_amount
        capacity = supplemental.get("capacity")
        if capacity:
            required = convert_quantity(
                line["itemId"],
                Decimal(str(amount_value)) * effective_scale,
                line["unit"],
                capacity["unit"],
            )
            if required is not None:
                return (
                    required / Decimal(str(capacity["amount"])) * supplemental_amount,
                    supplemental["unit"],
                    supplemental["unitLabel"],
                    Decimal("0"),
                )
        return supplemental_amount * effective_scale, supplemental["unit"], supplemental["unitLabel"], Decimal("0")
    if amount_value is None:
        return None, line["unit"], line["unitLabel"], Decimal("0")
    return Decimal(str(amount_value)) * effective_scale, line["unit"], line["unitLabel"], Decimal("0")


def seasoning_usage(line):
    """調味料の用途を一つの表示文字列へまとめる。"""
    if line.get("usage"):
        return line["usage"]
    return "・".join(item.get("usage", "") for item in line.get("usages") or [] if item.get("usage"))


class MealBase(BaseRestApi):
    """レシピと人数に応じた買い物リストの共通処理。"""

    def __init__(self, db_path=None):
        """献立APIをmealスキーマで初期化する。"""
        super().__init__(class_name=self.__class__.__name__, db_path=db_path, db_schema="meal")

    def validate_body(self, request_dict):
        """リクエスト本文の共通検証を行う。"""
        return super().validate_body(request_dict)

    def list_recipes(self, user_id):
        """現在のユーザーの有効なレシピを更新日順で取得する。"""
        rows = self.database.select(
            self.database.read_sql("SELECT_RECIPE", location=__file__),
            {"USER_ID": user_id},
        )
        recipes = [self.recipe_from_row(row) for row in rows]
        return [recipe for recipe in recipes if not recipe.pop("_deleted", False)]

    def save_recipe(self, user_id, recipe):
        """材料、換算条件、手順、動画URLを検証して保存する。"""
        try:
            clean_recipe = normalize_recipe(recipe)
        except RecipeValidationError as error:
            return response(400, {"errorMessage": str(error)})

        recipe_id = clean_recipe["recipeId"] or uuid.uuid4().hex
        rows = self.database.select(
            self.database.read_sql("SELECT_RECIPE_02", location=__file__),
            {"RECIPE_ID": recipe_id, "USER_ID": user_id},
        )
        existing = bool(rows and not self.recipe_from_row(rows[0]).get("_deleted"))
        if clean_recipe["recipeId"] and not existing:
            return response(404, {"errorMessage": "レシピが見つかりません。"})
        clean_recipe["recipeId"] = recipe_id
        recipe_payload = {
            key: clean_recipe[key]
            for key in ("schemaVersion", "source", "baseServings", "servingUnit", "cookTimeMin", "materials", "seasonings")
        }
        values = {
            "RECIPE_ID": recipe_id,
            "USER_ID": user_id,
            "NAME": clean_recipe["name"],
            # 既存AWSテーブルのINTEGER列との互換値。正確な小数人数はJSONに保存する。
            "BASE_SERVINGS": max(1, min(100, math.ceil(float(clean_recipe["baseServings"])))),
            "INGREDIENTS_JSON": json.dumps(recipe_payload, ensure_ascii=False),
            "STEPS_JSON": json.dumps(clean_recipe["steps"], ensure_ascii=False),
            "VIDEO_URL": clean_recipe["videoUrl"],
            "NOTES": clean_recipe["notes"],
            "UPDATED_AT": datetime.now(ZoneInfo(TIME_ZONE_JST)).isoformat(),
        }
        sql_name = "UPDATE_RECIPE" if existing else "INSERT_RECIPE"
        getattr(self.database, "execute" if existing else "insert")(
            self.database.read_sql(sql_name, location=__file__), values,
        )
        return response(200, {"recipeId": recipe_id})

    def delete_recipe(self, user_id, recipe_id):
        """本人所有のレシピを復元可能な論理削除状態へ変更する。"""
        rows = self.database.select(
            self.database.read_sql("SELECT_RECIPE_02", location=__file__),
            {"RECIPE_ID": recipe_id, "USER_ID": user_id},
        )
        if not rows:
            return response(404, {"ok": False})
        row = rows[0]
        recipe = self.recipe_from_row(row)
        if recipe.get("_deleted"):
            return response(404, {"ok": False})
        try:
            payload = json.loads(row.get("INGREDIENTS_JSON") or "[]")
        except (TypeError, json.JSONDecodeError):
            payload = {"materials": recipe.get("materials") or []}
        if not isinstance(payload, dict):
            payload = {"materials": recipe.get("materials") or []}
        payload["deleted"] = True
        payload["deletedAt"] = datetime.now(ZoneInfo(TIME_ZONE_JST)).isoformat()
        changed = self.database.execute(
            self.database.read_sql("SOFT_DELETE_RECIPE", location=__file__),
            {
                "RECIPE_ID": recipe_id,
                "USER_ID": user_id,
                "INGREDIENTS_JSON": json.dumps(payload, ensure_ascii=False),
                "UPDATED_AT": datetime.now(ZoneInfo(TIME_ZONE_JST)).isoformat(),
            },
        )
        return response(200 if changed else 404, {"ok": bool(changed)})

    def ingredient_master(self, user_id):
        """登録済みレシピから食材入力候補を作成する。"""
        master = {}
        for recipe in self.list_recipes(user_id):
            for line in [*(recipe.get("materials") or []), *(recipe.get("seasonings") or [])]:
                current = master.setdefault(line["itemId"], {
                    "itemId": line["itemId"],
                    "name": line["name"],
                    "category": line["category"],
                    "units": [],
                    "supplementalUnits": [],
                })
                unit = {"unit": line["unit"], "unitLabel": line["unitLabel"]}
                if unit not in current["units"]:
                    current["units"].append(unit)
                if line.get("supplementalUnit") and line["supplementalUnit"] not in current["supplementalUnits"]:
                    current["supplementalUnits"].append(line["supplementalUnit"])
        return sorted(master.values(), key=lambda item: item["name"])

    def get_plan(self, user_id):
        """保存済み計画を読み、現在のレシピから買い物リストを再計算する。"""
        rows = self.database.select(
            self.database.read_sql("SELECT_SHOPPING_PLAN", location=__file__),
            {"USER_ID": user_id},
        )
        row = rows[0] if rows else {}
        try:
            stored_items = json.loads(row.get("ITEMS_JSON") or "[]")
            checked = json.loads(row.get("CHECKED_JSON") or "[]")
        except (TypeError, json.JSONDecodeError):
            stored_items, checked = [], []
        if isinstance(stored_items, dict):
            raw_selections = stored_items.get("selections") or []
            raw_manual_items = stored_items.get("manualItems") or []
        else:
            raw_selections = stored_items
            raw_manual_items = []
        selections = self.normalize_selections(raw_selections, allow_empty=True)
        manual_items = self.normalize_manual_items(raw_manual_items)
        preview = self.build_shopping_preview(user_id, selections)
        if preview is None:
            selections = []
            preview = self.build_shopping_preview(user_id, selections)
        return self.plan_response(selections, checked, preview, manual_items)

    def save_plan(self, user_id, body):
        """料理ごとの人数、回数、購入状態を保存する。"""
        raw_items = body.get("selections", body.get("items"))
        raw_manual_items = body.get("manualItems") or []
        checked = body.get("checked") or []
        if not isinstance(checked, list):
            return response(400, {"errorMessage": "買い物チェックの形式が正しくありません。"})
        try:
            selections = self.normalize_selections(raw_items, allow_empty=True)
            manual_items = self.normalize_manual_items(raw_manual_items)
        except RecipeValidationError as error:
            return response(400, {"errorMessage": str(error)})
        preview = self.build_shopping_preview(user_id, selections)
        if preview is None:
            return response(400, {"errorMessage": "献立に存在しないレシピが含まれています。"})
        valid_keys = {
            item["rowId"]
            for group in preview["materialGroups"]
            for item in group["items"]
        } | {item["rowId"] for item in preview["seasonings"]} | {
            item["rowId"] for item in manual_items
        }
        clean_checked = sorted({str(key) for key in checked} & valid_keys)
        self.database.insert(
            self.database.read_sql("INSERT_SHOPPING_PLAN", location=__file__),
            {
                "USER_ID": user_id,
                "ITEMS_JSON": json.dumps({
                    "schemaVersion": "shopping_plan_v2",
                    "selections": selections,
                    "manualItems": manual_items,
                }, ensure_ascii=False),
                "CHECKED_JSON": json.dumps(clean_checked, ensure_ascii=False),
                "UPDATED_AT": datetime.now(ZoneInfo(TIME_ZONE_JST)).isoformat(),
            },
        )
        return response(200, self.plan_response(selections, clean_checked, preview, manual_items))

    @staticmethod
    def normalize_manual_items(values):
        """レシピにない日用品・食材を手動買い物項目として検証する。

        2026-09-30 Codex: 日用品も既存の買い物計画と一緒に永続化するため追加。
        """
        if not isinstance(values, list) or len(values) > 100:
            raise RecipeValidationError("手動買い物項目の形式が正しくありません。")
        normalized = []
        seen = set()
        for item in values:
            if not isinstance(item, dict):
                raise RecipeValidationError("手動買い物項目の形式が正しくありません。")
            name = clean_text(item.get("name"), 100)
            if not name:
                raise RecipeValidationError("手動買い物項目の名称を入力してください。")
            manual_id = clean_text(item.get("manualId"), 100) or f"manual_{uuid.uuid4().hex}"
            if manual_id in seen:
                continue
            seen.add(manual_id)
            normalized.append({
                "manualId": manual_id,
                "rowId": f"manual-{manual_id}",
                "name": name,
                "quantity": clean_text(item.get("quantity"), 40),
                "category": clean_text(item.get("category"), 40) or "その他",
            })
        return normalized

    def normalize_selections(self, values, allow_empty=False):
        """新旧双方の献立選択形式を共通形式へ変換する。"""
        if not isinstance(values, list) or len(values) > 100 or (not allow_empty and not values):
            raise RecipeValidationError("献立の形式が正しくありません。")
        selections = []
        for item in values:
            if not isinstance(item, dict):
                raise RecipeValidationError("献立の形式が正しくありません。")
            recipe_id = clean_text(item.get("recipeId"), 100)
            target = decimal_value(
                item.get("targetServings", item.get("people")),
                "人数",
                minimum="0.1",
                maximum=100,
            )
            if target.as_tuple().exponent < -1:
                raise RecipeValidationError("人数は0.1人単位で入力してください。")
            count = decimal_value(
                item.get("cookCount", item.get("count")),
                "作る回数",
                minimum=1,
                maximum=99,
            )
            if count != count.to_integral():
                raise RecipeValidationError("作る回数は整数で入力してください。")
            if not recipe_id:
                raise RecipeValidationError("レシピを選択してください。")
            selections.append({
                "recipeId": recipe_id,
                "targetServings": display_number(target),
                "cookCount": int(count),
            })
        return selections

    def build_shopping_preview(self, user_id, selections):
        """補助単位と包装容量を使って買い物リストを生成する。"""
        recipes = {recipe["recipeId"]: recipe for recipe in self.list_recipes(user_id)}
        material_map = {}
        seasoning_map = {}
        selection_rows = []
        for selection in selections:
            recipe = recipes.get(selection["recipeId"])
            if recipe is None:
                return None
            scale = (
                Decimal(str(selection["targetServings"]))
                / Decimal(str(recipe["baseServings"]))
                * Decimal(str(selection["cookCount"]))
            )
            selection_rows.append({
                **selection,
                "recipeName": recipe["name"],
            })
            for line in recipe.get("materials") or []:
                if not line.get("shoppingRequired", True):
                    continue
                amount, unit, unit_label, minimum = scale_line(line, scale)
                key = (line["itemId"], unit, unit_label)
                row_id = f"material-{line['itemId']}-{unit}-{unit_label}"
                item = material_map.setdefault(key, {
                    "rowId": row_id,
                    "itemId": line["itemId"],
                    "name": line["name"],
                    "category": line["category"],
                    "calculatedAmount": Decimal("0") if amount is not None else None,
                    "unit": unit,
                    "unitLabel": unit_label,
                    "sources": [],
                    "minimumPurchaseAmount": minimum,
                })
                if amount is not None:
                    item["calculatedAmount"] = (item["calculatedAmount"] or Decimal("0")) + amount
                item["minimumPurchaseAmount"] = max(item["minimumPurchaseAmount"], minimum)
                source = {
                    "recipeId": recipe["recipeId"],
                    "recipeName": recipe["name"],
                    "usage": seasoning_usage(line),
                }
                if source not in item["sources"]:
                    item["sources"].append(source)

            for line in recipe.get("seasonings") or []:
                if not line.get("shoppingRequired", True):
                    continue
                key = line["itemId"] or stable_item_id(line["name"])
                item = seasoning_map.setdefault(key, {
                    "rowId": f"seasoning-{key}",
                    "itemId": line["itemId"],
                    "name": line["name"],
                    "category": line["category"],
                    "sources": [],
                })
                source = {
                    "recipeId": recipe["recipeId"],
                    "recipeName": recipe["name"],
                    "usage": seasoning_usage(line),
                }
                if source not in item["sources"]:
                    item["sources"].append(source)

        grouped = defaultdict(list)
        for item in material_map.values():
            calculated = item["calculatedAmount"]
            minimum = item.pop("minimumPurchaseAmount")
            if minimum > 0:
                calculated = max(calculated or Decimal("0"), minimum)
            item["calculatedAmount"] = rounded(calculated) if calculated is not None else None
            item["purchaseAmount"] = purchase_quantity(calculated, item["unit"], item["unitLabel"])
            grouped[item["category"]].append(item)
        return {
            "generatedAt": datetime.now(ZoneInfo(TIME_ZONE_JST)).isoformat(timespec="seconds"),
            "selections": selection_rows,
            "materialGroups": [
                {"category": category, "items": sorted(items, key=lambda item: item["name"])}
                for category, items in sorted(grouped.items(), key=lambda pair: pair[0])
            ],
            "seasonings": sorted(seasoning_map.values(), key=lambda item: item["name"]),
            "summary": {
                "recipeCount": len(selection_rows),
                "materialCount": len(material_map),
                "seasoningCount": len(seasoning_map),
            },
        }

    def shopping_list(self, user_id, selected):
        """旧画面互換の同名・同単位材料リストを返す。"""
        recipes = {row["recipeId"]: row for row in self.list_recipes(user_id)}
        totals = {}
        for item in selected:
            recipe = recipes.get(item.get("recipeId"))
            if recipe is None:
                return None
            count = Decimal(str(item.get("count", item.get("cookCount", 0))))
            people = Decimal(str(item.get("people", item.get("targetServings", 0))))
            factor = count * people / Decimal(str(recipe["baseServings"]))
            ingredients = recipe.get("ingredients") or [
                {"name": line["name"], "quantity": line.get("amount"), "unit": line.get("unitLabel") or line["unit"]}
                for line in recipe.get("materials") or []
                if line.get("amount") is not None
            ]
            for ingredient in ingredients:
                key = (ingredient["name"].strip().casefold(), ingredient["unit"].strip())
                if key not in totals:
                    totals[key] = {
                        "key": f"{key[0]}|{key[1]}",
                        "name": ingredient["name"],
                        "unit": ingredient["unit"],
                        "quantity": Decimal("0"),
                    }
                totals[key]["quantity"] += Decimal(str(ingredient["quantity"])) * factor
        return [
            {**row, "quantity": float(row["quantity"].quantize(Decimal("0.01")))}
            for row in totals.values()
        ]

    @staticmethod
    def plan_response(selections, checked, preview, manual_items=None):
        """新画面データと旧画面互換データを同時に返す。"""
        legacy_items = [
            {"recipeId": item["recipeId"], "count": item["cookCount"], "people": item["targetServings"]}
            for item in selections
        ]
        legacy_shopping = [
            {
                "key": item["rowId"],
                "name": item["name"],
                "quantity": item["purchaseAmount"],
                "unit": item["unitLabel"],
            }
            for group in preview["materialGroups"]
            for item in group["items"]
        ]
        return {
            "selections": selections,
            "items": legacy_items,
            "checked": list(checked),
            "manualItems": list(manual_items or []),
            "preview": preview,
            "shoppingList": legacy_shopping,
        }

    @staticmethod
    def recipe_from_row(row):
        """新旧DBレコードを画面用の共通レシピへ変換する。"""
        try:
            stored = json.loads(row.get("INGREDIENTS_JSON") or "[]")
        except (TypeError, json.JSONDecodeError):
            stored = []
        if isinstance(stored, dict):
            materials = stored.get("materials") or []
            seasonings = stored.get("seasonings") or []
            base_servings = stored.get("baseServings", row.get("BASE_SERVINGS") or 1)
            source = stored.get("source") or ""
            serving_unit = stored.get("servingUnit") or "人"
            cook_time = stored.get("cookTimeMin") or 0
            deleted = bool(stored.get("deleted"))
            schema_version = stored.get("schemaVersion") or "shopping_recipe_v4"
        else:
            materials = [
                {
                    "itemId": stable_item_id(item.get("name") or "食材"),
                    "name": item.get("name") or "食材",
                    "amount": item.get("quantity"),
                    "unit": item.get("unit") or "count",
                    "unitLabel": item.get("unit") or "個",
                    "category": "その他",
                    "scalable": True,
                    "shoppingRequired": True,
                }
                for item in stored
                if isinstance(item, dict)
            ]
            seasonings, source, serving_unit, cook_time, deleted = [], "", "人", 0, False
            base_servings = row.get("BASE_SERVINGS") or 1
            schema_version = "shopping_recipe_v4"
        try:
            steps = json.loads(row.get("STEPS_JSON") or "[]")
        except (TypeError, json.JSONDecodeError):
            steps = []
        ingredients = [
            {
                "name": line.get("name") or "",
                "quantity": line.get("amount"),
                "unit": line.get("unitLabel") or line.get("unit") or "",
            }
            for line in materials
            if line.get("amount") is not None
        ]
        return {
            "schemaVersion": schema_version,
            "recipeId": row["RECIPE_ID"],
            "name": row["NAME"],
            "source": source,
            "baseServings": base_servings,
            "servingUnit": serving_unit,
            "cookTimeMin": cook_time,
            "materials": materials,
            "seasonings": seasonings,
            "ingredients": ingredients,
            "steps": steps if isinstance(steps, list) else [],
            "videoUrl": row.get("VIDEO_URL") or "",
            "notes": row.get("NOTES") or "",
            "updatedAt": str(row.get("UPDATED_AT") or ""),
            "_deleted": deleted,
        }
