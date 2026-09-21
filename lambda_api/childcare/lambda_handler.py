"""育児 API の HTTP ルーティング。"""

import json

from src.api.childcare.babyReference import BabyReference
from src.api.childcare.babyRegistration import BabyRegistration
from src.api.childcare.babyUpdateDelete import BabyUpdateDelete
from src.api.childcare.babyEventReference import BabyEventReference
from src.api.childcare.babyEventRegistration import BabyEventRegistration
from src.api.childcare.babyEventUpdateDelete import BabyEventUpdateDelete
from src.api.childcare.familyReference import FamilyReference
from src.api.childcare.familyRegistration import FamilyRegistration
from src.api.childcare.familyInviteRegistration import FamilyInviteRegistration
from src.api.childcare.familyJoin import FamilyJoin
from src.api.childcare.familyMemberUpdateDelete import FamilyMemberUpdateDelete


def lambda_handler(event, context):
    """
    育児 HTTP リクエストを家族または赤ちゃん API へ渡す。

    Args:
        event (dict): API Gateway イベント。
        context: Lambda コンテキスト。

    Returns:
        dict: HTTP レスポンス。
    """
    path = (event.get("rawPath") or event.get("path") or "").rstrip("/")
    method = (event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod") or "").upper()
    raw = event.get("body") or {}
    body = json.loads(raw) if isinstance(raw, str) else dict(raw)
    parts = path.strip("/").split("/")
    if parts == ["childcare", "families"] and method == "GET":
        api = FamilyReference
    elif parts == ["childcare", "families"] and method == "POST":
        api = FamilyRegistration
    elif parts == ["childcare", "families", "join"] and method == "POST":
        api = FamilyJoin
    elif len(parts) == 4 and parts[:2] == ["childcare", "families"] and parts[3] == "invites" and method == "POST":
        api = FamilyInviteRegistration
        body.update(action="invite", familyId=parts[2])
    elif len(parts) == 5 and parts[:2] == ["childcare", "families"] and parts[3] == "members" and method == "DELETE":
        api = FamilyMemberUpdateDelete
        body.update(action="remove_member", familyId=parts[2], userId=parts[4])
    elif len(parts) == 4 and parts[:2] == ["childcare", "families"] and parts[3] == "babies" and method == "GET":
        api = BabyReference
        body.update(action="list_babies", familyId=parts[2])
    elif parts == ["childcare", "babies"] and method == "POST":
        api = BabyRegistration
    elif len(parts) == 3 and parts[:2] == ["childcare", "babies"] and method in {"PUT", "DELETE"}:
        api = BabyUpdateDelete
        body.update(action="save_baby" if method == "PUT" else "delete_baby", babyId=parts[2])
        if method == "PUT":
            body["baby"] = {**body.get("baby", {}), "babyId": parts[2]}
    elif len(parts) == 4 and parts[:2] == ["childcare", "babies"] and parts[3] == "events" and method in {"GET", "POST"}:
        api = BabyEventReference if method == "GET" else BabyEventRegistration
        body.update(action="list_events" if method == "GET" else "save_event", babyId=parts[2])
        if method == "GET":
            body["day"] = (event.get("queryStringParameters") or {}).get("day")
        else:
            body["event"] = {**body.get("event", {}), "babyId": parts[2]}
    elif len(parts) == 5 and parts[:2] == ["childcare", "babies"] and parts[3] == "events" and method in {"PUT", "DELETE"}:
        api = BabyEventUpdateDelete
        body.update(action="save_event" if method == "PUT" else "delete_event", babyId=parts[2], eventId=parts[4])
        if method == "PUT":
            body["event"] = {**body.get("event", {}), "babyId": parts[2], "eventId": parts[4]}
    else:
        return {"statusCode": 404, "headers": {"Content-Type": "application/json"}, "body": '{"errorMessage":"操作が見つかりません。"}'}
    return api().lambda_handler({**event, "body": body}, context)
