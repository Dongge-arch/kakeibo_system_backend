from src.api.settings.auto_linkage.autoLinkageApi import AutoLinkageApi


def lambda_handler(event, context):
    event["body"] = {"action": "list"}
    return AutoLinkageApi().lambda_handler(event, context)
