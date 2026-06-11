import json

from src.api.settings.auto_linkage.autoLinkageApi import AutoLinkageApi


def lambda_handler(event, context):
    body = json.loads(event.get("body") or "{}") if isinstance(
        event.get("body"), str) else event.get("body") or {}
    body["action"] = "run"
    # connectionType はリクエスト本文ではなく API Gateway のパスパラメータから受け取る。
    body["connectionType"] = (
        (event.get("pathParameters") or {}).get("connection_type")
        or body.get("connectionType")
    )
    event["body"] = body
    return AutoLinkageApi().lambda_handler(event, context)
