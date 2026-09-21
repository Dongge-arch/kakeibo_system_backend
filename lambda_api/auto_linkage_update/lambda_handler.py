import json

from src.api.kakeibo.settings.auto_linkage.autoLinkageUpdateDelete import AutoLinkageUpdateDelete


def lambda_handler(event, context):
    body = json.loads(event.get("body") or "{}") if isinstance(event.get("body"), str) else event.get("body") or {}
    body["action"] = "update"
    body["connectionType"] = (event.get("pathParameters") or {}).get("connection_type")
    event["body"] = body
    return AutoLinkageUpdateDelete().lambda_handler(event, context)
