"""REST API の共通基底クラス。"""

from src.common.auth_context import get_current_user_id, reset_current_user_id, set_current_user_id
from src.common.auth_token import verify_token
from src.common.base.base_lambda import BaseLambda
from src.common.exception import Error


class BaseRestApi(BaseLambda):
    """HTTP API の実装が継承するクラス。"""

    def call(self, body=None, headers=None, **kwargs):
        """
        署名済みJWTのユーザーをリクエストコンテキストへ設定する。

        Args:
            body (dict): リクエスト本文。
            headers (dict): HTTPヘッダー。
            **kwargs: BaseLambdaへ渡す追加情報。

        Returns:
            dict: APIレスポンス。
        """
        normalized = self.normalize_headers(headers or {})
        authorization = str(normalized.get("authorization") or "")
        token = authorization[7:] if authorization.lower().startswith("bearer ") else ""
        user_id = verify_token(token).get("userId") if token else None
        context_token = set_current_user_id(str(user_id)) if user_id else None
        try:
            return super().call(body=body, headers=headers, **kwargs)
        finally:
            if context_token is not None:
                reset_current_user_id(context_token)

    def require_user_id(self, request_dict: dict) -> str:
        """
        検証済みJWTまたは内部バッチのユーザーIDを取得する。

        Args:
            request_dict (dict): リクエストコンテキスト。

        Returns:
            str: 認証済みユーザーID。
        """
        user_id = get_current_user_id()
        if not user_id:
            raise Error(status_code=401, error_code="1000062", message="ログインしてください。")
        return user_id
