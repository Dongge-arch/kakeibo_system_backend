"""アプリ設定参照 API。"""

from src.api.kakeibo.settings.app_settings.appSettingsBase import AppSettingsBase
from src.common.functions.response import response


class AppSettingsReference(AppSettingsBase):
    """ユーザーのアプリ設定を取得する。"""

    def main(self, request_dict):
        """
        処理概要: アプリ設定を参照する。
        処理内容:
          1. 認証済みユーザーを特定する。
          2. 最新の設定と AI 利用量を取得する。
          3. 設定を返す。

        Args:
            request_dict (dict): 認証済みリクエスト。

        Returns:
            dict: アプリ設定の API レスポンス。
        """
        return response(200, self.get_settings(self.require_user_id(request_dict)))
