"""献立・育児 API の権限と計算を検証する。"""

from datetime import datetime, timezone
import importlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.api.childcare.babyBase import BabyBase
from src.api.childcare.babyReference import BabyReference
from src.api.childcare.babyEventRegistration import BabyEventRegistration
from src.api.childcare.babyEventReference import BabyEventReference
from src.api.childcare.familyInviteRegistration import FamilyInviteRegistration
from src.api.meal.recipeReference import RecipeReference
from src.api.meal.recipeRegistration import RecipeRegistration
from src.api.meal.recipeUpdateDelete import RecipeUpdateDelete
from src.api.meal.shoppingPlanReference import ShoppingPlanReference
from src.api.meal.shoppingPlanUpdate import ShoppingPlanUpdate
from src.common.auth_token import issue_token
from src.common.base.base_batch import BaseBatch
from src.common.base.base_lambda import BaseLambda
from src.common.base.base_rest_api import BaseRestApi
from src.common.functions.response import response


class FakeDatabase:
    """必要最小限のSQL実行を記録するDB。"""

    def __init__(self, rows=None):
        self.rows = rows or []
        self.statements = []

    def read_sql(self, name, location=None):
        return (Path(location).parent / "sql" / f"{name}.sql").read_text(encoding="utf-8")

    def select(self, sql, params=None):
        self.statements.append((sql, params))
        return self.rows

    def insert(self, sql, params=None):
        self.statements.append((sql, params))
        return 1

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        return 1


def instance_without_connection(api_type, rows=None):
    """クラウドDBに接続せずビジネスロジックをテストする。"""
    api = object.__new__(api_type)
    api.database = FakeDatabase(rows)
    return api


def test_api_and_batch_share_base_lambda():
    assert issubclass(BaseRestApi, BaseLambda)
    assert issubclass(BaseBatch, BaseLambda)


def test_new_module_requires_signed_token():
    api = instance_without_connection(RecipeReference)
    user_id = "test-user"
    token = issue_token({"userId": user_id})
    assert api.require_verified_user_id({"headers": {"authorization": f"Bearer {token}"}}) == user_id
    try:
        api.require_verified_user_id({"headers": {"x-kakeibo-user-id": user_id}})
    except Exception as error:
        assert getattr(error, "status_code", None) == 401
    else:
        raise AssertionError("unsigned user id was accepted")


def test_shopping_aggregates_recipe_count_and_people():
    api = instance_without_connection(RecipeReference)
    api.list_recipes = lambda user_id: [
        {"recipeId": "a", "baseServings": 2, "ingredients": [{"name": "玉ねぎ", "quantity": 1, "unit": "個"}]},
        {"recipeId": "b", "baseServings": 4, "ingredients": [{"name": "玉ねぎ", "quantity": 2, "unit": "個"}]},
    ]
    rows = api.shopping_list("user", [
        {"recipeId": "a", "count": 2, "people": 3},
        {"recipeId": "b", "count": 1, "people": 2},
    ])
    assert rows == [{"key": "玉ねぎ|個", "name": "玉ねぎ", "unit": "個", "quantity": 4.0}]


def test_meal_endpoints_keep_individual_operations():
    for api_type, method, body in (
        (RecipeReference, "list_recipes", {}),
        (RecipeRegistration, "save_recipe", {"recipe": {"name": "Soup"}}),
        (RecipeUpdateDelete, "delete_recipe", {"action": "delete_recipe", "recipeId": "recipe-1"}),
        (ShoppingPlanReference, "get_plan", {}),
        (ShoppingPlanUpdate, "save_plan", {"items": []}),
    ):
        api = instance_without_connection(api_type)
        api.require_verified_user_id = lambda request: "owner"
        handler = MagicMock(return_value=[] if method == "list_recipes" else response(200, {"ok": True}))
        setattr(api, method, handler)
        result = api.main({"body": body})
        assert result["statusCode"] == 200
        handler.assert_called_once()


def test_malformed_recipe_returns_validation_error():
    api = instance_without_connection(RecipeRegistration)
    api.require_verified_user_id = lambda request: "owner"
    assert api.main({"body": {"recipe": "invalid"}})["statusCode"] == 400


def test_private_schema_logs_no_request_or_response_body():
    api = instance_without_connection(RecipeReference)
    api.database = MagicMock(schema="meal")
    api.logger = MagicMock()
    api.main = lambda request: response(200, {"private": "baby data"})
    token = issue_token({"userId": "owner"})
    api.call(body={"action": "list_recipes", "private": "milk amount"},
             headers={"authorization": f"Bearer {token}"}, validate_b=False)
    logged = str(api.logger.info.call_args_list)
    assert "milk amount" not in logged
    assert "baby data" not in logged


