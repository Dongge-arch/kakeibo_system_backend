"""アプリ設定保存 API。"""

from src.api.kakeibo.settings.app_settings.appSettingsBase import AppSettingsBase
from src.common.functions.response import response


class AppSettingsRegistration(AppSettingsBase):
    """ユーザーのアプリ設定を履歴として保存する。"""

    def main(self, request_dict):
        """
        処理概要: アプリ設定を保存する。
        処理内容:
          1. 認証済みユーザーを特定する。
          2. 設定値を新しい履歴として保存する。
          3. 保存結果を返す。

        Args:
            request_dict (dict): 設定を含む認証済みリクエスト。

        Returns:
            dict: 保存結果の API レスポンス。
        """
        user_id = self.require_user_id(request_dict)
        self.save_settings((request_dict.get("body") or {}).get("settings") or {}, user_id)
        return response(200, {"ok": True})
