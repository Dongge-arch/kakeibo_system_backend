import json

from src.api.kakeibo.settings.auto_linkage.autoLinkageLogin import AutoLinkageLogin


def lambda_handler(event, context):
    body = json.loads(event.get("body") or "{}") if isinstance(event.get("body"), str) else event.get("body") or {}
    body["action"] = "login"
    body["connectionType"] = (event.get("pathParameters") or {}).get("connection_type")
    event["body"] = body
    return AutoLinkageLogin().lambda_handler(event, context)