def test_family_member_check_scopes_baby_access():
    api = instance_without_connection(BabyReference)
    assert not api.is_member("user-a", "family-b")
    assert api.database.statements[-1][1] == {"USER_ID": "user-a", "FAMILY_ID": "family-b"}


def test_family_invite_is_owner_only():
    api = instance_without_connection(FamilyInviteRegistration)
    result = api.create_invite("user-a", "family-b")
    assert result["statusCode"] == 403
    assert len(api.database.statements) == 1


def test_baby_event_from_postgres_timestamp_is_japan_time():
    row = {
        "EVENT_ID": "e", "BABY_ID": "b", "EVENT_TYPE": "feed",
        "HAPPENED_AT": datetime(2026, 9, 19, 16, 0, tzinfo=timezone.utc),
        "DATA_JSON": '{"method":"breast"}', "CREATED_BY": "u",
    }
    event = BabyBase.event_from_row(row)
    assert event["happenedAt"] == "2026-09-20T01:00:00+09:00"


def test_baby_events_require_family_membership():
    api = instance_without_connection(BabyEventReference)
    api.require_verified_user_id = lambda request: "outsider"
    api.authorized_baby = MagicMock(return_value=None)
    api.list_events = MagicMock()
    result = api.main({"body": {"babyId": "baby-1", "day": "2026-09-20"}})
    assert result["statusCode"] == 403
    api.authorized_baby.assert_called_once_with("outsider", "baby-1")
    api.list_events.assert_not_called()

    registration = instance_without_connection(BabyEventRegistration)
    registration.require_verified_user_id = lambda request: "member"
    registration.authorized_baby = lambda user_id, baby_id: {"BABY_ID": baby_id}
    registration.save_event = MagicMock(return_value=response(200, {"eventId": "event-1"}))
    assert registration.main({"body": {"babyId": "baby-1", "event": {"type": "feed"}}})["statusCode"] == 200
    registration.save_event.assert_called_once_with("member", {"BABY_ID": "baby-1"}, {"type": "feed"})


@pytest.mark.parametrize("path,method,body,expected", [
    ("/meal/recipes", "GET", {}, "RecipeReference"),
    ("/meal/recipes", "POST", {"recipe": {"name": "Soup"}}, "RecipeRegistration"),
    ("/meal/recipes", "POST", {"recipe": {"recipeId": "r"}}, "RecipeUpdateDelete"),
    ("/meal/recipes", "POST", {"recipe": "invalid"}, "RecipeRegistration"),
    ("/meal/recipes/r", "DELETE", {}, "RecipeUpdateDelete"),
    ("/meal/plan", "GET", {}, "ShoppingPlanReference"),
    ("/meal/plan", "PUT", {"items": []}, "ShoppingPlanUpdate"),
    ("/childcare/families", "GET", {}, "FamilyReference"),
    ("/childcare/families", "POST", {"name": "Family"}, "FamilyRegistration"),
    ("/childcare/families/join", "POST", {"code": "code"}, "FamilyJoin"),
    ("/childcare/families/f/invites", "POST", {}, "FamilyInviteRegistration"),
    ("/childcare/families/f/members/u", "DELETE", {}, "FamilyMemberUpdateDelete"),
    ("/childcare/families/f/babies", "GET", {}, "BabyReference"),
    ("/childcare/babies", "POST", {"baby": {}}, "BabyRegistration"),
    ("/childcare/babies/b", "PUT", {"baby": {}}, "BabyUpdateDelete"),
    ("/childcare/babies/b", "DELETE", {}, "BabyUpdateDelete"),
    ("/childcare/babies/b/events", "GET", {}, "BabyEventReference"),
    ("/childcare/babies/b/events", "POST", {"event": {}}, "BabyEventRegistration"),
    ("/childcare/babies/b/events/e", "PUT", {"event": {}}, "BabyEventUpdateDelete"),
    ("/childcare/babies/b/events/e", "DELETE", {}, "BabyEventUpdateDelete"),
])
def test_module_routes_select_one_api(monkeypatch, path, method, body, expected):
    domain = path.split("/")[1]
    router = importlib.import_module(f"lambda_api.{domain}.lambda_handler")
    class FakeApi:
        def lambda_handler(self, event, context):
            return expected, event["body"]
    monkeypatch.setattr(router, expected, FakeApi)
    result, routed_body = router.lambda_handler({"rawPath": path, "requestContext": {"http": {"method": method}}, "body": body}, None)
    assert result == expected
    if "/events" in path:
        assert routed_body["babyId"] == "b"
