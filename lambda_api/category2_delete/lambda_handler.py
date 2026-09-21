from src.api.kakeibo.master.category2.category2UpdateDelete import Category2UpdateDelete
import json

def _body(event):
    if isinstance(event.get("body"), str):
        return json.loads(event.get("body") or "{}")
    return event.get("body") or {}

def _set_body(event, body):
    event["body"] = body
    return event

def lambda_handler(event, context):
    body = _body(event)
    query = event.get("queryStringParameters") or {}
    path = event.get("pathParameters") or {}
    body["action"] = "delete_category2"
    event = _set_body(event, body)
    return Category2UpdateDelete().lambda_handler(event, context)
