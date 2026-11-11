from src.api.kakeibo.settings.gmail_oauth.gmailOAuth import GmailOAuthStart


def lambda_handler(event, context):
    event["body"] = {}
    return GmailOAuthStart().lambda_handler(event, context)
