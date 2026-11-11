from src.api.kakeibo.settings.gmail_oauth.gmailOAuth import GmailOAuthCallback


def lambda_handler(event, context):
    query = event.get("queryStringParameters") or {}
    return GmailOAuthCallback().call(body={}, headers=event.get("headers") or {}, query=query)
