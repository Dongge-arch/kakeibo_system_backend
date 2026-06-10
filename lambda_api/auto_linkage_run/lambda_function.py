import json

from src.api.settings.auto_linkage.autoLinkageApi import AutoLinkageApi


def lambda_handler(event, context):
    body = json.loads(event.get("body") or "{}") if isinstance(event.get("body"), str) else event.get("body") or {}
    body["action"] = "run"
    body["connectionType"] = (event.get("pathParameters") or {}).get("connection_type")
    event["body"] = body
    return AutoLinkageApi().lambda_handler(event, context)
