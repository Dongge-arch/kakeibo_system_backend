# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""献立、レシピ、買い物計画を扱うAPI。"""

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from src.common.functions.response import response
from src.common.base import BaseRestApi


class MealBase(BaseRestApi):
    """レシピと人数に応じた買い物リストの共通処理。"""

    def __init__(self, db_path=None):
        """
        献立APIを初期化する。

        Args:
            db_path (str | None): DB接続に使用するパス。

        Returns:
            None: 戻り値なし。
        """
        super().__init__(class_name=self.__class__.__name__, db_path=db_path, db_schema="meal")

    def validate_body(self, request_dict):
        """
        リクエスト本文の共通検証を行う。

        Args:
            request_dict (dict): リクエストコンテキスト。

        Returns:
            None: 戻り値なし。
        """
        return super().validate_body(request_dict)

    def list_recipes(self, user_id):
        """
        現在のユーザーのレシピを更新日順で取得する。

        Args:
            user_id (str): ログインユーザーID。

        Returns:
            list[dict]: レシピ一覧。
        """
        rows = self.database.select(
            self.database.read_sql("SELECT_RECIPE", location=__file__),
            {"USER_ID": user_id},
        )
        return [self.recipe_from_row(row) for row in rows]

    def save_recipe(self, user_id, recipe):
        """
        材料、手順、動画URLを検証して保存する。

        Args:
            user_id (str): ログインユーザーID。
            recipe (dict): 保存するレシピ。

        Returns:
            dict: 保存したレシピIDを含むAPIレスポンス。
        """
        if not isinstance(recipe, dict):
            return response(400, {"errorMessage": "レシピの形式が正しくありません。"})
        name = str(recipe.get("name") or "").strip()[:120]
        ingredients = recipe.get("ingredients")
        steps = recipe.get("steps")
        try:
            servings = int(recipe.get("baseServings") or 0)
        except (TypeError, ValueError):
            servings = 0
        if not name or not 1 <= servings <= 100:
            return response(400, {"errorMessage": "料理名と1〜100人分の基準人数を入力してください。"})
        if not isinstance(ingredients, list) or not ingredients or len(ingredients) > 100:
            return response(400, {"errorMessage": "材料を1〜100件入力してください。"})
        clean_ingredients = []
        for item in ingredients:
            if not isinstance(item, dict):
                return response(400, {"errorMessage": "材料の形式が正しくありません。"})
            ingredient_name = str(item.get("name") or "").strip()[:100]
            unit = str(item.get("unit") or "").strip()[:30]
            try:
                quantity = Decimal(str(item.get("quantity")))
            except (InvalidOperation, TypeError):
                quantity = Decimal(0)
            if not ingredient_name or not quantity.is_finite() or not 0 < quantity <= 100000:
                return response(400, {"errorMessage": "材料名と正の分量を入力してください。"})
            clean_ingredients.append({"name": ingredient_name, "quantity": float(quantity), "unit": unit})
        if not isinstance(steps, list) or len(steps) > 100:
            return response(400, {"errorMessage": "手順の形式が正しくありません。"})
        clean_steps = [str(step).strip()[:1000] for step in steps if str(step).strip()]
        video_url = str(recipe.get("videoUrl") or "").strip()[:1000]
        if video_url and urlparse(video_url).scheme not in ("https", "http"):
            return response(400, {"errorMessage": "動画URLはhttp(s)で指定してください。"})

        recipe_id = str(recipe.get("recipeId") or uuid.uuid4().hex)
        existing = self.database.select(
            self.database.read_sql("SELECT_RECIPE_02", location=__file__),
            {"RECIPE_ID": recipe_id, "USER_ID": user_id},
        )
        if recipe.get("recipeId") and not existing:
            return response(404, {"errorMessage": "レシピが見つかりません。"})
        values = {
            "RECIPE_ID": recipe_id, "USER_ID": user_id, "NAME": name, "BASE_SERVINGS": servings,
            "INGREDIENTS_JSON": json.dumps(clean_ingredients, ensure_ascii=False),
            "STEPS_JSON": json.dumps(clean_steps, ensure_ascii=False),
            "VIDEO_URL": video_url, "NOTES": str(recipe.get("notes") or "").strip()[:3000],
            "UPDATED_AT": datetime.now(timezone.utc).isoformat(),
        }
        if existing:
            self.database.execute(
                self.database.read_sql("UPDATE_RECIPE", location=__file__), values,
            )
        else:
            self.database.insert(
                self.database.read_sql("INSERT_RECIPE", location=__file__), values,
            )
        return response(200, {"recipeId": recipe_id})

    def delete_recipe(self, user_id, recipe_id):
        """
        本人所有のレシピだけ削除する。

        Args:
            user_id (str): ログインユーザーID。
            recipe_id (str): 削除するレシピID。

        Returns:
            dict: 削除結果を含むAPIレスポンス。
        """
        changed = self.database.execute(
            self.database.read_sql("DELETE_RECIPE", location=__file__),
            {"RECIPE_ID": recipe_id, "USER_ID": user_id},
        )
        return response(200 if changed else 404, {"ok": bool(changed)})

    def get_plan(self, user_id):
        """
        保存済み献立を読み、現在のレシピ分量から買い物リストを作る。

        Args:
            user_id (str): ログインユーザーID。

        Returns:
            dict: 献立、チェック状態、買い物リスト。
        """
        rows = self.database.select(self.database.read_sql("SELECT_SHOPPING_PLAN", location=__file__), {"USER_ID": user_id})
        row = rows[0] if rows else {}
        selected = json.loads(row.get("ITEMS_JSON") or "[]")
        checked = json.loads(row.get("CHECKED_JSON") or "[]")
        return {"items": selected, "checked": checked, "shoppingList": self.shopping_list(user_id, selected)}

    def save_plan(self, user_id, body):
        """
        料理ごとの作る回数と人数を保存する。

        Args:
            user_id (str): ログインユーザーID。
            body (dict): 献立とチェック状態。

        Returns:
            dict: 更新後の献立と買い物リスト。
        """
        items = body.get("items")
        checked = body.get("checked") or []
        if not isinstance(items, list) or len(items) > 100 or not isinstance(checked, list):
            return response(400, {"errorMessage": "献立の形式が正しくありません。"})
        clean_items = []
        for item in items:
            if not isinstance(item, dict):
                return response(400, {"errorMessage": "献立の形式が正しくありません。"})
            try:
                count = int(item.get("count") or 0)
                people = int(item.get("people") or 0)
            except (TypeError, ValueError):
                return response(400, {"errorMessage": "作る回数と人数を確認してください。"})
            if not 1 <= count <= 100 or not 1 <= people <= 100:
                return response(400, {"errorMessage": "作る回数と人数は1〜100で指定してください。"})
            clean_items.append({"recipeId": str(item.get("recipeId") or ""), "count": count, "people": people})
        shopping = self.shopping_list(user_id, clean_items)
        if shopping is None:
            return response(400, {"errorMessage": "献立に存在しないレシピが含まれています。"})
        checked_keys = {str(key) for key in checked}
        valid_keys = {row["key"] for row in shopping}
        values = {
            "USER_ID": user_id,
            "ITEMS_JSON": json.dumps(clean_items, ensure_ascii=False),
            "CHECKED_JSON": json.dumps(sorted(checked_keys & valid_keys), ensure_ascii=False),
            "UPDATED_AT": datetime.now(timezone.utc).isoformat(),
        }
        self.database.insert(
            self.database.read_sql("INSERT_SHOPPING_PLAN", location=__file__), values,
        )
        return response(200, {"items": clean_items, "checked": sorted(checked_keys & valid_keys), "shoppingList": shopping})

    def shopping_list(self, user_id, selected):
        """
        同名・同単位の材料を合算する。

        Args:
            user_id (str): ログインユーザーID。
            selected (list[dict]): 料理ID、回数、人数の一覧。

        Returns:
            list[dict] | None: 合算した材料一覧。料理が見つからない場合はNone。
        """
        recipes = {row["recipeId"]: row for row in self.list_recipes(user_id)}
        totals = {}
        for item in selected:
            recipe = recipes.get(item.get("recipeId"))
            if recipe is None:
                return None
            factor = Decimal(item["count"]) * Decimal(item["people"]) / Decimal(recipe["baseServings"])
            for ingredient in recipe["ingredients"]:
                key = (ingredient["name"].strip().casefold(), ingredient["unit"].strip())
                if key not in totals:
                    totals[key] = {"key": f"{key[0]}|{key[1]}", "name": ingredient["name"],
                                   "unit": ingredient["unit"], "quantity": Decimal(0)}
                totals[key]["quantity"] += Decimal(str(ingredient["quantity"])) * factor
        return [{**row, "quantity": float(row["quantity"].quantize(Decimal("0.01")))}
                for row in totals.values()]

    @staticmethod
    def recipe_from_row(row):
        """
        DB項目名を画面用の項目名に変換する。

        Args:
            row (dict): レシピのDB行。

        Returns:
            dict: 画面用レシピ情報。
        """
        return {"recipeId": row["RECIPE_ID"], "name": row["NAME"],
                "baseServings": row["BASE_SERVINGS"],
                "ingredients": json.loads(row["INGREDIENTS_JSON"]),
                "steps": json.loads(row["STEPS_JSON"]), "videoUrl": row.get("VIDEO_URL") or "",
                "notes": row.get("NOTES") or "", "updatedAt": row["UPDATED_AT"]}
