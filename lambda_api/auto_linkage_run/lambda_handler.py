import json

from src.api.kakeibo.settings.auto_linkage.autoLinkageRun import AutoLinkageRun


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
    return AutoLinkageRun().lambda_handler(event, context)
