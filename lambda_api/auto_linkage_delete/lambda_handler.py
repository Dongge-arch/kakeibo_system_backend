from src.api.kakeibo.settings.auto_linkage.autoLinkageUpdateDelete import AutoLinkageUpdateDelete


def lambda_handler(event, context):
    event["body"] = {
        "action": "delete",
        "connectionType": (event.get("pathParameters") or {}).get("connection_type"),
    }
    return AutoLinkageUpdateDelete().lambda_handler(event, context)
