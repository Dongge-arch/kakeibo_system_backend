from src.api.kakeibo.settings.user_auth.passwordResetConfirm import PasswordResetConfirm
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
    body["action"] = "reset_password"
    event = _set_body(event, body)
    return PasswordResetConfirm().lambda_handler(event, context)
