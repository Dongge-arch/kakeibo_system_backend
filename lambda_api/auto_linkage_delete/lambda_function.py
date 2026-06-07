from src.api.settings.auto_linkage.autoLinkageApi import AutoLinkageApi


def lambda_handler(event, context):
    event["body"] = {
        "action": "delete",
        "connectionType": (event.get("pathParameters") or {}).get("connection_type"),
    }
    return AutoLinkageApi().lambda_handler(event, context)
