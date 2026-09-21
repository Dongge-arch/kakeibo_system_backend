from src.api.kakeibo.settings.auto_linkage.autoLinkageReference import AutoLinkageReference


def lambda_handler(event, context):
    event["body"] = {"action": "list"}
    return AutoLinkageReference().lambda_handler(event, context)
